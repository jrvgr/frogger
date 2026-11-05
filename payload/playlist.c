/* "Add to Playlist" (holdmenu.c): the songs of the row held go into a hidden
 * scratch playlist first, while the list is still on screen, and once a
 * playlist is picked in Playlists they're copied into it and it's saved.
 *
 * Stock's add (0xc0b30) appends to the playlist at lib+0x48, On-The-Go, and
 * so does its save (0xf4ad4 writes OTGPlaylistInfo files from lib+0x48), so
 * both run with lib+0x48 holding our playlist for the time being, as the
 * queue does (queue.c). Playlists made on the iPod (Save Playlist names them
 * "New Playlist N", +0x124 holds N) live in OTGPlaylistInfo_N, which Apple
 * reads at boot (0xc5a90); On-The-Go in OTGPlaylistInfo, saved when Apple
 * sees its flag ([lib]+0xb42, as 0xc0b30 sets it). Playlists synced from
 * Crate have no file of Apple's, so they get one of ours in the same format,
 * FroggerPlaylist_I (I: the playlist's index in lib+0x870), and the first
 * time Playlists opens (playlist_load_saved) each is read back with Apple's
 * loader (0xc5a90) and, if that works, takes the synced contents' place.
 * The files carry the iTunesDB's stamp, as Apple's do, so after a sync the
 * loader turns them down; Crate reads them on the next sync to keep what
 * was added.
 *
 * Emptying a playlist goes through list_empty, not Apple's 0x465b0, whose
 * ending also resets the list on screen: going back to it, it'd be empty.
 * docs/re-notes.md, "Playlists made on the iPod". */

#include <stdint.h>
#include "playlist.h"
#include "disk.h"

#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define LIB_OTG         (0x48 / 4)
#define LIB_LISTS       (0x870 / 4)     /* the playlists, [0] the library */
#define LIB_N_LISTS     (0x874 / 4)
#define LIST_SAVED_N    (0x124 / 4)     /* "New Playlist N": N, else 0 */
#define PREFS_OTG_DIRTY 0xb42           /* in [lib]: On-The-Go is to be saved */

#define new_temp_list   ((uint32_t (*)(uint32_t lib, uint32_t *list))0xac2ec)
/* 0x465b0's emptying of a playlist, without its ending, which also resets
 * the list on screen (0x9d7c4, lib+0x898) and marks On-The-Go to be saved:
 * stop it if it's playing, 'pldm' (0 means go on), remove the items. */
#define list_stop       ((void (*)(uint32_t list))0xa97bc)
#define list_pldm       ((uint32_t (*)(uint32_t list))0x5aea8)
#define list_remove_all ((void (*)(uint32_t list))0xba31c)
/* 0x51250(lib, source, key, 0, dest): appends source's songs to dest, the
 * way 0xc0b30 does with 0x849a4(lib) as the key. */
#define copy_list       ((void (*)(uint32_t lib, uint32_t src, uint32_t key, uint32_t zero, uint32_t dest))0x51250)
#define list_key        ((uint32_t (*)(uint32_t lib))0x849a4)
/* 0x08eb.ee(row): whether Playlists' row is On-The-Go. */
#define row_is_otg      ((uint32_t (*)(uint32_t ui, uint32_t row))0x9f6e8)
/* Paths (out: 0x108 bytes) to iPod_Control\iTunes\<name>: to write, which
 * creates the file, emptying one that's there (0x53a24; volume kind 'itun'),
 * and to read (0x7b3bc, -0x2b when there's no such file). And the On-The-Go
 * file writer, from the playlist at lib+0x48. */
#define make_path       ((uint32_t (*)(void *out, uint32_t kind, const char *dir, const char *name))0x53a24)
#define find_path       ((uint32_t (*)(void *out, const char *name))0x7b3bc)
#define write_otg_file  ((uint32_t (*)(uint32_t lib, void *path))0xf4ad4)
#define ITUN            0x6974756eu
/* 0xc5a90(dest, tracks, stamp, path): appends the songs of an On-The-Go file
 * to dest, if it carries `stamp`; 0 means it did. Apple calls it with the
 * library's track list (0x6fcfc([lib])) and the iTunesDB's stamp (0x77600). */
#define read_otg_file   ((uint32_t (*)(uint32_t dest, uint32_t tracks, uint32_t stamp, void *path))0xc5a90)
#define lib_tracks      ((uint32_t (*)(uint32_t root))0x6fcfc)
#define db_stamp        ((uint32_t (*)(void))0x77600)
#define PLAYER_LIST     (0x2a4 / 4)

static struct {
    uint32_t scratch;
    uint32_t loading;           /* playlist_load_saved's own (the scratch may be in use) */
    uint32_t otg;               /* On-The-Go, while something stands in for it */
    int loaded;                 /* the FroggerPlaylist files have been read */
    uint32_t save_list, save_index;     /* a save waiting for the disk (playlist_flush) */
} pl;

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static uint32_t library(void)
{
    uint32_t ui = UI_OBJECT;

    return ui ? word(ui, 0x1c / 4) : 0;
}

static uint32_t list_count(uint32_t list)
{
    return word(word(list, 0x24 / 4), 0x2c / 4);
}

static void stand_in(uint32_t lib, uint32_t list)
{
    pl.otg = word(lib, LIB_OTG);
    ((volatile uint32_t *)lib)[LIB_OTG] = list;
}

static void stand_down(uint32_t lib)
{
    if (pl.otg)
        ((volatile uint32_t *)lib)[LIB_OTG] = pl.otg;
    pl.otg = 0;
}

void list_empty(uint32_t list)
{
    list_stop(list);
    if (list_pldm(list) == 0)
        list_remove_all(list);
}

void playlist_begin_add(void)
{
    uint32_t lib = library();

    if (!lib || pl.otg)
        return;
    if (!pl.scratch && new_temp_list(lib, &pl.scratch) != 0)
        pl.scratch = 0;
    if (!pl.scratch)
        return;
    if (list_count(pl.scratch))
        list_empty(pl.scratch); /* left from a pick that went wrong */
    stand_in(lib, pl.scratch);
}

/* After the add: whether there's anything to pick a playlist for. */
int playlist_end_add(void)
{
    uint32_t lib = library();
    int any = pl.otg && list_count(pl.scratch) > 0;

    if (lib)
        stand_down(lib);
    return any;
}

static uint32_t path[0x108 / 4];

/* path = iPod_Control\iTunes\<prefix><n>, to write (creating the file) or to
 * read; 0 if it couldn't be made (or, to read, there's no such file). */
static void *numbered_path(const char *prefix, uint32_t n, int write)
{
    char name[32], digits[10];
    unsigned i = 0, d = 0;

    while (prefix[i] && i < sizeof name - sizeof digits - 1) {
        name[i] = prefix[i];
        i++;
    }
    do
        digits[d++] = (char)('0' + n % 10);
    while ((n /= 10) && d < sizeof digits);
    while (d)
        name[i++] = digits[--d];
    name[i] = 0;
    for (d = 0; d < sizeof path / 4; d++)
        path[d] = 0;
    if (write)
        return make_path(path, ITUN, "iPod_Control\\iTunes\\", name) == 0 ? path : 0;
    return find_path(path, name) == 0 ? path : 0;
}

/* Writes the playlist `list` to an On-The-Go file at p. */
static void save_to(uint32_t lib, uint32_t list, void *p)
{
    if (!p)
        return;
    stand_in(lib, list);
    write_otg_file(lib, p);
    stand_down(lib);
}

/* The FroggerPlaylist files back into the synced playlists they're for. */
void playlist_load_saved(void)
{
    uint32_t lib = library(), n, i, list, playing;
    void *p;

    if (pl.loaded || !lib || !(n = word(lib, LIB_N_LISTS)))
        return;
    pl.loaded = 1;
    if (new_temp_list(lib, &pl.loading) != 0 || !pl.loading)
        return;
    playing = word(word(word(lib, 0), 1), PLAYER_LIST);
    for (i = 1; i < n; i++) {
        list = word(word(lib, LIB_LISTS), i);
        if (list == word(lib, LIB_OTG) || word(list, LIST_SAVED_N) || list == playing)
            continue;
        if (list_count(pl.loading))
            list_empty(pl.loading);
        if (!(p = numbered_path("FroggerPlaylist_", i, 0))
            || read_otg_file(pl.loading, lib_tracks(word(lib, 0)), db_stamp(), p) != 0 || !list_count(pl.loading))
            continue;
        if (list_count(list))
            list_empty(list);
        copy_list(lib, pl.loading, list_key(lib), 0, list);
    }
    if (list_count(pl.loading))
        list_empty(pl.loading);
}

/* Playlists' row `row` (as 0x08df.a9 gives it, untagged) was picked: the
 * scratch songs go there. The row's playlist is lib+0x870's [row + 1], as
 * 0x08eb.e2(row) finds it (0xd6760); On-The-Go is the row 0x08eb.ee says. */
void playlist_pick(uint32_t row)
{
    uint32_t ui = UI_OBJECT, lib = library(), target, i;

    target = 0;
    i = 0;
    if (lib && pl.scratch && list_count(pl.scratch)) {
        if (row_is_otg(ui, row))
            target = word(lib, LIB_OTG);
        else if ((i = row + 1) < word(lib, LIB_N_LISTS))
            target = word(word(lib, LIB_LISTS), i);
    }
    if (target) {
        playlist_load_saved();  /* before it's written over */
        copy_list(lib, pl.scratch, list_key(lib), 0, target);
        if (target == word(lib, LIB_OTG))
            ((volatile uint8_t *)word(lib, 0))[PREFS_OTG_DIRTY] = 1;
        else {
            if (pl.save_list && pl.save_list != target)
                playlist_flush();       /* another one still waiting: that first */
            pl.save_list = target;
            pl.save_index = i;
            if (disk_idle(DISK_IDLE_US))
                playlist_flush();
        }
    }
    playlist_cancel();
}

/* The playlist playlist_pick changed, saved: at once when the disk is free,
 * else from tick_hook once it is (a refill running, or a drive that stopped
 * answering, disk.c), so the UI neither waits on the disk nor writes over a
 * song change (skips.c). */
void playlist_flush(void)
{
    uint32_t lib = library(), target = pl.save_list;

    if (!target || !lib || pl.otg)
        return;                 /* (pl.otg: an add is standing in for On-The-Go) */
    pl.save_list = 0;
    if (word(target, LIST_SAVED_N))
        save_to(lib, target, numbered_path("OTGPlaylistInfo_", word(target, LIST_SAVED_N), 1));
    else
        save_to(lib, target, numbered_path("FroggerPlaylist_", pl.save_index, 1));
}

/* tick_hook, on the UI thread. */
void playlist_tick(void)
{
    if (pl.save_list && disk_idle(DISK_IDLE_US))
        playlist_flush();
}

/* The pick is done or cancelled: empties the scratch list. */
void playlist_cancel(void)
{
    if (pl.scratch && !pl.otg && list_count(pl.scratch))
        list_empty(pl.scratch);
}

/* The scratch list, for the hold menu's other actions, which also add the
 * held row's songs there to see which they are. */
uint32_t playlist_scratch(void)
{
    return pl.scratch;
}

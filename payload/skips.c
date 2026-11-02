/* Skip counts: a song left with Next, or for another song, after 2 s and
 * before 20 s of it counts as skipped (iTunes' rule); one that plays to its
 * end, Prev, Stop, pause and sleep don't count. 2.3 keeps no skip count (the
 * iTunesDB of 2.3 has no field for it), so the skips go in
 * iPod_Control/iTunes/FroggerSkips (skips.h has the format) for Crate, which
 * keeps them in its own library.
 *
 * Where a song is left (docs/re-notes.md, "Skips"):
 * - Next: 0xb81d4(player, flags). The button (0xaca28) and Up Next's pick
 *   (queue.c) pass 0; a song's end (0xb7840) passes NEXT_AT_END. Hook at its
 *   first instruction.
 * - A pick: every "start playing this" (a list's row, Shuffle Songs, the
 *   queue's first song) loads its item with 0xb8eb4(player, item). Hook at
 *   its first instruction. The list picks unload the song playing just
 *   before (skips_keep), and 0xd9268's loads (callers in the player, not
 *   known) don't count.
 * - Prev is 0xb75dc → 0xb8cf8, which neither of those sees.
 * The song being left and how far it got are the player's: [player+0x2a8]
 * (+0x20 its track record) and [player+0x2164] (ms), which Apple's bookmark
 * reads the same way (0xb902c).
 *
 * The file is saved with Play Counts (counts_hook), which Apple writes a
 * second or two after a song change too (event 'prwp': likely as the disk
 * goes idle) and at sleep, and read back
 * once each database has loaded. hooks.S has the glue. */

#include <stdint.h>
#include "skips.h"
#include "hide.h"

#define PLAYER_ITEM      (0x2a8 / 4)
#define PLAYER_POS       ((0x2000 + 0x164) / 4)     /* ms into the track */
#define ITEM_TRACK       (0x20 / 4)
#define PICK_US          1000000u                   /* keep_hook's note lasts this long */
#define SKIP_NOT_FROM    0xd92bcu                   /* 0xd9268's call of 0xb8eb4 returns here */

#define MAX_SKIPS 2048  /* songs with skips since the last sync; more are dropped */

struct skip { uint32_t pos, id, count, last; };

static struct skip skip[MAX_SKIPS];
static uint32_t n_skip, gen, dirty;                 /* gen: hide_gen() + 1 once read back */

#define make_path   ((uint32_t (*)(void *out, uint32_t kind, const char *dir, const char *name))0x53a24)
#define find_path   ((uint32_t (*)(void *out, const char *name))0x7b3bc)
#define fw_open     ((int (*)(void *path, void *file, uint32_t mode, uint32_t type))0x403fc)
#define fw_create   ((int (*)(void *path, void *file, uint32_t zero, uint32_t type))0x40474)
#define fw_read     ((int (*)(void *file, uint32_t *len, void *data))0x404ec)
#define fw_write    ((int (*)(void *file, uint32_t *len, const void *data))0x407e8)
#define fw_close    ((int (*)(void *))0x40110)
#define db_stamp    ((uint32_t (*)(void))0x77600)
#define clock_us    ((void (*)(uint32_t *us))0x87de0)
#define mac_time    ((void (*)(uint32_t *out))0xa065c)  /* as 0xb79ac sets "last played" */
#define ITUN        0x6974756eu
#define FW_READ     0x20000
#define FW_DATA     0x64617461u

static uint32_t path[0x108 / 4], file[0x80 / 4];
static const char name[] = "FroggerSkips";

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static void clear(uint32_t *p, unsigned n)
{
    while (n--)
        *p++ = 0;
}

static struct skip *entry(uint32_t pos, uint32_t id)
{
    uint32_t i;

    for (i = 0; i < n_skip; i++)
        if (skip[i].pos == pos)
            return &skip[i];
    if (n_skip == MAX_SKIPS)
        return 0;
    skip[n_skip].pos = pos;
    skip[n_skip].id = id;
    skip[n_skip].count = skip[n_skip].last = 0;
    return &skip[n_skip++];
}

/* The song `track` is being left for another at `ms`: a skip if that's 2-20 s. */
static void left(uint32_t track, uint32_t ms)
{
    uint32_t id;
    int pos;
    struct skip *s;

    if (gen != hide_gen() + 1 || !track || ms < SKIP_MIN_MS || ms >= SKIP_MAX_MS)
        return;
    if ((pos = hide_position(track, &id)) < 0 || !(s = entry(pos, id)))
        return;
    s->count++;
    mac_time(&s->last);
    dirty = 1;
}

static uint32_t playing(uint32_t player)
{
    uint32_t item = word(player, PLAYER_ITEM);

    return item ? word(item, ITEM_TRACK) : 0;
}

/* The song playing as a pick began (keep_hook), for the pick's load. */
static struct { uint32_t track, ms, at; } before;

/* 0xb81d4(player, flags), Next. */
void skips_next(uint32_t player, uint32_t flags)
{
    if (player && !(flags & NEXT_AT_END))
        left(playing(player), word(player, PLAYER_POS));
}

/* keep_hook: 0x5e8cc(lib), the first step of every list pick (0xb6c38,
 * 0xb6af8, 0xb7310, 0xb7468, 0xb7174), deletes the list playing, and that
 * unloads its song (0xb7fb8 → 0xb8ed8(player, 0)) before the pick's
 * 0xb8eb4. So note the song here; a later call, with nothing playing, keeps
 * the note. */
void skips_keep(uint32_t lib)
{
    uint32_t player = word(word(lib, 0), 1), track;

    if (!player || !(track = playing(player)))
        return;
    before.track = track;
    before.ms = word(player, PLAYER_POS);
    clock_us(&before.at);
}

/* 0xb8eb4(player, item), a pick; `from` is its caller's return address. */
void skips_pick(uint32_t player, uint32_t item, uint32_t from)
{
    uint32_t track, ms, now;

    if (!player || !item || from == SKIP_NOT_FROM)
        return;
    if ((track = playing(player)) != 0)
        ms = word(player, PLAYER_POS);          /* (0xb70c4 doesn't unload first) */
    else {
        clock_us(&now);
        track = before.track && now - before.at < PICK_US ? before.track : 0;
        ms = before.ms;
    }
    before.track = 0;
    if (track != word(item, ITEM_TRACK))        /* not the same song again */
        left(track, ms);
}

/* After a skip (skips_tick), and from counts_hook as Play Counts is written
 * (sleep, or the database unloading while its positions still hold), in
 * case a tick hasn't come since. */
void skips_save(void)
{
    struct skip_file_header h = { SKIP_FILE_MAGIC, SKIP_FILE_VERSION, sizeof(struct skip), 0, 0, 0 };
    uint32_t len;

    if (!dirty || gen != hide_gen() + 1)
        return;
    h.stamp = db_stamp();
    h.count = n_skip;
    clear(path, sizeof path / 4);
    clear(file, sizeof file / 4);
    if (make_path(path, ITUN, "iPod_Control\\iTunes\\", name) != 0 || fw_create(path, file, 0, FW_DATA) != 0)
        return;
    len = sizeof h;
    fw_write(file, &len, &h);
    len = n_skip * sizeof(struct skip);
    fw_write(file, &len, skip);
    fw_close(file);
    dirty = 0;
}

/* tick_hook, on the UI thread: once a database has loaded, the file back
 * (entries whose track is still there by position and id). It's not saved
 * here after a skip: a skip is a song change, so the player is reading the
 * next song into RAM just then, and a file written over that left a device
 * unable to play anything until a restart. counts_hook saves it with Play
 * Counts, which keeps the skips as long as Apple keeps the plays. */
void skips_tick(void)
{
    struct skip_file_header h;
    struct skip e, *s;
    uint32_t len, i;

    if (gen == hide_gen() + 1)
        return;
    if (!hide_tracks())
        return;
    gen = hide_gen() + 1;
    n_skip = dirty = 0;
    clear(path, sizeof path / 4);
    clear(file, sizeof file / 4);
    if (find_path(path, name) != 0 || fw_open(path, file, FW_READ, FW_DATA) != 0)
        return;
    len = sizeof h;
    if (fw_read(file, &len, &h) == 0 && len == sizeof h && h.magic == SKIP_FILE_MAGIC
        && h.version == SKIP_FILE_VERSION && h.entry_size == sizeof e && h.stamp == db_stamp())
        for (i = 0; i < h.count; i++) {
            len = sizeof e;
            if (fw_read(file, &len, &e) != 0 || len != sizeof e)
                break;
            if (hide_record(e.pos, e.id) && (s = entry(e.pos, e.id)) != 0) {
                s->count = e.count;
                s->last = e.last;
            }
        }
    fw_close(file);
}

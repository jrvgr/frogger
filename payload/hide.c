/* Hidden songs: a track whose iTunesDB record carries the hide flag (see
 * hide.h) stays out of the lists by artist, album, genre and composer, but
 * still shows in Songs and plays from every playlist it is in.
 *
 * The track loader (0xc4a68) hands us each flagged track as it loads. Every
 * library list asks 0x58440 whether to keep each master playlist item, and
 * browse_hook makes that ask hide_entry() first; the browse loop at 0xf1ce8
 * does the same through filter_hook. hooks.S has the glue. */

#include <stdint.h>
#include "hide.h"
#include "disk.h"
#include "debug.h"
#include "tracks.h"

/* A set of track record addresses, with open addressing. 0 is an empty
 * slot, GONE one whose track was shown again (Show), which a lookup walks
 * past and an insert takes. When the table is full, further tracks simply
 * stay visible. */
#define TABLE_BITS 14   /* 16384 hidden songs */
#define TABLE_SIZE (1u << TABLE_BITS)

#define GONE 1u      /* no record is at 1 */

static uint32_t table[TABLE_SIZE];

struct hide_state hide_state;

static uint32_t *slot(uint32_t track, int insert)
{
    uint32_t i = (track * 2654435761u) >> (32 - TABLE_BITS);
    uint32_t n, *gone = 0;

    for (n = 0; n < TABLE_SIZE; n++, i = (i + 1) & (TABLE_SIZE - 1)) {
        if (table[i] == track)
            return &table[i];
        if (table[i] == GONE && !gone)
            gone = &table[i];
        if (table[i] == 0)
            break;
    }
    if (!insert)
        return 0;
    if (!gone && n < TABLE_SIZE)
        gone = &table[i];
    if (gone)
        *gone = track;
    return gone;
}

void hide_reset(void)
{
    uint32_t i;

    for (i = 0; i < TABLE_SIZE; i++)
        table[i] = 0;
}

void hide_mark(uint32_t track)
{
    if (track > GONE)
        slot(track, 1);
}

static void unmark(uint32_t track)
{
    uint32_t *s = track ? slot(track, 0) : 0;

    if (s)
        *s = GONE;
}

int hide_track(uint32_t track)
{
    return track > GONE && slot(track, 0);
}

/* `owner` is the playlist the browse loop is walking (item word 0). Only
 * library browsing hides anything: inside a playlist every track shows. */
int hide_entry(uint32_t owner, uint32_t track)
{
    if (hide_state.show_all || !owner || !track)
        return 0;
#ifndef FROGGER_HIDE_EVERYWHERE  /* test builds: hide in every list, to tell a wrong owner from an unused loop */
    if (owner != hide_state.master && owner != *(const uint32_t *)track)
        return 0;
#endif
    return hide_track(track);
}

/* Songs hidden on the iPod (the hold menu's Hide, holdmenu.c). The iTunesDB
 * can't be written here, so they go in iPod_Control/iTunes/FroggerHidden
 * (hide.h has the format; Crate reads it on the next sync and writes the
 * flag into the iTunesDB), which is read back after each database load.
 * Entries name the track by key (tracks.h: its dbid, else its id, size and
 * length), so they still apply after another app's sync; ones whose song
 * is gone are dropped. Versions 1 and 2 named it by position and id and are
 * read only with the stamp of the iTunesDB they were written for; the next
 * save writes version 3. Each entry says hidden or shown. Shown (Show, on a
 * song the iTunesDB flags) overrides the flag here, and tells Crate not to
 * flag it again; a song Show un-hides that only the file hid, or Hide hides
 * again that the iTunesDB flags, simply leaves the file. */
#define MAX_MINE   4096

static uint32_t mine[MAX_MINE], n_mine;         /* positions, SHOWN */
static uint32_t flagged[MAX_TRACKS / 32];       /* by position: the iTunesDB's flag */
#define SHOWN 0x80000000u
static uint32_t loaded;                         /* the database (tracks_gen) the file was read for */
/* The iTunesDB's stamp (0x77600: a stat of the file, so a directory read
 * that wakes a sleeping disk): read once as the database loads, when the
 * disk is up anyway, not at each Hide on the UI's thread. */
static uint32_t stamp;

/* The firmware's file calls, for the save task: tracks.c's file_* share one
 * path and file buffer on the UI's thread, so the task has its own. */
#define make_path   ((uint32_t (*)(void *out, uint32_t kind, const char *dir, const char *name))0x53a24)
#define fw_create   ((int (*)(void *path, void *file, uint32_t zero, uint32_t type))0x40474)
#define fw_write    ((int (*)(void *file, uint32_t *len, const void *data))0x407e8)
#define fw_close    ((int (*)(void *))0x40110)
#define db_stamp    ((uint32_t (*)(void))0x77600)
#define ITUN        0x6974756eu
#define FW_DATA     0x64617461u

static const char name[] = "FroggerHidden";

static void clear(uint32_t *p, unsigned n)
{
    while (n--)
        *p++ = 0;
}

static int is_flagged(uint32_t pos)
{
    return (flagged[pos / 32] >> (pos % 32)) & 1;
}

/* pos's entry: hidden or shown, or none when that's what the iTunesDB says. */
static void note_mine(uint32_t pos, int shown)
{
    uint32_t i;

    for (i = 0; i < n_mine && (mine[i] & ~SHOWN) != pos; i++)
        ;
    if (shown != is_flagged(pos)) {
        if (i < n_mine)
            mine[i] = mine[--n_mine];
        return;
    }
    if (i < n_mine)
        mine[i] = pos | (shown ? SHOWN : 0);
    else if (n_mine < MAX_MINE)
        mine[n_mine++] = pos | (shown ? SHOWN : 0);
}

/* The file's contents, staged on the UI's side (stage) for the save task to
 * write: the header, then the entries, their keys taken while the database
 * `mine`'s positions are in is the loaded one (stageable). */
static struct {
    struct hide_file_header h;
    struct hide_entry e[MAX_MINE];
} out;
static uint32_t out_path[0x108 / 4], out_file[0x80 / 4];

static void stage(void)
{
    uint32_t i;
    struct hide_file_header h = { HIDE_FILE_MAGIC, HIDE_FILE_VERSION, sizeof(struct hide_entry), stamp, n_mine, 0 };

    out.h = h;
    for (i = 0; i < n_mine; i++) {
        tracks_key(mine[i] & ~SHOWN, &out.e[i].key);
        out.e[i].flags = mine[i] & SHOWN ? HIDE_ENTRY_SHOWN : 0;
    }
}

/* Writes what stage() put in `out`: on the save task (or, with no task, the
 * UI's). Returns fw_create's result. */
static int write_out(void)
{
    uint32_t len;
    int r;

    clear(out_path, sizeof out_path / 4);
    clear(out_file, sizeof out_file / 4);
    if (make_path(out_path, ITUN, "iPod_Control\\iTunes\\", name) != 0)
        return -1;
    if ((r = fw_create(out_path, out_file, 0, FW_DATA)) != 0)
        return r;
    len = sizeof out.h + out.h.count * sizeof out.e[0];
    fw_write(out_file, &len, &out);
    fw_close(out_file);
    return 0;
}

static void note(uint32_t track, int shown)
{
    uint32_t pos;

    if (loaded == tracks_gen() && tracks_position(track, &pos) && pos < tracks_count())
        note_mine(pos, shown);
}

/* The hold menu's Hide: track hidden now, and in the file. */
void hide_add(uint32_t track)
{
    if (!track)
        return;
    hide_mark(track);
    note(track, 0);
}

/* The hold menu's Show (on a hidden song): track shown now, and in the file. */
void hide_show(uint32_t track)
{
    if (!track)
        return;
    unmark(track);
    note(track, 1);
}

/* The hold menu's Hide or Show is done: the file is written, but never on
 * the UI's thread. Its stamp (a stat of the iTunesDB, now read at load)
 * and creating the file both wake a disk that has gone to sleep
 * (and a flash card's IDE bridge with it) and reads the FAT; an SD adapter
 * can drop out on that wake-up (the supply dips, disk.c), and the UI then
 * waited out the 10 s timeout and the recovery: the wheel and Menu frozen,
 * and the clicks made meanwhile replayed at once afterwards. So a task of
 * our own, FroggerSave (as art.c's FroggerArt reads covers), writes it once
 * the disk is free (disk_idle: no refill running, so no write over a song
 * change, skips.c). The UI only stages the contents (save_tick, hide_flush)
 * while the task isn't writing, so they don't change under it. With no
 * task, the UI writes them itself at a tick when the disk is free. */
static volatile struct { uint32_t want, staged, done; int task; } sv;

#define fw_thread   ((uint32_t (*)(const char *name, void (*entry)(void), const char *args, uint32_t prio, \
                                   uint32_t stack, uint32_t zero1, uint32_t zero2))0xac6fc)
#define fw_sleep    ((void (*)(uint32_t zero, uint32_t ticks))0x3460)   /* 10 ms ticks */
#define SAVE_TASK_PRIO  0x40    /* TrackCacheReadTask's, as FroggerArt */
#define SAVE_TASK_STACK 0x1000
#define SAVE_POLL_TICKS 10      /* 100 ms */

static void save_task_main(void)
{
    uint32_t staged;
    int r;

    for (;;) {
        staged = sv.staged;
        if (staged != sv.done && disk_idle(DISK_IDLE_US)) {
            r = write_out();
            debug_note(DEBUG_TAG('h', 'w', 'r', 't'), (uint32_t)r, out.h.count);
            sv.done = staged;
        } else {
            fw_sleep(0, SAVE_POLL_TICKS);
        }
    }
}

void hide_save(void)
{
    sv.want++;
    debug_note(DEBUG_TAG('h', 's', 'a', 'v'), n_mine, tracks_count());
    if (!sv.task) {
        uint32_t t = fw_thread("FroggerSave", save_task_main, 0, SAVE_TASK_PRIO, SAVE_TASK_STACK, 0, 0);
        sv.task = t && t < 0x80000000u ? 1 : -1;
    }
}

/* Whether stage() may take keys now: `mine`'s positions are in the loaded
 * database (not one a new load has since replaced in tracks.c's table). */
static int stageable(void)
{
    return loaded == tracks_gen() && tracks_ready();
}

/* Stages a save still to be written for the task (counts_hook too, as Apple
 * writes Play Counts). */
void hide_flush(void)
{
    if (sv.task > 0 && sv.want != sv.staged && sv.staged == sv.done && stageable()) {
        stage();
        sv.staged = sv.want;
    }
}

static void save_tick(void)
{
    if (sv.want == sv.staged || sv.staged != sv.done)
        return;                 /* nothing new, or the task is still writing the last */
    if (sv.task > 0)
        hide_flush();
    else if (stageable() && disk_idle(DISK_IDLE_US)) {     /* no task: on the UI's thread */
        stage();
        sv.staged = sv.want;
        debug_note(DEBUG_TAG('h', 'w', 'r', 'u'), (uint32_t)write_out(), out.h.count);
        sv.done = sv.staged;
    }
}

/* One entry of the file: hidden or shown at pos, if that's its track. */
static void apply(uint32_t pos, uint32_t flags)
{
    uint32_t track = tracks_record(pos);

    if (!track)
        return;
    if (flags & HIDE_ENTRY_SHOWN)
        unmark(track);
    else
        hide_mark(track);
    note_mine(pos, flags & HIDE_ENTRY_SHOWN);
}

/* tick_hook, on the UI thread (after tracks_tick): once the database has
 * loaded, the file back. Version 3 by key; versions 1 and 2 by position and
 * id, only for the iTunesDB they were written for (version 1 has no flags
 * word: all hidden). A save still waiting from the database before is
 * dropped (its positions are gone with it); one the task is writing is
 * waited for, so the file isn't read half written. */
void hide_tick(void)
{
    struct hide_file_header h;
    struct hide_entry e;
    uint32_t i, pos, old[3];
    int p;

    save_tick();
    if (loaded == tracks_gen() || !tracks_ready() || sv.staged != sv.done)
        return;
    loaded = tracks_gen();
    n_mine = 0;
    sv.want = sv.staged;
    stamp = db_stamp();
    clear(flagged, sizeof flagged / 4);
    for (pos = 0; pos < tracks_count(); pos++)
        if (hide_track(tracks_record(pos)))
            flagged[pos / 32] |= 1u << (pos % 32);
    if (!file_open(name))
        return;
    if (file_read(&h, sizeof h) && h.magic == HIDE_FILE_MAGIC) {
        if (h.version == HIDE_FILE_VERSION && h.entry_size == sizeof e) {
            for (i = 0; i < h.count && file_read(&e, sizeof e); i++)
                if ((p = tracks_find(&e.key)) >= 0)
                    apply((uint32_t)p, e.flags);
        } else if (((h.version == 1 && h.entry_size == 8) || (h.version == 2 && h.entry_size == 12))
                   && h.stamp == stamp) {
            for (i = 0; i < h.count; i++) {
                old[2] = 0;
                if (!file_read(old, h.entry_size))
                    break;
                if (old[0] < tracks_count()) {
                    struct track_key k;
                    tracks_key(old[0], &k);
                    if (k.id == old[1])
                        apply(old[0], old[2]);
                }
            }
        }
    }
    file_close();
}

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
 * flag into the iTunesDB), which is read back after each database load. The
 * file carries the iTunesDB's stamp, like Apple's On-The-Go files, so a sync
 * makes it stale. Entries are the track's position in the iTunesDB (the mhit's
 * index, as track_hook counts), its track id (mhit+0x10) and whether it's
 * hidden or shown. Shown (Show, on a song the iTunesDB flags) overrides the
 * flag here, and tells Crate not to flag it again; a song Show un-hides that
 * only the file hid, or Hide hides again that the iTunesDB flags, simply
 * leaves the file. */
#define MAX_TRACKS 16384
#define MAX_MINE   4096

static uint32_t track_rec[MAX_TRACKS], track_id[MAX_TRACKS], n_tracks;
static uint32_t mine[MAX_MINE], n_mine;         /* positions, SHOWN */
static uint32_t flagged[MAX_TRACKS / 32];       /* by position: the iTunesDB's flag */
#define SHOWN 0x80000000u
static int loaded;
static uint32_t gen;                            /* databases loaded */
/* The iTunesDB's stamp (0x77600: a stat of the file, so a directory read
 * that wakes a sleeping disk): read once as the database loads, when the
 * disk is up anyway, not at each Hide on the UI's thread. */
static uint32_t stamp;

#define make_path   ((uint32_t (*)(void *out, uint32_t kind, const char *dir, const char *name))0x53a24)
#define find_path   ((uint32_t (*)(void *out, const char *name))0x7b3bc)
#define fw_open     ((int (*)(void *path, void *file, uint32_t mode, uint32_t type))0x403fc)
#define fw_create   ((int (*)(void *path, void *file, uint32_t zero, uint32_t type))0x40474)
#define fw_read     ((int (*)(void *file, uint32_t *len, void *data))0x404ec)
#define fw_write    ((int (*)(void *file, uint32_t *len, const void *data))0x407e8)
#define fw_close    ((int (*)(void *))0x40110)
#define db_stamp    ((uint32_t (*)(void))0x77600)
#define ITUN        0x6974756eu
#define FW_READ     0x20000
#define FW_DATA     0x64617461u

static uint32_t path[0x108 / 4], file[0x80 / 4];
static const char name[] = "FroggerHidden";

/* track_hook, for every track record as the database loads. */
void hide_loaded(uint32_t record, uint32_t pos, uint32_t id)
{
    if (pos == 0) {
        n_tracks = n_mine = 0;
        loaded = 0;
        gen++;
    }
    if (pos < MAX_TRACKS) {
        track_rec[pos] = record;
        track_id[pos] = id;
        n_tracks = pos + 1;
    }
}

/* For skips.c: the loaded database's tracks by position. */
uint32_t hide_gen(void)
{
    return gen;
}

uint32_t hide_tracks(void)
{
    return n_tracks;
}

int hide_position(uint32_t track, uint32_t *id)
{
    uint32_t pos;

    for (pos = 0; pos < n_tracks; pos++)
        if (track_rec[pos] == track) {
            *id = track_id[pos];
            return pos;
        }
    return -1;
}

uint32_t hide_record(uint32_t pos, uint32_t id)
{
    return pos < n_tracks && track_id[pos] == id ? track_rec[pos] : 0;
}

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
 * write: the header, then the entries. */
static struct {
    struct hide_file_header h;
    uint32_t e[MAX_MINE][3];
} out;
static uint32_t out_path[0x108 / 4], out_file[0x80 / 4];

static void stage(void)
{
    uint32_t i;
    struct hide_file_header h = { HIDE_FILE_MAGIC, HIDE_FILE_VERSION, 12, stamp, n_mine, 0 };

    out.h = h;
    for (i = 0; i < n_mine; i++) {
        out.e[i][0] = mine[i] & ~SHOWN;
        out.e[i][1] = track_id[out.e[i][0]];
        out.e[i][2] = mine[i] & SHOWN ? HIDE_ENTRY_SHOWN : 0;
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

    for (pos = 0; pos < n_tracks && track_rec[pos] != track; pos++)
        ;
    if (pos < n_tracks)
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
    debug_note(DEBUG_TAG('h', 's', 'a', 'v'), n_mine, n_tracks);
    if (!sv.task) {
        uint32_t t = fw_thread("FroggerSave", save_task_main, 0, SAVE_TASK_PRIO, SAVE_TASK_STACK, 0, 0);
        sv.task = t && t < 0x80000000u ? 1 : -1;
    }
}

/* Stages a save still to be written for the task (counts_hook too, as Apple
 * writes Play Counts). */
void hide_flush(void)
{
    if (sv.task > 0 && sv.want != sv.staged && sv.staged == sv.done) {
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
    else if (disk_idle(DISK_IDLE_US)) {     /* no task: on the UI's thread */
        stage();
        sv.staged = sv.want;
        debug_note(DEBUG_TAG('h', 'w', 'r', 'u'), (uint32_t)write_out(), out.h.count);
        sv.done = sv.staged;
    }
}

/* tick_hook, on the UI thread: once the database has loaded, the file back
 * (version 1's entries have no flags word: all hidden). */
void hide_tick(void)
{
    struct hide_file_header h;
    uint32_t len, i, pos, e[3];

    save_tick();
    if (loaded || !n_tracks)
        return;
    loaded = 1;
    stamp = db_stamp();
    clear(flagged, sizeof flagged / 4);
    for (pos = 0; pos < n_tracks; pos++)
        if (hide_track(track_rec[pos]))
            flagged[pos / 32] |= 1u << (pos % 32);
    clear(path, sizeof path / 4);
    clear(file, sizeof file / 4);
    if (find_path(path, name) != 0 || fw_open(path, file, FW_READ, FW_DATA) != 0)
        return;
    len = sizeof h;
    if (fw_read(file, &len, &h) == 0 && len == sizeof h && h.magic == HIDE_FILE_MAGIC
        && ((h.version == 1 && h.entry_size == 8) || (h.version == HIDE_FILE_VERSION && h.entry_size == 12))
        && h.stamp == stamp)
        for (i = 0; i < h.count; i++) {
            e[2] = 0;
            len = h.entry_size;
            if (fw_read(file, &len, e) != 0 || len != h.entry_size)
                break;
            if (e[0] < n_tracks && track_id[e[0]] == e[1]) {
                if (e[2] & HIDE_ENTRY_SHOWN)
                    unmark(track_rec[e[0]]);
                else
                    hide_mark(track_rec[e[0]]);
                note_mine(e[0], e[2] & HIDE_ENTRY_SHOWN);
            }
        }
    fw_close(file);
}

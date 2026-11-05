/* Resume for long tracks: a song of 20 minutes or more (a DJ mix) starts where
 * it was left, a few seconds back, and starts over once it has played to the
 * end. Settings › Resume Mixes turns it off.
 *
 * 2.3 already does this for audiobooks, and only by the file's name: as it
 * loads a track (0xb8ed8), 0xb7efc sets the player flag 0x40 when the path ends
 * in ".m4b" (0xc0 for Audible), and that flag is all the rest looks at:
 *
 * - leaving the track (another one loads: Next, Prev, a pick, the end of the
 *   song, Up Next) stores the position in the track record's bookmark,
 *   track+0x60 (0xb903c), and marks it changed;
 * - starting it begins at track+0x60 (0xb9550) instead of 0;
 * - Stop keeps the position (0xb9cc4);
 * - track+0x60 is mhit+0x6c in the iTunesDB (track loader, 0xc4bcc), and the
 *   bookmark word of the Play Counts file (written by 0xf4d6c, read back at
 *   boot by the database load at 0xe4064), so it survives a restart, and a
 *   sync if Crate carries it over.
 *
 * So resume_flags sets 0x40 for long tracks as they load (hook at 0xb9354, just
 * before the flags are stored at [player+0x2380]), and Apple does the rest.
 * Only for the tracks flagged here: resume_start starts RESUME_BACK_MS early,
 * resume_save stores 0 for a track left in its last RESUME_END_MS (it played to
 * the end), and resume_flush puts the playing track's position in its
 * bookmark before the Play Counts file is written (the sleep path writes it
 * without loading another track first). FroggerBookmarks keeps them by key
 * too, for a sync by an app that drops them (the end of this file). hooks.S
 * has the glue. */

#include <stdint.h>
#include "resume.h"
#include "settings.h"
#include "tracks.h"

#define UI_OBJECT        (*(volatile uint32_t *)0x43580c)
#define PLAYER_ITEM      (0x2a8 / 4)
#define PLAYER_POS       ((0x2000 + 0x164) / 4)     /* ms into the track */
#define PLAYER_FLAGS     ((0x2000 + 0x380) / 4)
#define ITEM_TRACK       (0x20 / 4)
#define TRACK_LENGTH     (0x54 / 4)                 /* ms, mhit+0x28 */
#define TRACK_BOOKMARK   (0x60 / 4)                 /* ms, mhit+0x6c */
#define ROOT_PLAYER      (4 / 4)
#define ROOT_COUNTS_DIRTY 0xb41                     /* byte: 0xf4d6c writes Play Counts only if set (0xeb4b8) */
#define db_stamp         ((uint32_t (*)(void))0x77600)

/* The track record resume_flags last flagged: the one loaded, if it's ours. */
static uint32_t resume_track;

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static int resume_on(void)
{
    uint32_t ui = UI_OBJECT, lib;

    if (!ui || !(lib = word(ui, 0x1c / 4)) || !word(lib, 0))
        return 1;
    return !(word(word(lib, 0), 0xb04 / 4) & FROGGER_PREF_NO_RESUME);
}

/* 0xb9354 in 0xb8ed8: `flags` is about to become [player+0x2380] for track
 * record `track`, the one loading. */
uint32_t resume_flags(uint32_t flags, uint32_t track)
{
    resume_track = 0;
    if (!track || flags & PLAYER_BOOKMARK || word(track, TRACK_LENGTH) < RESUME_MIN_MS || !resume_on())
        return flags;
    resume_track = track;
    return flags | PLAYER_BOOKMARK;
}

static uint32_t finished(uint32_t pos, uint32_t track)
{
    return pos + RESUME_END_MS >= word(track, TRACK_LENGTH) ? 0 : pos;
}

/* 0xb9550: the new track starts at `pos`, its bookmark. */
uint32_t resume_start(uint32_t pos, uint32_t player)
{
    uint32_t item = word(player, PLAYER_ITEM);

    if (!resume_track || !item || word(item, ITEM_TRACK) != resume_track)
        return pos;
    pos = finished(pos, resume_track);
    return pos > RESUME_BACK_MS ? pos - RESUME_BACK_MS : 0;
}

/* 0xb903c: `pos` is about to become the bookmark of `track`, which is being
 * left. */
uint32_t resume_save(uint32_t pos, uint32_t track)
{
    return track == resume_track ? finished(pos, track) : pos;
}

/* 0xf4d6c(lib) is about to write the Play Counts file. */
void resume_flush(uint32_t lib)
{
    uint32_t root = word(lib, 0), player, item, pos;

    if (!resume_track || !root || !(player = word(root, ROOT_PLAYER)))
        return;
    item = word(player, PLAYER_ITEM);
    if (!item || word(item, ITEM_TRACK) != resume_track || !(word(player, PLAYER_FLAGS) & PLAYER_BOOKMARK))
        return;
    pos = finished(word(player, PLAYER_POS), resume_track);
    if (pos == word(resume_track, TRACK_BOOKMARK))
        return;
    ((volatile uint32_t *)resume_track)[TRACK_BOOKMARK] = pos;
    *(volatile uint8_t *)(root + ROOT_COUNTS_DIRTY) = 1;
}

/* FroggerBookmarks (resume.h): the bookmarks of the long tracks, by key, so
 * they outlast a sync by an app that doesn't carry Play Counts' bookmarks
 * into the new iTunesDB. Written with Play Counts (counts_hook, after
 * resume_flush), only when one has changed; read back once a new database
 * has loaded, for the tracks that came without a bookmark of their own. */
static const char bm_name[] = "FroggerBookmarks";
static uint32_t bm_gen, bm_sum;

/* The long tracks' bookmarks: how many, and a sum to tell a change; with
 * `write`, each as an entry of the file (open for writing). */
static uint32_t bm_scan(int write, uint32_t *sum)
{
    struct bookmark_entry e;
    uint32_t pos, track, n = 0, s = 0;

    for (pos = 0; pos < tracks_count(); pos++) {
        track = tracks_record(pos);
        if (word(track, TRACK_LENGTH) < RESUME_MIN_MS || !word(track, TRACK_BOOKMARK))
            continue;
        n++;
        s = (s * 31 + pos) * 31 + word(track, TRACK_BOOKMARK);
        if (write) {
            tracks_key(pos, &e.key);
            e.ms = word(track, TRACK_BOOKMARK);
            file_write(&e, sizeof e);
        }
    }
    *sum = s ^ n;
    return n;
}

/* counts_hook, as Play Counts is written. */
void bookmarks_save(void)
{
    struct bookmark_file_header h = { BOOKMARK_FILE_MAGIC, BOOKMARK_FILE_VERSION, sizeof(struct bookmark_entry), 0, 0, 0 };
    uint32_t sum;

    if (bm_gen != tracks_gen() || !tracks_ready())
        return;
    h.count = bm_scan(0, &sum);
    if (sum == bm_sum || !file_create(bm_name))
        return;
    h.stamp = db_stamp();
    file_write(&h, sizeof h);
    bm_scan(1, &sum);
    file_close();
    bm_sum = sum;
}

/* tick_hook, on the UI thread (after tracks_tick). For the iTunesDB the
 * file was written with, Play Counts has the same bookmarks already. */
void bookmarks_tick(void)
{
    struct bookmark_file_header h;
    struct bookmark_entry e;
    uint32_t i, track, any = 0, ui = UI_OBJECT, lib;
    int p;

    if (bm_gen == tracks_gen() || !tracks_ready())
        return;
    bm_gen = tracks_gen();
    if (resume_on() && file_open(bm_name)) {
        if (file_read(&h, sizeof h) && h.magic == BOOKMARK_FILE_MAGIC && h.version == BOOKMARK_FILE_VERSION
            && h.entry_size == sizeof e && h.stamp != db_stamp())
            for (i = 0; i < h.count && file_read(&e, sizeof e); i++)
                if ((p = tracks_find(&e.key)) >= 0 && (track = tracks_record((uint32_t)p)) != 0
                    && word(track, TRACK_LENGTH) >= RESUME_MIN_MS && !word(track, TRACK_BOOKMARK)
                    && e.ms < word(track, TRACK_LENGTH)) {
                    ((volatile uint32_t *)track)[TRACK_BOOKMARK] = e.ms;
                    any = 1;
                }
        file_close();
    }
    if (any && ui && (lib = word(ui, 0x1c / 4)) && word(lib, 0))
        *(volatile uint8_t *)(word(lib, 0) + ROOT_COUNTS_DIRTY) = 1;   /* into Play Counts too */
    bm_scan(0, &bm_sum);
}

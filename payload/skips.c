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
#include "tracks.h"

#define PLAYER_ITEM      (0x2a8 / 4)
#define PLAYER_POS       ((0x2000 + 0x164) / 4)     /* ms into the track */
#define ITEM_TRACK       (0x20 / 4)
#define PICK_US          1000000u                   /* keep_hook's note lasts this long */
#define SKIP_NOT_FROM    0xd92bcu                   /* 0xd9268's call of 0xb8eb4 returns here */

#define MAX_SKIPS 2048  /* songs with skips since the last sync; more are dropped */

struct skip { uint32_t pos, id, count, last; };

static struct skip skip[MAX_SKIPS];
static uint32_t n_skip, gen, dirty;                 /* gen: tracks_gen() once read back */

#define db_stamp    ((uint32_t (*)(void))0x77600)
#define clock_us    ((void (*)(uint32_t *us))0x87de0)
#define mac_time    ((void (*)(uint32_t *out))0xa065c)  /* as 0xb79ac sets "last played" */

static const char name[] = "FroggerSkips";

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
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
    uint32_t pos;
    struct track_key k;
    struct skip *s;

    if (gen != tracks_gen() || !track || ms < SKIP_MIN_MS || ms >= SKIP_MAX_MS)
        return;
    if (!tracks_position(track, &pos) || pos >= tracks_count())
        return;
    tracks_key(pos, &k);
    if (!(s = entry(pos, k.id)))
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
    struct skip_file_header h = { SKIP_FILE_MAGIC, SKIP_FILE_VERSION, sizeof(struct skip_entry), 0, 0, 0 };
    struct skip_entry e;
    uint32_t i;

    if (!dirty || gen != tracks_gen())
        return;
    h.stamp = db_stamp();
    h.count = n_skip;
    if (!file_create(name))
        return;
    file_write(&h, sizeof h);
    for (i = 0; i < n_skip; i++) {
        tracks_key(skip[i].pos, &e.key);
        e.count = skip[i].count;
        e.last = skip[i].last;
        file_write(&e, sizeof e);
    }
    file_close();
    dirty = 0;
}

static void restore(uint32_t pos, uint32_t count, uint32_t last)
{
    struct track_key k;
    struct skip *s;

    tracks_key(pos, &k);
    if ((s = entry(pos, k.id)) != 0) {
        s->count += count;
        s->last = last > s->last ? last : s->last;
    }
}

/* tick_hook, on the UI thread (after tracks_tick): once a database has
 * loaded, the file back: version 2 by key (entries whose song is gone are
 * dropped), version 1 by position and id, only for the iTunesDB it was
 * written for. It's not saved here after a skip: a skip is a song change, so
 * the player is reading the next song into RAM just then, and a file written
 * over that left a device unable to play anything until a restart.
 * counts_hook saves it with Play Counts, which keeps the skips as long as
 * Apple keeps the plays. */
void skips_tick(void)
{
    struct skip_file_header h;
    struct skip_entry e;
    uint32_t i, old[4];
    int p;

    if (gen == tracks_gen() || !tracks_ready())
        return;
    gen = tracks_gen();
    n_skip = dirty = 0;
    if (!file_open(name))
        return;
    if (file_read(&h, sizeof h) && h.magic == SKIP_FILE_MAGIC) {
        if (h.version == SKIP_FILE_VERSION && h.entry_size == sizeof e) {
            for (i = 0; i < h.count && file_read(&e, sizeof e); i++)
                if ((p = tracks_find(&e.key)) >= 0)
                    restore((uint32_t)p, e.count, e.last);
            dirty = h.stamp != db_stamp();      /* a new database: write it for this one */
        } else if (h.version == 1 && h.entry_size == sizeof old && h.stamp == db_stamp()) {
            for (i = 0; i < h.count && file_read(old, sizeof old); i++) {
                struct track_key k;
                tracks_key(old[0], &k);
                if (old[0] < tracks_count() && k.id == old[1])
                    restore(old[0], old[2], old[3]);
            }
            dirty = 1;                          /* written again as version 2 */
        }
    }
    file_close();
}

/* Up Next: the hold menu's "Add to Queue" (holdmenu.c) puts songs in a
 * queue of their own, a hidden playlist, and they play next. On-The-Go is
 * Apple's again; holding Select on it in Playlists still clears it.
 *
 * The queue is a temporary playlist made the way Apple makes the copy of a
 * list it plays (0xac2ec: flag 0x40, never shown in Playlists). Stock's add
 * (0xc0b30) appends to the playlist at lib+0x48, On-The-Go, so for "Add to
 * Queue" that word holds the queue while the add runs (queue_begin_add,
 * queue_end_add), and queue_add_hook tells us where the new songs start:
 *
 * - Nothing playing: the added song starts at once, from the queue.
 * - Something else playing: the queue is armed. Apple asks 0xb7b00 for the
 *   item after the current one (to preload it, at the end of a song and on
 *   Next), and while armed queue_next() answers with the first song added.
 *   Once that plays, the player's list is the queue and Apple carries on
 *   through it by itself. When the queue runs out, playback goes back to the
 *   list it left, with the song after the one the queue cut in after.
 * - Already playing from the queue: the songs just join its end.
 *
 * Played songs stay in the list but behind q.next; once nothing in it is
 * playing or waiting, the next add empties it first. Starting another list
 * would delete the list Now Playing played from (0x5e8cc, lib+0x44), so
 * queue_keep spares the queue, and while the queue plays after cutting in,
 * lib+0x44 names it (queue_next), as Now Playing needs. hooks.S has the glue; docs/re-notes.md,
 * "On-The-Go and the play queue", the objects.
 *
 * Up Next (holdmenu.c, browse.c) shows the songs still waiting: after the
 * one playing, while the queue plays, or from q.next on while it's armed.
 * 2.3 can't take one song out of a playlist (On-The-Go only clears), so a
 * song removed there stays in the list, marked in q.removed: Up Next leaves
 * it out and queue_next skips it, as it skips nothing else. */

#include <stdint.h>
#include "queue.h"
#include "playlist.h"

/* The library object (Apple's code reaches it the same way, 0x6a15c): the
 * menu object at 0x43580c, +0x1c. The library's word 0 is the root object,
 * whose +4 is the player. */
#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define LIB_SOURCE      (0x44 / 4)      /* the list Now Playing plays from */
#define LIB_OTG         (0x48 / 4)
#define LIB_PLAYED_CB   (0x3c / 4)
#define PLAYER_LIST     (0x2a4 / 4)
#define PLAYER_ITEM     (0x2a8 / 4)
#define ITEM_KEY        (0x10 / 4)

#define TCMD_INT(n)     (((n) << 1) | 1)

/* A playlist's items: [[list+0x24]+0x2c] is the count, and 0x78d60(list,
 * 1, 0, i) item i in playlist order (as 0xb6c38 starts a list at a row). */
#define list_item   ((uint32_t (*)(uint32_t list, uint32_t kind, uint32_t rev, uint32_t i))0x78d60)
/* 0xb6c38's steps to play item from its list: load it, mark the list as
 * the one playing (shuffle state, 0xda9a4; 0xce9b0), then start it. */
#define player_load     ((uint32_t (*)(uint32_t player, uint32_t item))0xb8eb4)
#define list_playing    ((void (*)(uint32_t list, uint32_t shuffle))0xda9a4)
#define list_touch      ((void (*)(uint32_t list))0xce9b0)
#define player_start    ((uint32_t (*)(uint32_t player, uint32_t item, uint32_t flags))0xb8548)
/* Clear Playlist's Confirm: the menu object's native method next to "add to
 * On-The-Go" (0xc0ce8). Stops On-The-Go if it's playing, empties it
 * (0x465b0), marks it to be saved and refreshes the menus. */
#define ui_clear_otg    ((void (*)(uint32_t ui))0x465fc)
/* A new temporary playlist into *list (0 means made). */
#define new_temp_list   ((uint32_t (*)(uint32_t lib, uint32_t *list))0xac2ec)

#define QUEUE_MAX       1000            /* On-The-Go's limit; later songs can't be removed */

static struct {
    uint32_t list;      /* the queue, once made */
    uint32_t otg;       /* On-The-Go, while the queue stands in for it */
    uint8_t otg_dirty;  /* ... and its to-be-saved flag from before ([lib]+0xb42) */
    uint32_t armed;
    uint32_t next;      /* the queue's index of the first song waiting */
    uint32_t resume;    /* playing the queue: go back to ret_list after it */
    uint32_t ret_list;
    uint32_t ret_key;   /* the item the queue cut in after */
    uint32_t jump;      /* Up Next's pick: queue_next answers with song jump - 1 */
    int any_removed;
    uint8_t removed[QUEUE_MAX / 8];     /* by the queue's index: taken out in Up Next */
} q;

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static uint32_t list_count(uint32_t list)
{
    return word(word(list, 0x24 / 4), 0x2c / 4);
}

static void play_from(uint32_t lib, uint32_t list, uint32_t i)
{
    uint32_t player = word(word(lib, 0), 1);
    uint32_t item = list_item(list, 1, 0, i);
    void (*played)(uint32_t, uint32_t) = (void (*)(uint32_t, uint32_t))word(lib, LIB_PLAYED_CB);

    if (!item)
        return;
    ((volatile uint32_t *)lib)[LIB_SOURCE] = list;
    if (player_load(player, item))
        return;
    list_playing(list, *(const volatile uint8_t *)(word(lib, 0) + 0x20));
    list_touch(list);
    if (played)
        played(0, 0);
    player_start(player, item, 1);
}

static uint32_t library(void)
{
    uint32_t ui = UI_OBJECT;

    return ui ? word(ui, 0x1c / 4) : 0;
}

static int queue_playing(uint32_t lib)
{
    uint32_t cur = word(word(word(lib, 0), 1), PLAYER_ITEM);

    return cur && word(cur, 0) == q.list;
}

static int is_removed(uint32_t i)
{
    return i < QUEUE_MAX && (q.removed[i / 8] & (1u << (i % 8)));
}

static void forget_removed(void)
{
    unsigned i;

    for (i = 0; i < sizeof q.removed; i++)
        q.removed[i] = 0;
    q.any_removed = 0;
}

/* The queue's index of item (by its key, +0x10, which 0xb7b00 finds items
 * by through 0x6ff40), or -1. */
static int index_of(uint32_t item)
{
    uint32_t n = list_count(q.list), i, it;

    for (i = 0; i < n; i++)
        if ((it = list_item(q.list, 1, 0, i)) && word(it, ITEM_KEY) == word(item, ITEM_KEY))
            return (int)i;
    return -1;
}

/* "Add to Queue" is about to run stock's add: the queue stands in for
 * On-The-Go until queue_end_add. */
void queue_begin_add(void)
{
    uint32_t lib = library();

    if (!lib || q.otg)
        return;
    if (!q.list && new_temp_list(lib, &q.list) != 0)
        q.list = 0;
    if (!q.list)
        return;                 /* then it goes to On-The-Go, as before */
    if (!q.armed && !queue_playing(lib) && list_count(q.list)) {
        list_empty(q.list);     /* everything in it has played */
        forget_removed();
    }
    q.otg = word(lib, LIB_OTG);
    q.otg_dirty = ((volatile uint8_t *)word(lib, 0))[0xb42];
    ((volatile uint32_t *)lib)[LIB_OTG] = q.list;
}

void queue_end_add(void)
{
    uint32_t lib = library();

    if (lib && q.otg) {
        ((volatile uint32_t *)lib)[LIB_OTG] = q.otg;
        ((volatile uint8_t *)word(lib, 0))[0xb42] = q.otg_dirty;   /* On-The-Go's to-be-saved flag, as before the add (playlist.c) */
    }
    q.otg = 0;
}

/* 0xc0b30 just added songs to library `lib`'s lib+0x48; `first` is the index
 * of the first one (the count before). Only the queue's adds matter here. */
void queue_added(uint32_t lib, uint32_t first)
{
    uint32_t player = word(word(lib, 0), 1);
    uint32_t cur = word(player, PLAYER_ITEM);

    if (!q.otg || word(lib, LIB_OTG) != q.list || first >= list_count(q.list))
        return;
    if (!cur) {
        q.armed = 0;
        play_from(lib, q.list, first);
        return;
    }
    if (word(cur, 0) == q.list)
        return;
    /* A queue already waiting keeps its place, unless it was emptied under it. */
    if (!q.armed || q.next >= first)
        q.next = first;
    q.armed = 1;
}

/* 0x5e8cc(lib) is about to delete the list Now Playing played from
 * (lib+0x44), as something else starts. Not if that's the queue: then it's
 * the list the queue cut in after, if any (see queue_next). */
void queue_keep(uint32_t lib)
{
    if (q.list && word(lib, LIB_SOURCE) == q.list) {
        ((volatile uint32_t *)lib)[LIB_SOURCE] = q.resume ? q.ret_list : 0;
        q.resume = 0;
    }
}

/* Now Playing plays from lib+0x44 (0x5e8cc deletes it, as above), and when
 * opened on a song from another list it goes back instead (fn 185, which
 * then lands on the main menu: Select on the playing song in Songs). So it
 * follows the player into the queue and back out. */
static void set_source(uint32_t from, uint32_t to)
{
    uint32_t lib = library();

    if (lib && word(lib, LIB_SOURCE) == from)
        ((volatile uint32_t *)lib)[LIB_SOURCE] = to;
}

/* 0xb7b00(player, list, key, flags): the item to play after the one with
 * `key` in `list`. Returns On-The-Go's queued item, the way back after it,
 * QUEUE_NO_NEXT for none (hooks.S returns 0 then), or 0 for Apple's own
 * answer. Every caller asks about the player's current item. */
uint32_t queue_next(uint32_t player, uint32_t list, uint32_t key, uint32_t flags)
{
    uint32_t cur, item, n;
    int i;

    if (q.jump) {               /* Up Next's pick (queue_play) */
        item = list_item(q.list, 1, 0, q.jump - 1);
        q.jump = 0;
        q.armed = 0;
        if (list != q.list) {
            q.resume = 1;
            q.ret_list = list;
            q.ret_key = key;
        }
        return item ? item : QUEUE_NO_NEXT;
    }
    if (q.list && list == q.list) {
        q.armed = 0;            /* the queue is playing: Apple goes on from here */
        if (!q.resume && !q.any_removed)
            return 0;
        if (q.resume)
            set_source(q.ret_list, q.list);
        /* Apple's answer, past the songs taken out in Up Next (0xb7b00 finds
         * any item by its key; the count bounds Repeat's wrapping round) */
        item = queue_next_orig(player, list, key, flags);
        for (n = list_count(q.list); item && n; n--) {
            i = index_of(item);
            if (i < 0 || !is_removed((uint32_t)i))
                break;
            item = queue_next_orig(player, list, word(item, ITEM_KEY), flags);
        }
        if (!n)
            item = 0;
        if (!item && q.resume)
            item = queue_next_orig(player, q.ret_list, q.ret_key, flags);
        return item ? item : QUEUE_NO_NEXT;
    }
    if (q.resume && list == q.ret_list)
        set_source(q.list, q.ret_list);
    q.resume = 0;               /* back in another list */
    if (!q.armed)
        return 0;
    cur = word(player, PLAYER_ITEM);
    if (!cur || list != word(player, PLAYER_LIST) || key != word(cur, ITEM_KEY))
        return 0;
    if (q.next >= list_count(q.list)) {
        q.armed = 0;            /* cleared since */
        return 0;
    }
    q.resume = 1;
    q.ret_list = list;
    q.ret_key = key;
    return list_item(q.list, 1, 0, q.next);
}

static void queue_clear(void)
{
    uint32_t ui = UI_OBJECT;

    if (!ui || !word(word(ui, 0x1c / 4), LIB_OTG))
        return;
    ui_clear_otg(ui);
}

/* vm_hook, for the bytecode pcs in queue.h; returns the pc to go on with.
 * At the Playlists hold guard, local0 ([[vm+0x10]+0x24], what push_local
 * reads) is the highlighted row, and row 0 is On-The-Go. */
uint32_t queue_vm(uint32_t pc, uint32_t vm)
{
    if (pc == QUEUE_FN_HOLD && word(word(word(vm, 0x10 / 4), 0x24 / 4), 0) == TCMD_INT(0))
        queue_clear();
    return pc;
}

/* Play Album Next (holdmenu.c): songs of list src (an album's, by index, in order)
 * into the queue, the way stock's add appends one row's song (0x4fb50:
 * 0x506ec(item, list, 0, 0), between 0xa5054 and 0xef76c on the database,
 * [lib+0x868]); each then plays as an "Add to Queue" of it would. One at a
 * time, as that many adds would: with all of them in before playback started
 * (0xda9a4), the playing list's index array was left with a garbage entry,
 * which 0xe1220 then wrote through (into Apple's image, in emupod). */
#define append_item ((void (*)(uint32_t item, uint32_t list, uint32_t a, uint32_t b))0x506ec)
#define list_key    ((uint32_t (*)(uint32_t lib))0x849a4)
#define db_begin    ((void (*)(uint32_t db))0xa5054)
#define db_end      ((void (*)(uint32_t db))0xef76c)

void queue_add_items(uint32_t src, const uint32_t *idx, unsigned n)
{
    uint32_t lib = library(), db, first;
    unsigned i;

    queue_begin_add();
    if (!lib || !q.otg || !n) {
        queue_end_add();
        return;
    }
    db = word(lib, 0x868 / 4);
    for (i = 0; i < n; i++) {
        first = list_count(q.list);
        db_begin(db);
        append_item(list_item(src, list_key(lib), 0, idx[i]), q.list, 0, 0);
        db_end(db);
        queue_added(lib, first);
    }
    queue_end_add();
}

/* Up Next (holdmenu.c): the queue's index of the first song waiting, or the
 * count when none is: the one after the song playing if that's the queue's,
 * else q.next while armed. */
static uint32_t first_waiting(uint32_t lib)
{
    uint32_t cur = word(word(word(lib, 0), 1), PLAYER_ITEM), n = list_count(q.list);
    int i;

    if (cur && word(cur, 0) == q.list)
        return (i = index_of(cur)) < 0 ? n : (uint32_t)i + 1;
    return q.armed ? q.next : n;
}

uint32_t queue_list(void)
{
    return q.list;
}

/* The songs waiting, in the order they'll play, as the queue's indices
 * into idx (max of them); returns how many. */
unsigned queue_waiting(uint32_t *idx, unsigned max)
{
    uint32_t lib = library(), n, i;
    unsigned k = 0;

    if (!lib || !q.list)
        return 0;
    n = list_count(q.list);
    for (i = first_waiting(lib); i < n && k < max; i++)
        if (!is_removed(i))
            idx[k++] = i;
    return k;
}

/* Select on Up Next's row for the queue's song i: it plays now, and the queue
 * goes on from there (the songs before it count as played). Something is
 * playing (the queue's or another list's song, or nothing would wait), so
 * it's Apple's Next (0xb81d4(player, 0), as the button's 0xaca28), which
 * asks queue_next, which answers with song i: from another list, the queue
 * cuts in there as it does at a song's end, and goes back after. Starting
 * it with play_from's steps instead, over another list playing, left a
 * stray write in Apple's image (0xc4, in emupod). */
#define player_next     ((void (*)(uint32_t player, uint32_t flags))0xb81d4)

void queue_play(uint32_t i)
{
    uint32_t lib = library(), player;

    if (!lib || !q.list || i >= list_count(q.list))
        return;
    player = word(word(lib, 0), 1);
    if (!word(player, PLAYER_ITEM)) {
        q.armed = 0;
        play_from(lib, q.list, i);
        return;
    }
    q.jump = i + 1;
    player_next(player, 0);
    q.jump = 0;
}

/* Remove from Queue: the queue's song i won't play. */
void queue_remove(uint32_t i)
{
    uint32_t n;

    if (!q.list || i >= QUEUE_MAX)
        return;
    q.removed[i / 8] |= 1u << (i % 8);
    q.any_removed = 1;
    if (q.armed && i == q.next) {
        for (n = list_count(q.list); q.next < n && is_removed(q.next); q.next++)
            ;
        if (q.next >= n)
            q.armed = 0;        /* nothing left to cut in with */
    }
}

/* Clear Queue: none of the songs waiting will play (the one playing ends as
 * it would). */
void queue_clear_waiting(void)
{
    uint32_t lib = library(), n, i;

    if (!lib || !q.list)
        return;
    n = list_count(q.list);
    for (i = first_waiting(lib); i < n && i < QUEUE_MAX; i++)
        q.removed[i / 8] |= 1u << (i % 8);
    q.any_removed = 1;
    q.armed = 0;
}

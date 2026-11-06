/* The Music lists' browse state, so the hold menu can leave a list and come
 * back to it as it was (docs/re-notes.md, "Browsing the Music lists").
 *
 * The lists are one native query on the library: the playlist browsed
 * (lib+0x40), a filter per level (genre lib+0x58, artist +0x5c, composer
 * +0x60, album +0x64; -1 is "All") with each filter's name for the title
 * (+0x68, +0x268, +0x468, +0x668), and the rows of each level as arrays of
 * string-pool keys (genres lib+0x878, artists +0x880, composers +0x888,
 * albums +0x890; count in the next word) or playlist items (songs, +0x898).
 * A list's Select sets the filter (0x08eb.e3 artist, .e5 album) and builds the
 * next level (.f7 albums, .f9 songs); Menu (fn 14) only reruns the previous
 * screen's opener, which builds nothing, so that list shows whatever its
 * array holds then. A screen's View (and its list widget) is one object, so
 * an album's songs and Songs are the same list.
 *
 * Going somewhere else and back therefore needs the state put back:
 * browse_save notes it, and browse_restore points the query at the same
 * playlist (0xd6760, which also frees every array and clears the filters),
 * copies the filters and names back, builds again every array there was
 * (they're built through 0x58440, browse_hook's predicate, so a song hidden
 * since drops out), has each list's builder refresh its widget, and puts the
 * held list's cursor back on its row. */

#include <stdint.h>
#include "browse.h"
#include "hide.h"

#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define LIB_BROWSED     (0x40 / 4)
#define LIB_STATE       0x58            /* filters and their names: to 0x868 */
#define LIB_STATE_END   0x868
#define LIB_ARRAYS      (0x878 / 4)     /* genres, artists, composers, albums, songs: pointer, count */
#define LIB_ARTISTS     (0x880 / 4)
#define LIB_ALBUMS      (0x890 / 4)
#define LIB_LEVEL       (0x86c / 4)
#define LIB_LISTS       (0x870 / 4)
#define LIB_N_LISTS     (0x874 / 4)
#define UI_CACHE        (0x12f8 / 4)    /* the builders' last counts: songs, albums, composers, artists, genres */
#define UI_ROWS         (0x1618 / 4)    /* rows picked: genre, artist, composer, album */
#define UI_MODE         (0x168c / 4)
#define TRACK_ARTIST    (0x28 / 4)      /* string-pool keys (artist.c: the album artist) */
#define TRACK_ALBUM     (0x30 / 4)
#define TRACK_NUMBER    0x7c            /* halfword (mhit+0x2c); +0x7e: of how many */
#define ITEM_TRACK      (0x20 / 4)
#define PLAYER_ITEM     (0x2a8 / 4)

/* 0xd6760(lib, i): browse playlist i of lib+0x870 (0 the library), as
 * 0x08eb.dd (0xd6138) does with 0; frees the arrays, clears the filters. */
#define browse_list     ((uint32_t (*)(uint32_t lib, uint32_t i))0xd6760)
#define browse_reset    ((void (*)(uint32_t ui))0xd6138)
#define set_level       ((void (*)(uint32_t lib, uint32_t level))0xdce44)
#define set_artist      ((uint32_t (*)(uint32_t lib, int32_t i))0xd539c)
/* Each level's array, built from the query: returns its count. */
static const uint32_t build_array[5] = { 0x7c3a0, 0x7c1a8, 0x7c368, 0x7c178, 0x7c460 };
/* The 0x08eb methods that build a level and refresh its list: .f8, .f5, .f6,
 * .f7, .f9 (ui); each does nothing while its count is the cached one. */
static const uint32_t build_list[5] = { 0xf0fe8, 0xefdec, 0xf0670, 0xefd9c, 0xf2518 };
static const uint8_t cache_of[5] = { 4, 3, 2, 1, 0 };   /* UI_CACHE + n */
#define list_item       ((uint32_t (*)(uint32_t list, uint32_t kind, uint32_t rev, uint32_t i))0x78d60)
/* The order stock's add takes a list's items in (0xc0b30, 0x4fb50); 0x506ec appends only
 * those (order 1 gave items that left garbage in the queue's item array). */
#define list_key        ((uint32_t (*)(uint32_t lib))0x849a4)
extern uint32_t letter_widget;  /* letters.c: the list the wheel last moved */
static uint32_t held_widget, good_widget;   /* good: the last one that was the held list's */

/* A row is held: the list the wheel last moved, before the popup moves its own. */
void browse_held(void)
{
    held_widget = letter_widget;
}

static struct {
    int saved;
    int kind;
    uint32_t row, widget;
    uint32_t browsed, level, arrays;
    uint32_t lib_state[(LIB_STATE_END - LIB_STATE) / 4];
    uint32_t cache[5], rows[4], mode;
} bs;

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static void put(uint32_t addr, unsigned i, uint32_t v)
{
    ((volatile uint32_t *)addr)[i] = v;
}

static uint32_t call1(uint32_t fn, uint32_t a)
{
    return ((uint32_t (*)(uint32_t))fn)(a);
}

static uint32_t library(void)
{
    uint32_t ui = UI_OBJECT;

    return ui ? word(ui, 0x1c / 4) : 0;
}

/* The row of a list widget's cursor (+0x90; its vtable+0x11c, as 0x816a8). */
static uint32_t cursor_row(uint32_t w)
{
    uint32_t c = word(w, 0x90 / 4), vt = word(c, 0);

    return ((uint32_t (*)(uint32_t))(vt + word(vt, 0x11c / 4)))(c);
}

/* The held list (kind, untagged row) is about to be left. */
void browse_save(int kind, uint32_t row)
{
    uint32_t ui = UI_OBJECT, lib = library(), w = held_widget, i;

    bs.saved = 0;
    if (!lib)
        return;
    bs.kind = kind;
    bs.row = row;
    /* The held list's widget, if the wheel moved it last: its rows are its
     * level's array (Albums and Artists have "All" too). (Its cursor can't
     * tell: with the popup up it isn't on the row.) */
    i = kind == LIST_SONGS ? word(lib, 0x89c / 4) : kind == LIST_ALBUMS ? word(lib, 0x894 / 4) + 1
      : kind == LIST_ARTISTS ? word(lib, 0x884 / 4) + 1 : 0;
    if (!(w && word(w, 0x90 / 4) && i && word(w, 0x9c / 4) == i))
        w = good_widget;       /* the wheel last moved the popup: the list from before */
    bs.widget = w && word(w, 0x90 / 4) && i && word(w, 0x9c / 4) == i ? w : 0;
    if (bs.widget)
        good_widget = bs.widget;
    bs.browsed = word(lib, LIB_BROWSED);
    bs.level = word(lib, LIB_LEVEL);
    bs.arrays = 0;
    for (i = 0; i < 5; i++)
        if (word(lib, LIB_ARRAYS + 2 * i))
            bs.arrays |= 1u << i;
    for (i = 0; i < sizeof bs.lib_state / 4; i++)
        bs.lib_state[i] = word(lib, LIB_STATE / 4 + i);
    for (i = 0; i < 5; i++)
        bs.cache[i] = word(ui, UI_CACHE + i);
    for (i = 0; i < 4; i++)
        bs.rows[i] = word(ui, UI_ROWS + i);
    bs.mode = word(ui, UI_MODE);
    bs.saved = 1;
}

/* The list widget's cursor to row, the way the wheel moves it (0x90fe4:
 * vtable+0x15c(n) down, +0x158(-n) up). */
static void move_to(uint32_t w, uint32_t row)
{
    uint32_t rows = word(w, 0x9c / 4), vt;
    int32_t d;

    if (!word(w, 0x90 / 4) || !rows)
        return;
    if (row >= rows)
        row = rows - 1;
    d = (int32_t)row - (int32_t)cursor_row(w);
    vt = word(w, 0);
    if (d > 0)
        ((void (*)(uint32_t, int32_t))(vt + word(vt, 0x15c / 4)))(w, d);
    else if (d < 0)
        ((void (*)(uint32_t, int32_t))(vt + word(vt, 0x158 / 4)))(w, d);
}

void browse_drop(void)
{
    bs.saved = 0;
}

void browse_restore(void)
{
    uint32_t ui = UI_OBJECT, lib = library(), i;

    if (!bs.saved || !lib)
        return;
    bs.saved = 0;
    /* A save that no longer fits the library (a playlist it browsed is gone,
     * as after a sync) is dropped rather than put back. */
    if (bs.browsed >= word(lib, LIB_N_LISTS))
        return;
    browse_list(lib, bs.browsed);
    for (i = 0; i < sizeof bs.lib_state / 4; i++)
        put(lib, LIB_STATE / 4 + i, bs.lib_state[i]);
    set_level(lib, bs.level);
    for (i = 0; i < 5; i++)
        if (bs.arrays & (1u << i))
            call1(build_array[i], lib);
    for (i = 0; i < 5; i++)
        put(ui, UI_CACHE + i, bs.cache[i]);
    for (i = 0; i < 4; i++)
        put(ui, UI_ROWS + i, bs.rows[i]);
    put(ui, UI_MODE, bs.mode);
    for (i = 0; i < 5; i++)
        if (bs.arrays & (1u << i)) {
            put(ui, UI_CACHE + cache_of[i], 0xffffffffu);
            call1(build_list[i], ui);
        }
    if (bs.widget && bs.kind != LIST_OTHER)
        move_to(bs.widget, bs.row);
}

static uint32_t find_key(uint32_t array, uint32_t n, uint32_t key)
{
    uint32_t i;

    for (i = 0; array && i < n; i++)
        if (word(array, i) == key)
            return i + 1;               /* row 0 is "All" */
    return 0;
}

/* Go to Album: the query reset (0x08eb.dd) with every artist, so the row of
 * track's album in Albums; 0 if it isn't there (hidden). */
uint32_t browse_album_row(uint32_t track)
{
    uint32_t ui = UI_OBJECT, lib = library(), n;

    if (!lib || !track)
        return 0;
    browse_reset(ui);
    set_artist(lib, -1);
    n = call1(build_array[3], lib);
    return find_key(word(lib, LIB_ALBUMS), n, word(track, TRACK_ALBUM));
}

/* Go to Artist: the row of track's artist in Artists. */
uint32_t browse_artist_row(uint32_t track)
{
    uint32_t ui = UI_OBJECT, lib = library(), n;

    if (!lib || !track)
        return 0;
    browse_reset(ui);
    n = call1(build_array[1], lib);
    return find_key(word(lib, LIB_ARTISTS), n, word(track, TRACK_ARTIST));
}

static uint32_t number(uint32_t track)
{
    return *(const volatile uint16_t *)(track + TRACK_NUMBER);
}

/* Play Album Next: the library's songs of track's album, by track number,
 * from track on (after: the ones after it), as indices into the library
 * (*list) in the order stock's add takes them (list_key); returns how many.
 * An item stays good only between 0xa5054 and 0xef76c on the database (as
 * 0x4fb50 brackets its loop), so queue_add_items fetches them again. */
#define db_begin        ((void (*)(uint32_t db))0xa5054)
#define db_end          ((void (*)(uint32_t db))0xef76c)
unsigned browse_album_items(uint32_t track, int after, uint32_t *list, uint32_t *idx, uint32_t *nums, unsigned max)
{
    uint32_t lib = library(), master, n, i, t, from, key, db, num;
    unsigned k = 0, j;

    if (!lib || !track || !(master = word(word(lib, LIB_LISTS), 0)))
        return 0;
    *list = master;
    key = list_key(lib);
    from = number(track);
    n = word(word(master, 0x24 / 4), 0x2c / 4);
    db = word(lib, 0x868 / 4);
    db_begin(db);
    for (i = 0; i < n && k < max; i++) {
        uint32_t item = list_item(master, key, 0, i);
        if (!item || !(t = word(item, ITEM_TRACK)) || word(t, TRACK_ALBUM) != word(track, TRACK_ALBUM))
            continue;
        num = number(t);
        if (t == track ? after : num < from || (num == from && after))
            continue;
        for (j = k++; j && nums[j - 1] > num; j--) {
            idx[j] = idx[j - 1];
            nums[j] = nums[j - 1];
        }
        idx[j] = i;
        nums[j] = num;
    }
    db_end(db);
    return k;
}

/* The track playing, or 0. */
uint32_t browse_playing(void)
{
    uint32_t lib = library(), item;

    item = lib ? word(word(word(lib, 0), 1), PLAYER_ITEM) : 0;
    return item ? word(item, ITEM_TRACK) : 0;
}

/* Up Next (holdmenu.c): the songs list shows items idx[] of `list` (in that
 * order). 0x7c460, the songs array's builder, keeps an array that's there
 * (lib+0x898, count +0x89c) and only builds one from the browsed playlist
 * when there's none, so ours goes in its place, allocated as 0x7c460 does
 * (0xaa10c), and 0xd6760 / 0x9d7c4 free it (0xa9f70) when the browse state
 * goes back. `fresh`: before the songs screen opens (fn 208 builds and shows
 * it), from Songs' own reset (0x08eb.de, 0xd6478: caches, the row picked -1,
 * so .ee doesn't take it for On-The-Go) at the songs' level; otherwise the
 * list on screen is redone in place (.f9, its cached count invalidated),
 * which puts its cursor back on row 0, so it goes to `row` again (clamped),
 * on the list held (browse_held), if that's the one with these rows. */
#define mem_alloc       ((uint32_t (*)(uint32_t size))0xaa10c)
#define mem_free        ((void (*)(uint32_t p))0xa9f70)
#define songs_reset     ((void (*)(uint32_t ui))0xd6478)
#define LIB_SONGS       (0x898 / 4)

void browse_items(uint32_t list, const uint32_t *idx, unsigned n, int fresh, uint32_t row)
{
    uint32_t ui = UI_OBJECT, lib = library(), arr, db, w = held_widget;
    unsigned k;

    if (!lib || !list || !n)
        return;
    if (fresh) {
        songs_reset(ui);
        set_level(lib, 4);
    }
    if (!(arr = mem_alloc(4 * n)))
        return;
    db = word(lib, 0x868 / 4);
    db_begin(db);
    for (k = 0; k < n; k++)
        put(arr, k, list_item(list, 1, 0, idx[k]));
    db_end(db);
    if (word(lib, LIB_SONGS))
        mem_free(word(lib, LIB_SONGS));
    put(lib, LIB_SONGS, arr);
    put(lib, LIB_SONGS + 1, n);
    put(ui, UI_CACHE, 0xffffffffu);
    if (fresh)
        return;
    call1(build_list[4], ui);
    if (w && word(w, 0x90 / 4) && word(w, 0x9c / 4) == n)
        move_to(w, row);
}

/* The hold menu's Show: whether every song of the held row (kind, untagged
 * row) is hidden, which with Settings > Show Hidden on is listed. A song's
 * row is its item in the songs array; an album's or an artist's (row 0 is
 * All: no) the library's songs with that key, an album's also with the
 * artist picked (+0x5c, an index into the artists array, if one is). The
 * genre picked isn't looked at, so an album of that name and artist in
 * another genre counts too. */
#define LIB_ARTIST      (0x5c / 4)
int browse_row_hidden(int kind, uint32_t row)
{
    uint32_t lib = library(), master, n, i, t, key, by = 0, artist, db;
    int any = 0;

    if (!lib)
        return 0;
    if (kind == LIST_SONGS) {
        if (row >= word(lib, LIB_SONGS + 1) || !word(lib, LIB_SONGS))
            return 0;
        t = word(word(word(lib, LIB_SONGS), row), ITEM_TRACK);
        return hide_track(t);
    }
    if ((kind != LIST_ALBUMS && kind != LIST_ARTISTS) || !row)
        return 0;
    i = kind == LIST_ALBUMS ? LIB_ALBUMS : LIB_ARTISTS;
    if (row > word(lib, i + 1) || !word(lib, i))
        return 0;
    key = word(word(lib, i), row - 1);
    artist = word(lib, LIB_ARTIST);
    if (kind == LIST_ALBUMS && artist != 0xffffffffu && word(lib, LIB_ARTISTS)
        && artist < word(lib, LIB_ARTISTS + 1))
        by = word(word(lib, LIB_ARTISTS), artist);
    if (!(master = word(word(lib, LIB_LISTS), 0)))
        return 0;
    n = word(word(master, 0x24 / 4), 0x2c / 4);
    db = word(lib, 0x868 / 4);
    db_begin(db);
    for (i = 0; i < n; i++) {
        uint32_t item = list_item(master, 1, 0, i);
        if (!item || !(t = word(item, ITEM_TRACK)))
            continue;
        if (kind == LIST_ALBUMS ? word(t, TRACK_ALBUM) != key || (by && word(t, TRACK_ARTIST) != by)
                                : word(t, TRACK_ARTIST) != key)
            continue;
        if (!hide_track(t)) {
            any = 0;
            break;
        }
        any = 1;
    }
    db_end(db);
    return any;
}

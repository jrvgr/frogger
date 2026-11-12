/* The Hidden row: Music › Artists, Albums, Genres and Composers leave out
 * the items whose songs are all hidden (hide.c). While some are, and
 * Settings › Show Hidden is off, the list starts with a row "Hidden (N)",
 * above Apple's "All". Select on it shows just those N items, in the same
 * list (no "All" row, title "Hidden"), with everything below them listed in
 * full: Select drills in as usual, and the hold menu's Show un-hides. Menu
 * there goes back to the whole list, on the Hidden row (or off it, if
 * nothing is hidden any more).
 *
 * Apple's lists stay as they are: a list's rows are its level's array
 * (lib+0x878.., docs/re-notes.md, "Browsing the Music lists"), with "All"
 * as row 0, and its widget only knows a row count and asks the UI object's
 * getter for each row's text. So the widget's rows are shifted against
 * Apple's (`shift`: 1 for the Hidden row on top, -1 for the Hidden list,
 * whose "All" is left out), at the three places they meet:
 *
 * - the row count: each list's builder (0x08eb.f8/.f5/.f6/.f7) takes its
 *   array's count + 1 for "All" (count_hook at that add), then sends it to
 *   the widget unless it's the count it cached;
 * - the rows' text: 0x7998c(ui, 'Str ', property, row, &text) (label_hook);
 * - the row read, 0x08df.a9() (0x816a8, a9_hook): every list's Select, Play
 *   and hold handler reads its row through it. The Hidden row reads as -1,
 *   no row: Play and the hold do nothing there, and Select is caught just
 *   after its row read (hiddenrow_vm).
 *
 * Which list a widget is: each Music list has a widget of its own (its
 * screen's), whose +0x1c names the count property it shows (0x3305 Genres,
 * 0x3304 Artists, 0x3303 Composers, 0x3302 Albums). The Albums widget also
 * shows an artist's or composer's albums; the shift is set at each build, so
 * it's 0 then.
 *
 * The Hidden list is the level's array built with nothing hidden
 * (hide_state.reveal, which also lists everything below it), then cut down
 * to the hidden items. The count: an item is hidden when it is some hidden
 * song's (artist, album, genre or composer string-pool key, track +0x28,
 * +0x30, +0x38, +0x34) and no shown song's. Worked out from tracks.c's
 * records, once per change (hide_gen). Only the lists at the top count: no
 * genre, artist or composer picked above them. */

#include <stdint.h>
#include "hiddenrow.h"
#include "hide.h"
#include "tracks.h"
#include "browse.h"
#include "holdmenu.h"
#include "debug.h"

#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define obj_08de        (*(volatile uint32_t *)0x41e938)    /* the bytecode's 0x08de */
#define set_text        ((void (*)(uint32_t obj, uint32_t element, uint32_t str, uint32_t flags))0x1fabc)
#define find_child      ((uint32_t (*)(uint32_t view, uint32_t id))0x66d94)
#define TITLE           0x25e7
#define LIST_ELEMENT    0x1700          /* a screen's list widget (0x816a8 finds it the same way) */
#define W_PROP          (0x1c / 4)      /* low half: the count property the widget shows */
#define FOURCC_STR      0x53747220u
#define TCMD_INT(n)     (((n) << 1) | 1)
#define LIB_BROWSED     (0x40 / 4)
#define LIB_FILTERS     (0x58 / 4)      /* genre, artist, composer, album: -1 is All */

static const uint16_t count_prop[HR_LISTS] = { 0x3305, 0x3304, 0x3303, 0x3302 };
static const uint16_t label_prop[HR_LISTS] = { 0x3365, 0x3364, 0x3363, 0x3362 };
static const uint16_t array_of[HR_LISTS] = { 0x878, 0x880, 0x888, 0x890 };
static const uint8_t key_of[HR_LISTS] = { 0x38, 0x28, 0x34, 0x30 };
/* The filters that narrow a list (bits: genre, artist, composer, album). */
static const uint8_t above[HR_LISTS] = { 0, 1, 1, 7 };
/* Their titles, as their openers set them (fn 53's pool constants, as
 * 0x1fabc gets them: Music's Genres, Artists, Composers, Albums). */
static const uint32_t list_title[HR_LISTS] = { 0xffffffe7u, 0xffffffe8u, 0xffffffeau, 0xffffffe9u };
static const uint32_t pick_pc[HR_LISTS] = { HR_PICK_GENRES, HR_PICK_ARTISTS, HR_PICK_COMPOSERS, HR_PICK_ALBUMS };

static struct {
    int8_t shift[HR_LISTS];
    int mode;                   /* the Hidden list is up: its list + 1 */
    int depth;                  /* screens opened over it */
    uint32_t gen;               /* the database it was opened on */
    uint32_t widget;            /* its widget */
    int picked;                 /* 0x816a8 just read the Hidden row of list + 1 */
} hr;

/* The hidden items: per list, the keys some hidden song has (hid) and some
 * shown song has (vis), for keys below KEYS (pool indices; any other key
 * counts as shown). */
#define KEYS 16384
static uint32_t hid[HR_LISTS][KEYS / 32], vis[HR_LISTS][KEYS / 32];
static struct { int valid; uint32_t tracks, hide; uint32_t n[HR_LISTS]; } cnt;

char hiddenrow_text[16];

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static void put(uint32_t addr, unsigned i, uint32_t v)
{
    ((volatile uint32_t *)addr)[i] = v;
}

static int is_hidden(unsigned l, uint32_t key)
{
    return key < KEYS && ((hid[l][key / 32] & ~vis[l][key / 32]) >> (key % 32) & 1);
}

static void count(void)
{
    uint32_t pos, t, k, i, n;
    unsigned l;

    if (cnt.valid && cnt.tracks == tracks_gen() && cnt.hide == hide_gen())
        return;
    cnt.valid = tracks_ready();
    cnt.tracks = tracks_gen();
    cnt.hide = hide_gen();
    for (l = 0; l < HR_LISTS; l++) {
        for (i = 0; i < KEYS / 32; i++)
            hid[l][i] = vis[l][i] = 0;
        cnt.n[l] = 0;
    }
    if (!cnt.valid || !hide_any())
        return;
    for (pos = 0; pos < tracks_count(); pos++) {
        if (!(t = tracks_record(pos)))
            continue;
        uint32_t (*set)[KEYS / 32] = hide_track(t) ? hid : vis;
        for (l = 0; l < HR_LISTS; l++)
            if ((k = word(t, key_of[l] / 4)) < KEYS)
                set[l][k / 32] |= 1u << (k % 32);
    }
    for (l = 0; l < HR_LISTS; l++)
        for (i = 0; i < KEYS / 32; i++)
            for (n = hid[l][i] & ~vis[l][i]; n; n &= n - 1)
                cnt.n[l]++;
    debug_note(DEBUG_TAG('h', 'r', 'c', 'n'), cnt.n[HR_ARTISTS] | cnt.n[HR_ALBUMS] << 16,
               cnt.n[HR_GENRES] | cnt.n[HR_COMPOSERS] << 16);
}

/* The Hidden list is gone for good (a new database, or its screen left
 * some way we didn't see). */
static void drop(void)
{
    hr.mode = 0;
    hide_state.reveal = 0;
}

/* count_hook, in list's builder: n is its array's count, the list's rows are
 * n + 1 for "All"; returns the widget's rows. */
uint32_t hiddenrow_count(uint32_t n, unsigned list, uint32_t ui)
{
    uint32_t lib = word(ui, 0x1c / 4), arr, i, j;
    unsigned f;
    int top;

    hr.shift[list] = 0;
    if (hr.mode && hr.gen != tracks_gen())
        drop();
    if (!lib || list >= HR_LISTS || hide_state.show_all)
        return n + 1;
    top = word(lib, LIB_BROWSED) == 0;
    for (f = 0; f < 4; f++)
        if ((above[list] >> f & 1) && word(lib, LIB_FILTERS + f) != 0xffffffffu)
            top = 0;
    if (!top)
        return n + 1;
    if (hr.mode && hr.mode != (int)list + 1)
        return n + 1;           /* everything listed, below another Hidden list */
    count();
    if (hr.mode) {
        arr = word(lib, array_of[list] / 4);
        for (i = j = 0; arr && i < n; i++)
            if (is_hidden(list, word(arr, i)))
                put(arr, j++, word(arr, i));
        put(lib, array_of[list] / 4 + 1, j);
        hr.shift[list] = -1;
        return j;
    }
    if (!cnt.n[list])
        return n + 1;
    hr.shift[list] = 1;
    return n + 2;
}

int hiddenrow_shift(unsigned list)
{
    return list < HR_LISTS ? hr.shift[list] : 0;
}

static int list_of_label(uint32_t prop)
{
    unsigned l;

    for (l = 0; l < HR_LISTS; l++)
        if (prop == label_prop[l])
            return (int)l;
    return -1;
}

static int any_shift(void)
{
    return hr.shift[0] | hr.shift[1] | hr.shift[2] | hr.shift[3];
}

static void make_text(unsigned list)
{
    static const char s[] = "Hidden (";
    char digits[10], *d = hiddenrow_text;
    uint32_t n = cnt.n[list];
    unsigned i = 0;
    const char *p;

    for (p = s; *p; )
        *d++ = *p++;
    do
        digits[i++] = (char)('0' + n % 10);
    while ((n /= 10) && i < sizeof digits);
    while (i && d < hiddenrow_text + sizeof hiddenrow_text - 2)
        *d++ = digits[--i];
    *d++ = ')';
    *d = 0;
}

/* label_hook: 0x7998c(ui, fourcc, prop, row, out) is asked for a row of a
 * list: 1 if that's the Hidden row (*out is its label), else row becomes
 * Apple's. */
int hiddenrow_label(uint32_t prop, uint32_t *row, const char **out)
{
    int l;

    if (!any_shift() || (l = list_of_label(prop)) < 0 || !hr.shift[l])
        return 0;
    if (hr.shift[l] > 0 && *row == 0) {
        make_text((unsigned)l);
        *out = hiddenrow_text;
        return 1;
    }
    *row -= (uint32_t)hr.shift[l];
    return 0;
}

static int list_of_widget(uint32_t w)
{
    unsigned l;

    for (l = 0; w && l < HR_LISTS; l++)
        if ((word(w, W_PROP) & 0xffff) == count_prop[l])
            return (int)l;
    return -1;
}

/* a9_hook: 0x816a8(obj) read row of the list on obj's screen ([obj+0x24]); Apple's row
 * instead, -1 for the Hidden row. */
int32_t hiddenrow_a9(int32_t row, uint32_t obj)
{
    uint32_t screen, w;
    int l;

    hr.picked = 0;
    if (row < 0 || !any_shift() || !(screen = word(obj, 0x24 / 4)))
        return row;
    w = find_child(screen, LIST_ELEMENT);
    if ((l = list_of_widget(w)) < 0 || !hr.shift[l])
        return row;
    row -= hr.shift[l];
    if (row < 0) {
        hr.picked = l + 1;
        hr.widget = w;
        return -1;
    }
    return row;
}

/* Before list is built again: its own filter and the ones below it back to
 * All. Menu back from a list leaves the one picked there set (an album, from
 * Albums), and the query would build only that. Through Apple's setters
 * (0x08eb.e6/.e3/.e4/.e5's), which also drop the songs' verdicts 0x58440
 * cached under the old query (0x9d7ec). */
static const uint32_t set_filter[4] = { 0xd5f0c, 0xd539c, 0xd5744, 0xd5150 };   /* (lib, i) */

static void unfilter(unsigned list)
{
    uint32_t lib = UI_OBJECT ? word(UI_OBJECT, 0x1c / 4) : 0;
    unsigned f;

    for (f = 0; lib && f < 4; f++)
        if (!(above[list] >> f & 1))
            ((uint32_t (*)(uint32_t, int32_t))set_filter[f])(lib, -1);
}

static void title(uint32_t str)
{
    if (obj_08de && str)
        set_text(obj_08de, TITLE, str, 0x80);
}

/* Select on the Hidden row of list: that list again, hidden items only. */
static void open_hidden(unsigned list)
{
    hr.mode = (int)list + 1;
    hr.depth = 0;
    hr.gen = tracks_gen();
    hide_state.reveal = 1;
    debug_note(DEBUG_TAG('h', 'r', 'o', 'p'), list, cnt.n[list]);
    unfilter(list);
    browse_rebuild(list, hr.widget, 0);
    title(HR_STR_TITLE);
}

/* fn 14 (Menu) at the Hidden list: the whole list again, on the Hidden
 * row. */
int hiddenrow_back(void)
{
    unsigned list;

    if (!hr.mode || hr.depth > 0)
        return 0;
    list = (unsigned)hr.mode - 1;
    drop();
    debug_note(DEBUG_TAG('h', 'r', 'b', 'k'), list, 0);
    unfilter(list);
    browse_rebuild(list, hr.widget, 0);
    title(list_title[list]);
    return 1;
}

void hiddenrow_screen(int back)
{
    if (!hr.mode)
        return;
    if (!back)
        hr.depth++;
    else if (--hr.depth < 0)
        drop();                 /* back past it: fn 14 wasn't seen there */
}

uint32_t hiddenrow_vm(uint32_t pc, uint32_t vm)
{
    unsigned l;

    (void)vm;
    for (l = 0; l < HR_LISTS; l++)
        if (pc == pick_pc[l]) {
            if (hr.picked != (int)l + 1)
                return pc;
            hr.picked = 0;
            if (!hr.mode)
                open_hidden(l);
            return HM_NIL;      /* the handler's row is -1 */
        }
    return pc;
}

const void *hiddenrow_resource(uint32_t fourcc, uint32_t id, uint32_t *size)
{
    static const char s[] = "Hidden";

    if (fourcc != FOURCC_STR || id != HR_STR_TITLE)
        return 0;
    *size = sizeof s;
    return s;
}

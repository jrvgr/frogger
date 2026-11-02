/* Now Playing's two pages: the cover page (title, cover art, progress bar, no
 * title bar) and Apple's. Now Playing opens on the cover page; Select goes to
 * Apple's page, and from there Apple's own cycle runs (scrubbing, rating); when
 * it comes back to normal (Select after a scrub or from rating, or its 5 s
 * timeout) the cover page returns. docs/nowplaying.md has the details.
 *
 * The View resource is only read at boot, so the pages are switched by
 * changing the live objects: their layout coordinates, laid out again by the
 * firmware (set_layout), and visibility through the firmware's own SetVisible
 * (an object's vtable + 0x94); both repaint. Everything here runs inside the
 * firmware's handling of a key or a screen change, so the new page is drawn
 * in that same drawing batch.
 *
 * Object layout: +0x00 vtable (relative: a slot holds an offset from the
 * vtable), +0x10 parent, +0x18 type, +0x1c id (low halfword), +0x20 flags
 * (0x800 shown, 0x1000 hidden), +0x58 the rectangle on the display (top,
 * left, bottom, right; set by the layout from the coordinates at +0x28..+0x54,
 * and a Str draws its text from an origin only SetRect updates); a View's clip
 * is at +0x58 and +0x78, its children at +0x70 (count at +0x6c). */

#include <stdint.h>
#include "settings.h"
#include "nowplaying.h"

#define TYPE_BMAP 0x424d6170u
#define TYPE_STR  0x53747220u

#define OBJ(o, off)  (*(volatile uint32_t *)((o) + (off)))

/* Coordinate anchors (docs/nowplaying.md) */
#define ABS         0x80000002u    /* the value as is */
#define ABS_HEIGHT  0x80000008u    /* a height */
#define FIT_HEIGHT  0x80000018u    /* the content's height */

enum { COVER, APPLE };

static struct {
    uint32_t art, view, screens, bar, title;
    uint32_t bar_area;          /* the progress bar's screen stack (None 0xff33): progress, scrub, rating */
    uint32_t others[7];         /* the "1 of 2" row, artist, album: hidden on the cover page */
    unsigned n_others;
    int32_t title_top;          /* Apple's top coordinate in the View (+0x30) */
    uint32_t art_size[2];       /* the art's height and width values (+0x48, +0x54): 0 while it's switched off */
    int open, page, busy;
    int lifted;                 /* the View's coordinates are the cover page's */
} np;

static void set_visible(uint32_t obj, uint32_t on)
{
    uint32_t vt = OBJ(obj, 0);
    void (*fn)(uint32_t, uint32_t) = (void (*)(uint32_t, uint32_t))(vt + OBJ(vt, 0x94));

    fn(obj, on);
}

/* The page's layout, through the coordinates the firmware lays elements out
 * from (an element's +0x28..+0x54: reference, anchor and value for top, left,
 * height and width), since it lays them out again by itself (when a screen
 * opens, when Select's cycle comes back to normal) and rectangles written
 * directly don't last.
 *
 * The cover page has no title bar: the bar container's height (+0x44 anchor,
 * +0x48 value) becomes a fixed 0 instead of fitting its content (anchor bit
 * 0x10). The screen container is laid out below the bar, so it and Now
 * Playing's View start at the top of the display, and the View's elements
 * placed as is (top anchor ABS) move down by the bar's height to stay where
 * they were; the ones placed relative to another follow it. The title goes
 * to NP_TITLE_TOP.
 *
 * Laying the root out again would resize the screen container and so lay
 * out all of its 79 screens (some 150 ms), so the bar's, the screen
 * container's and the View's rectangles and clips (+0x58, +0x78) are set to
 * what that would give, and only the View is laid out again (0x42768; the
 * flag repaints), which moves its elements through their SetRect, which
 * also lays a Str's text out again. The firmware's own root layouts then
 * find nothing to change. */
static void set_layout(int cover)
{
    void (*layout)(uint32_t, uint32_t) = (void (*)(uint32_t, uint32_t))0x42768;
    uint32_t kids = OBJ(np.view, 0x70), n = OBJ(np.view, 0x6c), i;
    int32_t top = cover ? 0 : NP_BAR_HEIGHT;

    if (np.lifted != cover) {
        for (i = 0; i < n; i++) {
            uint32_t c = OBJ(kids, 4 * i);
            if (c == np.title)
                OBJ(c, 0x30) = (uint32_t)(cover ? NP_TITLE_TOP : np.title_top);
            else if (OBJ(c, 0x2c) == ABS)
                OBJ(c, 0x30) += cover ? NP_BAR_HEIGHT : -NP_BAR_HEIGHT;
        }
        np.lifted = cover;
    }
    OBJ(np.bar, 0x44) = cover ? ABS_HEIGHT : FIT_HEIGHT;
    OBJ(np.bar, 0x48) = (uint32_t)top;
    OBJ(np.bar, 0x60) = (uint32_t)top;      /* bottoms */
    OBJ(np.bar, 0x80) = (uint32_t)top;
    OBJ(np.screens, 0x58) = (uint32_t)top;  /* tops */
    OBJ(np.screens, 0x78) = (uint32_t)top;
    OBJ(np.view, 0x58) = (uint32_t)top;
    OBJ(np.view, 0x78) = (uint32_t)top;
    layout(np.view, 1);
}

static uint32_t id_of(uint32_t obj)
{
    return OBJ(obj, 0x1c) & 0xffff;
}

/* The objects around the art element, once. */
static int np_find(uint32_t art)
{
    uint32_t root, kids, n, i;

    if (np.art == art)
        return 1;
    np.view = OBJ(art, 0x10);
    np.screens = OBJ(np.view, 0x10);
    root = OBJ(np.screens, 0x10);
    if (id_of(np.view) != NP_VIEW_ID || !root || OBJ(root, 0x6c) < 1)
        return 0;
    np.bar = OBJ(OBJ(root, 0x70), 0);
    if (id_of(np.bar) != 0x2503)
        return 0;
    kids = OBJ(np.view, 0x70);
    n = OBJ(np.view, 0x6c);
    np.title = 0;
    np.bar_area = 0;
    np.n_others = 0;
    for (i = 0; i < n; i++) {
        uint32_t c = OBJ(kids, 4 * i), id = id_of(c);
        if (id == 0x3319)
            np.title = c;
        else if (id == 0xff33)
            np.bar_area = c;
        else if (id == 0x331f || id == 0x25ed || id == 0x335e || id == 0x25ec || id == 0x25eb
                 || id == 0x331a || id == 0x331b) {
            if (np.n_others < sizeof np.others / sizeof np.others[0])
                np.others[np.n_others++] = c;
        }
    }
    if (!np.title || !np.bar_area || np.n_others != 7)
        return 0;
    np.title_top = (int32_t)OBJ(np.title, 0x30);
    np.art_size[0] = OBJ(art, 0x48);
    np.art_size[1] = OBJ(art, 0x54);
    np.art = art;
    return 1;
}

static void show_cover(int art_too)
{
    unsigned i;

    set_visible(np.bar, 0);
    for (i = 0; i < np.n_others; i++)
        set_visible(np.others[i], 0);
    set_layout(1);
    if (art_too)
        set_visible(np.art, 1);
    np.page = COVER;
}

static void show_apple(int art_too)
{
    unsigned i;

    if (art_too)
        set_visible(np.art, 0);
    set_layout(0);
    for (i = 0; i < np.n_others; i++)
        set_visible(np.others[i], 1);
    set_visible(np.bar, 1);
    np.page = APPLE;
}

/* Settings › Cover Page, as Now Playing opens. Off, Now Playing is Apple's
 * page: the art stays shown (its being hidden is how Now Playing's closing
 * is seen) but takes no room, its height and width 0, and the cycle is all
 * Apple's (np_vm acts only on the cover page). */
static void cover_switch(void)
{
    int on = frogger_on(FEATURE_COVER);
    uint32_t h = on ? np.art_size[0] : 0, w = on ? np.art_size[1] : 0;

    np.page = on ? COVER : APPLE;
    if (OBJ(np.art, 0x48) != h || OBJ(np.art, 0x54) != w) {
        OBJ(np.art, 0x48) = h;
        OBJ(np.art, 0x54) = w;
        ((void (*)(uint32_t, uint32_t))0x42768)(np.view, 1);
    }
}

/* Whether obj is one the cover page keeps hidden. */
static int cover_hides(uint32_t obj)
{
    unsigned i;

    if (obj == np.bar)
        return 1;
    for (i = 0; i < np.n_others; i++)
        if (obj == np.others[i])
            return 1;
    return 0;
}

/* vis_hook: every element's visibility change (0xb4578); returns 1 to skip it.
 * Ours is the art: it's Now Playing's last child, so when it's shown the
 * screen is opening with everything else already shown, and when it's hidden
 * the screen is closing. Now Playing shows its children more than once while
 * it opens, so on the cover page the ones it hides stay hidden: showing them
 * again is skipped. */
int np_visibility(uint32_t obj, uint32_t on)
{
    uint32_t shown;

    if (np.busy)
        return 0;
    if (on && np.open && np.page == COVER && cover_hides(obj))
        return 1;
    if (OBJ(obj, 0x18) != TYPE_BMAP || id_of(obj) != FROGGER_BMAP_ART)
        return 0;
    shown = (OBJ(obj, 0x20) & 0x1800) == 0x800;
    if (on == shown)
        return 0;
    /* Views also show their elements while they're built at boot, long before
     * any screen is up; a real opening marks the View itself shown first. */
    if (on && (OBJ(OBJ(obj, 0x10), 0x20) & 0x1800) != 0x800)
        return 0;
    np.busy = 1;
    if (on && np_find(obj)) {
        np.open = 1;
        cover_switch();
        if (np.page == COVER) {
            np_art_retry();
            show_cover(0);
        }
    } else if (!on && np.open) {
        np.open = 0;
        if (np.page == COVER) {         /* the screen goes, so just put back what other screens share */
            set_layout(0);
            set_visible(np.bar, 1);
        }
        np.page = COVER;
    }
    np.busy = 0;
    return 0;
}

/* Set by art.c when another song starts. np_playing can run from the playback
 * side (a song ending), where neither reading the card nor drawing is safe, so
 * the next bytecode instruction (the UI's own loop, where Now Playing updates
 * for the new song) loads the cover (np_art_update), and if it changed,
 * invalidates the element, which repaints it: the firmware draws the art
 * element from our bitmap but doesn't know it changed. (SetVisible's own
 * invalidate, 0xe0bc0, only runs for objects with flag 0x10, which the art
 * doesn't have; laying the View out again repaints only what moved.) */
volatile uint8_t np_art_dirty;

/* The page switch slides, as Apple's screens do: Select's new page comes in
 * from the right, the cover page coming back from the left.
 *
 * The firmware draws into the framebuffer (0x3835a0: 128 rows of 40 bytes,
 * 2 bits a pixel) and copies each dirty rectangle to the LCD as it draws it
 * (lcd_update_rect 0xd2db4), when the last end-update of a batch (0x68dfc)
 * drains them, a draw cycle after the key. So: the old page is kept before
 * the switch, lcd_hook holds the LCD back while that batch draws the new
 * page, and as the drain ends (drawn_hook) the two pages slide across, in
 * whole 8-pixel columns (an LCD word), then the new one stays up. If no
 * drain comes, np_tick lets the LCD go again. */
#define FB          ((uint8_t *)0x3835a0)
#define FB_ROWS     128
#define FB_ROW      40
#define FB_COLS     20              /* 8-pixel columns, 2 bytes each */
#define SLIDE_FRAMES 8
#define SLIDE_US    25000u          /* a frame; Apple's slides step every 30 ms */
#define HOLD_US     500000u         /* the longest the LCD is held for a drain */
#define clock_us    ((void (*)(uint32_t *us))0x87de0)

static uint8_t page_old[FB_ROWS * FB_ROW], page_new[FB_ROWS * FB_ROW];
static struct { int from_left; uint32_t since; } slide;
volatile uint8_t np_lcd_hold, np_lcd_held;     /* lcd_hook's: hold it; a flush was held */

static void copy(uint8_t *to, const uint8_t *from, uint32_t n)
{
    while (n--)
        *to++ = *from++;
}

static void lcd_all(void)
{
    static const int32_t all[4] = { 0, 0, FB_ROWS, 160 };    /* top, left, bottom, right */

    lcd_flush(0, all);
}

static void slide_begin(int from_left)
{
    if (!frogger_on(FEATURE_SLIDE))
        return;                 /* Settings › Page Slide off: the switch as it is drawn */
    copy(page_old, FB, sizeof page_old);
    slide.from_left = from_left;
    clock_us(&slide.since);
    np_lcd_held = 0;
    np_lcd_hold = 1;
}

/* Frame k of SLIDE_FRAMES: the new page in by k columns' worth, the old one
 * pushed out by as much. */
static void slide_frame(unsigned k)
{
    unsigned d = FB_COLS * k / SLIDE_FRAMES * 2, row;   /* bytes the new page is in */

    for (row = 0; row < FB_ROWS; row++) {
        uint8_t *fb = FB + row * FB_ROW;
        const uint8_t *o = page_old + row * FB_ROW, *n = page_new + row * FB_ROW;
        if (slide.from_left) {
            copy(fb, n + FB_ROW - d, d);
            copy(fb + d, o, FB_ROW - d);
        } else {
            copy(fb, o + d, FB_ROW - d);
            copy(fb + FB_ROW - d, n, d);
        }
    }
    lcd_all();
}

/* The bar area in the page sliding in left blank: coming back to the cover
 * page (always from scrubbing or rating) it still shows the rating dots or
 * the scrub knob, until its own slide to the progress bar ticks
 * (np_transition) just after ours and draws it. */
static void blank_bar(void)
{
    int32_t top = (int32_t)OBJ(np.bar_area, 0x58), bottom = (int32_t)OBJ(np.bar_area, 0x60), row;

    if (top < 0)
        top = 0;
    if (bottom > FB_ROWS)
        bottom = FB_ROWS;
    for (row = top; row < bottom; row++) {
        uint8_t *p = page_new + row * FB_ROW;
        unsigned i;
        for (i = 0; i < FB_ROW; i++)
            p[i] = 0;
    }
}

/* drawn_hook: a drain of dirty rectangles ended (or an end-update that
 * wasn't the last). After the switch's, the framebuffer holds the new page,
 * which slides in. */
void np_drawn(void)
{
    uint32_t t, start;
    unsigned k;

    if (!np_lcd_hold || !np_lcd_held)
        return;
    copy(page_new, FB, sizeof page_new);
    if (slide.from_left)
        blank_bar();
    clock_us(&start);
    for (k = 1; k < SLIDE_FRAMES; k++) {
        slide_frame(k);
        do
            clock_us(&t);
        while (t - start < k * SLIDE_US);
    }
    copy(FB, page_new, sizeof page_new);
    np_lcd_hold = 0;
    lcd_all();
}

/* tick_hook: the switch's drain never came; show what's drawn. */
void np_tick(void)
{
    uint32_t now;

    if (!np_lcd_hold)
        return;
    clock_us(&now);
    if (now - slide.since > HOLD_US) {
        np_lcd_hold = 0;
        lcd_all();
    }
}

/* vm_hook: the bytecode interpreter is about to run the instruction at pc;
 * returns the pc to run instead. */
uint32_t np_vm(uint32_t pc)
{
    if (np_art_dirty && !np.busy) {
        np_art_dirty = 0;
        if (np_art_update() && np.open && np.page == COVER)        /* the firmware's invalidate (0xda3cc, what SetVisible ends in) */
            ((void (*)(uint32_t))0xda3cc)(np.art);
    }
    if (!np.open || np.busy)
        return pc;
    if (pc == NP_FN_SELECT && np.page == COVER) {
        np.busy = 1;
        slide_begin(0);
        show_apple(1);
        np.busy = 0;
        return NP_FN_RETURN;           /* Apple's page in its normal state: no scrubbing yet */
    }
    if ((pc == NP_FN_RATED || pc == NP_FN_TIMEOUT || pc == NP_FN_SCRUBBED) && np.page == APPLE
        && OBJ(np.art, 0x48)) {         /* not with Cover Page off (cover_switch): Apple's page stays */
        np.busy = 1;
        slide_begin(1);
        show_cover(1);
        np.busy = 0;
    }
    /* Menu: the screen slides away, below the title bar like any other, so
     * the bar comes back now rather than once the slide is over. The title
     * goes (Apple's place is under the art); Now Playing shows it again when
     * it next opens. */
    if (pc == NP_FN_MENU && np.page == COVER) {
        np.busy = 1;
        set_visible(np.title, 0);
        set_layout(0);
        set_visible(np.bar, 1);
        np.page = APPLE;
        np.busy = 0;
    }
    return pc;
}

/* trans_hook: a screen stack starts a slide (0xe3a9c); returns 1 to have it
 * end on its first tick. Back to normal, the bar area slides from the rating
 * dots (or the scrub knob) to the progress bar, a wipe across the cover page
 * that has just drawn around it; so the progress bar replaces them at once.
 * (Until that tick the stack still draws its old view.) */
int np_transition(uint32_t stack)
{
    return np.open && np.page == COVER && stack == np.bar_area;
}

/* Whether Now Playing is the screen up (the hold menu's hold there). */
int np_is_open(void)
{
    return np.open;
}

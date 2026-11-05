/* Lock Cover: with Hold on and a song playing or paused, the screen shows the
 * song's cover large (the 72x72 FroggerArt cover at 1.5x), its title and a
 * progress bar, like a lock screen. Hold off, the screen is what it was.
 * Settings › Lock Cover switches it off; with nothing playing it's stock.
 *
 * Stock 2.3 with Hold on (docs/re-notes.md, "Key input"): the Hold thread
 * (0x13c2a0) sees the pin change and its handler (0x8d470) tells the UI,
 * which draws a small lock in the title bar; every key is dropped in
 * 0xbe110, which draws nothing. So the lock screen is drawn over whatever is
 * up, and nothing of Apple's reaches the LCD while it's there:
 *
 * - lock_tick (tick_hook, the UI thread, about every 0.25 s) reads Hold
 *   (0x7a9b8, as 0xbe110 does) and draws the lock screen when it goes on, a
 *   new song or cover comes, or the bar moves a pixel. Drawing is the
 *   firmware's own LCD copy (lcd_flush) from the framebuffer, with ours
 *   swapped in for the copy and Apple's put back after, so the firmware
 *   keeps drawing its screen underneath as if nothing happened.
 * - lcd_hook asks lock_lcd while Lock Cover could show (lock_armed): with
 *   Hold on, Apple's flushes are skipped (the title bar's lock, the clock,
 *   the next song); Hold off, the first one puts all of Apple's screen back.
 *   lock_tick does that too if no flush comes.
 *
 * The backlight is left alone: it does what stock does. */

#include <stdint.h>
#include "lock.h"
#include "settings.h"
#include "nowplaying.h"

#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define PLAYER_ITEM     (0x2a8 / 4)                 /* 0 when stopped */
#define PLAYER_POS      ((0x2000 + 0x164) / 4)      /* ms into the track */
#define ITEM_TRACK      (0x20 / 4)
#define TRACK_LIBRARY   0                           /* a track record's first word */
#define TRACK_TITLE     (0x24 / 4)                  /* a key in the title pool */
#define TRACK_LENGTH    (0x54 / 4)                  /* ms */
#define TITLE_POOL      0xb0                        /* on the library object (0xeb1e8, field 2) */

#define hold_on     ((int (*)(void))0x7a9b8)
/* The string pool calls 0xbfb44 makes for 0xeb1e8: lock, look a key up
 * (UTF-16 halfwords, the length in bytes; 0 = found), unlock. */
#define pool_lock   ((void (*)(uint32_t pool))0xa5004)
#define pool_get    ((int (*)(uint32_t pool, uint32_t key, const uint16_t **text, uint32_t *bytes))0x81ee8)
#define pool_unlock ((void (*)(uint32_t pool))0xef738)

#define FB          ((uint8_t *)0x3835a0)           /* 128 rows of 40 bytes, 2 bits a pixel */
#define FB_ROWS     128
#define FB_ROW      40

volatile uint8_t lock_armed;

static struct {
    int shown;
    uint32_t track, art_gen, bar;   /* what the screen on the LCD shows */
} lk;

static uint8_t screen[FB_ROWS * FB_ROW], apple[FB_ROWS * FB_ROW];

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static void copy(uint8_t *to, const uint8_t *from, uint32_t n)
{
    while (n--)
        *to++ = *from++;
}

static uint32_t player(void)
{
    uint32_t ui = UI_OBJECT, lib;

    if (!ui || !(lib = word(ui, 0x1c / 4)) || !word(lib, 0))
        return 0;
    return word(word(lib, 0), 1);
}

/* The track record playing or paused; 0 if none. */
static uint32_t playing(uint32_t p)
{
    uint32_t item;

    return p && (item = word(p, PLAYER_ITEM)) ? word(item, ITEM_TRACK) : 0;
}

/* A pixel of the screen being made, level 0 (light) to 3 (black); the
 * framebuffer's order is a BMap's, top bits first. */
static void put(unsigned x, unsigned y, unsigned level)
{
    uint8_t *b = &screen[y * FB_ROW + x / 4];
    unsigned shift = 6 - 2 * (x & 3);

    *b = (uint8_t)((*b & ~(3u << shift)) | level << shift);
}

/* The cover, 72x72 BMap rows, at 1.5x: destination pixel d shows source d * 2 / 3. */
static void draw_art(const uint8_t *px)
{
    unsigned x, y;

    for (y = 0; y < LOCK_ART; y++) {
        const uint8_t *row = px + (y * 2 / 3) * NP_ART_ROW;
        for (x = 0; x < LOCK_ART; x++) {
            unsigned s = x * 2 / 3;
            put(LOCK_ART_LEFT + x, LOCK_ART_TOP + y, (row[s / 4] >> (6 - 2 * (s & 3))) & 3);
        }
    }
}

/* A 5x7 font with descenders, ASCII 0x20-0x7e: five columns, bit 0 the top
 * row (the classic LCD font, as in Adafruit GFX's glcdfont.c, BSD licence). */
static const uint8_t font[95][5] = {
    {0x00,0x00,0x00,0x00,0x00}, {0x00,0x00,0x5f,0x00,0x00}, {0x00,0x07,0x00,0x07,0x00}, {0x14,0x7f,0x14,0x7f,0x14},
    {0x24,0x2a,0x7f,0x2a,0x12}, {0x23,0x13,0x08,0x64,0x62}, {0x36,0x49,0x56,0x20,0x50}, {0x00,0x08,0x07,0x03,0x00},
    {0x00,0x1c,0x22,0x41,0x00}, {0x00,0x41,0x22,0x1c,0x00}, {0x2a,0x1c,0x7f,0x1c,0x2a}, {0x08,0x08,0x3e,0x08,0x08},
    {0x00,0x80,0x70,0x30,0x00}, {0x08,0x08,0x08,0x08,0x08}, {0x00,0x00,0x60,0x60,0x00}, {0x20,0x10,0x08,0x04,0x02},
    {0x3e,0x51,0x49,0x45,0x3e}, {0x00,0x42,0x7f,0x40,0x00}, {0x72,0x49,0x49,0x49,0x46}, {0x21,0x41,0x49,0x4d,0x33},
    {0x18,0x14,0x12,0x7f,0x10}, {0x27,0x45,0x45,0x45,0x39}, {0x3c,0x4a,0x49,0x49,0x31}, {0x41,0x21,0x11,0x09,0x07},
    {0x36,0x49,0x49,0x49,0x36}, {0x46,0x49,0x49,0x29,0x1e}, {0x00,0x00,0x14,0x00,0x00}, {0x00,0x40,0x34,0x00,0x00},
    {0x00,0x08,0x14,0x22,0x41}, {0x14,0x14,0x14,0x14,0x14}, {0x00,0x41,0x22,0x14,0x08}, {0x02,0x01,0x59,0x09,0x06},
    {0x3e,0x41,0x5d,0x59,0x4e}, {0x7c,0x12,0x11,0x12,0x7c}, {0x7f,0x49,0x49,0x49,0x36}, {0x3e,0x41,0x41,0x41,0x22},
    {0x7f,0x41,0x41,0x41,0x3e}, {0x7f,0x49,0x49,0x49,0x41}, {0x7f,0x09,0x09,0x09,0x01}, {0x3e,0x41,0x41,0x51,0x73},
    {0x7f,0x08,0x08,0x08,0x7f}, {0x00,0x41,0x7f,0x41,0x00}, {0x20,0x40,0x41,0x3f,0x01}, {0x7f,0x08,0x14,0x22,0x41},
    {0x7f,0x40,0x40,0x40,0x40}, {0x7f,0x02,0x1c,0x02,0x7f}, {0x7f,0x04,0x08,0x10,0x7f}, {0x3e,0x41,0x41,0x41,0x3e},
    {0x7f,0x09,0x09,0x09,0x06}, {0x3e,0x41,0x51,0x21,0x5e}, {0x7f,0x09,0x19,0x29,0x46}, {0x26,0x49,0x49,0x49,0x32},
    {0x03,0x01,0x7f,0x01,0x03}, {0x3f,0x40,0x40,0x40,0x3f}, {0x1f,0x20,0x40,0x20,0x1f}, {0x3f,0x40,0x38,0x40,0x3f},
    {0x63,0x14,0x08,0x14,0x63}, {0x03,0x04,0x78,0x04,0x03}, {0x61,0x59,0x49,0x4d,0x43}, {0x00,0x7f,0x41,0x41,0x41},
    {0x02,0x04,0x08,0x10,0x20}, {0x00,0x41,0x41,0x41,0x7f}, {0x04,0x02,0x01,0x02,0x04}, {0x40,0x40,0x40,0x40,0x40},
    {0x00,0x03,0x07,0x08,0x00}, {0x20,0x54,0x54,0x78,0x40}, {0x7f,0x28,0x44,0x44,0x38}, {0x38,0x44,0x44,0x44,0x28},
    {0x38,0x44,0x44,0x28,0x7f}, {0x38,0x54,0x54,0x54,0x18}, {0x00,0x08,0x7e,0x09,0x02}, {0x18,0xa4,0xa4,0x9c,0x78},
    {0x7f,0x08,0x04,0x04,0x78}, {0x00,0x44,0x7d,0x40,0x00}, {0x20,0x40,0x40,0x3d,0x00}, {0x7f,0x10,0x28,0x44,0x00},
    {0x00,0x41,0x7f,0x40,0x00}, {0x7c,0x04,0x78,0x04,0x78}, {0x7c,0x08,0x04,0x04,0x78}, {0x38,0x44,0x44,0x44,0x38},
    {0xfc,0x18,0x24,0x24,0x18}, {0x18,0x24,0x24,0x18,0xfc}, {0x7c,0x08,0x04,0x04,0x08}, {0x48,0x54,0x54,0x54,0x24},
    {0x04,0x04,0x3f,0x44,0x24}, {0x3c,0x40,0x40,0x20,0x7c}, {0x1c,0x20,0x40,0x20,0x1c}, {0x3c,0x40,0x30,0x40,0x3c},
    {0x44,0x28,0x10,0x28,0x44}, {0x4c,0x90,0x90,0x90,0x7c}, {0x44,0x64,0x54,0x4c,0x44}, {0x00,0x08,0x36,0x41,0x00},
    {0x00,0x00,0x77,0x00,0x00}, {0x00,0x41,0x36,0x08,0x00}, {0x02,0x01,0x02,0x04,0x02},
};

/* Latin-1's letters 0xc0-0xff without their accents. */
static const char latin1[] = "AAAAAAACEEEEIIIIDNOOOOOxOUUUUYPsaaaaaaaceeeeiiiidnooooo/ouuuuypy";

static char ascii(uint16_t c)
{
    if (c >= 0x20 && c < 0x7f)
        return (char)c;
    if (c >= 0xc0 && c <= 0xff)
        return latin1[c - 0xc0];
    if (c == 0x2018 || c == 0x2019)
        return '\'';
    if (c == 0x201c || c == 0x201d)
        return '"';
    if (c == 0x2013 || c == 0x2014)
        return '-';
    return c == 0xa0 ? ' ' : '?';
}

#define TITLE_MAX   26          /* 6 px a letter: 156 of the 160 */

/* The track's title, centred; cut short with ".." if it doesn't fit. */
static void draw_title(uint32_t track)
{
    char text[TITLE_MAX];
    uint32_t lib = word(track, TRACK_LIBRARY), pool, bytes = 0, n = 0, i, x, col;
    const uint16_t *s = 0;

    if (!lib)
        return;
    pool = lib + TITLE_POOL;
    pool_lock(pool);
    if (pool_get(pool, word(track, TRACK_TITLE), &s, &bytes) == 0 && s) {
        for (i = 0; i < bytes / 2 && n < TITLE_MAX; i++)
            text[n++] = ascii(s[i]);
        if (i < bytes / 2) {
            text[TITLE_MAX - 2] = text[TITLE_MAX - 1] = '.';
        }
    }
    pool_unlock(pool);
    x = (160 - n * 6 + 1) / 2;
    for (i = 0; i < n; i++, x += 6) {
        const uint8_t *g = font[text[i] - 0x20];
        for (col = 0; col < 5; col++) {
            unsigned y;
            for (y = 0; y < 8; y++)
                if (g[col] >> y & 1)
                    put(x + col, LOCK_TITLE_TOP + y, 3);
        }
    }
}

/* How much of the bar is filled, in pixels of LOCK_ART. */
static uint32_t bar_of(uint32_t p, uint32_t track)
{
    uint32_t len = word(track, TRACK_LENGTH), pos = word(p, PLAYER_POS);

    if (!len)
        return 0;
    if (pos >= len)
        return LOCK_ART;
    return (uint32_t)((uint64_t)pos * LOCK_ART / len);
}

static void draw_bar(uint32_t fill)
{
    unsigned x, y;

    for (y = 0; y < LOCK_BAR_ROWS; y++)
        for (x = 0; x < LOCK_ART; x++)
            put(LOCK_ART_LEFT + x, LOCK_BAR_TOP + y, x < fill ? 3 : 1);
}

static void lcd_all(void)
{
    static const int32_t all[4] = { 0, 0, FB_ROWS, 160 };    /* top, left, bottom, right */

    lcd_flush(0, all);
}

/* The lock screen to the LCD: ours in the framebuffer for the copy, then
 * Apple's back. All of this is on the UI thread, where Apple draws too. */
static void show(uint32_t track, uint32_t bar)
{
    const uint8_t *art = np_art_pixels();
    unsigned i;

    for (i = 0; i < sizeof screen; i++)
        screen[i] = 0;
    if (art)
        draw_art(art);
    draw_title(track);
    draw_bar(bar);
    copy(apple, FB, sizeof apple);
    copy(FB, screen, sizeof screen);
    lcd_all();
    copy(FB, apple, sizeof apple);
    lk.shown = 1;
    lk.track = track;
    lk.art_gen = np_art_gen;
    lk.bar = bar;
}

static void hide(void)
{
    lk.shown = 0;
    lcd_all();
}

int lock_lcd(uint32_t display, const int32_t *rect)
{
    (void)display;
    (void)rect;
    if (hold_on())
        return 1;
    if (!lk.shown)
        return 0;
    hide();             /* Hold just went off: all of Apple's screen, this flush with it */
    return 1;
}

void lock_tick(void)
{
    uint32_t p = player(), track = playing(p), bar;

    lock_armed = track && frogger_on(FEATURE_LOCK);
    if (lock_armed && hold_on()) {
        bar = bar_of(p, track);
        if (!lk.shown || track != lk.track || np_art_gen != lk.art_gen || bar != lk.bar)
            show(track, bar);
    } else if (lk.shown) {
        hide();
    }
}

int lock_shown(void)
{
    return lk.shown;
}

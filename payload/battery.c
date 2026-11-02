/* The battery as a percentage ("87%") in the title bar, in place of the bars.
 *
 * The bar's battery is a container (None 0x3342, one per bar View, six in
 * all) with a child per state. Every 30 s, and when a screen opens, 0x8e760
 * asks 0x42af4 for the state and has 0xe0c9c show that child on each
 * container. On battery the state is BATTERY_LEVEL0 + level, the level 0..15
 * that 0x74388 keeps at [0x370d64] and moves one step per reading. A reading
 * is 0x118de0: the raw value from 0x118e40 (a model-specific read; emupod's
 * fails, so it shows no battery), bucketed by the 15 rising thresholds at
 * 0x36ffc0.
 *
 * battery_read (the bl 0x118e40 in 0x118de0) notes the raw value as it goes
 * by. battery_state (the bl 0x42af4 in 0x8e760) turns it into a percentage:
 * along Apple's own thresholds, linear between two of them, 0% below the
 * first and 100% from the last, so 15 equal steps of Apple's curve; it's an
 * approximation of the charge left, as the bars are. It draws the number
 * into a bitmap and shows one of the first two level children, which both
 * get that bitmap from battery_resource; a new number shows the other one,
 * so Apple's own show/hide repaints it. Charging, charged and the low-battery
 * text stay Apple's. Both hooks are BL hooks into C: they stand in for the
 * call they replace. */

#include <stdint.h>
#include "battery.h"
#include "settings.h"

#define FOURCC_BMAP 0x424d6170u

#define FW_STATE    0x42af4         /* 0x42af4(bar): the battery's state */
#define FW_RAW      0x118e40        /* 0x118e40(&raw): 0 when it read one */
#define THRESHOLDS  ((const volatile uint16_t *)0x36ffc0)
#define STEPS       15

#define TEXT_TOP    2               /* 7 rows of text in the 10 */
#define TEXT_RIGHT  23              /* the column after the text: where Apple's icon ends */

static volatile uint32_t raw_new, raw_last;    /* raw_new: a reading since battery_state's last look */
static uint32_t pct16;                          /* the percentage, smoothed, x16; 0 = none yet */
static uint32_t shown = 0xffffffffu;            /* the number in the bitmap */
static uint32_t child;                          /* 0 or 1: which of the two shows it */

static struct {
    uint32_t zero[2];
    uint32_t height, width;
    uint16_t row, depth, d5, format;
    uint32_t length;
    uint8_t px[BATTERY_H * BATTERY_ROW];
} bmap;

/* 4 x 7 digits and a 5 x 7 "%", a row per byte, leftmost column in the
 * highest of the glyph's bits. */
static const uint8_t glyph[11][7] = {
    { 6, 9, 9, 9, 9, 9, 6 },
    { 2, 6, 2, 2, 2, 2, 7 },
    { 6, 9, 1, 2, 4, 8, 15 },
    { 14, 1, 1, 6, 1, 1, 14 },
    { 2, 6, 10, 10, 15, 2, 2 },
    { 15, 8, 14, 1, 1, 9, 6 },
    { 6, 8, 8, 14, 9, 9, 6 },
    { 15, 1, 2, 2, 4, 4, 4 },
    { 6, 9, 9, 6, 9, 9, 6 },
    { 6, 9, 9, 7, 1, 1, 6 },
    { 24, 25, 2, 4, 8, 19, 3 },
};
#define PERCENT 10

int32_t battery_read(uint32_t *raw)
{
    int32_t r = ((int32_t (*)(uint32_t *))FW_RAW)(raw);

    if (r == 0) {
        raw_last = *raw;
        raw_new = 1;
    }
    return r;
}

/* Raw to 0..100 along Apple's thresholds (rising; a table that isn't gives -1). */
static int percent_of(uint32_t raw)
{
    uint32_t lo, hi;
    unsigned k;

    if (THRESHOLDS[0] >= THRESHOLDS[STEPS - 1])
        return -1;
    if (raw < THRESHOLDS[0])
        return 0;
    if (raw >= THRESHOLDS[STEPS - 1])
        return 100;
    for (k = 1; raw >= THRESHOLDS[k]; k++)
        ;
    lo = THRESHOLDS[k - 1];
    hi = THRESHOLDS[k];
    if (hi <= lo)
        return -1;
    return (int)((100 * (k - 1) + 100 * (raw - lo) / (hi - lo)) / (STEPS - 1));
}

static void glyph_at(int x, const uint8_t *g, int w)
{
    int row, col;

    for (row = 0; row < 7; row++)
        for (col = 0; col < w; col++)
            if (g[row] & (1 << (w - 1 - col))) {
                int px = x + col;
                bmap.px[(TEXT_TOP + row) * BATTERY_ROW + px / 4] |= (uint8_t)(3 << (6 - 2 * (px & 3)));
            }
}

static void header(void)
{
    bmap.height = BATTERY_H;
    bmap.width = BATTERY_W;
    bmap.row = BATTERY_ROW;
    bmap.depth = 2;
    bmap.length = sizeof bmap.px;
}

static void draw(uint32_t pct)
{
    unsigned i, n = pct >= 100 ? 3 : pct >= 10 ? 2 : 1;
    int x = TEXT_RIGHT - (int)(5 * n + 5);
    uint32_t div = n == 3 ? 100 : n == 2 ? 10 : 1;

    header();
    for (i = 0; i < sizeof bmap.px; i++)
        bmap.px[i] = 0;
    for (i = 0; i < n; i++, x += 5, div /= 10)
        glyph_at(x, glyph[pct / div % 10], 4);
    glyph_at(x, glyph[PERCENT], 5);
}

uint32_t battery_state(uint32_t bar)
{
    uint32_t state = ((uint32_t (*)(uint32_t))FW_STATE)(bar), pct;
    int p;

    if (state < BATTERY_LEVEL0 || state >= BATTERY_LEVEL0 + BATTERY_LEVELS || !frogger_on(FEATURE_BATTERY))
        return state;           /* charging, charged, low, none, or switched off: Apple's */
    if (raw_new) {
        raw_new = 0;
        if ((p = percent_of(raw_last)) >= 0) {
            /* a quarter of the way to each new reading, as Apple's level moves a step at a time */
            if (!pct16)
                pct16 = (uint32_t)p * 16 + 1;
            else
                pct16 = (3 * pct16 + (uint32_t)p * 16 + 2) / 4;
        }
    }
    pct = pct16 ? (pct16 + 7) / 16 : (state - BATTERY_LEVEL0) * 100 / (BATTERY_LEVELS - 1);
    if (pct > 100)
        pct = 100;
    if (pct != shown) {
        draw(pct);
        shown = pct;
        child ^= 1;
    }
    return BATTERY_LEVEL0 + child;
}

/* frogger_resource: the first two level bitmaps are ours. */
const void *battery_resource(uint32_t fourcc, uint32_t id, uint32_t *size)
{
    if (fourcc != FOURCC_BMAP || (id != BATTERY_BMAP && id != BATTERY_BMAP + 1) || !frogger_on(FEATURE_BATTERY))
        return 0;
    if (!bmap.height)
        header();               /* loaded before the first state: blank */
    *size = sizeof bmap;
    return &bmap;
}

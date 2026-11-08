/* The clicker in the headphones.
 *
 * Apple's click is a tone on the piezo: a task (around 0x13c600, mailbox 20)
 * keeps up to 16 tones (a divisor and a length, [r7]/[r6] by index r4) and
 * plays each by programming the second UART (0xc0006040-0x4c) at 0x13c6ec,
 * then waits out its length. A click is divisor 0x64, length 0x64.
 * click_hook (hooks.S, at 0x13c6e8, where the divisor is loaded) asks
 * click_tone, which can mix a click into the music and have the task skip
 * the piezo (Headphones), or both (Both). Speaker is Apple's. The piezo's
 * sound is the task's pump (0x13c724-0x13c7c4), 0xaa bytes into the UART
 * while a tone is on: skipping it means ending the tone (hooks.S).
 *
 * The music: the decoder (on the COP) writes s16 stereo into a ring at
 * 0x4449f80-0x4461980 (96768 bytes, uncached), up to [0x4001770c]; the sound
 * FIQ (one of the variants at 0x3443xx, copied to IRAM 0x400177c0) takes it
 * from [0x40017704] into the I2S FIFO (0xc0002540, 14 slots free at most).
 * The decoder stays some 40 ms or more ahead. So the click is added to what's
 * decoded and not yet played, starting CLICK_LEAD frames past the read
 * pointer: no FIQ change, before the codec (so it follows the headphone
 * volume), and the FIQ never sees a half-done sample (16-bit stores).
 *
 * The FIQ runs only while a song plays (it's masked when paused or stopped).
 * click_tone waits up to PLAYING_US (3 ms) for the read pointer to move; if it
 * doesn't, or the pointers aren't in the ring, or too little is decoded,
 * the click goes to the piezo instead, even in Headphones.
 *
 * The click: about 1 kHz square for 4 ms, rounded off by a one-pole
 * low-pass (as the piezo's mass does), 10 ms with its ring-out, at 44.1 kHz
 * (other rates just play it a little higher or lower). Click Volume sets its
 * peak: about -18, -12 and -6 dBFS (quieter was lost under music on a device). */

#include <stdint.h>
#include "settings.h"

#define RING_START      0x04449f80u
#define RING_END        0x04461980u
#define RING_READ       (*(volatile uint32_t *)0x40017704)
#define RING_WRITE      (*(volatile uint32_t *)0x4001770c)
#define USEC_TIMER      (*(volatile uint32_t *)0xcf001110)

#define CLICK_FRAMES    441             /* 10 ms at 44.1 kHz */
#define CLICK_TONE      176             /* 4 ms of it the square wave */
#define CLICK_HALF      22              /* half a period: 1002 Hz */
#define CLICK_LEAD      64              /* frames past the read pointer (1.5 ms) */
#define CLICK_MIN       (CLICK_FRAMES / 2)  /* fewer decoded frames than this: the piezo */
#define CLICK_MAX_LEN   0x80            /* a tone this long or shorter is a click */
#define PLAYING_US      3000            /* the FIQ runs every 7 frames (0.16 ms): waiting longer costs only a paused click */

/* Peaks for Quiet, Medium, Loud: 32767 * 10^(-18/20, -12/20, -6/20). */
static const int16_t click_peak[3] = { 4125, 8231, 16423 };

static int16_t click[CLICK_FRAMES];     /* peak 32767 */

uint32_t clicker_mixed, clicker_fallback;   /* counts, for a look from emupod or a debug record */

static uint32_t prefs_flags(void)
{
    uint32_t ui = *(volatile uint32_t *)0x43580c, lib, prefs;

    if (!ui || !(lib = ((volatile uint32_t *)ui)[0x1c / 4]) || !(prefs = *(volatile uint32_t *)lib))
        return 0;
    return ((volatile uint32_t *)prefs)[0xb04 / 4];
}

unsigned clicker_place(void)
{
    unsigned v = (prefs_flags() & FROGGER_PREF_PLACE) >> FROGGER_PREF_PLACE_SHIFT;

    return v <= CLICK_BOTH ? v : CLICK_SPEAKER;
}

unsigned clicker_volume(void)
{
    unsigned v = (prefs_flags() & FROGGER_PREF_VOLUME) >> FROGGER_PREF_VOLUME_SHIFT;

    return v <= CLICK_LOUD ? v : CLICK_QUIET;
}

static void click_make(void)
{
    int32_t y = 0, peak = 1, i;

    for (i = 0; i < CLICK_FRAMES; i++) {
        int32_t x = i >= CLICK_TONE ? 0 : (i / CLICK_HALF) & 1 ? -32767 : 32767;
        y += (x - y) * 45 / 128;        /* y += 0.35 (x - y): ~4 kHz */
        click[i] = (int16_t)y;
        if (y > peak)
            peak = y;
        if (-y > peak)
            peak = -y;
    }
    for (i = 0; i < CLICK_FRAMES; i++)
        click[i] = (int16_t)(click[i] * 32767 / peak);
}

static int in_ring(uint32_t p)
{
    return p >= RING_START && p < RING_END && !(p & 3);
}

/* Adds the click at `level` to the music; 0 if it can't (nothing playing). */
static int click_mix(unsigned level)
{
    uint32_t rd = RING_READ, wr, t0, n, have, p, i;
    int32_t gain = click_peak[level];

    if (!in_ring(rd))
        return 0;
    for (t0 = USEC_TIMER; RING_READ == rd; )
        if (USEC_TIMER - t0 > PLAYING_US)
            return 0;                   /* the FIQ isn't running: paused or stopped */
    rd = RING_READ;
    wr = RING_WRITE;
    if (!in_ring(rd) || !in_ring(wr))
        return 0;
    have = (wr >= rd ? wr - rd : wr + (RING_END - RING_START) - rd) / 4;
    if (have < CLICK_LEAD + CLICK_MIN)
        return 0;
    n = have - CLICK_LEAD < CLICK_FRAMES ? have - CLICK_LEAD : CLICK_FRAMES;
    if (!click[CLICK_HALF])
        click_make();
    p = rd + CLICK_LEAD * 4;
    for (i = 0; i < n; i++) {
        int32_t c = click[i] * gain >> 15, s;
        volatile int16_t *f;
        unsigned ch;

        if (p >= RING_END)
            p -= RING_END - RING_START;
        f = (volatile int16_t *)p;
        for (ch = 0; ch < 2; ch++) {
            s = f[ch] + c;
            f[ch] = (int16_t)(s > 32767 ? 32767 : s < -32768 ? -32768 : s);
        }
        p += 4;
    }
    return 1;
}

/* The piezo task is about to play a tone (divisor, length): returns nonzero
 * to leave the piezo out. Apple's Clicker Off sends no tones. */
int click_tone(uint32_t divisor, uint32_t length)
{
    unsigned place = clicker_place();

    (void)divisor;
    if (place == CLICK_SPEAKER || length > CLICK_MAX_LEN)
        return 0;
    if (!click_mix(clicker_volume())) {
        clicker_fallback++;
        return 0;                       /* nothing playing: the piezo, even in Headphones */
    }
    clicker_mixed++;
    return place == CLICK_PHONES;
}

static const char *const clicker_strings[] = {
    [FROGGER_STR_VOLUME - FROGGER_STR_VOLUME] = "Click Volume",
    [FROGGER_STR_QUIET - FROGGER_STR_VOLUME] = "Quiet",
    [FROGGER_STR_MEDIUM - FROGGER_STR_VOLUME] = "Medium",
    [FROGGER_STR_LOUD - FROGGER_STR_VOLUME] = "Loud",
    [FROGGER_STR_SPEAKER - FROGGER_STR_VOLUME] = "Speaker",
    [FROGGER_STR_PHONES - FROGGER_STR_VOLUME] = "Headphones",
    [FROGGER_STR_BOTH - FROGGER_STR_VOLUME] = "Both",
};

const char *clicker_string(uint32_t id)
{
    return id >= FROGGER_STR_VOLUME && id <= FROGGER_STR_BOTH ? clicker_strings[id - FROGGER_STR_VOLUME] : 0;
}

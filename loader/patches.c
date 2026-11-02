#include "patches.h"
#include "payload.h"
#include "pp5002.h"
#include "holdmenu.h"

/* Patches for Apple's iPod 3G firmware 2.3. The hooks into the resident
 * payload (payload/, hidden songs) come from build/loader/payload.h,
 * which tools/mkpayload.py generates. A plain patch looks like:
 *
 *   #ifndef FROGGER_DISABLE_darkmode
 *   static const uint8_t darkmode_orig[] = { 0x00, 0x00, 0xa0, 0xe3 };
 *   static const uint8_t darkmode_repl[] = { 0x03, 0x00, 0xa0, 0xe3 };
 *   { 0x2800abcd, sizeof darkmode_orig, darkmode_orig, darkmode_repl },
 */
/* "Settings" becomes "Frogger!" in the main menu and on the Settings screen:
 * the sign that you're running the modified OS (hold Menu at boot for the
 * stock one). Build with -DFROGGER_NO_MARK to leave it alone. */
#ifndef FROGGER_NO_MARK
static const uint8_t settings_orig[] = { 'S', 'e', 't', 't', 'i', 'n', 'g', 's' };
static const uint8_t settings_repl[] = { 'F', 'r', 'o', 'g', 'g', 'e', 'r', '!' };
/* (0x1917ce is the tail of "Reset All Settings", so it is left alone.) */
#define MARK_PATCHES \
    { 0x28191914, sizeof settings_orig, settings_orig, settings_repl }, \
    { 0x28191c80, sizeof settings_orig, settings_orig, settings_repl },
#else
#define MARK_PATCHES
#endif

/* The payload lives in the top 1 MiB of DRAM (payload/payload.lds), taken
 * from the end of Apple's heap. 0x91e90 hands out the heap as everything
 * from its start to the end of DRAM, length [mem+0x20] - [mem+0x24] masked
 * to 26 bits; the mask is a no-op (both are plain addresses below 32 MiB),
 * so it becomes `sub ip, ip, #0x100000`. The end of DRAM itself isn't
 * probed: boot passes bank config 0x7000 (0x2a8, 0x2ac: bank 3 is 32 MiB,
 * 0x59024), which the two guards check. [mem+0x20] stays 32 MiB for the
 * memory controller (0xa92d8) and cache setup. docs/re-notes.md, "Free RAM". */
#if PAYLOAD_ADDR < 0x29f00000u
#error "the payload must sit in the top 1 MiB that HEAP_PATCHES reserves"
#endif
static const uint8_t bank7_orig[] = { 0x07, 0x00, 0xa0, 0xe3 };    /* mov r0, #7 */
static const uint8_t bank3_orig[] = { 0x00, 0xc6, 0x8c, 0xe1 };    /* orr ip, ip, r0, lsl #12 */
static const uint8_t heap_orig[] = { 0xfc, 0xc4, 0xcc, 0xe3 };     /* bic ip, ip, #0xfc000000 */
static const uint8_t heap_repl[] = { 0x01, 0xc6, 0x4c, 0xe2 };     /* sub ip, ip, #0x100000 */
#define HEAP_PATCHES \
    { 0x280002a8, sizeof bank7_orig, bank7_orig, bank7_orig }, \
    { 0x280002ac, sizeof bank3_orig, bank3_orig, bank3_orig }, \
    { 0x28091eac, sizeof heap_orig, heap_orig, heap_repl },

const struct patch patches[] = {
    MARK_PATCHES
    HEAP_PATCHES
    PAYLOAD_PATCHES
};
#define NUM_PATCHES (sizeof patches / sizeof patches[0])

static int bytes_equal(const volatile uint8_t *a, const uint8_t *b, uint32_t n)
{
    while (n--)
        if (*a++ != *b++)
            return 0;
    return 1;
}

static void copy_bytes(uint32_t to, uint32_t from, uint32_t n)
{
    while (n--)
        *(volatile uint8_t *)(DRAM_START + to++) = *(const volatile uint8_t *)(DRAM_START + from++);
}

/* The hold menu (payload/holdmenu.c): its bytecode into the popup's own
 * stock list (Menu 0x25ba, two items), which is pointed at the payload's
 * with four more rows, and on into Apple's Settings Menu, unused once
 * settings_install has pointed Settings at the payload's copy. Both are
 * read-only once Apple's OS runs. */
#define HM_BUNDLE_DATA  (0x181d20u + 0x313cu)

static int holdmenu_check(void)
{
    volatile uint32_t *e = (volatile uint32_t *)(DRAM_START + HM_POPUP_ENTRY);

    volatile uint32_t *m = (volatile uint32_t *)(DRAM_START + HM_MAIN_ENTRY);
    volatile uint32_t *mm = (volatile uint32_t *)(DRAM_START + HM_BUNDLE_DATA + HM_MAIN_OFFSET);

    return e[0] == HM_POPUP_ID && e[1] == HM_POPUP_OFFSET && e[2] == HM_POPUP_SIZE
        && *(volatile uint32_t *)(DRAM_START + HM_BUNDLE_DATA + HM_POPUP_OFFSET) == 2
        && m[0] == HM_MAIN_ID && m[1] == HM_MAIN_OFFSET && m[2] == HM_MAIN_SIZE
        && mm[0] == HM_MAIN_ITEMS && mm[1 + HM_MAIN_LIKE * 10 + 8] == HM_MAIN_LABEL;
}

/* The main menu (Menu 0x2512) into the payload's hm_main, with the Queue row
 * after Music: Settings' item with fn 28 (0x1ae2) and our label. */
static void main_install(void)
{
    volatile uint32_t *e = (volatile uint32_t *)(DRAM_START + HM_MAIN_ENTRY);
    volatile uint32_t *src = (volatile uint32_t *)(DRAM_START + HM_BUNDLE_DATA + HM_MAIN_OFFSET) + 1;
    volatile uint32_t *dst = (volatile uint32_t *)(DRAM_START + PAYLOAD_SYM_HM_MAIN);
    volatile uint32_t *item;
    unsigned i, w, n = 0;

    dst[n++] = HM_MAIN_ITEMS + 1;
    for (i = 0; i < HM_MAIN_ITEMS; i++) {
        for (w = 0; w < 10; w++)
            dst[n++] = src[i * 10 + w];
        if (i == HM_MAIN_AFTER) {
            item = &dst[n];
            for (w = 0; w < 10; w++)
                dst[n++] = src[HM_MAIN_LIKE * 10 + w];
            item[3] = 0x1ae2;           /* fn 28 */
            item[5] = HM_STR_UPNEXT;
            item[8] = HM_STR_UPNEXT;
        }
    }
    e[1] = PAYLOAD_SYM_HM_MAIN - HM_BUNDLE_DATA;
    e[2] = n * 4;
}

void holdmenu_install(void)
{
    volatile uint32_t *e = (volatile uint32_t *)(DRAM_START + HM_POPUP_ENTRY);

    copy_bytes(HM_SNIPPET, PAYLOAD_SYM_HM_CODE, HM_CODE_LEN);
    e[1] = PAYLOAD_SYM_HM_POPUP - HM_BUNDLE_DATA;
    e[2] = 4 + HM_ROWS * 40;
    main_install();
}

/* The payload goes in before any hook can reach it. */
static void install_payload(void)
{
    volatile uint8_t *dst = (volatile uint8_t *)PAYLOAD_ADDR;
    uint32_t i;

    for (i = 0; i < sizeof payload; i++)
        dst[i] = payload[i];
    for (; i < sizeof payload + PAYLOAD_BSS_LEN; i++)
        dst[i] = 0;
}

int apply_patches(void)
{
    unsigned i, applied = 0;
    uint32_t j;

    for (i = 0; i < NUM_PATCHES; i++)
        if (patches[i].len &&
            !bytes_equal((const volatile uint8_t *)patches[i].addr, patches[i].orig, patches[i].len))
            return -1;
    if (!settings_check() || !nowplaying_check() || !holdmenu_check())
        return -1;

    install_payload();
    settings_install();
    nowplaying_install();
    holdmenu_install();

    for (i = 0; i < NUM_PATCHES; i++) {
        if (!patches[i].len)
            continue;
        for (j = 0; j < patches[i].len; j++)
            ((volatile uint8_t *)patches[i].addr)[j] = patches[i].repl[j];
        applied++;
    }

    return applied;
}

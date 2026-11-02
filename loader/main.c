/* Frogger loader: decide between stock and patched Apple OS.
 *
 * Hold Menu at boot for the stock OS.
 * Otherwise the patches are applied to the osos image Apple's boot code
 * already put at DRAM_START, and that is what boots. */

#include <stdint.h>
#include "pp5002.h"
#include "patches.h"

static int has_apple_tag(void)
{
    static const char tag[] = "portalplayer";
    const volatile char *p = (const volatile char *)(DRAM_START + 0x20);
    unsigned i;

    for (i = 0; i < sizeof tag - 1; i++)
        if (p[i] != tag[i])
            return 0;
    return 1;
}

uint32_t main(void)
{
    volatile unsigned settle;
    uint8_t lines;

    GPIOA_ENABLE = 0xff;
    GPIOA_OUTPUT_EN = 0;
    for (settle = 0; settle < 10000; settle++)
        ;
    lines = GPIOA_INPUT_VAL;

    /* Not Apple's OS below us: don't touch it, just boot what's there. */
    if (!has_apple_tag())
        return DRAM_START;

#ifndef FROGGER_IGNORE_BUTTONS  /* test builds: always patch, to tell a misread button from the rest */
    /* Only Menu decides. The hold switch doesn't: stock 2.3 reads bit 5 high
     * as Hold on (docs/re-notes.md, Key input), the opposite of what this
     * check used to assume, so with Hold off every boot came out stock. */
    if (!(lines & BTN_MENU))
        return DRAM_START;
#else
    (void)lines;
#endif

    apply_patches();
    return DRAM_START;
}

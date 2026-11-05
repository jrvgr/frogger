/* Puts Frogger's items into Apple's Settings menu.
 *
 * Settings is a Menu resource in osos's UI bundle: a count and 40-byte items.
 * It can't grow in place, so we copy it into the payload (settings_menu), add
 * our item after Clicker and point the bundle's index entry at the copy. Our
 * item is a clone of Clicker (an On/Off item) with our id and label; the
 * payload answers for that id (payload/settings.c). docs/tcmd.md has the
 * layouts. Addresses are osos's, before the remap: DRAM_START + address. */

#include <stdint.h>
#include "pp5002.h"
#include "payload.h"
#include "settings.h"

#define BUNDLE          0x181d20u   /* the UI resource bundle */
#define BUNDLE_DATA     0x313cu     /* its data offset: index offsets count from here */
#define SETTINGS_ENTRY  0x182258u   /* Menu index entry: id, offset, size */
#define SETTINGS_ID     0x278du
#define SETTINGS_OFFSET 0x9684u
#define SETTINGS_SIZE   (4 + SETTINGS_ITEMS * 4 * MENU_ITEM_WORDS)
#define CLICKER         8           /* Clicker's row */
#define CLICKER_ITEM    0x282du     /* its word 6 */

#define RAM(a) ((volatile uint32_t *)(DRAM_START + (a)))

static volatile uint32_t *settings_stock(void)
{
    return RAM(BUNDLE + BUNDLE_DATA + SETTINGS_OFFSET);
}

int settings_check(void)
{
    volatile uint32_t *e = RAM(SETTINGS_ENTRY), *m = settings_stock();

    return e[0] == SETTINGS_ID && e[1] == SETTINGS_OFFSET && e[2] == SETTINGS_SIZE
        && m[0] == SETTINGS_ITEMS && m[1 + CLICKER * MENU_ITEM_WORDS + 6] == CLICKER_ITEM;
}

/* After the payload is in place (its .bss is cleared by then). */
void settings_install(void)
{
    volatile uint32_t *src = settings_stock();
    volatile uint32_t *dst = RAM(PAYLOAD_SYM_SETTINGS_MENU);
    volatile uint32_t *e = RAM(SETTINGS_ENTRY);
    volatile uint32_t *item;
    unsigned i, n = 0;

    dst[n++] = SETTINGS_ITEMS + FROGGER_ITEMS;
    for (i = 0; i < SETTINGS_ITEMS * MENU_ITEM_WORDS; i++) {
        dst[n++] = src[1 + i];
        if (i == (CLICKER + 1) * MENU_ITEM_WORDS - 1) {
            item = &dst[n];
            for (unsigned w = 0; w < MENU_ITEM_WORDS; w++)
                dst[n++] = src[1 + CLICKER * MENU_ITEM_WORDS + w];
            /* word 5: 0x03NN + label (NN counts the value rows: Clicker is 0x0f) */
            item[5] = 0x03100000u | FROGGER_STR_HIDDEN;
            item[6] = FROGGER_ITEM_HIDDEN;
            item[8] = FROGGER_STR_HIDDEN;
            item = &dst[n];
            for (unsigned w = 0; w < MENU_ITEM_WORDS; w++)
                dst[n++] = src[1 + CLICKER * MENU_ITEM_WORDS + w];
            item[5] = 0x03110000u | FROGGER_STR_LETTERS;
            item[6] = FROGGER_ITEM_LETTERS;
            item[8] = FROGGER_STR_LETTERS;
            item = &dst[n];
            for (unsigned w = 0; w < MENU_ITEM_WORDS; w++)
                dst[n++] = src[1 + CLICKER * MENU_ITEM_WORDS + w];
            item[5] = 0x03120000u | FROGGER_STR_RESUME;
            item[6] = FROGGER_ITEM_RESUME;
            item[8] = FROGGER_STR_RESUME;
            for (unsigned f = 0; f < FEATURES; f++) {   /* the feature switches */
                item = &dst[n];
                for (unsigned w = 0; w < MENU_ITEM_WORDS; w++)
                    dst[n++] = src[1 + CLICKER * MENU_ITEM_WORDS + w];
                item[5] = (0x03130000u + (f << 16)) | (FROGGER_STR_FEATURE + f);
                item[6] = FROGGER_ITEM_FEATURE + f;
                item[8] = FROGGER_STR_FEATURE + f;
            }
            item = &dst[n];                             /* Flash Storage: Off, Auto, On */
            for (unsigned w = 0; w < MENU_ITEM_WORDS; w++)
                dst[n++] = src[1 + CLICKER * MENU_ITEM_WORDS + w];
            item[5] = (0x03130000u + (FEATURES << 16)) | FROGGER_STR_FLASH;
            item[6] = FROGGER_ITEM_FLASH;
            item[8] = FROGGER_STR_FLASH;
        }
    }
    e[1] = PAYLOAD_SYM_SETTINGS_MENU - (BUNDLE + BUNDLE_DATA);
    e[2] = n * 4;
}

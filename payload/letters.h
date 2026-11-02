#ifndef FROGGER_LETTERS_H
#define FROGGER_LETTERS_H

/* Jump by letter (letters.c). Once the wheel moves LETTER_RUN rows within
 * LETTER_FAST_US microseconds, every LETTER_ROWS rows' worth of wheel moves a
 * letter instead, in lists of at least LETTER_MIN_ROWS rows. */
#define LETTER_RUN      3
#define LETTER_FAST_US  150000
#define LETTER_ROWS     3
#define LETTER_MIN_ROWS 40

/* The title while jumping: the letter, under two string ids taken in turn,
 * since the title only fetches its text again when the id changes (both
 * free in Apple's bundle, tests/test_settings.py). */
#define LETTER_STR      0x3f14
#define LETTER_STR2     0x3f15
/* The title is back once the wheel has been still this long. */
#define LETTER_TITLE_US 800000

#ifndef __ASSEMBLER__
#include <stdint.h>

int32_t letter_step(uint32_t widget, int32_t step);
extern volatile uint32_t letter_prop;
extern volatile uint32_t letter_title;
extern volatile uint8_t letter_setting;
const void *letter_resource(uint32_t fourcc, uint32_t id, uint32_t *size);
void letter_tick(void);
#endif

#endif

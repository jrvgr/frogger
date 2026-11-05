#ifndef FROGGER_LOCK_H
#define FROGGER_LOCK_H

/* Lock Cover (lock.c): with Hold on and a song playing or paused, the screen
 * shows the cover large, the title and the progress bar. */

#define LOCK_ART        108         /* the 72x72 cover at 1.5x, nearest neighbour */
#define LOCK_ART_TOP    2
#define LOCK_ART_LEFT   ((160 - LOCK_ART) / 2)
#define LOCK_TITLE_TOP  113         /* a 5x7 line (8 rows with descenders) */
#define LOCK_BAR_TOP    123         /* the progress bar: 3 rows, as wide as the cover */
#define LOCK_BAR_ROWS   3

#ifndef __ASSEMBLER__
#include <stdint.h>

/* Set by lock_tick when Lock Cover could show (the switch on, a song
 * playing or paused): lcd_hook then asks lock_lcd. */
extern volatile uint8_t lock_armed;
/* lcd_hook, while lock_armed: 1 to skip Apple's flush of rect. */
int lock_lcd(uint32_t display, const int32_t *rect);
/* tick_hook: Hold on or off, a new song, the bar moved. */
void lock_tick(void);
/* Whether the lock screen is on the LCD (nowplaying.c's slide leaves it). */
int lock_shown(void);
#endif

#endif

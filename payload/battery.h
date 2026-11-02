#ifndef FROGGER_BATTERY_H
#define FROGGER_BATTERY_H

/* The battery as a percentage in the title bar (battery.c). docs/re-notes.md,
 * "The battery icon", has the firmware side. */

/* The states the bar's battery takes (0x42af4): 0-2 charging (animated), 3
 * charged, BATTERY_LEVEL0 + level for levels 0..15 on battery, 20 the low-battery
 * text, 21 nothing (no reading yet). Each is a child of the container
 * (None 0x3342), shown by 0xe0c9c(container, state). */
#define BATTERY_LEVEL0   4
#define BATTERY_LEVELS   16

/* The level children's bitmaps (Apple's, 25 x 10, 2 bits): the first two
 * show our percentage instead, taken in turn so the new text repaints. */
#define BATTERY_BMAP     0x2594
#define BATTERY_W        25
#define BATTERY_H        10
#define BATTERY_ROW      8              /* bytes per row: 50 bits, padded to 4 bytes */

#ifndef __ASSEMBLER__
#include <stdint.h>

int32_t battery_read(uint32_t *raw);
uint32_t battery_state(uint32_t bar);
const void *battery_resource(uint32_t fourcc, uint32_t id, uint32_t *size);
#endif

#endif

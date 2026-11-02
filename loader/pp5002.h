/* PP5002 registers the loader touches. Addresses from Rockbox's
 * firmware/export/pp5002.h (reverse engineered by Rockbox and iPodLinux;
 * there is no public PortalPlayer datasheet). */
#ifndef FROGGER_PP5002_H
#define FROGGER_PP5002_H

#include <stdint.h>

#define REG8(a)  (*(volatile uint8_t *)(a))
#define REG32(a) (*(volatile uint32_t *)(a))

#define DRAM_START       0x28000000u

#define PROCESSOR_ID     REG32(0xc4000000)
#define PROC_ID_CPU      0x55
#define PROC_ID_COP      0xaa

#define GPIOA_ENABLE     REG8(0xcf000000)
#define GPIOA_OUTPUT_EN  REG8(0xcf000010)
#define GPIOA_INPUT_VAL  REG8(0xcf000030)

/* iPod 3G button lines on GPIO A, all active low (button-1g-3g.c). */
#define BTN_RIGHT        0x01
#define BTN_SELECT       0x02
#define BTN_PLAY         0x04
#define BTN_LEFT         0x08
#define BTN_MENU         0x10
#define BTN_HOLD         0x20 /* 3G: stock 2.3 reads high as hold on (re-notes.md, Key input) */

#endif

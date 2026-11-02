#ifndef FROGGER_DEBUG_H
#define FROGGER_DEBUG_H

/* The debug record (debug.c): a trail of the bytecode pcs vm_hook hands to
 * C, and the registers of the last crash, kept where a reset doesn't clear
 * them and written to iPod_Control/iTunes/FroggerDebug on the next boot.
 *
 * It lives at the top of the gap after the loader's appended copy (which
 * ends at 0x346368 + the loader's size), below 0x360000: Apple's boot neither
 * loads nor clears anything there. loader/Makefile checks that the loader
 * stays below it. */
#define DEBUG_ADDR      0x35f800
#define DEBUG_END       0x360000
#define DEBUG_MAGIC     0x46524442      /* 'FRDB' */
#define DEBUG_TRAIL     128             /* trail entries kept */
#define DEBUG_STACK     32              /* words of the crashed code's stack */
#define DEBUG_CRASH     0xc0de0000      /* trail entries a crash adds: | kind */

#ifndef __ASSEMBLER__
#include <stdint.h>

void debug_vm(uint32_t pc, uint32_t to);
void crash_note(const uint32_t *frame, uint32_t kind, uint32_t spsr, uint32_t sp, uint32_t lr);
void debug_tick(void);
#endif

#endif

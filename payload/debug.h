#ifndef FROGGER_DEBUG_H
#define FROGGER_DEBUG_H

/* The debug record (debug.c): a trail of the bytecode pcs vm_hook hands to
 * C, and the registers of the last crash, kept where a reset doesn't clear
 * them and written to iPod_Control/iTunes/FroggerDebug on the next boot.
 *
 * It lives at the top of the gap after the loader's appended copy (which
 * ends at 0x346368 + the loader's size), below 0x360000: Apple's boot neither
 * loads nor clears anything there. loader/Makefile checks that the loader
 * stays below it (a loader of up to 72 KiB). 32 KiB: a whole session's trail
 * (a device's runs of a few minutes wrote 200-900 entries; 128 lost the
 * start of every one). */
#define DEBUG_ADDR      0x358000
#define DEBUG_END       0x360000
#define DEBUG_MAGIC     0x46524442      /* 'FRDB' */
#define DEBUG_TRAIL     3400            /* trail entries kept */
#define DEBUG_NOTES     256             /* C-side notes kept (debug_note) */
#define DEBUG_STACK     32              /* words of the crashed code's stack */
#define DEBUG_CRASH     0xc0de0000      /* trail entries a crash adds: | kind */

#ifndef __ASSEMBLER__
#include <stdint.h>

void debug_vm(uint32_t pc, uint32_t to);
/* A note from the C side (tag: DEBUG_TAG, four letters; two values) in the
 * record's own list, which the VM trail doesn't push out. A no-op in normal
 * builds. */
#define DEBUG_TAG(a, b, c, d)   ((uint32_t)(a) | (uint32_t)(b) << 8 | (uint32_t)(c) << 16 | (uint32_t)(d) << 24)
#ifdef FROGGER_DEBUG
void debug_note(uint32_t tag, uint32_t a, uint32_t b);
#else
#define debug_note(tag, a, b)   ((void)(tag), (void)(a), (void)(b))
#endif
void crash_note(const uint32_t *frame, uint32_t kind, uint32_t spsr, uint32_t sp, uint32_t lr);
void debug_tick(void);
#endif

#endif

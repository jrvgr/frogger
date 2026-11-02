#ifndef FROGGER_RESUME_H
#define FROGGER_RESUME_H

/* Resume for long tracks (resume.c): Apple's own audiobook bookmark, switched
 * on for every track of RESUME_MIN_MS or longer. docs/re-notes.md, "Bookmarks
 * (resume)", has the player code it relies on. */

#define RESUME_MIN_MS    (20u * 60 * 1000)  /* 20 minutes and up */
#define RESUME_BACK_MS   5000u              /* start this much before where it was left */
#define RESUME_END_MS    15000u             /* left this close to the end: finished, start over */

/* The player's flags for the loaded track ([player+0x2380], from 0xb7efc):
 * 0x40 means "bookmarkable", which Apple sets only for a path ending in .m4b
 * (0xc0 for Audible). */
#define PLAYER_BOOKMARK  0x40u

#ifndef __ASSEMBLER__
#include <stdint.h>

uint32_t resume_flags(uint32_t flags, uint32_t track);
uint32_t resume_start(uint32_t pos, uint32_t player);
uint32_t resume_save(uint32_t pos, uint32_t track);
void resume_flush(uint32_t lib);
#endif

#endif

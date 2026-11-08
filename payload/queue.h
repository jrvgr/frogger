#ifndef FROGGER_QUEUE_H
#define FROGGER_QUEUE_H

/* Up Next, a hidden playlist of its own (queue.c). docs/re-notes.md,
 * "On-The-Go and the play queue", has the objects and how they were found. */

/* fn 191, the Playlists list's hold handler: the bytecode pc of its guard
 * that skips row 0 (On-The-Go can't be added to itself). local0 is the
 * highlighted row there. */
#define QUEUE_FN_HOLD   0x195ced

/* queue_next's answer when there's no song after (hooks.S returns 0 for
 * it): every one left in the queue was taken out in Up Next. */
#define QUEUE_NO_NEXT   1

#ifndef __ASSEMBLER__
#include <stdint.h>

void queue_added(uint32_t lib, uint32_t first);
uint32_t queue_next(uint32_t player, uint32_t list, uint32_t key, uint32_t flags);
uint32_t queue_next_orig(uint32_t player, uint32_t list, uint32_t key, uint32_t flags);
uint32_t queue_vm(uint32_t pc, uint32_t vm);
void queue_begin_add(void);
void queue_end_add(void);
void queue_keep(uint32_t lib);
void queue_add_items(uint32_t src, const uint32_t *idx, unsigned n);
void queue_add_after_album(uint32_t src);
/* Up Next (holdmenu.c) */
uint32_t queue_list(void);
unsigned queue_waiting(uint32_t *idx, unsigned max);
void queue_play(uint32_t i);
void queue_remove(uint32_t i);
void queue_clear_waiting(void);
#endif

#endif

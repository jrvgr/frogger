#ifndef FROGGER_BROWSE_H
#define FROGGER_BROWSE_H

/* The Music lists' browse state, for the hold menu's Go to Album, Go to
 * Artist and Hide (browse.c), Play Album Next's songs and Up Next's list. */

#include <stdint.h>

/* The origin list's kind, which says which list's widget gets its row back. */
enum { LIST_OTHER, LIST_SONGS, LIST_ALBUMS, LIST_ARTISTS };

void browse_held(void);
void browse_save(int kind, uint32_t row);
void browse_restore(void);
void browse_drop(void);      /* forget what browse_save kept */
uint32_t browse_album_row(uint32_t track);
uint32_t browse_artist_row(uint32_t track);
unsigned browse_album_items(uint32_t track, int after, uint32_t *list, uint32_t *idx, uint32_t *nums, unsigned max);
uint32_t browse_playing(void);
int browse_row_hidden(int kind, uint32_t row);
/* hiddenrow.c: level's array (0-3) built again, the list refreshed, its cursor on row. */
void browse_rebuild(unsigned level, uint32_t widget, uint32_t row);
/* Up Next: the songs list shows these items of list. */
void browse_items(uint32_t list, const uint32_t *idx, unsigned n, int fresh, uint32_t row);
/* Whether the songs array is still the one browse_items put in. */
int browse_items_shown(void);

#endif

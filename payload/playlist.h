#ifndef FROGGER_PLAYLIST_H
#define FROGGER_PLAYLIST_H

/* "Add to Playlist" (playlist.c), driven by the hold menu (holdmenu.c). */

#include <stdint.h>

void playlist_begin_add(void);
int playlist_end_add(void);
void playlist_pick(uint32_t row);
void playlist_cancel(void);
void playlist_load_saved(void);
uint32_t playlist_scratch(void);

/* The Playlists title (pool constant 0x85), which the picker renames. */
#define PLAYLISTS_TITLE 0xfff2

/* Empties a playlist the way Clear Playlist does, but leaves the list on
 * screen alone. */
void list_empty(uint32_t list);

#endif

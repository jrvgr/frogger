#ifndef FROGGER_PLAYLIST_H
#define FROGGER_PLAYLIST_H

/* "Add to Playlist" (playlist.c), driven by the hold menu (holdmenu.c). */

#include <stdint.h>

void playlist_begin_add(void);
int playlist_end_add(void);
void playlist_pick(uint32_t row);
void playlist_cancel(void);
void playlist_flush(void);
void playlist_tick(void);
void playlist_load_saved(void);
uint32_t playlist_scratch(void);

/* iPod_Control/iTunes/FroggerPlaylist_<id>: a synced playlist's songs after
 * an Add to Playlist, <id> its persistent id (mhyp+0x1c, which the playlist
 * object keeps at +0x14) as 16 hex digits, upper case. This 24-byte header,
 * then `count` entries of entry_size bytes, the songs in order, each a track
 * key (tracks.h). All little-endian. stamp is the iTunesDB's (0x77600) when
 * it was written, for information. Songs no longer in the database are left
 * out when it's read back. A playlist without an id (0) gets the old file,
 * FroggerPlaylist_I in Apple's On-The-Go format (docs/file-formats.md). */
#define PLAYLIST_FILE_MAGIC   0x50475246u   /* "FRGP" */
#define PLAYLIST_FILE_VERSION 1
struct playlist_file_header {
    uint32_t magic;
    uint16_t version, entry_size;       /* 1, 20 */
    uint32_t stamp;
    uint32_t count;
    uint32_t id_lo, id_hi;              /* the playlist's, as in the name */
};

/* The Playlists title (pool constant 0x85), which the picker renames. */
#define PLAYLISTS_TITLE 0xfff2

/* Empties a playlist the way Clear Playlist does, but leaves the list on
 * screen alone. */
void list_empty(uint32_t list);

#endif

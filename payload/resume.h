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
#include "tracks.h"

/* iPod_Control/iTunes/FroggerBookmarks: where each track of RESUME_MIN_MS or
 * more was left (its bookmark, track+0x60, when not 0), by key (tracks.h).
 * This 20-byte header (as FroggerHidden's, hide.h), then `count` entries of
 * entry_size bytes: the key and the bookmark in ms. All u32, little-endian.
 * stamp is the iTunesDB's (0x77600) when it was written: with that database
 * Play Counts has the same bookmarks, so the file is used only once the
 * stamp differs (another sync), for the tracks that came without a bookmark.
 * docs/file-formats.md. */
#define BOOKMARK_FILE_MAGIC   0x42475246u   /* "FRGB" */
#define BOOKMARK_FILE_VERSION 1
struct bookmark_file_header {
    uint32_t magic;
    uint16_t version, entry_size;       /* 1, 24 */
    uint32_t stamp;
    uint32_t count;
    uint32_t reserved;
};
struct bookmark_entry {
    struct track_key key;
    uint32_t ms;
};

uint32_t resume_flags(uint32_t flags, uint32_t track);
uint32_t resume_start(uint32_t pos, uint32_t player);
uint32_t resume_save(uint32_t pos, uint32_t track);
void resume_flush(uint32_t lib);
void bookmarks_save(void);
void bookmarks_tick(void);
#endif

#endif

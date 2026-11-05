#ifndef FROGGER_TRACKS_H
#define FROGGER_TRACKS_H

/* The loaded iTunesDB's tracks (tracks.c), and how Frogger's files name one:
 * by a key that survives another app's sync, not by the track's position in
 * the database (docs/file-formats.md).
 *
 * A key is the mhit's dbid (+0x70, 64 bits, the persistent id iTunes and
 * most syncing apps keep for a song), its track id (+0x10), size in bytes
 * (+0x24) and length in ms (+0x28). A key matches the track with the same
 * dbid; if there's none (or the key has no dbid), the track with the same
 * id, size and length, as long as one of the two has no dbid. Otherwise the
 * entry is for a song that isn't there any more, and it's dropped. */

#define MAX_TRACKS      16384           /* tracks Frogger's files can name */
#define TRACK_KEY_BYTES 20

#ifndef __ASSEMBLER__
#include <stdint.h>

struct track_key {
    uint32_t dbid_lo, dbid_hi;          /* mhit+0x70 */
    uint32_t id;                        /* mhit+0x10 */
    uint32_t size;                      /* mhit+0x24 */
    uint32_t length;                    /* mhit+0x28, ms */
};

/* track_hook, for every track record as the database loads (mhit: its header). */
void tracks_loaded(uint32_t record, uint32_t pos, const uint32_t *mhit);
/* tick_hook: builds the lookup once a database has loaded. */
void tracks_tick(void);

uint32_t tracks_gen(void);              /* databases loaded so far */
int tracks_ready(void);                 /* this database's lookup is built */
uint32_t tracks_total(void);            /* tracks in the database (positions) */
uint32_t tracks_count(void);            /* of them, the first MAX_TRACKS: the ones with keys */
uint32_t tracks_record(uint32_t pos);   /* 0 if pos >= tracks_count() */
int tracks_position(uint32_t record, uint32_t *pos);
void tracks_key(uint32_t pos, struct track_key *k);
int tracks_find(const struct track_key *k);     /* its position, or -1 */

/* Frogger's files in iPod_Control\iTunes (on the UI thread: one at a time).
 * file_create creates or empties it. */
int file_open(const char *name);
int file_create(const char *name);
int file_read(void *data, uint32_t len);        /* 1 if all len bytes came */
void file_write(const void *data, uint32_t len);
void file_close(void);
#endif

#endif

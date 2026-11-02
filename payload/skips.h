#ifndef FROGGER_SKIPS_H
#define FROGGER_SKIPS_H

/* Skip counts (skips.c): a song left with Next or for another song, after
 * SKIP_MIN_MS and before SKIP_MAX_MS of it (iTunes' rule), counts as skipped. */
#define SKIP_MIN_MS      2000u
#define SKIP_MAX_MS      20000u

/* 0xb81d4(player, flags)'s flag for a song that played to its end (0xb7840
 * passes it; the Next button's 0xaca28 and Up Next pass 0). */
#define NEXT_AT_END      0x10u

#ifndef __ASSEMBLER__
#include <stdint.h>

/* iPod_Control/iTunes/FroggerSkips: the songs skipped on the iPod since the
 * last sync, for Crate. This 20-byte header (as FroggerHidden's, hide.h), then
 * `count` entries of entry_size bytes: the track's position in the iTunesDB
 * (the mhit's index in the mhlt, from 0), its track id (mhit+0x10), its skips
 * and the time of the last one (seconds since 1904, local time: the clock of
 * Play Counts' "last played", 0xa065c). All u32, little-endian. stamp is the
 * iTunesDB's (0x77600): after a sync it no longer matches and the file is
 * ignored. */
#define SKIP_FILE_MAGIC   0x53475246u   /* "FRGS" */
#define SKIP_FILE_VERSION 1
struct skip_file_header {
    uint32_t magic;
    uint16_t version, entry_size;       /* 1, 16 */
    uint32_t stamp;
    uint32_t count;
    uint32_t reserved;
};

void skips_next(uint32_t player, uint32_t flags);
void skips_pick(uint32_t player, uint32_t item, uint32_t from);
void skips_keep(uint32_t lib);
void skips_save(void);
void skips_tick(void);
#endif

#endif

#ifndef FROGGER_HIDE_H
#define FROGGER_HIDE_H

/* A track whose mhit has this word at +0x98 is hidden. The firmware reads
 * that header word but never uses it, and nothing else writes it. "HIDE",
 * read as a little-endian word. */
#define HIDE_MHIT_OFFSET 0x98
#define HIDE_MAGIC 0x45444948

#ifndef __ASSEMBLER__
#include <stdint.h>

/* Shared with hooks.S, which uses the byte offsets. */
struct hide_state {
    uint8_t is_master;  /* +0: playlist being loaded is the master (library) */
    uint8_t show_all;   /* +1: Settings › Show Hidden (settings.c): hide nothing */
    uint8_t pad[2];
    uint32_t master;    /* +4: master playlist object */
};

extern struct hide_state hide_state;

/* iPod_Control/iTunes/FroggerHidden: the songs hidden (the hold menu's
 * Hide) or shown again (Show) on the iPod, for Crate to read on the next
 * sync. This 20-byte header, then `count` entries of entry_size bytes: the
 * track's position in the iTunesDB (the mhit's index in the mhlt, from 0),
 * its track id (mhit+0x10) and flags (HIDE_ENTRY_SHOWN: shown, else hidden;
 * version 1 had no flags word, entry_size 8, all hidden). All u32,
 * little-endian. stamp is the iTunesDB's (0x77600, as Apple's On-The-Go
 * files carry): after a sync it no longer matches and the file is ignored. */
#define HIDE_FILE_MAGIC   0x48475246u   /* "FRGH" */
#define HIDE_FILE_VERSION 2
#define HIDE_ENTRY_SHOWN  1u
struct hide_file_header {
    uint32_t magic;
    uint16_t version, entry_size;       /* 2, 12 */
    uint32_t stamp;
    uint32_t count;
    uint32_t reserved;
};

void hide_reset(void);
void hide_mark(uint32_t track);
int hide_track(uint32_t track);
int hide_entry(uint32_t owner, uint32_t track);
void hide_loaded(uint32_t record, uint32_t pos, uint32_t id);
void hide_add(uint32_t track);
void hide_show(uint32_t track);
void hide_save(void);
void hide_tick(void);
uint32_t hide_gen(void);
uint32_t hide_tracks(void);
int hide_position(uint32_t track, uint32_t *id);
uint32_t hide_record(uint32_t pos, uint32_t id);
#endif

#endif

/* The loaded database's tracks: what each track record is (its position in
 * the iTunesDB and its key, tracks.h), for Frogger's files, which name songs
 * by key so they still find them after another app has synced (a new
 * iTunesDB, other positions and track ids). docs/file-formats.md.
 *
 * track_hook hands us each record as the track loader makes it, with the
 * mhit header it was made from: the firmware's track record keeps neither the
 * position nor the dbid (re-notes, "Browsing the Music lists": +0x1c is not
 * the id, and the loader never reads mhit+0x70). Records are allocated in
 * blocks of 100 (on a real library), one after another within a block and
 * the blocks anywhere, so a record's position is found from where each run
 * of evenly spaced records starts (art.c used to do this alone); with too
 * many runs, a search of the table. Once the database has loaded (tracks_tick)
 * two hash tables find a key's track: by dbid, and by track id. */

#include <stdint.h>
#include "tracks.h"

static uint32_t track_rec[MAX_TRACKS], track_id[MAX_TRACKS], dbid_lo[MAX_TRACKS], dbid_hi[MAX_TRACKS];
static uint32_t size[MAX_TRACKS], length[MAX_TRACKS];
static uint32_t n_stored, total, gen, built;

#define MAX_RUNS 240     /* blocks of 100 tracks: room for some 24000 */
static struct {
    uint32_t spacing, n_runs, last;
    int broken;
    struct { uint32_t record, pos; } run[MAX_RUNS];
} runs;

/* Hash tables of position + 1 (0: empty), open addressing. */
#define HASH_BITS 15
#define HASH_SIZE (1u << HASH_BITS)
static uint16_t by_dbid[HASH_SIZE], by_id[HASH_SIZE];

static uint32_t hash(uint32_t v)
{
    return (v * 2654435761u) >> (32 - HASH_BITS);
}

void tracks_loaded(uint32_t record, uint32_t pos, const uint32_t *mhit)
{
    if (pos == 0) {
        gen++;
        n_stored = 0;
        runs.spacing = runs.n_runs = 0;
        runs.broken = 0;
    } else if (!runs.spacing && record > runs.last && record - runs.last < 0x1000) {
        runs.spacing = record - runs.last;      /* the record size: the first two in a row */
    }
    if (pos == 0 || !runs.spacing || record != runs.last + runs.spacing) {
        if (runs.n_runs == MAX_RUNS) {
            runs.broken = 1;
        } else {
            runs.run[runs.n_runs].record = record;
            runs.run[runs.n_runs].pos = pos;
            runs.n_runs++;
        }
    }
    runs.last = record;
    total = pos + 1;
    if (pos < MAX_TRACKS) {
        track_rec[pos] = record;
        track_id[pos] = mhit[0x10 / 4];
        size[pos] = mhit[0x24 / 4];
        length[pos] = mhit[0x28 / 4];
        dbid_lo[pos] = mhit[0x70 / 4];
        dbid_hi[pos] = mhit[0x74 / 4];
        n_stored = pos + 1;
    }
}

static void insert(uint16_t *table, uint32_t v, uint32_t pos)
{
    uint32_t i = hash(v), n;

    for (n = 0; n < HASH_SIZE && table[i]; n++)
        i = (i + 1) & (HASH_SIZE - 1);
    if (n < HASH_SIZE)
        table[i] = (uint16_t)(pos + 1);
}

void tracks_tick(void)
{
    uint32_t i;

    if (built == gen || !n_stored)
        return;
    for (i = 0; i < HASH_SIZE; i++)
        by_dbid[i] = by_id[i] = 0;
    for (i = 0; i < n_stored; i++) {
        if (dbid_lo[i] | dbid_hi[i])
            insert(by_dbid, dbid_lo[i] ^ dbid_hi[i], i);
        insert(by_id, track_id[i], i);
    }
    built = gen;
}

uint32_t tracks_gen(void)
{
    return gen;
}

int tracks_ready(void)
{
    return gen && built == gen;
}

uint32_t tracks_total(void)
{
    return total;
}

uint32_t tracks_count(void)
{
    return n_stored;
}

uint32_t tracks_record(uint32_t pos)
{
    return pos < n_stored ? track_rec[pos] : 0;
}

int tracks_position(uint32_t record, uint32_t *pos)
{
    uint32_t i;

    if (!record)
        return 0;
    if (runs.broken) {
        for (i = 0; i < n_stored; i++)
            if (track_rec[i] == record) {
                *pos = i;
                return 1;
            }
        return 0;
    }
    for (i = 0; i < runs.n_runs; i++) {
        uint32_t start = runs.run[i].record, off = record - start;
        uint32_t n = (i + 1 < runs.n_runs ? runs.run[i + 1].pos : total) - runs.run[i].pos;
        if (record < start)
            continue;
        if (runs.spacing ? off % runs.spacing == 0 && off / runs.spacing < n : off == 0) {
            *pos = runs.run[i].pos + (runs.spacing ? off / runs.spacing : 0);
            return 1;
        }
    }
    return 0;
}

void tracks_key(uint32_t pos, struct track_key *k)
{
    if (pos >= n_stored) {
        k->dbid_lo = k->dbid_hi = k->id = k->size = k->length = 0;
        return;
    }
    k->dbid_lo = dbid_lo[pos];
    k->dbid_hi = dbid_hi[pos];
    k->id = track_id[pos];
    k->size = size[pos];
    k->length = length[pos];
}

int tracks_find(const struct track_key *k)
{
    uint32_t i, n, p, has_dbid = k->dbid_lo | k->dbid_hi;

    if (!tracks_ready())
        return -1;
    if (has_dbid)
        for (i = hash(k->dbid_lo ^ k->dbid_hi), n = 0; n < HASH_SIZE && by_dbid[i]; n++, i = (i + 1) & (HASH_SIZE - 1)) {
            p = by_dbid[i] - 1u;
            if (dbid_lo[p] == k->dbid_lo && dbid_hi[p] == k->dbid_hi)
                return (int)p;
        }
    for (i = hash(k->id), n = 0; n < HASH_SIZE && by_id[i]; n++, i = (i + 1) & (HASH_SIZE - 1)) {
        p = by_id[i] - 1u;
        if (track_id[p] == k->id && size[p] == k->size && length[p] == k->length
            && (!has_dbid || !(dbid_lo[p] | dbid_hi[p])))
            return (int)p;
    }
    return -1;
}

/* The firmware's file calls (docs/re-notes.md, "Files"; hide.c has the same). */
#define make_path   ((uint32_t (*)(void *out, uint32_t kind, const char *dir, const char *name))0x53a24)
#define find_path   ((uint32_t (*)(void *out, const char *name))0x7b3bc)
#define fw_open     ((int (*)(void *path, void *file, uint32_t mode, uint32_t type))0x403fc)
#define fw_create   ((int (*)(void *path, void *file, uint32_t zero, uint32_t type))0x40474)
#define fw_read     ((int (*)(void *file, uint32_t *len, void *data))0x404ec)
#define fw_write    ((int (*)(void *file, uint32_t *len, const void *data))0x407e8)
#define fw_close    ((int (*)(void *))0x40110)
#define ITUN        0x6974756eu
#define FW_READ     0x20000
#define FW_DATA     0x64617461u

static uint32_t path[0x108 / 4], file[0x80 / 4];

static void clear(void)
{
    uint32_t i;

    for (i = 0; i < sizeof path / 4; i++)
        path[i] = 0;
    for (i = 0; i < sizeof file / 4; i++)
        file[i] = 0;
}

int file_open(const char *name)
{
    clear();
    return find_path(path, name) == 0 && fw_open(path, file, FW_READ, FW_DATA) == 0;
}

int file_create(const char *name)
{
    clear();
    return make_path(path, ITUN, "iPod_Control\\iTunes\\", name) == 0 && fw_create(path, file, 0, FW_DATA) == 0;
}

int file_read(void *data, uint32_t len)
{
    uint32_t got = len;

    return fw_read(file, &got, data) == 0 && got == len;
}

void file_write(const void *data, uint32_t len)
{
    fw_write(file, &len, data);
}

void file_close(void)
{
    fw_close(file);
}

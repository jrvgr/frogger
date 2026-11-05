/* Resources Frogger adds to Apple's UI bundle, served by string_hook when the
 * bundle lookup (0x875c4) asks for them: our Settings label and the cover of
 * the song that's playing (docs/nowplaying.md).
 *
 * A BMap is a 28-byte header (8 zero bytes, height, width, bytes per row,
 * 1, 0, 0, data length) and then 2-bit pixels, top bit first, 3 = black, each
 * row padded to 4 bytes.
 *
 * Covers come from iPod_Control/iTunes/FroggerArt, which Crate writes with
 * the iTunesDB (nowplaying.h has the layout). It's indexed by a track's
 * position in the database, and the firmware's track records don't carry
 * one, so track_hook tells us where each record is as the database loads.
 * They're allocated in blocks of 100 (on a real library), one after another
 * within a block and the blocks anywhere, so we keep where each run of evenly
 * spaced records starts. If there are too many runs, covers stay off. */

#include <stdint.h>
#include "settings.h"
#include "nowplaying.h"
#include "holdmenu.h"
#include "letters.h"
#include "battery.h"

#define FOURCC_STR  0x53747220u
#define FOURCC_BMAP 0x424d6170u

#define ART_SIZE NP_ART_SIZE
#define ART_ROW  NP_ART_ROW

/* The cover-art Now Playing View; the loader fills it (loader/nowplaying.c). */
uint32_t np_view[NP_VIEW_SIZE / 4];

static struct {
    uint32_t zero[2];
    uint32_t height, width;
    uint16_t row, depth, d5, format;
    uint32_t length;
    uint8_t px[NP_ART_BYTES];
} art;

/* Where the track records are (np_track_loaded): runs of records `spacing`
 * apart, each from its first record and position to the next run's. */
#define MAX_RUNS 240     /* blocks of 100 tracks: room for some 24000 */
static struct {
    uint32_t spacing, count, n_runs, last;
    int broken;
    struct { uint32_t record, pos; } run[MAX_RUNS];
} records;

/* The firmware's file calls (docs/re-notes.md, "Files"). A path is a volume
 * word and then a DOS-style name. */
struct fw_path { uint32_t volume; char name[0x104]; };
#define fw_volume ((uint32_t (*)(void))0xb1d50)
#define fw_open   ((int (*)(struct fw_path *, void *, uint32_t, uint32_t))0x403fc)
#define fw_read   ((int (*)(void *, uint32_t *, void *))0x404ec)
#define fw_seek   ((int (*)(void *, uint32_t, uint32_t))0x4069c)
#define fw_close  ((int (*)(void *))0x40110)
#define FW_READ   0x20000
#define FW_DATA   0x64617461u   /* 'data' */

static struct fw_path art_path;
static uint32_t art_file[0x80 / 4];
static const char art_name[] = "iPod_Control\\iTunes\\FroggerArt";

static void art_header(void)
{
    art.height = art.width = ART_SIZE;
    art.row = ART_ROW;
    art.depth = 2;          /* bits per pixel (1 is a 1-bit BMap, like the ">" arrow 0x2579) */
    art.length = sizeof art.px;
}

/* What art.px holds: an image index from the file, or the "no cover" frame,
 * ART_FRAME + why. The frame shows why (art_none), so a device tells which
 * step went wrong. The read failures (ART_IO) are tried again when Now
 * Playing next opens. */
enum {
    WHY_NO_COVER,       /* the file has none for this song */
    WHY_NO_POSITION,    /* the track isn't one we saw load (or too many runs) */
    WHY_OPEN,           /* the file didn't open */
    WHY_HEADER_READ,
    WHY_HEADER,         /* not a FroggerArt this payload reads */
    WHY_TRACK_COUNT,    /* made for another database than the one loaded */
    WHY_INDEX_READ,
    WHY_IMAGE_READ,
};
#define ART_FRAME   0xff00u
#define ART_IO(s)   ((s) == ART_FRAME + WHY_OPEN || (s) == ART_FRAME + WHY_HEADER_READ \
                     || (s) == ART_FRAME + WHY_INDEX_READ || (s) == ART_FRAME + WHY_IMAGE_READ)
static uint32_t art_shown = ART_FRAME;

/* The frog in the middle of the "no cover" frame: 24x17, BMap rows. */
#define FROG_W  24
#define FROG_H  17
static const uint8_t frog[FROG_H][FROG_W / 4] = {
    { 0x00, 0xff, 0x00, 0x00, 0xff, 0x00 },
    { 0x03, 0x55, 0xc0, 0x03, 0x55, 0xc0 },
    { 0x0d, 0x00, 0x70, 0x0d, 0x00, 0x70 },
    { 0x0d, 0x0f, 0x70, 0x0d, 0x0f, 0x70 },
    { 0x0d, 0x0f, 0x70, 0x0d, 0x0f, 0x70 },
    { 0x0d, 0x00, 0x7f, 0xfd, 0x00, 0x70 },
    { 0x35, 0x55, 0x55, 0x55, 0x55, 0x5c },
    { 0xd5, 0x55, 0x5d, 0x75, 0x55, 0x57 },
    { 0xd5, 0x55, 0x55, 0x55, 0x55, 0x57 },
    { 0xda, 0x55, 0x55, 0x55, 0x55, 0xa7 },
    { 0xd7, 0xf5, 0x55, 0x55, 0x5f, 0xd7 },
    { 0x35, 0x7f, 0xff, 0xff, 0xfd, 0x5c },
    { 0x0d, 0x55, 0x55, 0x55, 0x55, 0x70 },
    { 0x03, 0x55, 0x55, 0x55, 0x55, 0xc0 },
    { 0x0d, 0x7f, 0xff, 0xff, 0xfd, 0x70 },
    { 0x35, 0x5c, 0x00, 0x00, 0x35, 0x5c },
    { 0x3f, 0xfc, 0x00, 0x00, 0x3f, 0xfc },
};

/* The frog's mouth when something went wrong: rows 9-12 frown. */
static const uint8_t frog_sad[4][FROG_W / 4] = {
    { 0xd5, 0x55, 0x55, 0x55, 0x55, 0x57 },
    { 0xd5, 0x57, 0xff, 0xff, 0xd5, 0x57 },
    { 0x35, 0x7d, 0x55, 0x55, 0x7d, 0x5c },
    { 0x0d, 0x75, 0x55, 0x55, 0x5d, 0x70 },
};
#define FROG_SAD_ROW 9

/* What went wrong, as a 12x12 icon in the bottom right corner (a row per
 * 12 bits, left pixel in the high bit): the card (a read failed), a question
 * mark (the track isn't one we know), sync again (the file is another
 * database's), a warning (not a FroggerArt we read). */
#define ICON 12
static const uint16_t icon_card[ICON] = {
    0x3fc, 0x2ae, 0x2a3, 0x201, 0x285, 0x249, 0x231, 0x231, 0x249, 0x285, 0x201, 0x3ff,
};
static const uint16_t icon_question[ICON] = {
    0x1f8, 0x30c, 0x30c, 0x00c, 0x018, 0x030, 0x060, 0x060, 0x000, 0x060, 0x060, 0x000,
};
static const uint16_t icon_sync[ICON] = {
    0x0f4, 0x30c, 0x41c, 0x400, 0x800, 0x800, 0x802, 0x802, 0x404, 0x408, 0x330, 0x0c0,
};
static const uint16_t icon_warn[ICON] = {
    0x060, 0x090, 0x090, 0x168, 0x168, 0x264, 0x264, 0x402, 0x462, 0x462, 0x801, 0xfff,
};

/* And `why` itself, small in the bottom left corner, for the details: digits
 * 1-7, 3x5, a row per 3 bits, top row in the high bits. */
static const uint16_t digit[8] = {
    0, 0x2c97, 0x73e7, 0x73cf, 0x5bc9, 0x79cf, 0x79ef, 0x7249,
};

static void art_px(int x, int y, unsigned v)
{
    uint8_t *b = &art.px[y * ART_ROW + x / 4];
    int sh = 6 - 2 * (x & 3);

    *b = (uint8_t)((*b & ~(3 << sh)) | v << sh);
}

static const uint16_t *why_icon(uint32_t why)
{
    switch (why) {
    case WHY_NO_POSITION:   return icon_question;
    case WHY_HEADER:        return icon_warn;
    case WHY_TRACK_COUNT:   return icon_sync;
    case WHY_NO_COVER:      return 0;
    default:                return icon_card;
    }
}

/* No cover: a thin frame with the frog, so the page doesn't look broken. When
 * something went wrong the frog frowns, the icon says what, and `why` is in
 * the other corner. */
static void art_none(uint32_t why)
{
    const uint16_t *icon = why_icon(why);
    int x, y, top = (ART_SIZE - FROG_H) / 2;

    for (x = 0; x < (int)sizeof art.px; x++)
        art.px[x] = 0;
    for (y = 0; y < ART_SIZE; y++)
        for (x = 0; x < ART_SIZE; x++)
            if (x == 0 || y == 0 || x == ART_SIZE - 1 || y == ART_SIZE - 1)
                art_px(x, y, 2);
    for (y = 0; y < FROG_H; y++)
        for (x = 0; x < FROG_W / 4; x++)
            art.px[(top + y) * ART_ROW + (ART_SIZE - FROG_W) / 8 + x] =
                icon && y >= FROG_SAD_ROW && y < FROG_SAD_ROW + 4 ? frog_sad[y - FROG_SAD_ROW][x] : frog[y][x];
    if (!icon)
        return;
    for (y = 0; y < ICON; y++)
        for (x = 0; x < ICON; x++)
            if (icon[y] >> (ICON - 1 - x) & 1)
                art_px(ART_SIZE - 3 - ICON + x, ART_SIZE - 3 - ICON + y, 3);
    if (why < sizeof digit / sizeof digit[0])
        for (y = 0; y < 5; y++)
            for (x = 0; x < 3; x++)
                if (digit[why] >> (14 - 3 * y - x) & 1)
                    art_px(3 + x, ART_SIZE - 8 + y, 2);
}

static void copy_px(uint8_t *to, const uint8_t *from)
{
    unsigned i;

    for (i = 0; i < NP_ART_BYTES; i++)
        to[i] = from[i];
}

static int art_read(uint32_t offset, void *buf, uint32_t n)
{
    uint32_t got = n;

    return fw_seek(art_file, offset, 0) == 0 && fw_read(art_file, &got, buf) == 0 && got == n;
}

/* The cover for database position pos into art_buf, on the cover task.
 * Returns what it holds (art_shown's values); for an image, art_buf has it,
 * and an album's next song keeps the pixels it has. */
static uint8_t art_buf[NP_ART_BYTES];
static uint32_t buf_image = ART_FRAME;     /* the image art_buf holds; the task's own */

static uint32_t art_load(uint32_t pos)
{
    struct np_art_header h;
    uint16_t image;
    unsigned i;
    uint32_t got;

    art_path.volume = fw_volume();
    for (i = 0; i < sizeof art_name; i++)
        art_path.name[i] = art_name[i];
    for (i = 0; i < sizeof art_file / sizeof art_file[0]; i++)
        art_file[i] = 0;        /* nothing left over from a read that went wrong */
    if (fw_open(&art_path, art_file, FW_READ, FW_DATA) != 0)
        return ART_FRAME + WHY_OPEN;
    /* h.positions must be this database's track count: a file from before the last sync would
     * give the wrong songs' covers (Crate deletes it when it writes the database, but still) */
    if (!art_read(0, &h, sizeof h))
        got = ART_FRAME + WHY_HEADER_READ;
    else if (h.magic != NP_ART_MAGIC || h.version != NP_ART_VERSION || h.size != ART_SIZE
             || h.image_bytes != NP_ART_BYTES)
        got = ART_FRAME + WHY_HEADER;
    else if (h.positions != records.count || pos >= h.positions)
        got = ART_FRAME + WHY_TRACK_COUNT;
    else if (!art_read(sizeof h + 2 * pos, &image, 2))
        got = ART_FRAME + WHY_INDEX_READ;
    else if (image == NP_ART_NONE || image >= h.images)
        got = ART_FRAME + WHY_NO_COVER;
    else if (image == buf_image
             || art_read(np_art_images_offset(h.positions) + (uint32_t)image * NP_ART_BYTES, art_buf, NP_ART_BYTES))
        got = buf_image = image;
    else
        got = buf_image = ART_FRAME + WHY_IMAGE_READ;      /* art_buf may be half new */
    fw_close(art_file);
    return got;
}

/* track_hook, for every track record as the database loads. */
void np_track_loaded(uint32_t record, uint32_t pos)
{
    if (pos == 0) {
        records.spacing = 0;
        records.n_runs = 0;
        records.broken = 0;
    } else if (!records.spacing && record > records.last && record - records.last < 0x1000) {
        records.spacing = record - records.last;        /* the record size: the first two in a row */
    }
    if (pos == 0 || !records.spacing || record != records.last + records.spacing) {
        if (records.n_runs == MAX_RUNS) {
            records.broken = 1;
        } else {
            records.run[records.n_runs].record = record;
            records.run[records.n_runs].pos = pos;
            records.n_runs++;
        }
    }
    records.last = record;
    records.count = pos + 1;
}

/* A record's position in the database; 0 if it isn't one we saw load. */
static int position_of(uint32_t record, uint32_t *pos)
{
    uint32_t i;

    for (i = 0; i < records.n_runs; i++) {
        uint32_t start = records.run[i].record, off = record - start;
        uint32_t n = (i + 1 < records.n_runs ? records.run[i + 1].pos : records.count) - records.run[i].pos;
        if (record < start)
            continue;
        if (records.spacing ? off % records.spacing == 0 && off / records.spacing < n : off == 0) {
            *pos = records.run[i].pos + (records.spacing ? off / records.spacing : 0);
            return 1;
        }
    }
    return 0;
}

/* The track whose cover art.px should show, set by np_playing. */
static volatile uint32_t art_record;

/* play_hook, when a track starts as the song now playing (not the preload of
 * the next one). When a song ends by itself this runs on the playback side,
 * and a slow card (or a flaky CF adapter) there stalls the song change, so
 * nothing is read here: np_art_update hands the read to the cover task. */
void np_playing(uint32_t record)
{
    art_record = record;
    np_art_dirty = 1;
}

/* The cover read runs on a task of its own, FroggerArt (0xac6fc, the way
 * 0x54da8 starts TrackCacheReadTask), not on the UI's loop: a read waits for
 * the disk, behind a music-cache refill, or for 10 s and more when the drive
 * stops answering (disk.c), and the wheel and the screens must not. The UI
 * asks (job.want, job.record) and takes the answer (job.got, art_buf) when
 * job.done catches up; the task starts the next read only once the UI has
 * taken the last (job.taken), so art_buf doesn't change under the copy. */
static volatile struct { uint32_t record, want, done, taken, got; } job;
static int art_task;            /* 0 not started, 1 running, -1 couldn't be */

#define fw_thread   ((uint32_t (*)(const char *name, void (*entry)(void), const char *args, uint32_t prio, \
                                   uint32_t stack, uint32_t zero1, uint32_t zero2))0xac6fc)
#define fw_sleep    ((void (*)(uint32_t zero, uint32_t ticks))0x3460)   /* 10 ms ticks (emupod) */
#define ART_TASK_PRIO   0x40    /* TrackCacheReadTask's */
#define ART_TASK_STACK  0x2000
#define ART_POLL_TICKS  3       /* how soon the task sees a new song: 30 ms */

static uint32_t art_job(uint32_t record)
{
    uint32_t pos;

    if (records.broken || !position_of(record, &pos))
        return ART_FRAME + WHY_NO_POSITION;
    return art_load(pos);
}

static void art_task_main(void)
{
    uint32_t want;

    for (;;) {
        want = job.want;
        if (want != job.done && job.taken == job.done) {
            job.got = art_job(job.record);
            job.done = want;
        } else {
            fw_sleep(0, ART_POLL_TICKS);
        }
    }
}

/* On the UI's side (np_vm, np_tick): hands a new song to the cover task and
 * brings art.px up to date with what it read. Returns 1 if the picture
 * changed. Cheap when there's nothing to do: np_vm calls it a lot. */
int np_art_update(void)
{
    uint32_t done, got;

    if (np_art_dirty) {
        np_art_dirty = 0;
        if (!art.height) {      /* art_shown's first ART_FRAME */
            art_header();
            art_none(0);
        }
        job.record = art_record;
        job.want++;
        if (!art_task) {
            uint32_t t = fw_thread("FroggerArt", art_task_main, 0, ART_TASK_PRIO, ART_TASK_STACK, 0, 0);
            art_task = t && t < 0x80000000u ? 1 : -1;
        }
        if (art_task < 0 && job.taken == job.done) {    /* no task: read here, as before */
            job.got = art_job(job.record);
            job.done = job.want;
        }
    }
    done = job.done;
    if (done == job.taken)
        return 0;
    got = job.got;
    if (done != job.want) {     /* a newer song is asked for already */
        job.taken = done;
        return 0;
    }
    if (got != art_shown) {
        if (got >= ART_FRAME)
            art_none(got - ART_FRAME);
        else
            copy_px(art.px, art_buf);
    }
    job.taken = done;
    if (got == art_shown)
        return 0;               /* the album's cover, or the same frame, is up already */
    art_shown = got;
    return 1;
}

/* Now Playing opens: if the last cover couldn't be read, try it again. */
void np_art_retry(void)
{
    if (ART_IO(art_shown))
        np_art_dirty = 1;
}

/* The data for a resource Frogger provides, with its size in *size, or 0. */
const void *frogger_resource(uint32_t fourcc, uint32_t id, uint32_t *size)
{
    const void *hm = holdmenu_resource(fourcc, id, size);

    if (hm)
        return hm;
    if ((hm = letter_resource(fourcc, id, size)))
        return hm;
    if ((hm = battery_resource(fourcc, id, size)))
        return hm;
    if (fourcc == FOURCC_STR && id >= FROGGER_STR_FEATURE && id < FROGGER_STR_FEATURE + FEATURES) {
        const char *s = frogger_feature_labels[id - FROGGER_STR_FEATURE], *e = s;
        while (*e++)
            ;
        *size = (uint32_t)(e - s);
        return s;
    }
    if (fourcc == FOURCC_STR && id == FROGGER_STR_RESUME) {
        *size = frogger_label_resume_size;
        return frogger_label_resume;
    }
    if (fourcc == FOURCC_STR && id == FROGGER_STR_LETTERS) {
        *size = frogger_label_letters_size;
        return frogger_label_letters;
    }
    if (fourcc == FOURCC_STR && id == FROGGER_STR_HIDDEN) {
        *size = frogger_label_hidden_size;
        return frogger_label_hidden;
    }
    if (fourcc == FOURCC_BMAP && id == FROGGER_BMAP_ART) {
        if (!art.height) {
            art_header();
            art_none(0);
        }
        *size = sizeof art;
        return &art;
    }
    return 0;
}

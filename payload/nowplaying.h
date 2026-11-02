#ifndef FROGGER_NOWPLAYING_H
#define FROGGER_NOWPLAYING_H

/* The cover-art Now Playing page, shared by the loader (which adds the art
 * element to the screen's View, loader/nowplaying.c) and the payload (which
 * serves the picture, art.c, and switches pages, nowplaying.c).
 * docs/nowplaying.md has the View and object layouts.
 *
 * Apple's View 0x25ee stays as it is (9 elements: the "1 of 2" row e0-e4,
 * title, artist, album e5-e7, the progress bar widget e8), so the boot layout
 * gives Apple's page exactly. The art is a 10th element after them. The cover
 * page is made at runtime: the title bar hidden and given no height, so the
 * screen starts at the top of the display, the row, artist and album hidden,
 * and the title moved up. Select switches to Apple's page and back
 * (nowplaying.c). */

#define NP_VIEW_ID      0x25ee
#define NP_STOCK_SIZE   0x300       /* Apple's View 0x25ee */
#define NP_ART_EL_SIZE  0x4c        /* a BMap element: size word + 0x48 */
#define NP_VIEW_SIZE    (NP_STOCK_SIZE + NP_ART_EL_SIZE)

#define NP_ART_SIZE     72          /* pixels, square; a multiple of 4 */
#define NP_ART_TOP      0           /* View coordinates: 19 on the display, just below the title */
#define NP_ART_LEFT     ((160 - NP_ART_SIZE) / 2)
#define NP_BAR_HEIGHT   19          /* the title bar; the screens start below it */

/* The title's top on the cover page, on the display (its height stays). */
#define NP_TITLE_TOP    2

/* Now Playing's bytecode (docs/nowplaying.md): the normal state's Select
 * handler (fn 169) and its own "nothing to do" return, and the three ways back
 * to the normal state: Select while rating (fn 183), the 5 s timeout (fn 173)
 * and Select while scrubbing once the knob has moved (fn 172's call of fn 170;
 * unmoved, it goes on to rating). All go on into fn 170, but the rating state
 * runs that one too, so it doesn't tell. */
#define NP_FN_SELECT    0x195630
#define NP_FN_RETURN    0x1956c1
#define NP_FN_RATED     0x1959c0
#define NP_FN_TIMEOUT   0x1957de
#define NP_FN_SCRUBBED  0x1957bc
/* fn 160, Now Playing's Menu handler. */
#define NP_FN_MENU      0x1953f4

#define NP_ART_ROW      ((NP_ART_SIZE / 4 + 3) & ~3)    /* bytes per row, padded to 4 */
#define NP_ART_BYTES    (NP_ART_ROW * NP_ART_SIZE)

/* iPod_Control/iTunes/FroggerArt, written by Crate with each iTunesDB:
 * this header, then a u16 per track position in the iTunesDB (the image
 * index, or NP_ART_NONE) padded to 4 bytes, then the images, each
 * NP_ART_BYTES of BMap pixel rows (2 bits, 3 = black, top bit first). All
 * little-endian. Tracks of one album share an image. */
#define NP_ART_MAGIC    0x41475246u     /* "FRGA" */
#define NP_ART_VERSION  1
#define NP_ART_NONE     0xffff

#ifndef __ASSEMBLER__
#include <stdint.h>
extern uint32_t np_view[NP_VIEW_SIZE / 4];

struct np_art_header {
    uint32_t magic;
    uint16_t version, size;     /* size: NP_ART_SIZE */
    uint32_t positions;         /* tracks in the iTunesDB */
    uint32_t images;
    uint32_t image_bytes;       /* NP_ART_BYTES */
    uint32_t reserved;
};

static inline uint32_t np_art_images_offset(uint32_t positions)
{
    return (uint32_t)((sizeof(struct np_art_header) + 2 * positions + 3) & ~3u);
}

void np_track_loaded(uint32_t record, uint32_t pos);
void np_playing(uint32_t record);
int np_art_update(void);
void np_art_retry(void);
int np_visibility(uint32_t obj, uint32_t on);
uint32_t np_vm(uint32_t pc);
extern volatile uint8_t np_art_dirty;
int np_transition(uint32_t stack);
int np_is_open(void);
void np_drawn(void);
void np_tick(void);
/* lcd_update_rect (0xd2db4) past lcd_hook: rect is top, left, bottom, right. */
void lcd_flush(uint32_t display, const int32_t *rect);
#endif

#endif

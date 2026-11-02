/* Adds the cover-art element to Now Playing's View (payload/nowplaying.h).
 *
 * Views are laid out once at boot, so changing the resource here, before
 * Apple's OS runs, is enough. Apple's nine elements stay as they are, so the
 * layout gives Apple's page exactly; the art is appended as a tenth, where the
 * cover page shows it (the payload makes that page at runtime,
 * payload/nowplaying.c). The new View is bigger than Apple's, so it goes into
 * the payload (np_view) and the bundle's index entry points at it, as
 * settings.c does for the Settings menu. Addresses are osos's, before the
 * remap: DRAM_START + address. */

#include <stdint.h>
#include "pp5002.h"
#include "payload.h"
#include "settings.h"
#include "nowplaying.h"

#define BUNDLE      0x181d20u   /* the UI resource bundle */
#define BUNDLE_DATA 0x313cu     /* its data offset: index offsets count from here */
#define NP_ENTRY    0x184184u   /* View index entry: id, offset, size */
#define NP_OFFSET   0x1ac94u

#define FOURCC_BMAP 0x424d6170u
#define FOURCC_STR  0x53747220u
#define FOURCC_NONE 0x4e6f6e65u

#define ABS   0x80000002u       /* a coordinate as is (negative: from the far edge) */
#define SIZE  0x80000008u       /* a height */
#define SIZE4 0x80000004u       /* a width */

/* Byte offsets of Apple's elements (their size words) in View 0x25ee. */
#define EL_ICON   0x05c         /* BMap 0x25ed, the template for the art element */
#define EL_TITLE  0x198
#define EL_BAR    0x2b0         /* None 0xff33 */

#define RAM(a) ((volatile uint32_t *)(DRAM_START + (a)))

static volatile uint32_t *np_stock(void)
{
    return RAM(BUNDLE + BUNDLE_DATA + NP_OFFSET);
}

/* Word w of the element whose size word is at byte offset el. */
static uint32_t el_word(volatile uint32_t *view, unsigned el, unsigned w)
{
    return view[el / 4 + w];
}

int nowplaying_check(void)
{
    volatile uint32_t *e = RAM(NP_ENTRY), *v = np_stock();

    return e[0] == NP_VIEW_ID && e[1] == NP_OFFSET && e[2] == NP_STOCK_SIZE && v[0] == 9
        && el_word(v, EL_ICON, 2) == FOURCC_BMAP && el_word(v, EL_ICON, 3) == 0x25ed
        && el_word(v, EL_TITLE, 2) == FOURCC_STR && el_word(v, EL_TITLE, 3) == 0x3319
        && el_word(v, EL_BAR, 2) == FOURCC_NONE && el_word(v, EL_BAR, 3) == 0xff33;
}

/* Coordinate k (0 top, 1 left, 2 height, 3 width) of the element at word index el. */
static void coord(volatile uint32_t *view, unsigned el, unsigned k, uint32_t anchor, int32_t value)
{
    view[el + 7 + 3 * k] = 0;
    view[el + 8 + 3 * k] = anchor;
    view[el + 9 + 3 * k] = (uint32_t)value;
}

/* After the payload is in place (its .bss is cleared by then). */
void nowplaying_install(void)
{
    volatile uint32_t *src = np_stock();
    volatile uint32_t *dst = RAM(PAYLOAD_SYM_NP_VIEW);
    volatile uint32_t *e = RAM(NP_ENTRY);
    unsigned i, art = NP_STOCK_SIZE / 4;

    /* Apple's elements, then the art element (a copy of the icon's) last: the
     * payload takes the art being shown as "every other child is up". */
    for (i = 0; i < NP_STOCK_SIZE / 4; i++)
        dst[i] = src[i];
    for (i = 0; i < NP_ART_EL_SIZE / 4; i++)
        dst[art + i] = src[EL_ICON / 4 + i];
    dst[0] = 10;

    dst[art + 3] = FROGGER_BMAP_ART;
    coord(dst, art, 0, ABS, NP_ART_TOP);
    coord(dst, art, 1, ABS, NP_ART_LEFT);
    coord(dst, art, 2, SIZE, NP_ART_SIZE);
    coord(dst, art, 3, SIZE4, NP_ART_SIZE);

    e[1] = PAYLOAD_SYM_NP_VIEW - (BUNDLE + BUNDLE_DATA);
    e[2] = NP_VIEW_SIZE;
}

/* The hold menu: holding Select on a row of a Music list (a song, an album,
 * an artist, a playlist), or on Now Playing, opens a popup with the rows that
 * fit what was held, of: Add to Queue, Play Album Next, Add to Playlist, Go to
 * Album, Go to Artist, Hide. Menu goes back, and nothing flashes.
 *
 * The popup is stock's: the one Clear Playlist and Save Playlist open (fn 24,
 * screen 0x25e2). Its list was built at boot from Menu 0x25ba, which the
 * loader points at hm_popup: Apple's two rows and four more (fn 27, the
 * "Confirm" function, behind each). A row is shown or hidden with
 * 0x08df.a0(0x25ba, element, 3, hidden), as the main menu hides its items,
 * and the screen sizes itself to the rows shown. .a0 finds the list in the
 * screen that's up, and needs a deeper VM stack than a hold handler's, so it
 * runs as the popup's opener (fn 26) returns, in fn 110's frame (HM_VIS_RUN);
 * for Apple's popups it shows their two rows again and hides ours. fn 24
 * gives rows their labels (0x08de.60 on the
 * rows' elements) and keeps the function the other rows run in global 0x8e8
 * (fn 27 calls it; that function goes back itself).
 *
 * Each list binds holding Select to a bytecode hold handler (handlers[]). A
 * handler reads the highlighted row into local0 (0x08df.a9()), adds that
 * row's songs to On-The-Go through the UI object's methods, then flashes the
 * row (0x08df.ae(row)). Here:
 *
 * - Holding: the handler runs as stock does up to the row read. Then we keep
 *   the row and send the VM to HM_OPEN, which opens the popup the way fn 24
 *   does, with our labels and rows, and fn 191 as the function.
 * - Picking a row runs the hold handler (fn 191, sent on to the list's own):
 *   the first row through fn 27 too, since we send its fn 28 (Cancel) into fn
 *   27. Stock's own add runs, with all of its checks for that kind of list.
 *   Its row read now gives the popup's row, which is the action; we put the
 *   list's row back into local0 in its place. At the flash (or the handler's
 *   end, when it adds nothing) the VM goes on to fn 28's tail instead, which
 *   goes back, or to our own bytecode for Add to Playlist and Go to.
 * - "Add to Queue" has the queue stand in for On-The-Go while the add runs
 *   (queue.c, which plays it next); "Add to Playlist" a scratch playlist
 *   (playlist.c), then hm_pick goes back and opens Playlists (fn 188), where
 *   picking a row (fn 190, once it has read the row) copies the songs there.
 * - The other actions add into the scratch playlist too, to learn the held
 *   row's songs: Play Album Next queues the first one's album from it on
 *   (queue.c), Go to Album/Artist open that one's album or artist, Hide hides
 *   them all (hide.c). On a row whose songs are all hidden (Settings › Show
 *   Hidden lists them; or the song playing) Hide's row is relabelled Show
 *   (HM_RELABEL, browse_row_hidden), which shows them again.
 * - Go to Album/Artist and Hide leave the list's browse state changed, so it's
 *   saved first and put back (browse.c) when the screen we came from is up
 *   again: for Hide as the popup goes, for Go to when Menu has come back
 *   that far. Screens are counted at fn 20's slide forward and back.
 * - Now Playing binds no hold, so HM_NP_BIND stands in for fn 151 (which
 *   binds Select to fn 169 whenever Now Playing is in its normal state) and
 *   binds holding Select to fn 191 too. Held there, fn 191's row read finds no
 *   list, and the popup is for the song playing. hm.from is fn 191 then, so
 *   a pick (fn 191 again) is known as ours even before any list was held.
 *
 * - Up Next (queue.c, browse.c): on Now Playing, while songs wait in the
 *   queue, row 0 is relabelled "Up Next" (C sets the row's text after
 *   HM_OPEN's labels, HM_RELABEL, so no row of its own). It opens the songs
 *   list (HM_UPNEXT: back, then fn 208, as Go to Album does) on an item
 *   array of the waiting songs that browse_items puts in, titled Up Next;
 *   Menu comes back to Now Playing with the browse state as it was (GO_RETURN).
 *   Select there (fn 210's row read) plays that song from the queue and goes
 *   back; holding Select (fn 211) opens the popup with rows 0 and 1 relabelled
 *   Remove from Queue and Clear Queue, and the list is redone in place as the
 *   popup goes (or, with nothing left, HM_GO_BACK2 goes back twice).
 * - The main menu has a Queue row too, after Music, while songs wait (hm_main,
 *   which the loader fills): fn 33, which shows and hides the main menu's
 *   rows, ends in HM_MM_RUN, which shows or hides ours the same way. Its item
 *   runs fn 28, where main_queue opens the same list with no popup to go
 *   first; Menu, or Select on a song, goes back to the main menu.
 *
 * - On an album, row 1 is Play After Album (HM_RELABEL): the album's songs,
 *   as stock adds them to the scratch playlist, go into the queue to play
 *   once the album playing ends (queue_add_after_album).
 *
 * Holding On-The-Go itself in Playlists still clears it (queue.c).
 *
 * Holding Menu opens the same popup as quick settings (qs_items has how);
 * over a popup it's stock's backlight toggle still. */

#include <stdint.h>
#include "holdmenu.h"
#include "settings.h"
#include "queue.h"
#include "playlist.h"
#include "nowplaying.h"
#include "browse.h"
#include "hide.h"
#include "debug.h"

#define TCMD_INT(n)     (((n) << 1) | 1)
#define FOURCC_STR      0x53747220u
#define TCMD_UNTAG(v)   ((v) >> 1)

enum { ACT_QUEUE, ACT_NEXT, ACT_PLAYLIST, ACT_ALBUM, ACT_ARTIST, ACT_HIDE,
       ACT_UPNEXT };            /* Now Playing's row 0 while songs wait */
#define R(a)            (1u << (a))
#define ROWS_ANY        (R(ACT_QUEUE) | R(ACT_PLAYLIST))
#define ROWS_SONG       0x3fu
#define ROWS_ALBUM      (ROWS_ANY | R(ACT_NEXT) | R(ACT_ARTIST) | R(ACT_HIDE))    /* row 1 as Play After Album */
#define ROWS_ARTIST     (ROWS_ANY | R(ACT_HIDE))
#define ROWS_NP         (R(ACT_NEXT) | R(ACT_ALBUM) | R(ACT_ARTIST) | R(ACT_HIDE))
#define ROWS_NP_UPNEXT  (ROWS_NP | R(ACT_QUEUE))    /* row 0 as Up Next */
#define ROWS_UPNEXT     (R(ACT_QUEUE) | R(ACT_NEXT))    /* in Up Next: Remove from Queue, Clear Queue */

static const struct handler {
    uint16_t id;                /* the function id */
    uint16_t entry, row, flash, end;    /* code offsets */
    uint16_t len;               /* the body's length: it ends at entry + len */
    uint8_t rows, kind;         /* the popup's rows; the list (browse.h) */
} handlers[] = {
    { 0x75b, 0x337c, 0x339e, 0x33e0, 0x33ee, 0x74, ROWS_ANY, LIST_OTHER },      /* fn 191, Playlists */
    { 0x763, 0x36be, 0x36e0, 0x36fa, 0x3708, 0x4c, ROWS_ANY, LIST_OTHER },      /* fn 199 */
    { 0x76f, 0x3a1c, 0x3a4b, 0x3a65, 0x3a73, 0x5a, ROWS_SONG, LIST_SONGS },     /* fn 211, songs */
    { 0x770, 0x3a82, 0x3aa4, 0x3abe, 0x3acc, 0x4c, ROWS_ANY, LIST_OTHER },      /* fn 212 */
    { 0x777, 0x3c62, 0x3c91, 0x3cc2, 0x3cd0, 0x70, ROWS_ANY, LIST_OTHER },      /* fn 219, composers */
    { 0x77e, 0x3ea8, 0x3ed7, 0x3f08, 0x3f16, 0x70, ROWS_ALBUM, LIST_ALBUMS },    /* fn 226, albums */
    { 0x785, 0x40ea, 0x4119, 0x414a, 0x4158, 0x70, ROWS_ARTIST, LIST_ARTISTS }, /* fn 233, artists */
    { 0x78b, 0x4318, 0x4347, 0x4378, 0x4386, 0x70, ROWS_ANY, LIST_OTHER },      /* fn 239, genres */
};
#define VM_CODE_END     (0x24 / 4)  /* [vm+0x24]: where the running function ends (0x9d288 stops there) */
#define N_HANDLERS (sizeof handlers / sizeof handlers[0])
#define PLAYLISTS 0             /* row 0 there is On-The-Go */
#define POPUP_FN 0              /* handlers[0], fn 191: what the popup calls back */

/* The popup's rows: their elements (Apple's two, then the new ones, which
 * take their label's id) and labels. */
static const uint16_t row_el[HM_ROWS] = { 0x25d4, 0x25d5, HM_STR_PLAYLIST, HM_STR_ALBUM, HM_STR_ARTIST, HM_STR_HIDE };
#define ROW_LABELS      HM_STR_QUEUE, HM_STR_NEXT, HM_STR_PLAYLIST, HM_STR_ALBUM, HM_STR_ARTIST, HM_STR_HIDE

/* Menu 0x25ba, as the loader points its index entry here: a count and
 * 40-byte items. Apple's Cancel (fn 28, 0x1ae2) and Confirm (fn 27, 0x1ade);
 * ours are Confirm's with their own element and label (word 5: 0x03NN + the
 * element, as Apple's run 0x0307, 0x0308). */
#define ITEM(fn, nn, el)    0x24, 0x24, 0x1b2a, fn, 0, 0x03000000u | (nn) << 16 | (el), 0, 0x4f81, el, 0
/* Menu 0x2512 with the Queue row, as the loader copies it (patches.c). */
uint32_t hm_main[1 + (HM_MAIN_ITEMS + 1) * 10];

uint32_t hm_popup[1 + HM_ROWS * 10] = {
    HM_ROWS,
    ITEM(0x1ae2, 0x07, 0x25d4), ITEM(0x1ade, 0x08, 0x25d5), ITEM(0x1ade, 0x09, HM_STR_PLAYLIST),
    ITEM(0x1ade, 0x0a, HM_STR_ALBUM), ITEM(0x1ade, 0x0b, HM_STR_ARTIST), ITEM(0x1ade, 0x0c, HM_STR_HIDE),
};

#define B(x)    (x) >> 8, (x) & 0xff
/* Our bytecode, which the loader copies to HM_SNIPPET at boot: on a device,
 * Apple's image is read-only once it runs (a write there from here was a data
 * abort), though emupod lets it pass. So nothing in it changes at runtime:
 * what varies goes through local0 (the hold handler's, set here), or
 * holdmenu_vm picks the way through it (vm_hook sees every pc in it). The
 * step the VM lands on after a redirect doesn't come through vm_hook.
 *
 * HM_OPEN, fn 24's steps with our values, run in the hold handler's frame
 * (they all have a local; fn 191 has the most locals, 2, and the handlers all
 * take one argument, so its frame does for any of them):
 *   fn 53(0x80, title)                         the popup's title
 *   0x08de.60(element, label, 0x80)            each row's label
 *   0x08df.a0(0x25ba, element, 3, nil|true)    each row shown or hidden
 *   global 0x8e8 = fn 191                      what the rows run
 *   0x08de.76(fn 26)                           later: open the popup screen
 *   0x08df.9f(0x25ba, local0, 3)               the first row shown highlighted
 *   return nil
 * A row's hidden flag is nil unless holdmenu_vm sends the VM to its stub,
 * which pushes true and jumps back. */
#define LABEL(el, s)    0x3b, 0x08, 0xde, 0x35, 0x00, 0x60, 0x39, 0x58, B(el), 0x58, B(s), 0x58, 0x00, 0x80, \
                        0x3a, 0x00, 0x03, 0x02
#define VIS_IN(m, el)   0x3b, 0x08, 0xdf, 0x35, 0x00, 0xa0, 0x39, 0x58, B(m), 0x58, B(el), 0x58, 0x00, 0x03, \
                        0x43, 0x3a, 0x00, 0x04, 0x02
#define VIS(el)         VIS_IN(0x25ba, el)
#define VIS_PC(i)       (HM_VIS + HM_VIS_ROW * (i) + HM_VIS_PUSH)
#define STUB_PC(i)      (HM_VIS_STUB + 4 * (i))
#define STUB(i)         0x42, 0x06, B((VIS_PC(i) + 1 - (STUB_PC(i) + 1)) & 0xffff)
#define FN(id, n)       0x3b, B(id), 0x39, 0x3a, 0x00, n, 0x02     /* fn id(), no arguments */
#define UI(sel)         0x3b, 0x08, 0xeb, 0x35, 0x00, sel, 0x39    /* 0x08eb.sel( */
const uint8_t hm_code[HM_CODE_LEN] = {
    /* HM_OPEN */
    0x3b, 0x06, 0xd1, 0x39, 0x58, 0x00, 0x80, 0x58, B(HM_STR_TITLE), 0x3a, 0x00, 0x02, 0x02,
    /* HM_LABELS */
    LABEL(0x25d4, HM_STR_QUEUE), LABEL(0x25d5, HM_STR_NEXT), LABEL(HM_STR_PLAYLIST, HM_STR_PLAYLIST),
    LABEL(HM_STR_ALBUM, HM_STR_ALBUM), LABEL(HM_STR_ARTIST, HM_STR_ARTIST), LABEL(HM_STR_HIDE, HM_STR_HIDE),
    0x6c, 0x08, 0xe8, 0x3b, B(0x75b), 0x6d, 0x08, 0xe8, 0x02,
    0x3b, 0x08, 0xde, 0x35, 0x00, 0x76, 0x39, 0x3b, 0x06, 0xb6, 0x3a, 0x00, 0x01, 0x02,
    0x3b, 0x08, 0xdf, 0x35, 0x00, 0x9f, 0x39, 0x58, 0x25, 0xba, 0x56, 0x00, 0x00, 0x58, 0x00, 0x03,
    0x3a, 0x00, 0x03, 0x02,
    0x43, 0x05,
    /* HM_VIS_RUN, run at fn 26's return: fn 110 (HM_VIS); return nil */
    FN(0x70a, 0), 0x43, 0x05,
    /* HM_VIS, run in fn 110's frame */
    VIS(0x25d4), VIS(0x25d5), VIS(HM_STR_PLAYLIST), VIS(HM_STR_ALBUM), VIS(HM_STR_ARTIST), VIS(HM_STR_HIDE),
    0x43, 0x05,
    /* HM_VIS_STUB */
    STUB(0), STUB(1), STUB(2), STUB(3), STUB(4), STUB(5),
    /* HM_PICK: fn 14() (back from the popup), fn 188() (open Playlists), return nil */
    FN(0x6aa, 0), FN(0x758, 0), 0x43, 0x05,
    /* HM_GOTO_ALBUM: back; as Albums (fn 221: .dd; its opener fn 224: .f4(3),
     * the level, which sorts an album's songs by track rather than title) and
     * its row local0 (fn 225: .e5, the title, fn 208 builds the songs and
     * opens them) would, with every artist (.e3(0)) */
    FN(0x6aa, 0), UI(0xdd), 0x3a, 0x00, 0x00, 0x02, UI(0xf4), 0x58, 0x00, 0x03, 0x3a, 0x00, 0x01, 0x02,
    UI(0xe3), 0x58, 0x00, 0x00, 0x3a, 0x00, 0x01, 0x02,
    UI(0xe5), 0x56, 0x00, 0x00, 0x3a, 0x00, 0x01, 0x02,
    0x3b, 0x06, 0xd1, 0x39, 0x58, 0x33, 0x00, 0x58, 0x33, 0x17, 0x3a, 0x00, 0x02, 0x02,
    0x3b, 0x07, 0x6c, 0x39, 0x43, 0x3a, 0x00, 0x01, 0x02, 0x43, 0x05,
    /* HM_GOTO_ARTIST: back; as Artists (fn 228: .dd) and its row local0 (fn
     * 232: .e3, the title, fn 222 builds the artist's albums and opens them) */
    FN(0x6aa, 0), UI(0xdd), 0x3a, 0x00, 0x00, 0x02, UI(0xe3), 0x56, 0x00, 0x00, 0x3a, 0x00, 0x01, 0x02,
    0x3b, 0x06, 0xd1, 0x39, 0x58, 0x33, 0x00, 0x58, 0x33, 0x15, 0x3a, 0x00, 0x02, 0x02,
    0x3b, 0x07, 0x7a, 0x39, 0x43, 0x3a, 0x00, 0x01, 0x02, 0x43, 0x05,
    /* HM_NP_BIND: fn 41(fn 169) (fn 151: Select), then (HM_NP_CALL) fn 110,
     * whose frame (fn 151's has stack for 3) runs HM_NP_HOLD:
     * 0x08de.6a(2, Select, fn 191), the hold */
    0x3b, 0x06, 0xc5, 0x39, 0x3b, 0x07, 0x45, 0x3a, 0x00, 0x01, 0x02,
    FN(0x70a, 0), 0x43, 0x05,
    0x3b, 0x08, 0xde, 0x35, 0x00, 0x6a, 0x39, 0x58, 0x00, 0x02, 0x58, 0x00, 0x6f, 0x3b, 0x07, 0x5b,
    0x3a, 0x00, 0x03, 0x02, 0x43, 0x05,
    /* HM_UPNEXT: back; (HM_UPNEXT_BUILD) the title, fn 208 (as Go to Album:
     * .f9, which shows the array browse_items put in, and fn 209 opens the
     * songs screen with Select fn 210 and the hold fn 211); return nil */
    FN(0x6aa, 0),
    0x3b, 0x06, 0xd1, 0x39, 0x58, 0x00, 0x80, 0x58, B(HM_STR_UPNEXT), 0x3a, 0x00, 0x02, 0x02,
    0x3b, 0x07, 0x6c, 0x39, 0x43, 0x3a, 0x00, 0x01, 0x02, 0x43, 0x05,
    /* HM_GO_BACK2: back, then on into fn 28's tail (back; return nil) */
    FN(0x6aa, 0), 0x06, B((HM_GO_BACK - (HM_GO_BACK2 + 8)) & 0xffff),
    /* HM_QS_RUN, run at fn 243's entry: fn 480 (HM_OPEN); return nil */
    FN(0x87c, 0), 0x43, 0x05,
    /* HM_MM_RUN, run at fn 33's last drop (HM_MM_SHOW): that drop, fn 110
     * (HM_MM_VIS), on into fn 33's return */
    0x02, FN(0x70a, 0), 0x06, B((HM_MM_SHOWN - (HM_MM_RUN + 9)) & 0xffff),
    /* HM_MM_VIS, in fn 110's frame: 0x08df.a0(0x2512, Queue, 3, nil|true); return nil */
    VIS_IN(HM_MAIN_ID, HM_STR_UPNEXT), 0x43, 0x05,
    /* HM_MM_STUB: push true, jump back */
    0x42, 0x06, B((HM_MM_PUSH + 1 - (HM_MM_STUB + 1)) & 0xffff),
};
typedef char hm_code_fits[HM_SNIPPET + HM_CODE_LEN <= HM_SNIPPET_END ? 1 : -1];
typedef char hm_upnext_fits[HM_GO_BACK - (HM_GO_BACK2 + 7) < 0x8000 ? 1 : -1];
typedef char hm_mm_fits[HM_MM_SHOWN - (HM_MM_RUN + 9) < 0x8000 ? 1 : -1];
typedef char hm_rows_fit[sizeof row_el / sizeof row_el[0] == HM_ROWS ? 1 : -1];

#define obj_08de        (*(volatile uint32_t *)0x41e938)    /* the bytecode's 0x08de */
#define set_text        ((void (*)(uint32_t obj, uint32_t element, uint32_t str, uint32_t flags))0x1fabc)
/* The library's root object, the prefs: [[0x43580c]+0x1c] is the library. */
#define prefs_root()    (**(volatile uint32_t *volatile *)(*(volatile uint32_t *)0x43580c + 0x1c))

enum { GO_NONE, GO_CLOSE, GO_RETURN };  /* when browse_restore runs */

static struct {
    int open;                   /* our popup is up */
    int swallow;                /* the click letting go of Select is still to come */
    int selecting;              /* inside fn 50: a popup row was picked */
    int acting;                 /* a hold handler runs for one of our rows */
    int action;
    int picking;                /* Playlists is open to pick where the songs go */
    int np;                     /* the popup is for Now Playing's song */
    int upnext;                 /* the popup is for a row of Up Next */
    int apple;                  /* HM_VIS runs for Apple's popup */
    uint32_t vis_frame;         /* fn 110's next entry runs this instead (HM_VIS, HM_NP_HOLD) */
    int vis_dirty;              /* our rows may be shown: Apple's popup must hide them */
    unsigned vis;               /* our popup's rows */
    int go, go_pending, go_depth;
    const struct handler *from; /* the list's hold handler */
    uint32_t row;               /* the list's row (tagged) */
    int up;                     /* a popup (Apple's or ours) is up */
    int qs;                     /* ours is quick settings */
    int swallow_menu;           /* ... and the click letting go of Menu is still to come */
    int show;                   /* its songs are all hidden: Hide's row is Show */
    int sleep;                  /* quick settings' Sleep: HM_PICK goes on into Apple's sleep */
    uint32_t np_track;          /* Now Playing's popup: the song playing when it was held (last: the emupod scripts read the fields above by offset) */
} hm = { .vis_dirty = 1 };

/* Quick settings: holding Menu (fn 243, stock's backlight toggle) opens the
 * popup with rows 0-2 made into Settings' own items for the time it's up, and
 * row 4 as Apple's Clicker item (0x282d: settings.c steps Off, Speaker,
 * Headphones, Both), and row 3 as Sleep (a Confirm row: fn 27 calls fn 191, which goes back through
 * HM_PICK, with Apple's sleep, fn 249's body, in place of its second call):
 * fn 273 (word 3 0x1eb6, what an on/off or cycling item runs), the item id
 * (word 6) and word 7 0x2780, which sends fn 273's toggle message
 * (0x08f8.12e(list, item, 0x282f)) to the settings object, as from Settings.
 * So Select runs Apple's setter 0xdafc4 with all of its side effects:
 * Shuffle and Repeat cycle; Backlight Timer has no toggle, so settings.c
 * turns that into Off and back (qs_timer). The labels show the values, read
 * from the prefs (the library's root object). */
#define QS_ROWS         3
#define ITEM_SETTING    0x1eb6          /* word 3: fn 273 */
#define ITEM_TO_SETTINGS 0x2780         /* word 7 of Settings' items */
static const uint32_t qs_item[QS_ROWS] = { 0x279f, 0x27a9, 0x27ad };   /* Backlight Timer, Shuffle, Repeat */
static const uint16_t qs_str[QS_ROWS] = { HM_STR_QS_TIMER, HM_STR_QS_SHUFFLE, HM_STR_QS_REPEAT };

/* Row 4, after Sleep: Apple's Clicker item, whose toggle settings.c's
 * clicker_set steps Off, Speaker, Headphones, Both. */
#define QS_CLICKER      4

/* Rows 0-2 and 4 as Settings' items (on) or as hm_popup has them (off). */
static void qs_items(int on)
{
    unsigned i;

    for (i = 0; i <= QS_CLICKER; i++) {
        uint32_t *it = &hm_popup[1 + i * 10];
        if (i == QS_ROWS)
            continue;                   /* Sleep: the popup's own Confirm row */
        it[3] = on ? ITEM_SETTING : i ? 0x1ade : 0x1ae2;
        it[6] = on ? i == QS_CLICKER ? SETTING_CLICKER : qs_item[i] : 0;
        it[7] = on ? ITEM_TO_SETTINGS : 0x4f81;
    }
}

static void qs_relabel(void)
{
    unsigned i;

    for (i = 0; i < QS_ROWS; i++)
        set_text(obj_08de, row_el[i], qs_str[i], 0x80);
    set_text(obj_08de, row_el[QS_ROWS], HM_STR_QS_SLEEP, 0x80);
    set_text(obj_08de, row_el[QS_CLICKER], HM_STR_QS_CLICKER, 0x80);
}

#define MAX_ALBUM 99
static uint32_t album_idx[MAX_ALBUM], album_nums[MAX_ALBUM];

/* Up Next: the queue's index of each row's song. */
#define UPNEXT_MAX 1000
static struct {
    int open;                   /* Up Next was opened (it's up while hm.go_depth is 1) */
    int refresh;                /* redo the list as the popup over it goes */
    uint32_t row;               /* ... with the cursor back on this row */
    unsigned n;
    uint32_t idx[UPNEXT_MAX];
} up;


static volatile uint32_t *local0(uint32_t vm)
{
    uint32_t frame = ((volatile uint32_t *)vm)[0x10 / 4];
    return (volatile uint32_t *)((volatile uint32_t *)frame)[0x24 / 4];
}

static uint32_t open_popup(volatile uint32_t *l, unsigned rows)
{
    unsigned i;

    for (i = 0; i < HM_ROWS && !(rows & R(i)); i++)
        ;
    *l = TCMD_INT(row_el[i]);   /* HM_OPEN highlights it */
    hm.vis = rows;
    hm.vis_dirty = 1;
    hm.open = 1;
    hm.swallow = 1;
    return HM_OPEN;
}

/* The popup's row (0x08df.a9 counts the rows shown) -> the action. */
static int action_of(uint32_t row)
{
    unsigned i;

    for (i = 0; i < HM_ROWS; i++)
        if ((hm.vis & R(i)) && !row--)
            return (int)i;
    return ACT_QUEUE;
}

static uint32_t first_track(uint32_t list)
{
    uint32_t item = list && *(volatile uint32_t *)(*(volatile uint32_t *)(list + 0x24) + 0x2c)
                    ? ((uint32_t (*)(uint32_t, uint32_t, uint32_t, uint32_t))0x78d60)(list, 1, 0, 0) : 0;

    return item ? *(volatile uint32_t *)(item + 0x20) : 0;
}

/* Whether Up Next is the list up. Counting screens alone isn't enough: on a
 * device fn 20 can change screens past both slides it's counted at (its
 * early return while 0x08e0 is set, its unanimated 0x08df.90 while 0x08e1
 * isn't), and Select then fell through to stock's play from the songs array
 * (a new Now Playing screen over Up Next). So the songs array being ours is
 * enough too, and puts the count right: Up Next is depth 1. */
static int upnext_up(void)
{
    if (up.open && hm.go == GO_RETURN && !hm.go_pending && hm.go_depth == 1)
        return 1;
    if (!up.open || hm.open || !browse_items_shown())
        return 0;
    debug_note(DEBUG_TAG('u', 'p', 's', 'y'), hm.go | hm.go_pending << 4, (uint32_t)hm.go_depth);
    hm.go = GO_RETURN;
    hm.go_pending = 0;
    hm.go_depth = 1;
    return 1;
}

/* The popup on a row of Up Next: row 0 Remove from Queue, row 1 Clear Queue.
 * The list's browse state is Up Next's own, so nothing is saved here. */
static uint32_t upnext_act(int action, uint32_t row)
{
    up.row = row;
    if (action == ACT_QUEUE && row < up.n)
        queue_remove(up.idx[row]);
    else if (action == ACT_NEXT)
        queue_clear_waiting();
    up.n = queue_waiting(up.idx, UPNEXT_MAX);
    if (!up.n)
        return HM_GO_BACK2;     /* no empty list: back to Now Playing */
    up.refresh = 1;
    return HM_GO_BACK;
}

/* The main menu's Queue row (fn 28, which runs off a popup only as its
 * Cancel): the Queue list, as from Now Playing (ACT_UPNEXT), but with no
 * popup to go first, so its slide forward is depth 1. The title and fn 208
 * run in fn 110's frame (fn 28's has stack for two). */
static uint32_t main_queue(void)
{
    up.n = queue_waiting(up.idx, UPNEXT_MAX);
    if (!up.n)
        return HM_NIL;          /* played out since the main menu showed the row */
    up.open = 1;
    up.refresh = 0;
    hm.go = GO_RETURN;
    hm.go_pending = 0;
    hm.go_depth = 0;
    browse_save(LIST_OTHER, 0);
    browse_items(queue_list(), up.idx, up.n, 1, 0);     /* HM_UPNEXT_BUILD's, as we land there */
    hm.vis_frame = HM_UPNEXT_BUILD;
    return HM_VIS_RUN;
}

/* The popup is an album row's: row 1 is Play After Album. */
static int after_album(void)
{
    return !hm.np && !hm.upnext && hm.from && hm.from->kind == LIST_ALBUMS;
}

/* Our actions on `track` (the first of the held row's songs, or the one
 * playing); returns where the VM goes on. */
static uint32_t act(int action, uint32_t track, volatile uint32_t *l)
{
    uint32_t row, list, n, i;

    switch (action) {
    case ACT_NEXT:
        if (after_album()) {    /* the list goes back as for Hide */
            queue_add_after_album(playlist_scratch());
            break;
        }
        /* a song row: the list is as it was */
        n = browse_album_items(track, hm.np, &list, album_idx, album_nums, MAX_ALBUM);
        queue_add_items(list, album_idx, n);
        return HM_GO_BACK;
    case ACT_ALBUM:
    case ACT_ARTIST:
        row = action == ACT_ALBUM ? browse_album_row(track) : browse_artist_row(track);
        if (!row)
            break;
        *l = TCMD_INT(row);
        hm.go = GO_RETURN;
        hm.go_pending = 1;
        return action == ACT_ALBUM ? HM_GOTO_ALBUM : HM_GOTO_ARTIST;
    case ACT_UPNEXT:
        up.n = queue_waiting(up.idx, UPNEXT_MAX);
        if (!up.n)
            break;              /* played out since the popup opened */
        up.open = 1;
        up.refresh = 0;
        hm.go = GO_RETURN;
        hm.go_pending = 1;
        return HM_UPNEXT;       /* HM_UPNEXT_BUILD puts the songs in */
    case ACT_HIDE: {
        void (*f)(uint32_t) = hm.show ? hide_show : hide_add;
        if (hm.np)
            f(track);
        else if ((list = playlist_scratch()) != 0) {
            n = *(volatile uint32_t *)(*(volatile uint32_t *)(list + 0x24) + 0x2c);
            for (i = 0; i < n; i++) {
                uint32_t item = ((uint32_t (*)(uint32_t, uint32_t, uint32_t, uint32_t))0x78d60)(list, 1, 0, i);
                if (item)
                    f(*(volatile uint32_t *)(item + 0x20));
            }
        }
        hide_save();
        break;
    }
    }
    debug_note(DEBUG_TAG('a', 'c', 't', '0' + action), hm.show | hm.np << 1 | hm.upnext << 2, track);
    hm.go = GO_CLOSE;           /* the list as it was (hidden songs gone) once the popup goes */
    hm.go_pending = 1;
    return HM_GO_BACK;
}

/* fn 20 slides a screen in, forward or back: once the screen we came from is
 * up again, its browse state goes back (browse.c). */
static void screen(int back)
{
    debug_note(DEBUG_TAG('s', 'c', 'r', back ? 'b' : 'f'), hm.go | hm.go_pending << 4 | (up.open << 8), (uint32_t)hm.go_depth);
    if (!hm.go)
        return;
    if (hm.go_pending) {
        if (!back) {
            /* A screen opens while the popup's going is still to come: its
             * slide back went uncounted (fn 20 can return before either
             * slide, 0x592; never in emupod, suspected on a device). Go to
             * and Up Next open their list right after
             * going back, so this is that list, at depth 1; after Hide (or
             * an action that went nowhere) the list is up again: drop the
             * saved state rather than put it back over another list later. */
            hm.go_pending = 0;
            if (hm.go == GO_RETURN) {
                hm.go_depth = 1;
                return;
            }
            hm.go = GO_NONE;
            up.open = 0;
            browse_drop();
            return;
        }
        hm.go_pending = 0;          /* the popup went */
        hm.go_depth = 0;
        if (hm.go == GO_RETURN)
            return;
    } else if (!back) {
        hm.go_depth++;
        return;
    } else if (--hm.go_depth > 0) {
        if (hm.go_depth == 1 && up.open && up.refresh) {
            up.refresh = 0;     /* the Up Next popup went: the songs as they are now */
            browse_items(queue_list(), up.idx, up.n, 0, up.row);
        }
        return;
    }
    hm.go = GO_NONE;
    up.open = 0;
    browse_restore();
}

/* vm_hook, for the pcs in holdmenu.h; returns the pc to go on with. */
uint32_t holdmenu_vm(uint32_t pc, uint32_t vm)
{
    unsigned i;
    uint32_t off = pc - TCMD_CODE;

    if (pc >= HM_VIS && pc < HM_VIS_END) {
        for (i = 0; i < HM_ROWS; i++)
            if (pc == VIS_PC(i) && (hm.apple ? i >= 2 : !(hm.vis & R(i))))
                return STUB_PC(i);      /* hidden */
        return pc;
    }
    switch (pc) {
    case HM_RELABEL:
        if (hm.qs) {
            qs_relabel();
            *local0(vm) = TCMD_INT(row_el[0]);  /* HM_OPEN highlights it */
            return pc;
        }
        if (hm.np && (hm.vis & R(ACT_QUEUE)))
            set_text(obj_08de, row_el[ACT_QUEUE], HM_STR_UPNEXT, 0x80);
        if (hm.upnext) {
            set_text(obj_08de, row_el[ACT_QUEUE], HM_STR_REMOVE, 0x80);
            set_text(obj_08de, row_el[ACT_NEXT], HM_STR_CLEAR, 0x80);
        }
        if (hm.show && (hm.vis & R(ACT_HIDE)))
            set_text(obj_08de, row_el[ACT_HIDE], HM_STR_SHOW, 0x80);
        if (after_album() && (hm.vis & R(ACT_NEXT)))
            set_text(obj_08de, row_el[ACT_NEXT], HM_STR_AFTER, 0x80);
        return pc;
    case HM_UPNEXT_BUILD:
        browse_items(queue_list(), up.idx, up.n, 1, 0);
        return pc;
    case HM_SONG_PICK:
        if (!upnext_up())
            return pc;
        i = TCMD_UNTAG(*local0(vm));
        if (i < up.n)
            queue_play(up.idx[i]);
        return HM_GO_BACK;      /* to Now Playing, with the song picked */
    case HM_NP_CALL:
        hm.vis_frame = HM_NP_HOLD;
        return pc;
    case HM_QS_HOLD:
        if (hm.up || hm.open || !frogger_on(FEATURE_QUICK))
            return pc;                  /* over a popup, or switched off: stock's backlight toggle */
        hm.qs = 1;
        qs_items(1);
        hm.vis = R(0) | R(1) | R(2) | R(QS_ROWS) | R(QS_CLICKER);    /* the settings, Sleep, Clicker */
        hm.vis_dirty = 1;
        hm.open = 1;
        hm.swallow = 0;
        hm.swallow_menu = 1;
        hm.np = hm.upnext = hm.show = 0;
        hm.vis_frame = HM_OPEN;         /* in fn 480's frame */
        return HM_QS_RUN;
    case HM_QS_FRAME:
    case HM_FN_VIS_FRAME:
        if (!hm.vis_frame)
            return pc;                  /* Extras' own */
        pc = hm.vis_frame;
        hm.vis_frame = 0;
        return pc;
    case HM_POPUP_UP:
        /* Ours: its rows. Apple's (Clear, Save Playlist): its two rows
         * again, if ours may have changed them. */
        hm.up = 1;
        if (!hm.open && !hm.vis_dirty)
            return pc;
        hm.apple = !hm.open;
        hm.vis_dirty = hm.open;
        hm.vis_frame = HM_VIS;
        return HM_VIS_RUN;
    case HM_FN_NP_SELECT:
        return frogger_on(FEATURE_HOLD) ? HM_NP_BIND : pc;     /* off: no hold on Now Playing, as stock */
    case HM_SCREEN_FWD:
    case HM_SCREEN_BACK:
        screen(pc == HM_SCREEN_BACK);
        return pc;
    case HM_FN_SELECT:
        /* Letting go of a hold clicks Select. Stock lists swallow that click
         * (the hold handler binds it to fn 42, which only binds Select back),
         * but the popup binds it to fn 50, which would pick the first row. */
        if (hm.swallow) {
            hm.swallow = 0;
            return HM_FN_SELECT_NIL;
        }
        hm.selecting = 1;
        return pc;
    case HM_FN_SELECTED:
        hm.selecting = 0;
        if (hm.qs)
            qs_relabel();               /* the new value */
        return pc;
    case HM_FN_BACK:
        /* Letting go of a hold clicks Menu too, which the popup binds to
         * fn 14 (back). */
        if (hm.swallow_menu) {
            hm.swallow_menu = 0;
            return HM_NIL;
        }
        if (hm.qs) {
            hm.qs = 0;
            qs_items(0);
        }
        hm.up = 0;
        hm.open = 0;
        hm.swallow = 0;
        return pc;
    case HM_FN_CANCEL:
        if (hm.open && hm.selecting)
            return HM_FN_CONFIRM;
        return hm.selecting && !hm.up ? main_queue() : pc;     /* no popup: the main menu's Queue */
    case HM_MM_SHOW:
        hm.vis_frame = HM_MM_VIS;       /* in fn 110's frame */
        return HM_MM_RUN;
    case HM_MM_PUSH: {
        uint32_t one;
        return queue_waiting(&one, 1) ? pc : HM_MM_STUB;      /* shown while songs wait */
    }
    case HM_PICK_CALL:
        if (!hm.sleep)
            return pc;
        hm.sleep = 0;
        ((volatile uint32_t *)vm)[VM_CODE_END] = HM_SLEEP_END;
        return HM_SLEEP_BODY;
    case HM_PICKED:
        if (!hm.picking)
            return pc;
        hm.picking = 0;
        playlist_pick(TCMD_UNTAG(*local0(vm)));
        return HM_GO_BACK;
    case HM_PLAYLISTS:
        playlist_load_saved();  /* once: FroggerPlaylist files, before they show */
        return pc;
    case HM_PICK_MENU:
        if (hm.picking) {
            hm.picking = 0;
            playlist_cancel();
        }
        return pc;
    }
    for (i = 0; i < N_HANDLERS; i++) {
        const struct handler *h = &handlers[i];
        if (off == h->entry) {
            if (h == &handlers[POPUP_FN] && hm.open && hm.selecting && hm.qs) {
                hm.sleep = 1;           /* quick settings' only Confirm row */
                return HM_PICK;
            }
            if (h == &handlers[POPUP_FN] && hm.open && hm.selecting && hm.from && hm.from != h) {
                /* the popup's call: on into the list's own handler */
                ((volatile uint32_t *)vm)[VM_CODE_END] = TCMD_CODE + hm.from->entry + hm.from->len;
                hm.acting = 1;
                return TCMD_CODE + hm.from->entry;
            }
            hm.acting = hm.open && hm.selecting && h == hm.from;
            return pc;
        }
        if (off == h->row) {
            volatile uint32_t *l = local0(vm);
            if (hm.acting) {
                hm.action = action_of(TCMD_UNTAG(*l));
                debug_note(DEBUG_TAG('r', 'o', 'w', '0' + hm.action), TCMD_UNTAG(hm.row), (uint32_t)i);
                if (hm.upnext) {
                    hm.acting = 0;
                    return upnext_act(hm.action, TCMD_UNTAG(hm.row));
                }
                if (hm.np) {            /* no list: the song held, even if another plays now */
                    hm.acting = 0;
                    if (hm.action != ACT_NEXT)  /* the others put it back (hm.go); Play Album Next leaves it */
                        browse_save(LIST_OTHER, 0);
                    return act(hm.action == ACT_QUEUE ? ACT_UPNEXT : hm.action, hm.np_track, l);
                }
                if (hm.action == ACT_QUEUE)
                    queue_begin_add();
                else {
                    if (hm.action != ACT_PLAYLIST)      /* before the add changes it */
                        browse_save(hm.from->kind, TCMD_UNTAG(hm.row));
                    playlist_begin_add();
                }
                *l = hm.row;
                return pc;
            }
            if (!frogger_on(FEATURE_HOLD))
                return pc;              /* switched off: stock's add to On-The-Go */
            hm.np = i == POPUP_FN && np_is_open();
            hm.upnext = 0;
            if (hm.np) {
                if (!(hm.np_track = browse_playing())) {
                    hm.np = 0;
                    return HM_NIL;      /* nothing playing: no popup, and not Playlists' add with no list */
                }
                hm.from = h;            /* the pick comes back to fn 191 itself */
                up.n = queue_waiting(up.idx, UPNEXT_MAX);
                hm.show = hide_track(hm.np_track);
                return open_popup(l, up.n ? ROWS_NP_UPNEXT : ROWS_NP);
            }
            if (i == PLAYLISTS && *l == TCMD_INT(0))
                return pc;              /* On-The-Go: queue.c clears it */
            hm.from = h;
            hm.row = *l;
            browse_held();
            hm.upnext = h->kind == LIST_SONGS && upnext_up();
            hm.show = !hm.upnext && (h->rows & R(ACT_HIDE)) && browse_row_hidden(h->kind, TCMD_UNTAG(hm.row));
            return open_popup(l, hm.upnext ? ROWS_UPNEXT : h->rows);
        }
        if ((off == h->flash || off == h->end) && hm.acting) {
            hm.acting = 0;
            debug_note(DEBUG_TAG('f', 'l', 's', 'h'), (uint32_t)hm.action, off);
            if (hm.action == ACT_QUEUE) {
                queue_end_add();
                return HM_GO_BACK;
            }
            if (hm.action == ACT_PLAYLIST) {
                if (!playlist_end_add())
                    return HM_GO_BACK;
                hm.picking = 1;
                return HM_PICK;
            }
            if (!playlist_end_add()) {
                playlist_cancel();
                hm.go = GO_CLOSE;
                hm.go_pending = 1;
                return HM_GO_BACK;
            }
            pc = act(hm.action, first_track(playlist_scratch()), local0(vm));
            playlist_cancel();
            return pc;
        }
    }
    return pc;
}

static const char hm_title[] = "Frogger";
static const char *const hm_strings[] = {
    [HM_STR_QUEUE - HM_STR_TITLE] = "Add to Queue",
    [HM_STR_PLAYLIST - HM_STR_TITLE] = "Add to Playlist",
    [HM_STR_ADD_TO - HM_STR_TITLE] = "Add to",
    [HM_STR_NEXT - HM_STR_TITLE] = "Play Album Next",
    [HM_STR_ALBUM - HM_STR_TITLE] = "Go to Album",
    [HM_STR_ARTIST - HM_STR_TITLE] = "Go to Artist",
    [HM_STR_HIDE - HM_STR_TITLE] = "Hide",
    [HM_STR_UPNEXT - HM_STR_TITLE] = "Queue",
    [HM_STR_REMOVE - HM_STR_TITLE] = "Remove from Queue",
    [HM_STR_CLEAR - HM_STR_TITLE] = "Clear Queue",
    [HM_STR_SHOW - HM_STR_TITLE] = "Show",
    [HM_STR_AFTER - HM_STR_TITLE] = "Play After Album",
    [HM_STR_QS_SLEEP - HM_STR_TITLE] = "Sleep",
};

/* A quick settings row's label: the setting and its value, from the prefs
 * (Apple's setters: Shuffle 0xdc530 keeps on at +0x20 and Albums at +0x92,
 * Repeat 0xdc1dc 0 Off, 1 All, 2 One at +0x1c, the backlight timer 0xd8670
 * 0 Off, 2-5 the seconds, 6 Always On at +0xaf8). */
char qs_text[24];                       /* the last label made (emupod's quicksettings.py reads it) */

static const char *qs_label(uint32_t id)
{
    char *buf = qs_text;
    static const char *const timer[] = { "Off", "1 s", "2 s", "5 s", "10 s", "20 s", "Always On" };
    volatile uint8_t *root = (volatile uint8_t *)prefs_root();
    const char *name, *val;
    uint32_t v;
    char *d = buf;

    if (id == HM_STR_QS_CLICKER) {
        uint32_t f = *(volatile uint32_t *)(root + 0xb04);
        name = "Clicker";
        v = (f & FROGGER_PREF_PLACE) >> FROGGER_PREF_PLACE_SHIFT;
        val = !(f & FROGGER_PREF_CLICKER) ? "Off" : v == CLICK_PHONES ? "Headphones" : v == CLICK_BOTH ? "Both" : "Speaker";
    } else if (id == HM_STR_QS_SHUFFLE) {
        name = "Shuffle";
        val = !root[0x20] ? "Off" : root[0x92] ? "Albums" : "Songs";
    } else if (id == HM_STR_QS_REPEAT) {
        name = "Repeat";
        v = *(volatile uint32_t *)(root + 0x1c);
        val = v == 1 ? "All" : v == 2 ? "One" : "Off";
    } else {
        name = "Backlight";
        v = *(volatile uint32_t *)(root + 0xaf8);
        val = v < sizeof timer / sizeof timer[0] ? timer[v] : "?";
    }
    while (*name)
        *d++ = *name++;
    *d++ = ':';
    *d++ = ' ';
    while (*val && d < buf + sizeof qs_text - 1)
        *d++ = *val++;
    *d = 0;
    return buf;
}

/* Our strings, for string_hook (art.c). */
const void *holdmenu_resource(uint32_t fourcc, uint32_t id, uint32_t *size)
{
    const char *s, *e;

    if (fourcc != FOURCC_STR)
        return 0;
    if ((id & 0xffff) == PLAYLISTS_TITLE && hm.picking)
        id = HM_STR_ADD_TO;             /* the picker's title */
    if ((id >= HM_STR_QS_SHUFFLE && id < HM_STR_QS_SHUFFLE + QS_ROWS) || id == HM_STR_QS_CLICKER)
        s = qs_label(id);
    else if (id == HM_STR_TITLE)
        s = hm.qs ? "Settings" : hm_title;
    else if (id > HM_STR_TITLE && id - HM_STR_TITLE < sizeof hm_strings / sizeof hm_strings[0])
        s = hm_strings[id - HM_STR_TITLE];
    else
        s = 0;
    if (!s)
        return 0;
    for (e = s; *e++; )
        ;
    *size = (uint32_t)(e - s);
    return s;
}

#ifdef FROGGER_DEBUG
/* Whether the debug trail keeps pc: most pcs in [HM_LO, HM_HI] are just the
 * hold handlers' busy code (over a million steps a hold), so only the ones
 * holdmenu_vm looks at, every step of a hold handler up to its row read
 * (about 15: a device crashed in there), and everything outside that
 * range. */
static int trail_worthy(uint32_t pc)
{
    uint32_t off = pc - TCMD_CODE;
    unsigned i;

    if (pc >= HM_SNIPPET && pc < HM_SNIPPET_END)    /* our bytecode: ~150 steps a popup */
        return pc == HM_OPEN || pc == HM_RELABEL || pc == HM_VIS_RUN || pc == HM_UPNEXT_BUILD || pc == HM_NP_CALL
            || pc == HM_PICK || pc == HM_PICK_CALL || pc == HM_QS_RUN || pc == HM_MM_RUN;
    if (pc < HM_LO || pc > HM_HI || pc == HM_PICKED || pc == HM_PLAYLISTS || pc == HM_PICK_MENU)
        return 1;
    for (i = 0; i < N_HANDLERS; i++)
        if ((off >= handlers[i].entry && off <= handlers[i].row) || off == handlers[i].flash || off == handlers[i].end)
            return 1;
    return 0;
}
#endif

/* vm_hook's C side: the hold menu, Up Next, then Now Playing; in DEBUG=1
 * builds the debug trail notes where the pcs that matter went. */
uint32_t frogger_vm(uint32_t pc, uint32_t vm)
{
    uint32_t to = holdmenu_vm(pc, vm);

    to = queue_vm(to, vm);
    to = np_vm(to);
#ifdef FROGGER_DEBUG
    if (to != pc || trail_worthy(pc))
        debug_vm(pc, to);
#endif
    return to;
}

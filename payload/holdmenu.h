#ifndef FROGGER_HOLDMENU_H
#define FROGGER_HOLDMENU_H

/* The hold menu (holdmenu.c): holding Select on a row of a Music list, or on
 * Now Playing, opens a small popup (Add to Queue, Play Album Next, Add to
 * Playlist, Go to Album, Go to Artist, Hide; the rows that fit what was held;
 * on Now Playing also Up Next, and in Up Next Remove from Queue and Clear
 * Queue) instead of adding at once. Holding Menu, anywhere but over a popup,
 * opens the same popup as quick settings (Backlight Timer, Shuffle, Repeat, Sleep)
 * in place of stock's backlight toggle. docs/tcmd.md, "The hold menu", has how stock's
 * popups and hold handlers work. */

/* Our strings: the popup's title and its rows' labels. None of these ids
 * is in Apple's bundle (tests/test_settings.py). The new rows' elements take
 * their label's id, as Apple's rows do. */
#define HM_STR_TITLE    0x3f10
#define HM_STR_QUEUE    0x3f11
#define HM_STR_PLAYLIST 0x3f12
#define HM_STR_ADD_TO   0x3f13      /* the picker's title (Playlists' is renamed) */
#define HM_STR_NEXT     0x3f17
#define HM_STR_ALBUM    0x3f18
#define HM_STR_ARTIST   0x3f19
#define HM_STR_HIDE     0x3f1a
/* Up Next's: Now Playing's row 0 and Up Next's title; the Up Next popup's
 * rows 0 and 1 (holdmenu.c relabels those rows, so they need no rows of
 * their own). */
#define HM_STR_UPNEXT   0x3f1b
#define HM_STR_REMOVE   0x3f1c
#define HM_STR_CLEAR    0x3f1d
#define HM_STR_SHOW     0x3f1f      /* Hide's row on hidden songs (0x3f1e: settings.h's) */
#define HM_STR_AFTER    0x3f28      /* Play Album Next's row on albums: Play After Album */
/* Quick settings (hold Menu): rows 0-2's labels, which show the setting's
 * value ("Shuffle: Songs"), and row 3's. Its title is HM_STR_TITLE's id. */
#define HM_STR_QS_SHUFFLE 0x3f29
#define HM_STR_QS_REPEAT  0x3f2a
#define HM_STR_QS_TIMER   0x3f2b
#define HM_STR_QS_SLEEP   0x3f2c
#define HM_STR_QS_CLICKER 0x3f34    /* row 4: "Clicker: Headphones" (0x3f2d-0x3f33: settings.h's) */

/* The popup's list, Menu 0x25ba (Cancel, Confirm), which the loader points at
 * hm_popup: Apple's two items and four more. Its bundle index entry. */
#define HM_POPUP_ENTRY  0x18224cu
#define HM_POPUP_ID     0x25bau
#define HM_POPUP_OFFSET 0x9630u
#define HM_POPUP_SIZE   0x54u       /* 2 items */
#define HM_ROWS         6

/* The main menu, Menu 0x2512 (every row it can show; fn 33 hides the ones
 * Settings > Main Menu leaves out): the loader points its entry at hm_main,
 * Apple's 22 items with a Queue row after Music (HM_MAIN_AFTER), a clone of
 * Settings' (HM_MAIN_LIKE: a plain row with the arrow) whose function is fn
 * 28 (word 3 0x1ae2), which nothing else runs but a popup's Cancel. Its
 * element and label are HM_STR_UPNEXT's id. */
#define HM_MAIN_ENTRY   0x182210u
#define HM_MAIN_ID      0x2512u
#define HM_MAIN_OFFSET  0x8f14u
#define HM_MAIN_ITEMS   22
#define HM_MAIN_SIZE    (4 + HM_MAIN_ITEMS * 40)
#define HM_MAIN_AFTER   0           /* Music */
#define HM_MAIN_LIKE    17          /* Settings */
#define HM_MAIN_LABEL   0xffaau     /* Settings' label, checked at boot */

/* Bytecode pcs (code base 0x192948 + the offsets tools/re/tcmd.py prints).
 * The eight hold handlers (fn 191 Playlists, 199, 211 Songs, 212, 219, 226,
 * 233, 239), Playlists' opening (fn 188) and its Select (fn 190) and Menu
 * (fn 192) handlers all lie in [HM_LO, HM_HI]; vm_hook hands every pc in there to
 * holdmenu_vm, our own bytecode [HM_SNIPPET, HM_SNIPPET_END), and the single pcs
 * below. */
#define TCMD_CODE       0x192948
#define HM_LO           (TCMD_CODE + 0x323e)
#define HM_HI           (TCMD_CODE + 0x4386)
#define HM_FN_SELECT    (TCMD_CODE + 0xc38)     /* fn 50: send 0x08df.9b(), runs the item */
#define HM_FN_SELECTED  (TCMD_CODE + 0xc42)     /* fn 50, after that send */
#define HM_FN_SELECT_NIL (TCMD_CODE + 0xc43)    /* fn 50's return nil */
#define HM_FN_BACK      (TCMD_CODE + 0x43a)     /* fn 14 */
#define HM_GO_BACK      (TCMD_CODE + 0x7a8)     /* fn 28's tail: fn 14(); return nil */
#define HM_FN_CANCEL    (TCMD_CODE + 0x7a0)     /* fn 28: the popup's first row */
#define HM_FN_CONFIRM   (TCMD_CODE + 0x782)     /* fn 27: the other rows, calls global 0x8e8 */
/* fn 26 (the popup's deferred opener; Apple's and ours) returning, once its fn
 * 20 has put the popup screen up: 0x08df.a0 finds the list in the screen up,
 * so this is where the rows are shown or hidden (HM_VIS_RUN). */
#define HM_POPUP_UP     (TCMD_CODE + 0x774)
#define HM_FN_NP_SELECT (TCMD_CODE + 0x2834)    /* fn 151: Now Playing binds Select to fn 169 */
#define HM_SCREEN_FWD   (TCMD_CODE + 0x5f5)     /* fn 20 opens a screen: the slide forward */
#define HM_SCREEN_BACK  (TCMD_CODE + 0x5b5)     /* ... and back (fn 14's screen) */
#define HM_PICKED       (TCMD_CODE + 0x3310)    /* fn 190 (Playlists' Select), the row read */
#define HM_PICK_MENU    (TCMD_CODE + 0x33fc)    /* fn 192, Playlists' Menu */
#define HM_PLAYLISTS    (TCMD_CODE + 0x323e)    /* fn 188, opening Playlists */
#define HM_SONG_PICK    (TCMD_CODE + 0x39ea)    /* fn 210 (a songs list's Select), the row read */
#define HM_QS_HOLD      (TCMD_CODE + 0x4512)    /* fn 243: hold Menu (stock: 0x08ea.cb, the backlight) */
/* fn 249 (0x795), what holding Play runs once it's been held for a second
 * (fn 250 arms it): stop, Play bound to wake, the rest unbound, sleep
 * (0x08de.6f(9)). No arguments, locals or calls of its own: its body runs in
 * any frame with stack for a three-argument send. */
#define HM_SLEEP_BODY   (TCMD_CODE + 0x45ea)
#define HM_SLEEP_END    (TCMD_CODE + 0x45ea + 0xaa)
/* fn 480: no arguments, two locals and stack for five, like a hold handler's
 * frame, so HM_OPEN runs in it for quick settings (HM_QS_RUN). */
#define HM_QS_FRAME     (TCMD_CODE + 0x7fd0)
/* fn 33 (fn 36, the main menu's opener, runs it; Menu back to the main menu
 * too): 0x08df.a0 on each row by its Main Menu setting (fn 32 > 31 > 30). Its
 * last drop, only reached when the main menu is up: then HM_MM_RUN shows or
 * hides the Queue row, and goes on to its return. */
#define HM_MM_SHOW      (TCMD_CODE + 0x974)
#define HM_MM_SHOWN     (TCMD_CODE + 0x975)

/* Where our bytecode runs from. The VM returns once its pc reaches the running
 * function's end ([vm+0x24]; 0x9d288), with no check below, so bytecode can
 * run from anywhere lower, but not from the payload. This is the popup's own
 * stock Menu 0x25ba (0x54 bytes at 0x18e48c), unused once the loader points
 * its entry at hm_popup, and right after it Apple's Settings Menu (0x234
 * bytes at 0x18e4e0), unused once loader/settings.c points Settings at the
 * payload's copy. It's read-only once Apple's OS runs (on a device; emupod
 * doesn't care), so the loader copies hm_code there at boot, after its checks
 * and after settings_install has copied the menu. The parts (holdmenu.c has
 * them): */
#define HM_SNIPPET      0x18e48c
#define HM_SNIPPET_END  (0x18e4e0 + 0x234)
#define HM_OPEN         HM_SNIPPET              /* open the popup */
#define HM_LABELS       (HM_OPEN + 14)          /* its six rows' labels */
#define HM_RELABEL      (HM_LABELS + 6 * 20)    /* after them: holdmenu.c relabels rows 0, 1 */
#define HM_OPEN_END     (HM_LABELS + 6 * 20 + 10 + 14 + 20 + 2)
#define HM_VIS_RUN      HM_OPEN_END             /* call fn 110, which runs HM_VIS; return */
#define HM_VIS          (HM_VIS_RUN + 10)       /* show or hide each row: 21 bytes a row */
#define HM_VIS_ROW      21
#define HM_VIS_PUSH     16                      /* in a row: push nil (shown), or the stub */
#define HM_VIS_END      (HM_VIS + 6 * HM_VIS_ROW + 2)
#define HM_VIS_STUB     HM_VIS_END              /* per row: push true, jump back */
#define HM_PICK         (HM_VIS_STUB + 6 * 4)   /* back, then open Playlists */
/* fn 110 (Extras' setup, which shows or hides items with 0x08df.a0 itself):
 * its frame has stack for a four-argument send, which a hold handler's (5)
 * hasn't, so HM_VIS runs in it. */
#define HM_FN_VIS_FRAME (TCMD_CODE + 0x1e78)
#define HM_PICK_CALL    (HM_PICK + 8)           /* ... its call of fn 188 (quick settings' Sleep: fn 249's body) */
#define HM_GOTO_ALBUM   (HM_PICK + 18)
#define HM_GOTO_ARTIST  (HM_GOTO_ALBUM + 86)
#define HM_NP_BIND      (HM_GOTO_ARTIST + 58)   /* fn 151's body, then fn 110 (HM_NP_HOLD) */
#define HM_NP_CALL      (HM_NP_BIND + 11)
#define HM_NP_HOLD      (HM_NP_CALL + 10)       /* hold Select bound, in fn 110's frame */
#define HM_UPNEXT       (HM_NP_HOLD + 22)       /* back, Up Next's songs, open them */
#define HM_UPNEXT_BUILD (HM_UPNEXT + 8)         /* (back by then) holdmenu.c puts the songs in */
#define HM_GO_BACK2     (HM_UPNEXT + 33)        /* back twice: fn 14, then HM_GO_BACK */
#define HM_QS_RUN       (HM_GO_BACK2 + 11)      /* call fn 480, which runs HM_OPEN; return nil */
#define HM_MM_RUN       (HM_QS_RUN + 10)        /* fn 33's drop, fn 110 (HM_MM_VIS), on to HM_MM_SHOWN */
#define HM_MM_VIS       (HM_MM_RUN + 12)        /* the main menu's Queue row shown or hidden */
#define HM_MM_PUSH      (HM_MM_VIS + HM_VIS_PUSH)
#define HM_MM_STUB      (HM_MM_VIS + HM_VIS_ROW + 2)    /* push true, jump back */
#define HM_NIL          (HM_OPEN_END - 2)       /* return nil (HM_OPEN's end) */
#define HM_CODE_LEN     (HM_MM_STUB + 4 - HM_SNIPPET)

#ifndef __ASSEMBLER__
#include <stdint.h>

/* For the loader: the bytecode it copies to HM_SNIPPET, and the popup's Menu
 * it points HM_POPUP_ENTRY at (the popup reads its items from there, so
 * quick settings rewrites rows 0-2 while it's up). */
extern const uint8_t hm_code[];
extern uint32_t hm_popup[];
extern uint32_t hm_main[];     /* filled by the loader from Apple's main menu */

uint32_t holdmenu_vm(uint32_t pc, uint32_t vm);
const void *holdmenu_resource(uint32_t fourcc, uint32_t id, uint32_t *size);
uint32_t frogger_vm(uint32_t pc, uint32_t vm);
#endif

#endif

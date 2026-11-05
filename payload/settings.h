#ifndef FROGGER_SETTINGS_H
#define FROGGER_SETTINGS_H

/* Frogger's own Settings entries, shared by the loader (which adds the menu
 * item) and the payload (which answers for it). How Apple's Settings items
 * work: docs/tcmd.md, "The native side of a setting". */

/* Our item's id (menu word 6) and its label's string id. Neither exists in
 * Apple's bundle, and the item id is no case in the settings setter
 * (0xdafc4) or getter (0x7db68). */
#define FROGGER_ITEM_HIDDEN 0x2900
#define FROGGER_STR_HIDDEN  0x3f00
#define FROGGER_ITEM_LETTERS 0x2901     /* "Jump by Letter" (letters.c) */
#define FROGGER_STR_LETTERS  0x3f16
#define FROGGER_ITEM_RESUME  0x2902     /* "Resume Mixes" (resume.c) */
#define FROGGER_STR_RESUME   0x3f1e     /* not 0x3f17: the hold menu's Play Album Next */
/* Switches for the features some won't want: item 0x2903 + n, label
 * 0x3f20 + n, prefs bit 19 + n (set: Off). frogger_on(FEATURE_...) asks. */
#define FEATURE_COVER   0           /* Now Playing's cover page (nowplaying.c) */
#define FEATURE_HOLD    1           /* the hold menu, holding Select (holdmenu.c) */
#define FEATURE_QUICK   2           /* quick settings, holding Menu (holdmenu.c) */
#define FEATURE_BATTERY 3           /* the battery percentage (battery.c) */
#define FEATURE_SLIDE   4           /* the cover page's slide (nowplaying.c) */
#define FEATURE_LOCK    5           /* Lock Cover, the cover while Hold is on (lock.c) */
#define FEATURES        6
#define FROGGER_ITEM_FEATURE 0x2903
#define FROGGER_STR_FEATURE  0x3f20
/* "Flash Storage" (flash.c), after the switches: Off, Auto or On, in prefs
 * bits 28-29 (0 Off, the default). frogger_flash_mode() asks. */
#define FROGGER_ITEM_FLASH   0x2909     /* FROGGER_ITEM_FEATURE + FEATURES */
#define FROGGER_STR_FLASH    0x3f26     /* FROGGER_STR_FEATURE + FEATURES */
#define FROGGER_STR_AUTO     0x3f27     /* its value "Auto" */
#define FLASH_OFF  0
#define FLASH_AUTO 1
#define FLASH_ON   2

/* The cover-art bitmap (art.c). No View shows this id yet; build with
 * -DFROGGER_BMAP_ART=0x25ed to see the test picture in place of a small
 * Now Playing bitmap next to "1 of 2" (clipped to that element's box). */
#ifndef FROGGER_BMAP_ART
#define FROGGER_BMAP_ART 0x3f01
#endif

/* Bits in Apple's prefs flags word (prefs+0xb04) that hold our settings, so
 * they're saved with Apple's. Apple uses bits 0 and 1. */
#define FROGGER_PREF_SHOW_HIDDEN (1u << 16)
#define FROGGER_PREF_NO_LETTERS  (1u << 17)     /* set: Jump by Letter is Off (On by default) */
#define FROGGER_PREF_NO_RESUME   (1u << 18)     /* set: Resume Mixes is Off (On by default) */
#define FROGGER_PREF_NO_FEATURE  19             /* + FEATURE_...: set, that switch is Off */
/* Bits 19-23 are the first five switches; bits 24-26 the timer below, so the
 * sixth goes on at bit 27 (bits 28-29 are Flash Storage's, so a seventh needs
 * another spot). */
#define FROGGER_PREF_FEATURE(f)  (1u << ((f) < 5 ? FROGGER_PREF_NO_FEATURE + (f) : 27 + (f) - 5))
/* Bits 24-26: the backlight timer's last value other than Off and Always On
 * (quick settings' Backlight row cycles Off, it, Always On); 0 = none yet. */
#define FROGGER_PREF_TIMER_SHIFT 24
#define FROGGER_PREF_TIMER       (7u << FROGGER_PREF_TIMER_SHIFT)
#define FROGGER_PREF_FLASH_SHIFT 28
#define FROGGER_PREF_FLASH       (3u << FROGGER_PREF_FLASH_SHIFT)
#define FROGGER_ITEMS (4 + FEATURES)            /* our rows, after Clicker */

/* Apple's values are the string ids of what the row shows. */
#define SETTING_ON     0x279d   /* "On" */
#define SETTING_OFF    0x279e   /* "Off" */
#define SETTING_TOGGLE 0x282f   /* the message Select sends to an on/off item */
#define SETTING_TIMER  0x279f   /* Apple's Backlight Timer item */
#define TIMER_OFF      0x27a0   /* its values: Off, then 0x27a0 + 2..6 (2 s ... Always On) */
#define TIMER_DEFAULT  4        /* 10 s, when no value was ever picked */
#define TIMER_ALWAYS   6        /* Always On */

/* Settings (Menu 0x278d): a count, then 40-byte items. The loader copies it
 * here with our item after Clicker. */
#define SETTINGS_ITEMS 14
#define MENU_ITEM_WORDS 10

#ifndef __ASSEMBLER__
#include <stdint.h>

extern uint32_t settings_menu[1 + (SETTINGS_ITEMS + FROGGER_ITEMS) * MENU_ITEM_WORDS];
extern const char frogger_label_hidden[];
extern const uint32_t frogger_label_hidden_size;
extern const char frogger_label_letters[];
extern const uint32_t frogger_label_letters_size;
extern const char frogger_label_resume[];
extern const uint32_t frogger_label_resume_size;

/* Re-reads our settings from the prefs of library object `lib`. */
void settings_sync(uint32_t lib);
/* Whether a FEATURE_ switch is On (also before the prefs are up). */
int frogger_on(unsigned feature);
/* FLASH_OFF, FLASH_AUTO or FLASH_ON (Off until the prefs are up). */
unsigned frogger_flash_mode(void);
extern const char *const frogger_feature_labels[FEATURES];
extern const char frogger_label_flash[], frogger_label_auto[];
#endif

#endif

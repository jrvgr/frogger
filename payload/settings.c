/* Frogger's Settings entries: "Show Hidden", "Jump by Letter" and "Resume Long
 * Tracks", each On/Off.
 *
 * The loader puts our item into the Settings menu (loader/settings.c). Apple's
 * settings object then asks its setter (0xdafc4) and getter (0x7db68) about
 * it, and hooks.S hands those calls to setting_set()/setting_value() when the
 * item id is ours. The label comes from string_hook. See docs/tcmd.md.
 *
 * The values are saved with Apple's own preferences: the flags word at
 * prefs+0xb04, where Apple uses only bits 0 (Clicker) and 1 (re-notes,
 * "Saving settings"). Ours take bits 16 and up. The library object's first
 * word is the prefs struct; the settings object keeps the library at +0x54. */

#include <stdint.h>
#include "hide.h"
#include "settings.h"

uint32_t settings_menu[1 + (SETTINGS_ITEMS + FROGGER_ITEMS) * MENU_ITEM_WORDS];

const char frogger_label_hidden[] = "Show Hidden";
const uint32_t frogger_label_hidden_size = sizeof frogger_label_hidden;
const char frogger_label_letters[] = "Jump by Letter";
const uint32_t frogger_label_letters_size = sizeof frogger_label_letters;
const char frogger_label_resume[] = "Resume Mixes";
const uint32_t frogger_label_resume_size = sizeof frogger_label_resume;
const char *const frogger_feature_labels[FEATURES] = {
    [FEATURE_COVER] = "Cover Page",
    [FEATURE_HOLD] = "Hold Menu",
    [FEATURE_QUICK] = "Quick Settings",
    [FEATURE_BATTERY] = "Battery Percent",
    [FEATURE_SLIDE] = "Page Slide",
    [FEATURE_LOCK] = "Lock Cover",
};
const char frogger_label_flash[] = "Flash Storage";
const char frogger_label_auto[] = "Auto";

#define PREFS_FLAGS (0xb04 / 4)
#define SETTINGS_LIBRARY (0x54 / 4)

/* Apple's setter for the flags word: stores it, keeps a copy at 0x420a34
 * and marks the prefs for saving (0xacfac). Does nothing if unchanged. */
#define prefs_set_flags ((void (*)(uint32_t lib, uint32_t flags))0xd85cc)

static uint32_t prefs_flags(uint32_t lib)
{
    return (*(uint32_t **)lib)[PREFS_FLAGS];
}

static uint32_t library_of(uint32_t settings)
{
    return ((uint32_t *)settings)[SETTINGS_LIBRARY];
}

void settings_sync(uint32_t lib)
{
    hide_state.show_all = (prefs_flags(lib) & FROGGER_PREF_SHOW_HIDDEN) != 0;
}

/* An item's bit in the flags word, or 0 when the item isn't ours. Show
 * Hidden's bit means On, the others' Off (they're On by default). */
static uint32_t item_bit(uint32_t item)
{
    switch (item) {
    case FROGGER_ITEM_HIDDEN:   return FROGGER_PREF_SHOW_HIDDEN;
    case FROGGER_ITEM_LETTERS:  return FROGGER_PREF_NO_LETTERS;
    case FROGGER_ITEM_RESUME:   return FROGGER_PREF_NO_RESUME;
    default:
        if (item >= FROGGER_ITEM_FEATURE && item < FROGGER_ITEM_FEATURE + FEATURES)
            return FROGGER_PREF_FEATURE(item - FROGGER_ITEM_FEATURE);
        return 0;
    }
}

/* The prefs through the UI object ([[0x43580c]+0x1c] is the library, its
 * first word the prefs), as the features that ask run without a library at
 * hand; 0 until the UI is up, when everything counts as On. */
int frogger_on(unsigned feature)
{
    uint32_t ui = *(volatile uint32_t *)0x43580c, lib, prefs;

    if (!ui || !(lib = ((volatile uint32_t *)ui)[0x1c / 4]) || !(prefs = *(volatile uint32_t *)lib))
        return 1;
    return !(((volatile uint32_t *)prefs)[PREFS_FLAGS] & FROGGER_PREF_FEATURE(feature));
}

/* The prefs flags word through the UI object, or 0 before the UI is up. */
unsigned frogger_flash_mode(void)
{
    uint32_t ui = *(volatile uint32_t *)0x43580c, lib, prefs, v;

    if (!ui || !(lib = ((volatile uint32_t *)ui)[0x1c / 4]) || !(prefs = *(volatile uint32_t *)lib))
        return FLASH_OFF;
    v = (((volatile uint32_t *)prefs)[PREFS_FLAGS] & FROGGER_PREF_FLASH) >> FROGGER_PREF_FLASH_SHIFT;
    return v <= FLASH_ON ? v : FLASH_OFF;
}

/* Apple's Clicker: Off, or where it clicks (clicker.c). */
static uint32_t clicker_value(uint32_t flags)
{
    uint32_t v = (flags & FROGGER_PREF_PLACE) >> FROGGER_PREF_PLACE_SHIFT;

    if (!(flags & FROGGER_PREF_CLICKER))
        return SETTING_OFF;
    return v == CLICK_PHONES ? FROGGER_STR_PHONES : v == CLICK_BOTH ? FROGGER_STR_BOTH : FROGGER_STR_SPEAKER;
}

/* The string id of an item's value ("On"/"Off"), or 0 when it isn't ours. */
uint32_t setting_value(uint32_t item, uint32_t settings)
{
    uint32_t bit = item_bit(item);

    if (item == SETTING_CLICKER)
        return clicker_value(prefs_flags(library_of(settings)));
    if (item == FROGGER_ITEM_VOLUME) {
        uint32_t v = (prefs_flags(library_of(settings)) & FROGGER_PREF_VOLUME) >> FROGGER_PREF_VOLUME_SHIFT;
        return v == CLICK_LOUD ? FROGGER_STR_LOUD : v == CLICK_MEDIUM ? FROGGER_STR_MEDIUM : FROGGER_STR_QUIET;
    }

    if (item == FROGGER_ITEM_FLASH) {
        uint32_t v = (prefs_flags(library_of(settings)) & FROGGER_PREF_FLASH) >> FROGGER_PREF_FLASH_SHIFT;
        return v == FLASH_AUTO ? FROGGER_STR_AUTO : v == FLASH_ON ? SETTING_ON : SETTING_OFF;
    }
    if (!bit)
        return 0;
    return !(prefs_flags(library_of(settings)) & bit) == (item == FROGGER_ITEM_HIDDEN) ? SETTING_OFF : SETTING_ON;
}

#define apple_setter ((int (*)(uint32_t obj, uint32_t selector, uint32_t item, const uint16_t *msg))0xdafc4)
#define SELECTOR_PRID 0x70724944        /* 'prID' */
#define PREFS_TIMER (0xaf8 / 4)         /* the timer's value, 0xd8670 stores it */

/* Apple's setter only stores the timer in the prefs; the backlight keeps
 * its own copy, in seconds (0xffff Always On), until the next boot.
 * Settings' Backlight list (code 0x4408) also runs 0x08eb.111(seconds) and
 * 0x08ea.c7(), which take it and light the screen for it (or turn it off):
 * 0xd8710 on the UI object and 0xefec4 on the app object ([lib]+0xbc4). */
#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define PREFS_APP       0xbc4
#define backlight_seconds ((void (*)(uint32_t ui, uint32_t seconds))0xd8710)
#define backlight_apply ((void (*)(uint32_t app))0xefec4)

static void timer_apply(uint32_t lib, uint32_t v)
{
    static const uint16_t seconds[] = { 0, 1, 2, 5, 10, 20, 0xffff };

    backlight_seconds(UI_OBJECT, seconds[v]);
    backlight_apply(*(uint32_t *)lib + PREFS_APP);
}

/* The Backlight Timer item: Settings sends a value's id; remember it when
 * it's a timer (not Off or Always On). Quick settings sends the toggle
 * message (holdmenu.c), which Apple's setter has no case for: turn that into
 * the next of Off, the timer remembered and Always On, through Apple's
 * setter as Settings would, then apply it as Settings does. Returns 1 when
 * the message was ours. */
static int timer_set(uint32_t lib, const uint16_t *msg, uint32_t settings)
{
    static uint16_t value;
    uint32_t flags = prefs_flags(lib), last = (flags & FROGGER_PREF_TIMER) >> FROGGER_PREF_TIMER_SHIFT;
    uint32_t now = (*(uint32_t **)lib)[PREFS_TIMER], next;

    if (*msg != SETTING_TOGGLE) {
        if (*msg > TIMER_OFF && *msg < TIMER_OFF + TIMER_ALWAYS && (uint32_t)(*msg - TIMER_OFF) != last)
            prefs_set_flags(lib, (flags & ~FROGGER_PREF_TIMER) | (uint32_t)(*msg - TIMER_OFF) << FROGGER_PREF_TIMER_SHIFT);
        return 0;
    }
    if (now && now < TIMER_ALWAYS) {
        if (now != last)
            prefs_set_flags(lib, (flags & ~FROGGER_PREF_TIMER) | now << FROGGER_PREF_TIMER_SHIFT);
        next = TIMER_ALWAYS;
    } else if (now)
        next = 0;
    else
        next = last && last < TIMER_ALWAYS ? last : TIMER_DEFAULT;
    value = (uint16_t)(TIMER_OFF + next);
    apple_setter(settings, SELECTOR_PRID, SETTING_TIMER, &value);     /* through setting_set again: not ours */
    timer_apply(lib, next);
    return 1;
}

/* Apple's Clicker row, Select: Off, Speaker, Headphones, Both, Off. The
 * row's function (fn 401) sends the value it wants, the other one of On and
 * Off (the toggle message 0x282f too is taken). Off and On go through Apple's
 * own setter (its case at 0xdb348: obj+0x33 and prefs bit 0, and whatever
 * else it does); the place is ours, bits 30-31. Our own calls into Apple's
 * setter come back here (clicker_inside) and go on to Apple's. */
static int clicker_inside;

static int clicker_set(uint32_t lib, const uint16_t *msg, uint32_t settings)
{
    static uint16_t value;
    uint32_t flags = prefs_flags(lib), place = (flags & FROGGER_PREF_PLACE) >> FROGGER_PREF_PLACE_SHIFT;
    int on = (flags & FROGGER_PREF_CLICKER) != 0;

    if (clicker_inside)
        return 0;
    if (!(*msg == SETTING_TOGGLE || (on && *msg == SETTING_OFF) || (!on && *msg == SETTING_ON)))
        return 0;                       /* On while On, Off while Off: Apple's */
    if (!on) {
        prefs_set_flags(lib, flags & ~FROGGER_PREF_PLACE);     /* Speaker */
        value = SETTING_ON;
    } else if (place < CLICK_BOTH) {
        prefs_set_flags(lib, (flags & ~FROGGER_PREF_PLACE) | (place + 1) << FROGGER_PREF_PLACE_SHIFT);
        return 1;
    } else {
        prefs_set_flags(lib, flags & ~FROGGER_PREF_PLACE);
        value = SETTING_OFF;
    }
    clicker_inside = 1;
    apple_setter(settings, SELECTOR_PRID, SETTING_CLICKER, &value);
    clicker_inside = 0;
    return 1;
}

/* `msg` is what Apple's setter gets: the toggle message or a value's string
 * id. Returns 0 when the item isn't ours. */
int setting_set(uint32_t item, const uint16_t *msg, uint32_t settings)
{
    uint32_t lib, flags, bit = item_bit(item);
    int set;

    if (item == SETTING_TIMER)
        return timer_set(library_of(settings), msg, settings);
    if (item == SETTING_CLICKER)
        return clicker_set(library_of(settings), msg, settings);
    if (item == FROGGER_ITEM_VOLUME) {      /* Select steps Quiet, Medium, Loud */
        uint32_t v;

        lib = library_of(settings);
        flags = prefs_flags(lib);
        v = (flags & FROGGER_PREF_VOLUME) >> FROGGER_PREF_VOLUME_SHIFT;
        if (*msg == SETTING_TOGGLE)
            v = v >= CLICK_LOUD ? CLICK_QUIET : v + 1;
        else
            v = *msg == FROGGER_STR_LOUD ? CLICK_LOUD : *msg == FROGGER_STR_MEDIUM ? CLICK_MEDIUM : CLICK_QUIET;
        prefs_set_flags(lib, (flags & ~FROGGER_PREF_VOLUME) | v << FROGGER_PREF_VOLUME_SHIFT);
        return 1;
    }
    if (item == FROGGER_ITEM_FLASH) {        /* Select steps Off, Auto, On */
        uint32_t v;

        lib = library_of(settings);
        flags = prefs_flags(lib);
        v = (flags & FROGGER_PREF_FLASH) >> FROGGER_PREF_FLASH_SHIFT;
        if (*msg == SETTING_TOGGLE)
            v = v >= FLASH_ON ? FLASH_OFF : v + 1;
        else
            v = *msg == SETTING_ON ? FLASH_ON : *msg == FROGGER_STR_AUTO ? FLASH_AUTO : FLASH_OFF;
        prefs_set_flags(lib, (flags & ~FROGGER_PREF_FLASH) | v << FROGGER_PREF_FLASH_SHIFT);
        return 1;
    }
    if (!bit)
        return 0;
    lib = library_of(settings);
    flags = prefs_flags(lib);
    if (*msg == SETTING_TOGGLE)
        set = !(flags & bit);
    else
        set = (*msg == SETTING_ON) == (item == FROGGER_ITEM_HIDDEN);
    prefs_set_flags(lib, set ? flags | bit : flags & ~bit);
    settings_sync(lib);
    return 1;
}

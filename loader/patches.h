#ifndef FROGGER_PATCHES_H
#define FROGGER_PATCHES_H

#include <stdint.h>

/* One change to Apple's osos image, by its address in RAM. `orig` guards
 * against a different firmware build: if any enabled patch's original bytes
 * don't match, none are applied and the stock OS boots. */
struct patch {
    uint32_t addr;
    uint32_t len;
    const uint8_t *orig;
    const uint8_t *repl;
};

/* Returns the number of patches applied, or -1 if the image didn't match. */
int apply_patches(void);

/* Frogger's Settings items (settings.c): whether Apple's menu is the one we
 * know, and adding them once the payload is in place. */
int settings_check(void);
void settings_install(void);

/* The cover-art Now Playing View (nowplaying.c): the same pair. */
int nowplaying_check(void);
void nowplaying_install(void);

/* The hold menu's bytecode (payload/holdmenu.c), into Apple's Settings Menu
 * once settings_install has copied it: the image is read-only at runtime. */
void holdmenu_install(void);

#endif

#ifndef FROGGER_HIDDENROW_H
#define FROGGER_HIDDENROW_H

/* The Hidden row (hiddenrow.c): at the top of Music › Artists, Albums,
 * Genres and Composers, "Hidden (N)" while N of that list's items are
 * hidden (all their songs are), and Settings › Show Hidden is off. Select
 * on it shows only those N items, in the same list; Menu there goes back to
 * the whole list. docs/re-notes.md, "The Hidden row". */

/* The lists, by their browse level (lib+0x86c; also the order of
 * browse.c's arrays). */
#define HR_GENRES       0
#define HR_ARTISTS      1
#define HR_COMPOSERS    2
#define HR_ALBUMS       3
#define HR_LISTS        4

/* The Hidden list's title. Not in Apple's bundle (tests/test_settings.py). */
#define HR_STR_TITLE    0x3f35

/* Bytecode pcs: each list's Select handler just after its row read
 * (0x08df.a9() stored in local0): fn 238 Genres, 232 Artists, 218
 * Composers, 225 Albums. */
#define HR_PICK_GENRES      (0x192948 + 0x42d8)
#define HR_PICK_ARTISTS     (0x192948 + 0x40aa)
#define HR_PICK_COMPOSERS   (0x192948 + 0x3c22)
#define HR_PICK_ALBUMS      (0x192948 + 0x3e68)

#ifndef __ASSEMBLER__
#include <stdint.h>

/* The hooks (hooks.S). */
uint32_t hiddenrow_count(uint32_t n, unsigned list, uint32_t ui);
int hiddenrow_label(uint32_t prop, uint32_t *row, const char **out);
int32_t hiddenrow_a9(int32_t row, uint32_t obj);

/* For browse.c: a list's widget rows are its level's rows + shift (1: the
 * Hidden row on top, -1: the Hidden list, which has no "All"). */
int hiddenrow_shift(unsigned list);
/* For holdmenu.c: fn 20's slides, fn 14 (1: it went back to the whole list,
 * so fn 14 does nothing more), and the Select handlers' row checks. */
void hiddenrow_screen(int back);
int hiddenrow_back(void);
uint32_t hiddenrow_vm(uint32_t pc, uint32_t vm);
/* letters.c: the Hidden row's label, which sorts with no letter. */
extern char hiddenrow_text[];
const void *hiddenrow_resource(uint32_t fourcc, uint32_t id, uint32_t *size);
#endif

#endif

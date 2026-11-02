/* Jump by letter: spinning the wheel fast through a long Music list (Songs,
 * Artists, Albums, ...) moves a letter at a time instead of a few rows.
 *
 * The wheel's handler (0x90fe4) turns the clicks into a step (stock 2.3
 * speeds it up as you keep spinning: 0x90d50 → 0x4295c) and moves the list
 * by it: the list widget's vtable+0x15c(n) down, +0x158(-n) up. letter_hook
 * sits where that step is looked at (0x9106c). Fast spinning is told by the
 * times of the last moves (0x87de0, microseconds), not by stock's step,
 * which in emupod hardly grows. Spinning fast, every few rows' worth of
 * wheel becomes the distance to the next letter (down) or to the start of
 * this or the previous one (up), and in between the list waits.
 *
 * A row's text comes from the getter the list draws its rows with,
 * 0x7998c(ui, 'Str ', property, row, &text): text points at the row's
 * label, UTF-8, in the UI object's buffer. Each kind of list asks for its
 * own property (Songs 0x335f, Artists 0x3364, ...), so label_hook notes the
 * one the rows on screen last asked for (letter_prop). Music lists are
 * sorted, so the first row of the next letter is found by binary search.
 * Short lists (menus) are left alone.
 *
 * While jumping, the screen's title (element 0x25e7, set like fn 52 does,
 * 0x08de.60 → 0x1fabc) shows the letter, our string LETTER_STR or
 * LETTER_STR2 in turn (the title fetches text only for a new id). The title
 * comes back, the string title_hook noted when the screen set it, on the
 * next slow move or once the wheel has been still for LETTER_TITLE_US:
 * tick_hook runs letter_tick a few times a second on the UI thread (it's in
 * 0xe9664, which the UI's dispatcher calls about every quarter second).
 * docs/re-notes.md, "The wheel and the lists". */

#include <stdint.h>
#include "letters.h"
#include "settings.h"

#define UI_OBJECT       (*(volatile uint32_t *)0x43580c)
#define W_CURSOR        (0x90 / 4)      /* the widget's cursor: vtable+0x11c is its row */
#define W_ROWS          (0x9c / 4)
#define FOURCC_STR      0x53747220u

/* The 'Str ' property list rows last asked 0x7998c for (label_hook). */
volatile uint32_t letter_prop;

#define label_get   ((uint32_t (*)(uint32_t ui, uint32_t fourcc, uint32_t prop, uint32_t row, const char **out))0x7998c)
#define clock_us    ((void (*)(uint32_t *us))0x87de0)

static struct {
    uint32_t at[LETTER_RUN];    /* when the last moves were, oldest first */
    int32_t rows;               /* wheel rows not yet turned into a letter */
} lt;

/* Notes a move now; whether the last LETTER_RUN came within LETTER_FAST_US. */
static int spinning(void)
{
    uint32_t now;
    unsigned i;

    clock_us(&now);
    for (i = 0; i + 1 < LETTER_RUN; i++)
        lt.at[i] = lt.at[i + 1];
    lt.at[LETTER_RUN - 1] = now;
    return lt.at[0] && now - lt.at[0] < LETTER_FAST_US;
}

/* The title's string as the screen set it (title_hook), and whether we're
 * setting it ourselves (so title_hook leaves letter_title alone). */
volatile uint32_t letter_title;
volatile uint8_t letter_setting;

#define TITLE           0x25e7
#define obj_08de        (*(volatile uint32_t *)0x41e938)    /* the bytecode's 0x08de */
#define set_text        ((void (*)(uint32_t obj, uint32_t element, uint32_t str, uint32_t flags))0x1fabc)

static char letter_text[2];
static int title_shown;

static void show_title(uint32_t str)
{
    uint32_t obj = obj_08de;

    if (!obj)
        return;
    letter_setting = 1;
    set_text(obj, TITLE, str, 0x80);
    letter_setting = 0;
}

static void restore_title(void)
{
    if (title_shown && letter_title)
        show_title(letter_title);
    title_shown = 0;
}

/* tick_hook, a few times a second on the UI thread: the title comes back
 * once the wheel has been still for LETTER_TITLE_US. */
void letter_tick(void)
{
    uint32_t now;

    if (!title_shown)
        return;
    clock_us(&now);
    if (now - lt.at[LETTER_RUN - 1] >= LETTER_TITLE_US)
        restore_title();
}

/* frogger_resource: the letter the title shows. */
const void *letter_resource(uint32_t fourcc, uint32_t id, uint32_t *size)
{
    if (fourcc != FOURCC_STR || (id != LETTER_STR && id != LETTER_STR2) || !letter_text[0])
        return 0;
    *size = sizeof letter_text;
    return letter_text;
}

static uint32_t word(uint32_t addr, unsigned i)
{
    return ((const volatile uint32_t *)addr)[i];
}

static uint32_t current_row(uint32_t widget)
{
    uint32_t c = word(widget, W_CURSOR), vt = word(c, 0);
    uint32_t (*fn)(uint32_t) = (uint32_t (*)(uint32_t))(vt + word(vt, 0x11c / 4));

    return fn(c);
}

/* A row's letter: its first letter, upper case, after a leading "The ";
 * anything else is '#', which sorts first. */
static int letter(uint32_t ui, uint32_t row)
{
    const char *s = 0;
    char c;

    label_get(ui, FOURCC_STR, letter_prop, row, &s);
    if (!s)
        return '#';
    while (*s == ' ')
        s++;
    if ((s[0] | 0x20) == 't' && (s[1] | 0x20) == 'h' && (s[2] | 0x20) == 'e' && s[3] == ' ')
        s += 4;
    c = *s;
    if (c >= 'a' && c <= 'z')
        c -= 'a' - 'A';
    return c >= 'A' && c <= 'Z' ? c : '#';
}

/* The first row in [lo, hi) whose letter is at least l (hi if none). */
static uint32_t first_from(uint32_t ui, uint32_t lo, uint32_t hi, int l)
{
    while (lo < hi) {
        uint32_t mid = lo + (hi - lo) / 2;
        if (letter(ui, mid) < l)
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo;
}

/* The list the wheel last moved, for browse.c (the hold menu puts its row back). */
uint32_t letter_widget;

/* letter_hook: the wheel moves list `widget` by `step` rows; returns the
 * step to take instead. */
int32_t letter_step(uint32_t widget, int32_t step)
{
    uint32_t ui = UI_OBJECT, rows, cur, to;
    int l, fast;

    letter_widget = widget;
    if (step == 0)
        return 0;
    rows = word(widget, W_ROWS);
    if (!ui || !letter_prop || rows < LETTER_MIN_ROWS)
        return step;
    /* Settings > Jump by Letter: Apple's prefs flags word, [lib]+0xb04 */
    if (word(word(word(ui, 0x1c / 4), 0), 0xb04 / 4) & FROGGER_PREF_NO_LETTERS)
        return step;
    fast = spinning();
    if (!fast || (lt.rows ^ step) < 0)
        lt.rows = 0;                            /* slow, or turned round */
    if (!fast) {
        restore_title();
        return step;                            /* rows as usual */
    }
    lt.rows += step;
    if (lt.rows > -LETTER_ROWS && lt.rows < LETTER_ROWS)
        return 0;
    step = lt.rows;
    lt.rows = 0;
    cur = current_row(widget);
    if (cur >= rows)
        return step;
    l = letter(ui, cur);
    if (step > 0) {
        to = first_from(ui, cur + 1, rows, l + 1);
        if (to >= rows)
            to = rows - 1;
    } else {
        to = first_from(ui, 0, cur, l);         /* the start of this letter */
        if (to == cur && cur > 0)
            to = first_from(ui, 0, cur, letter(ui, cur - 1));   /* already there: the one before */
    }
    letter_text[0] = (char)letter(ui, to);
    title_shown = title_shown == 1 ? 2 : 1;
    show_title(title_shown == 1 ? LETTER_STR : LETTER_STR2);
    return (int32_t)to - (int32_t)cur;
}

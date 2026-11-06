/* The debug record, for finding what goes wrong on a device: emupod has no
 * cache, no real timing and a tiny library, so some crashes only happen on
 * the iPod.
 *
 * - The trail: every bytecode pc vm_hook hands to C (the hold handlers'
 *   range, our snippets, fn 50/14/28, Now Playing's handlers) and the pc it
 *   went on with, the last DEBUG_TRAIL of them.
 * - The crash: Apple's three abort vectors (undefined 0x140, prefetch abort
 *   0x158, data abort 0x170) push r0-r12 and lr and call 0x41e5c(frame,
 *   kind) with kind 1, 3 or 4. crash_hook (hooks.S) sits on its first
 *   instruction and hands crash_note the frame, the mode's spsr and the
 *   crashed mode's sp and lr; then Apple's handler goes on as before.
 *
 * Both live at DEBUG_ADDR, which survives a reset (Menu+Play) as long as the
 * RAM keeps power. The first UI tick after boot writes the previous boot's
 * record to iPod_Control/iTunes/FroggerDebug as text and starts a new one.
 * Read it in disk mode; build/payload/payload.sym and build/osos.dis place
 * the addresses. */

#include <stdint.h>
#include "debug.h"

static struct dbg {
    uint32_t magic, boot;
    uint32_t kind;                      /* 0, or 1/3/4 as Apple's vectors pass it */
    uint32_t spsr, sp, lr;              /* sp, lr: the crashed mode's */
    uint32_t regs[14];                  /* r0-r12, then lr in the abort mode */
    uint32_t stack[DEBUG_STACK];
    uint32_t n;                         /* trail entries written */
    uint32_t nn;                        /* notes written */
    uint32_t notes[DEBUG_NOTES][4];     /* tag, a, b, ms since boot; tag DEBUG_TAG_VM: n then */
    uint32_t trail[DEBUG_TRAIL][2];     /* pc, the pc it went on with */
} *const dbg = (struct dbg *)DEBUG_ADDR;

static int started;     /* the previous boot's record is written: trail this one */

typedef char dbg_fits[sizeof(struct dbg) <= DEBUG_END - DEBUG_ADDR ? 1 : -1];

void debug_vm(uint32_t pc, uint32_t to)
{
    uint32_t i;

    if (!started)
        return;
    i = dbg->n++ % DEBUG_TRAIL;
    dbg->trail[i][0] = pc;
    dbg->trail[i][1] = to;
}

#define FW_CLOCK_US     0x87de0     /* 0x87de0(&us) */

/* The C side's notes, in their own ring: what the hold menu did, the saves
 * and what they returned, the screen counting (holdmenu.c, hide.c). Each
 * also notes how far the VM trail was, to place it there. */
void debug_note(uint32_t tag, uint32_t a, uint32_t b)
{
    uint32_t i, us;

    if (!started)
        return;
    ((void (*)(uint32_t *))FW_CLOCK_US)(&us);
    i = dbg->nn++ % DEBUG_NOTES;
    dbg->notes[i][0] = tag;
    dbg->notes[i][1] = a;
    dbg->notes[i][2] = b;
    dbg->notes[i][3] = (us / 1000) << 12 | (dbg->n & 0xfff);
}

static int readable(uint32_t a)
{
    return (a & 3) == 0 && (a < 0x2000000 || (a >= 0x40000000 && a < 0x40018000));
}

/* The crash's main words go into the trail as well, as DEBUG_CRASH | kind
 * entries: on a device the record's register block came back from a reset
 * as 0xffffffff with stray bits, while the trail next to it was intact. */
static void trail_crash(uint32_t a, uint32_t b)
{
    uint32_t i = dbg->n++ % DEBUG_TRAIL;

    dbg->trail[i][0] = a;
    dbg->trail[i][1] = b;
}

void crash_note(const uint32_t *frame, uint32_t kind, uint32_t spsr, uint32_t sp, uint32_t lr)
{
    unsigned i;

    if (dbg->magic != DEBUG_MAGIC || dbg->kind)
        return;                         /* keep the first crash */
    trail_crash(DEBUG_CRASH | kind, frame[13]);     /* the abort lr */
    trail_crash(spsr, lr);
    trail_crash(sp, frame[0]);
    dbg->kind = kind;
    dbg->spsr = spsr;
    dbg->sp = sp;
    dbg->lr = lr;
    for (i = 0; i < 14; i++)
        dbg->regs[i] = frame[i];
    for (i = 0; i < DEBUG_STACK; i++)
        dbg->stack[i] = readable(sp) && readable(sp + 4 * i) ? ((const uint32_t *)sp)[i] : 0;
}

/* The firmware's file calls (as its On-The-Go writer 0xf4ad4 uses them). */
#define make_path   ((uint32_t (*)(void *out, uint32_t kind, const char *dir, const char *name))0x53a24)
#define fw_create   ((int (*)(void *path, void *file, uint32_t zero, uint32_t type))0x40474)
#define fw_write    ((int (*)(void *file, uint32_t *len, const void *data))0x407e8)
#define fw_close    ((int (*)(void *))0x40110)
#define ITUN        0x6974756eu
#define FW_DATA     0x64617461u     /* 'data' */

static uint32_t out_path[0x108 / 4];
static uint32_t out_file[0x80 / 4];
static char line[512];               /* lines are put together here and written a block at a time */
static unsigned len;

static void put(const char *s)
{
    while (*s && len < sizeof line)
        line[len++] = *s++;
}

static void hex(uint32_t v)
{
    int b;

    for (b = 28; b >= 0 && len < sizeof line; b -= 4)
        line[len++] = "0123456789abcdef"[(v >> b) & 15];
}

static void dec(uint32_t v)
{
    char d[10];
    unsigned n = 0;

    do
        d[n++] = (char)('0' + v % 10);
    while ((v /= 10) && n < sizeof d);
    while (n && len < sizeof line)
        line[len++] = d[--n];
}

static void write_out(void)
{
    uint32_t n = len;

    if (n)
        fw_write(out_file, &n, line);
    len = 0;
}

/* Ends a line; writes the block when another might not fit. (The header's
 * line once ran past a 96-byte buffer and lost its newline.) */
static void flush(void)
{
    if (len > sizeof line - 1)
        len = sizeof line - 1;
    line[len++] = '\n';
    if (len > sizeof line - 120)
        write_out();
}

static void tag(uint32_t t)
{
    unsigned i;

    for (i = 0; i < 4; i++, t >>= 8)
        line[len++] = (char)((t & 0xff) >= ' ' && (t & 0xff) < 0x7f ? t & 0xff : '?');
}

static void write_record(void)
{
    static const char *const kinds[] = { "?", "undefined instruction", "?", "prefetch abort", "data abort" };
    unsigned i, from, count;

    for (i = 0; i < sizeof out_path / 4; i++)
        out_path[i] = 0;
    if (make_path(out_path, ITUN, "iPod_Control\\iTunes\\", "FroggerDebug") != 0
        || fw_create(out_path, out_file, 0, FW_DATA) != 0)
        return;
    /* "record 2": the whole-session record (notes, a 3400-entry trail). A
     * file without it came from an older payload (a 96-byte line, the last
     * 128 trail entries, no notes), not from blocks this one lost. */
    put("Frogger debug, record 2, boot "); dec(dbg->boot); flush();
    if (dbg->kind) {
        put("crash: "); put(kinds[dbg->kind < 5 ? dbg->kind : 0]);
        put(" (kind "); dec(dbg->kind); put(")"); flush();
        put("spsr "); hex(dbg->spsr); put("  sp "); hex(dbg->sp); put("  lr "); hex(dbg->lr); flush();
        for (i = 0; i < 14; i++) {
            if (i == 13)
                put("abort lr ");
            else {
                put("r"); dec(i); put(i < 10 ? "  " : " ");
            }
            hex(dbg->regs[i]);
            if (i % 4 == 3 || i == 13)
                flush();
            else
                put("   ");
        }
        put("stack:"); flush();
        for (i = 0; i < DEBUG_STACK; i++) {
            put(" "); hex(dbg->stack[i]);
            if (i % 8 == 7)
                flush();
        }
    } else {
        put("no crash recorded"); flush();
    }
    count = dbg->nn < DEBUG_NOTES ? dbg->nn : DEBUG_NOTES;
    put("notes, oldest first ("); dec(dbg->nn); put(" in all): ms tag a b @trail entry (low 12 bits)"); flush();
    for (i = dbg->nn - count; i < dbg->nn; i++) {
        const uint32_t *t = dbg->notes[i % DEBUG_NOTES];
        dec(t[3] >> 12); put(" "); tag(t[0]); put(" "); hex(t[1]); put(" "); hex(t[2]);
        put(" @"); dec(t[3] & 0xfff); flush();
    }
    count = dbg->n < DEBUG_TRAIL ? dbg->n : DEBUG_TRAIL;
    from = dbg->n - count;
    put("vm trail, oldest first; c0de000K abort-lr, spsr lr, sp r0 is a crash ("); dec(dbg->n); put(" in all): pc [-> pc it went on with]"); flush();
    for (i = from; i < dbg->n; i++) {
        const uint32_t *t = dbg->trail[i % DEBUG_TRAIL];
        hex(t[0]);
        if (t[1] != t[0]) {
            put(" -> "); hex(t[1]);
        }
        flush();
    }
    write_out();
    fw_close(out_file);
}

/* tick_hook, a few times a second on the UI thread. */
void debug_tick(void)
{
    unsigned i;

    if (started)
        return;
    if (dbg->magic == DEBUG_MAGIC) {
        write_record();
        dbg->boot++;
    } else {
        dbg->magic = DEBUG_MAGIC;
        dbg->boot = 0;
    }
    dbg->kind = 0;
    dbg->n = 0;
    dbg->nn = 0;
    for (i = 0; i < DEBUG_TRAIL; i++)
        dbg->trail[i][0] = dbg->trail[i][1] = 0;
    started = 1;
}

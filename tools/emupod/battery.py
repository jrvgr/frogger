"""Frogger image: the battery as a percentage in the title bar (payload/battery.c).

emupod's battery read (0x118e40) fails (its hardware revision reads 0), so stock shows no battery
at all. Here 0x118e40 becomes a stub that returns a raw reading we choose (`ldr r1, [pc, #8];
str r1, [r0]; mov r0, #0; mov pc, lr; .word raw`), and the rest of Apple's path runs as is:
0x118de0 buckets it, 0x74388 smooths the level, 0x42af4 picks the state.

    battery.py           # each raw value in its own boot: the main menu and Apple's Now Playing
                         # page show the expected percentage; a change of raw value mid-run moves
                         # the number at the next 30 s reading without the bar going blank;
                         # charging keeps Apple's icon
    battery.py stock     # the same raw values on stock 2.3: the bars, for comparison (shots only)

Screenshots: build/emupod-work/bat_*.png. Exits 1 if a check fails.
"""
import struct, subprocess, sys
from ipod3g import Pod, W, OSOS

FAKE_RAW = 0x118e40
CHARGER = 0x7cf84               # 0x7cf84(obj): nonzero on the charger (0x42af4 then shows states 0-3)
THRESHOLDS = 0x36ffc0
fails = []

# 4 x 7 digits and a 5 x 7 "%", as in battery.c
GLYPH = [[6, 9, 9, 9, 9, 9, 6], [2, 6, 2, 2, 2, 2, 7], [6, 9, 1, 2, 4, 8, 15], [14, 1, 1, 6, 1, 1, 14],
         [2, 6, 10, 10, 15, 2, 2], [15, 8, 14, 1, 1, 9, 6], [6, 8, 8, 14, 9, 9, 6], [15, 1, 2, 2, 4, 4, 4],
         [6, 9, 9, 6, 9, 9, 6], [6, 9, 9, 7, 1, 1, 6], [24, 25, 2, 4, 8, 19, 3]]


def check(what, ok):
    print("  %-60s %s" % (what, "ok" if ok else "WRONG"))
    if not ok:
        fails.append(what)


def percent(raw, t):
    """battery.c's percent_of."""
    if raw < t[0]:
        return 0
    if raw >= t[14]:
        return 100
    k = next(k for k in range(1, 15) if raw < t[k])
    return (100 * (k - 1) + 100 * (raw - t[k - 1]) // (t[k] - t[k - 1])) // 14


def text_px(pct):
    """The set pixels of `pct`% in the 25 x 10 bitmap, as (x, y)."""
    s = str(pct)
    x, px = 23 - (5 * len(s) + 5), set()
    for g, w in [(GLYPH[int(c)], 4) for c in s] + [(GLYPH[10], 5)]:
        for row in range(7):
            for col in range(w):
                if g[row] & (1 << (w - 1 - col)):
                    px.add((x + col, 2 + row))
        x += 5
    return px


TEXTS = {frozenset(text_px(pct)): pct for pct in range(101)}


def bar_text(p):
    """The percentage the title bar shows (a 25 x 10 window there holding exactly its pixels), or None."""
    s = p.screen()
    for y0 in range(0, 9):
        for x0 in range(126, 136):
            got = frozenset((x, y) for x in range(25) for y in range(10) if s[(y0 + y) * 160 + x0 + x] == 3)
            if got in TEXTS:
                return TEXTS[got]
    return None


def bar_blank(p):
    s = p.screen()
    return all(s[y * 160 + x] != 3 for y in range(2, 14) for x in range(130, 160))


def boot(raw, osos=W + "/osos-frogger.img"):
    p = Pod(osos=osos, boot_us=0)
    p.m.mem_write(FAKE_RAW, list(struct.pack("<5I", 0xe59f1008, 0xe5801000, 0xe3a00000, 0xe1a0f00e, raw)))
    p.run(9_000_000)
    p.press("select"); p.settle()                   # Language -> English: the main menu
    return p


def set_raw(p, raw):
    p.m.mem_write(FAKE_RAW + 16, list(struct.pack("<I", raw)))


def now_playing(p):
    """Music > Songs > the first song; Select once for Apple's page (the cover page has no bar)."""
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
    p.press("select"); p.settle(); p.run(1_000_000)
    p.press("select"); p.settle()


# Apple's thresholds as emupod's boot leaves them (each run checks them)
T = (0x10e, 0x11e, 0x129, 0x133, 0x139, 0x13f, 0x147, 0x151, 0x15d, 0x16e, 0x17c, 0x190, 0x1a3, 0x1b8, 0x1ce)
RAWS = (T[0] - 0x20, T[2], (T[7] + T[8]) // 2, T[13] + 4, T[14] + 0x20)


def table(p):
    t = struct.unpack("<15H", bytes(p.m.mem_read(THRESHOLDS, 30)))
    check("thresholds as expected", t == T)


def level(raw, stock):
    """One process per boot (emupod opens once per process)."""
    want = percent(raw, T)
    tag = "stock" if stock else "frog"
    print("raw %#x: %d%%" % (raw, want))
    p = boot(raw, OSOS if stock else W + "/osos-frogger.img")
    table(p)
    p.shot("bat_%s_%x_menu.png" % (tag, raw))
    if not stock:
        check("main menu shows %d%%" % want, bar_text(p) == want)
    now_playing(p)
    p.shot("bat_%s_%x_np.png" % (tag, raw))
    if not stock:
        check("Now Playing (Apple's page) shows %d%%" % want, bar_text(p) == want)


def change():
    """A new reading moves the number a quarter of the way (battery.c), at the next 30 s reading."""
    print("change: %#x -> %#x" % (RAWS[-1], RAWS[0]))
    p = boot(RAWS[-1])
    check("starts at 100%", bar_text(p) == 100)
    set_raw(p, RAWS[0])
    seen, blank = [], 0
    for _ in range(620):                            # two readings, the screen every 100 ms
        p.run(100_000)
        v = bar_text(p)
        blank += v is None and bar_blank(p)
        if v is not None and (not seen or seen[-1] != v):
            seen.append(v)
    print("  shown:", seen)
    check("two readings: 100 -> 75 -> 56", seen == [100, 75, 56])
    check("the bar never went blank", blank == 0)
    p.shot("bat_frog_change.png")


def charging():
    """On the charger: Apple's icon, not a number."""
    print("charging")
    p = boot(T[10])
    p.m.mem_write(CHARGER, list(struct.pack("<2I", 0xe3a00001, 0xe1a0f00e)))   # mov r0, #1; mov pc, lr
    p.run(31_000_000)
    p.shot("bat_frog_charging.png")
    check("charging: no number, Apple's icon", bar_text(p) is None and not bar_blank(p))


def main():
    a = sys.argv[1:]
    if a[:1] == ["level"]:
        level(int(a[1], 0), a[2:] == ["stock"])
    elif a == ["change"]:
        change()
    elif a == ["charging"]:
        charging()
    else:
        stock = a == ["stock"]
        runs = [["level", "%#x" % r] + (["stock"] if stock else []) for r in RAWS]
        runs += [] if stock else [["change"], ["charging"]]
        bad = [r for r in runs if subprocess.run([sys.executable, __file__] + r).returncode]
        return 1 if bad else 0
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

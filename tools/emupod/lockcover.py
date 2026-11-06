"""Frogger image: Lock Cover (payload/lock.c), on the card with FroggerArt (mkart.py's art-card.img).
Checks:

1. Nothing playing: Hold on is stock (the lock in the title bar, the rest of the screen as it was).
2. A song playing, on the main menu: Hold on shows the lock screen (the cover, matching the
   72x72 cover in memory pixel for pixel, a title line, the bar); a key with Hold on changes
   nothing; Hold off gives back the main menu as it was.
3. The same from Now Playing's cover page.
4. Settings > Lock Cover off: saved (prefs flags bit 27); Hold on is stock again.

Screenshots lc_*.png. Exits 1 if a check fails."""
import struct, sys
from ipod3g import Pod, W, ROOT

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
ROW_LOCK = 17                                       # in Settings: after Page Slide (16)
BIT_LOCK = 27
ART = 72                                            # lock.h: LOCK_ART, LOCK_ART_TOP, LOCK_ART_LEFT
TOP, LEFT = 16, (160 - ART) // 2
BAR = 19                                            # the title bar's rows
fails = []

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
shown = lambda: rd(SYM["lk"])                       # lk.shown


def check(what, ok, msg=""):
    print("  %-64s %s" % (what, "ok" if ok else "WRONG " + msg))
    if not ok:
        fails.append(what)
        p.shot("lc_wrong.png", 1)


def lock_screen_ok(s):
    """The cover region is the 72x72 cover in art.c's buffer, and the title and bar
    rows below it aren't blank."""
    px = bytes(p.m.mem_read(SYM["art"] + 28, 20 * 72))
    for y in range(ART):
        for x in range(ART):
            sx, sy = x, y
            want = (px[sy * 20 + sx // 4] >> (6 - 2 * (sx & 3))) & 3
            if s[(TOP + y) * 160 + LEFT + x] != want:
                return "cover differs at (%d, %d)" % (x, y)
    if not any(s[96 * 160:104 * 160]):
        return "no title"
    if not any(s[109 * 160:112 * 160]):
        return "no bar"
    return None


def hold_cycle(where):
    before = p.settle()
    p.hold(True); p.run(1_000_000)
    s = p.settle(); p.shot("lc_%s_hold.png" % where, 2)
    bad = lock_screen_ok(s)
    check("%s: Hold on shows the lock screen" % where, shown() == 1 and bad is None, "shown %d %s" % (shown(), bad))
    p.press("menu", after_us=1_000_000); p.press("select", after_us=1_000_000)
    check("%s:   keys with Hold on change nothing" % where, p.settle() == s)
    p.hold(False); p.run(1_000_000)
    after = p.settle(); p.shot("lc_%s_off.png" % where, 2)
    check("%s:   Hold off: the screen as it was" % where, shown() == 0 and after == before, "shown %d" % shown())


def stock_hold(what):
    before = p.settle()
    p.hold(True); p.run(1_000_000)
    s = p.settle(); p.shot("lc_stock_%s.png" % what.split()[0].lower(), 2)
    check(what + ": Hold on is stock (title bar lock, the rest as it was)",
          shown() == 0 and s != before and s[BAR * 160:] == before[BAR * 160:], "shown %d" % shown())
    p.hold(False); p.run(1_000_000)
    check(what + ":   Hold off: as it was", p.settle() == before)


p.press("select"); p.settle()                       # Language: English, the main menu
stock_hold("Nothing playing")

p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()      # Music > Songs
p.press("select", after_us=2_000_000); p.settle()                               # Tone A: Now Playing
hold_cycle("Now Playing")
for _ in range(3):
    p.press("menu"); p.settle()                     # the main menu
hold_cycle("Main menu")

# Settings > Lock Cover: off
p.scroll(-20); p.settle(); p.scroll(2); p.settle(); p.run(300_000); p.press("select"); p.settle()
p.scroll(-30); p.settle(); p.scroll(ROW_LOCK); p.settle(); p.run(300_000)
p.press("select"); p.settle(); p.shot("lc_settings.png", 1)
flags = rd(rd(rd(rd(0x43580c) + 0x1c)) + 0xb04)
check("Lock Cover off: saved (prefs flags bit 27)", flags >> BIT_LOCK & 1, hex(flags))
p.press("menu"); p.settle()
stock_hold("Switch off")
sys.exit(1 if fails else 0)

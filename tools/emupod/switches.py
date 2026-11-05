"""Frogger image: Settings' feature switches (payload/settings.c, frogger_on). Boots with a fake
battery reading (battery.py's stub) on music-card.img and checks, with each switch On and then Off:

1. Page Slide off: the cover page switches to Apple's page with no slide frames between.
2. Hold Menu: on, holding Select in Songs opens the popup; off, it's Apple's add to On-The-Go, and
   holding Select on Now Playing does nothing.
3. Quick Settings: on, holding Menu opens it; off, it's Apple's backlight toggle (0x139a80).
4. Battery Percent: on, the title bar shows the percentage; off, Apple's bars.
5. Cover Page off: Now Playing opens on Apple's page, the art taking no room; on again, the cover
   page comes back.
6. The switches are saved in the prefs flags (bits 19-23). Lock Cover's (bit 27): lockcover.py.

Screenshots sw_*.png. Exits 1 if a check fails."""
import struct, sys
from ipod3g import ROOT
import battery as bat

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
ROW = {"cover": 12, "hold": 13, "quick": 14, "battery": 15, "slide": 16}    # in Settings, after Clicker (8)
BIT = {"cover": 19, "hold": 20, "quick": 21, "battery": 22, "slide": 23}
fails = []

p = bat.boot(bat.RAWS[2])
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
lib = rd(rd(0x43580c) + 0x1c)
hm = lambda i: rd(SYM["hm"] + 4 * i)                # 0 open, 18 qs
np_word = lambda i: rd(SYM["np"] + 4 * i)           # 0 art, 18 page (0 cover, 1 Apple's)
otg = lambda: rd(rd(rd(lib + 0x48) + 0x24) + 0x2c)  # On-The-Go's song count


def check(what, ok, msg=""):
    print("  %-60s %s" % (what, "ok" if ok else "WRONG " + msg))
    if not ok:
        fails.append(what)
        p.shot("sw_wrong.png", 1)


def flags():
    return rd(rd(lib) + 0xb04)


def switch(*names):
    """Main menu > Frogger! (Apple's Settings): Select on each switch's row, back to the main menu."""
    p.scroll(-20); p.settle(); p.scroll(2); p.settle(); p.run(300_000); p.press("select"); p.settle()
    p.scroll(-30); p.settle(); p.run(300_000)             # Settings opens on the row it was left on
    at = 0
    for name in sorted(names, key=ROW.get):
        p.scroll(ROW[name] - at); p.settle(); p.run(300_000); at = ROW[name]
        p.press("select"); p.settle()
    p.shot("sw_settings.png", 1)
    p.press("menu"); p.settle(); p.scroll(-20); p.settle()


def hold_menu():
    p.m.hook_start([0x139a80], None, 0)
    p.press("menu", hold_us=1_500_000); p.settle(); p.run(300_000)
    toggles = len(p.m.hook_log())
    p.m.hook_start([], None, 0)
    return toggles


def songs():
    """The main menu > Music > Songs (every list opens on the row it was left on)."""
    p.scroll(-20); p.settle(); p.press("select"); p.settle()
    p.scroll(-20); p.settle(); p.scroll(3); p.settle(); p.run(300_000); p.press("select"); p.settle()


def film_select():
    """Select, and how many distinct screens came between the one before and the one after."""
    before = p.settle()
    frames = [before]
    p.press("select", after_us=0)
    for _ in range(60):
        p.e.run_for(10_000)
        s = p.screen()
        if s != frames[-1]:
            frames.append(s)
    after = p.settle()
    return len([s for s in frames if s not in (before, after)])


print("all switches on")
check("Battery Percent on: the title bar shows a percentage", bat.bar_text(p) is not None, str(bat.bar_text(p)))
n = hold_menu()
check("Quick Settings on: hold Menu opens it", hm(18) == 1 and n == 0, "qs %d toggles %d" % (hm(18), n))
p.press("menu"); p.settle()

switch("slide")
check("Page Slide off: saved (prefs flags bit 23)", flags() >> BIT["slide"] & 1, hex(flags()))
songs()
p.press("select", after_us=1_500_000); p.settle()                   # Tone A: Now Playing, the cover page
check("Cover Page on: Now Playing opens on it", np_word(18) == 0)
between = film_select()
check("  Select with Page Slide off: no slide frames", np_word(18) == 1 and between <= 2, "%d between" % between)
p.press("menu"); p.settle()                                         # Songs
p.press("select", hold_us=2_000_000); p.settle()
check("Hold Menu on: hold Select in Songs opens the popup", hm(0) == 1)
p.press("menu"); p.settle(); p.press("menu"); p.settle(); p.press("menu"); p.settle()  # the main menu

switch("cover", "hold", "quick", "battery")
check("Cover, Hold, Quick, Battery off: saved (bits 19-22)", flags() >> 19 & 0x1f == 0x1f, hex(flags()))
p.run(31_000_000); p.settle()                                       # the next battery reading
check("Battery Percent off: Apple's bars, no percentage", bat.bar_text(p) is None and not bat.bar_blank(p), str(bat.bar_text(p)))
p.shot("sw_battery_off.png", 1)
n = hold_menu()
check("Quick Settings off: hold Menu is Apple's backlight toggle", hm(18) == 0 and n > 0, "qs %d toggles %d" % (hm(18), n))
p.press("menu"); p.settle()
songs()
before = otg()
p.press("select", hold_us=2_000_000); p.settle()
check("Hold Menu off: hold Select adds to On-The-Go, no popup", hm(0) == 0 and otg() == before + 1, "open %d otg %d -> %d" % (hm(0), before, otg()))
p.press("select", after_us=1_500_000); p.settle(); p.shot("sw_np.png", 1)
art = np_word(0)
check("Cover Page off: Now Playing opens on Apple's page", np_word(18) == 1 and rd(art + 0x48) == 0 and rd(art + 0x54) == 0,
      "page %d art %dx%d" % (np_word(18), rd(art + 0x48), rd(art + 0x54)))
p.press("select", hold_us=2_000_000); p.settle()
check("  hold Select on Now Playing: nothing (Hold Menu off)", hm(0) == 0)
p.press("menu"); p.settle(); p.press("menu"); p.settle(); p.press("menu"); p.settle()
switch("cover")
songs()
p.press("select", after_us=1_500_000); p.settle()
check("Cover Page on again: the cover page, the art 72x72", np_word(18) == 0 and rd(art + 0x48) == 72 and rd(art + 0x54) == 72,
      "page %d art %dx%d" % (np_word(18), rd(art + 0x48), rd(art + 0x54)))
sys.exit(1 if fails else 0)

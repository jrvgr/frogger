"""Frogger image + hmcard.py's card (qs-card.img): quick settings on hold Menu (payload/holdmenu.c,
settings.c). One run, checking as it goes (exits 1 on the first wrong step; screenshots qs_*.png):

1. Main menu: hold Menu opens the popup with five rows (Backlight, Shuffle, Repeat, Sleep, Clicker), and no
   backlight toggle runs (0x139a80).
2. Shuffle cycles Off > Songs > Albums > Off, Repeat Off > One > All > Off, through Apple's setter
   (0xdafc4) with Settings' toggle message: the settings object (+0x1c, +0x1d) and the prefs
   (+0x20/+0x92, +0x1c) agree, and the labels follow ("Shuffle: Songs").
3. Backlight: cycles the timer Off > the timer before (or 10 s) > Always On, and the backlight takes
   each at once (its own copy, UI object +0x164c, in seconds); the popup is titled Settings; the
   timer is remembered in the prefs flags (bits 24-26). Clicker (row 4, after Sleep) shows its value
   ("Clicker: Speaker") and cycles Speaker > Headphones > Both > Off > Speaker through Apple's
   Clicker item (0x282d; prefs bit 0 and bits 30-31).
4. Menu: the popup goes, the main menu is as before (same pixels). Settings shows the values
   (qs_settings.png, by eye).
5. Now Playing (paused, so the clock holds still): hold Menu opens it there too; Menu: Now Playing
   again (same pixels).
6. Songs: hold Select still opens the hold menu's song rows; hold Menu over it is stock's backlight
   toggle (no quick settings). Nothing in Apple's image changed.
7. Main menu: hold Menu > Sleep runs Apple's sleep (fn 249, what holding Play runs) to its end,
   and the popup's state is gone."""
import struct, sys
from ipod3g import Pod, W, ROOT
import hmcard

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
HM = SYM["hm"]
card = hmcard.make("qs-card.img")
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
rb = lambda a: p.m.mem_read(a, 1)[0]
END = 0x346368
snap = bytes(p.m.mem_read(0, END))
p.press("select"); p.settle()                                         # English: main menu
lib = rd(rd(0x43580c) + 0x1c)
root = rd(lib)
SETTINGS = [0]


def check(tag, ok, msg=""):
    now = bytes(p.m.mem_read(0, END))
    diff = [i for i in range(0, END, 4) if snap[i:i + 4] != now[i:i + 4]]
    if diff:
        msg += " (and Apple's image changed: %s)" % [(hex(a), snap[a:a + 4].hex(), now[a:a + 4].hex()) for a in diff[:4]]
        ok = False
    print("%-56s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        p.shot("qs_wrong.png"); sys.exit(1)


hm = lambda i: rd(HM + 4 * i)                                         # 0 open, 11 vis, 17 up, 18 qs


def hold_menu(shot):
    p.m.hook_start([0x139a80], None, 0)
    p.press("menu", hold_us=1_500_000); p.settle(); p.run(300_000)
    toggled = len(p.m.hook_log())
    p.m.hook_start([], None, 0)
    p.shot("qs_%s.png" % shot, 1)
    return toggled


def select():
    """Select on the row highlighted; returns the setter's (item, settings object) calls."""
    p.m.hook_start([0xdafc4], None, 0)
    p.press("select"); p.settle()
    calls = [(r[2], r[0]) for t, pc, r, _ in p.m.hook_log()]
    p.m.hook_start([], None, 0)
    if calls:
        SETTINGS[0] = calls[0][1]
    return [c[0] for c in calls]


def values():
    s = SETTINGS[0]
    shuffle = 0 if not rb(root + 0x20) else 2 if rb(root + 0x92) else 1
    repeat = {0: 0, 2: 1, 1: 2}[rd(root + 0x1c)]                      # prefs: 0 Off, 2 One, 1 All
    return shuffle, repeat, rd(root + 0xaf8), (rb(s + 0x1c), rb(s + 0x1d), rb(s + 0x28)) if s else None


menu_px = p.settle()
n = hold_menu("main")
check("main menu: hold Menu opens quick settings", hm(0) == 1 and hm(18) == 1 and hm(11) == 0x1f, "open %d qs %d vis %x" % (hm(0), hm(18), hm(11)))
check("  no backlight toggle", n == 0, "%d" % n)
t0 = rd(root + 0xaf8)
flags = lambda: rd(root + 0xb04)
last = t0 if 0 < t0 < 6 else 4                                       # Settings' timer, or 10 s
SECONDS = (0, 1, 2, 5, 10, 20, 0xffff)
ui = rd(0x43580c)
cycle = {0: (last, 6, 0), 6: (0, last, 6)}.get(t0, (6, 0, t0))       # Off > the timer > Always On
for i, want in enumerate(cycle):
    items = select()
    now, live = rd(root + 0xaf8), rd(ui + 0x164c)
    check("Backlight: Select -> %d" % want, now == want and items[:1] == [0x279f], "now %d items %s" % (now, [hex(i) for i in items]))
    check("  the backlight takes it at once (%d s)" % SECONDS[want], live == SECONDS[want], "ui+0x164c %d" % live)
    p.shot("qs_backlight%d.png" % i, 1)
check("  the value kept in the prefs flags", (flags() >> 24) & 7 == last, hex(flags()))
p.scroll(1); p.settle(); p.run(300_000)
for want in (1, 2, 0):
    items = select()
    sh, rp, tm, obj = values()
    check("Shuffle: Select -> %s" % ("Off", "Songs", "Albums")[want], items == [0x27a9] and sh == want and obj[0] == want,
          "items %s prefs %d obj %s" % ([hex(i) for i in items], sh, obj))
    p.shot("qs_shuffle%d.png" % want, 1)
check("  still quick settings", hm(18) == 1 and hm(0) == 1)
p.scroll(1); p.settle(); p.run(300_000)
for want in (1, 2, 0):
    items = select()
    sh, rp, tm, obj = values()
    check("Repeat: Select -> %s" % ("Off", "One", "All")[want], items == [0x27ad] and rp == want and obj[1] == want,
          "items %s prefs %d obj %s" % ([hex(i) for i in items], rp, obj))
p.scroll(2); p.settle(); p.run(300_000)                               # past Sleep: Clicker
qs_text = lambda: bytes(p.m.mem_read(SYM["qs_text"], 24)).split(b"\0")[0].decode()
check("Clicker: its row shows the value", qs_text() == "Clicker: Speaker", repr(qs_text()))
for want, tag in (((1, 1), "Headphones"), ((1, 2), "Both"), ((0, 0), "Off"), ((1, 0), "Speaker")):
    items = select()
    f = flags()
    check("Clicker: Select -> %s" % tag, (f & 1, f >> 30 & 3) == want and items[:1] == [0x282d] and qs_text() == "Clicker: " + tag,
          "flags %x items %s label %r" % (f, [hex(i) for i in items], qs_text()))
    p.shot("qs_clicker_%s.png" % tag.lower(), 1)
p.press("menu"); px = p.settle()
check("Menu: the popup goes, the main menu as before", hm(18) == 0 and hm(0) == 0 and hm(17) == 0 and px == menu_px)
check("  rows 0-2 and 4 are the popup's own again", [rd(SYM["hm_popup"] + 4 * (1 + 10 * i + 7)) for i in (0, 1, 2, 4)] == [0x4f81] * 4)
p.scroll(2); p.settle(); p.press("select"); p.settle()                 # Settings
p.scroll(5); p.settle(); p.shot("qs_settings.png", 1)                  # by eye: Shuffle Off, Repeat Off, Backlight Timer Off
p.press("menu"); p.settle()
p.scroll(-2); p.settle(); p.run(300_000)                              # back to Music
p.press("select"); p.settle()
p.scroll(3); p.press("select"); p.settle()                            # Songs
p.press("select", after_us=1_500_000); p.settle()                     # Apple: Now Playing
p.press("play", after_us=800_000)                                     # paused: the clock and bar hold still
np_px = p.settle()
hold_menu("np")
check("Now Playing: hold Menu opens quick settings", hm(18) == 1 and hm(11) == 0x1f)
p.press("menu", after_us=1_500_000); px = p.settle()
check("  Menu: Now Playing again", hm(18) == 0 and px == np_px)
p.press("menu", after_us=1_500_000); p.settle()                       # Songs
p.press("select", hold_us=2_000_000); p.settle(); p.shot("qs_holdselect.png", 1)
check("Songs: hold Select still opens the hold menu", hm(0) == 1 and hm(18) == 0 and hm(11) == 0x3f, "vis %x" % hm(11))
n = hold_menu("overpopup")
check("  hold Menu over it: stock's backlight toggle", hm(18) == 0 and n > 0, "qs %d toggles %d" % (hm(18), n))
p.press("menu"); p.settle()
check("  Menu: back in Songs", hm(0) == 0 and hm(17) == 0)
p.press("menu"); p.settle()                                           # Music, then the main menu
p.press("menu"); p.settle()
hold_menu("sleep")
p.scroll(3); p.settle(); p.run(300_000)                               # Sleep
p.m.hook_start([0x9bab8], None, 0)                                    # the bytecode's every step
p.press("select", after_us=3_000_000)
body = [r[0] - 0x192948 for t, pc, r, _ in p.m.hook_log() if 0x45ea <= r[0] - 0x192948 < 0x4694]
p.m.hook_start([], None, 0)
check("Sleep: Apple's sleep (fn 249) runs to 0x08de.6f(9), as holding Play does", 0x4684 in body and hm(18) == 0 and hm(0) == 0,
      "%d steps of fn 249, qs %d open %d" % (len(body), hm(18), hm(0)))

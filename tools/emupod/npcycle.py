"""Frogger image + art-card.img: Now Playing's pages, round the whole cycle (payload/nowplaying.c).
Plays Tone A from Songs (the cover page), presses Select four times (Apple's page, scrubbing,
rating, the cover page again), Menu (back in Songs), then from the main menu its Now Playing row.
Checks, from the screen and nowplaying.c's np (open, page):

1. Now Playing opens on the cover page: no title bar.
2. Select: Apple's page, with the title bar.
3. Select: scrubbing; Select: rating. Both Apple's page with only the bar changed, each its own.
4. Select: the cover page again, as it opened.
5. Menu: Now Playing closes (Songs, the title bar).
6. Main menu > Now Playing: the cover page again, as it opened.

Each step is shot 60 ms after the press (cyc_N_soon.png, to catch half-drawn transitions) and
once it's settled (cyc_N.png); also one contact sheet, cyc_sheet.png. Exits 1 on a wrong step."""
import struct, sys, zlib
from ipod3g import Pod, W, ROOT

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
TOP = 160 * 60                                      # the screen above the bar: title bar, title, cover/text
BAR = 19 * 160                                      # the title bar's rows
fails = []

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
np_open = lambda: rd(SYM["np"] + 4 * 17)
np_page = lambda: rd(SYM["np"] + 4 * 18)            # 0 the cover page, 1 Apple's
shots = []


def check(what, ok, msg=""):
    print("  %-62s %s" % (what, "ok" if ok else "WRONG " + msg))
    if not ok:
        fails.append(what)


def step(name, key, settle_us=1_200_000):
    p.press(key, hold_us=100_000, after_us=60_000); shots.append(p.screen())
    p.shot(f"cyc_{name}_soon.png", 2)
    p.run(settle_us); s = p.settle(); shots.append(s)
    p.shot(f"cyc_{name}.png", 2)
    return s


p.press("select"); p.settle()                                                  # English
p.press("select"); p.settle(); p.scroll(3); p.press("select"); songs = p.settle()   # Music > Songs
blank_bar = bytes(BAR)

cover = step("1_open", "select", 2_000_000)
check("1. Now Playing opens on the cover page", np_open() and np_page() == 0, "open %d page %d" % (np_open(), np_page()))
check("1.   no title bar (the top rows differ from Songs')", cover[:BAR] != songs[:BAR])
apple = step("2_apple", "select")
check("2. Select: Apple's page", np_open() and np_page() == 1, "page %d" % np_page())
check("2.   the title bar back, the rest changed", apple[:BAR] != cover[:BAR] and apple[:TOP] != cover[:TOP])
scrub = step("3_scrub", "select")
check("3. Select: scrubbing, on Apple's page", np_page() == 1 and scrub[:TOP] == apple[:TOP] and scrub != apple,
      "page %d" % np_page())
rating = step("4_rating", "select")
check("3. Select: rating, on Apple's page", np_page() == 1 and rating[:TOP] == apple[:TOP]
      and rating not in (apple, scrub), "page %d" % np_page())
back = step("5_cover", "select")
check("4. Select: the cover page again, as it opened", np_page() == 0 and back[:TOP] == cover[:TOP],
      "page %d" % np_page())
menu = step("6_menu", "menu")
check("5. Menu: Now Playing closed", not np_open() and menu[:BAR] != blank_bar and menu not in (cover, apple),
      "open %d" % np_open())
p.press("menu"); p.settle(); p.press("menu"); p.settle()                       # Music, the main menu
p.scroll(8); p.settle(); p.run(500_000)                                        # its last row: Now Playing
again = step("7_back", "select", 2_000_000)
check("6. Main menu > Now Playing: the cover page, as it opened", np_open() and np_page() == 0
      and again[:TOP] == cover[:TOP], "open %d page %d" % (np_open(), np_page()))

# A contact sheet: per step, "soon" over "settled" (160x128 each, 4 levels).
GREYS = [(0xc6, 0xd0, 0xc0), (0x8c, 0x95, 0x88), (0x50, 0x56, 0x4e), (0x10, 0x12, 0x10)]
cols, W2, H2 = len(shots) // 2, 160, 128
canvas = [[(255, 255, 255)] * (cols * (W2 + 6)) for _ in range(2 * (H2 + 6))]
for k, px in enumerate(shots):
    ox, oy = (k // 2) * (W2 + 6), (k % 2) * (H2 + 6)
    for y in range(H2):
        for x in range(W2):
            canvas[oy + y][ox + x] = GREYS[px[y * W2 + x] & 3]
raw = b"".join(b"\0" + bytes(c for q in r for c in q) for r in canvas)
ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
open(W + "/cyc_sheet.png", "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", len(canvas[0]), len(canvas), 8, 2, 0, 0, 0))
                                       + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))
print("wrote", W + "/cyc_sheet.png")
sys.exit(1 if fails else 0)

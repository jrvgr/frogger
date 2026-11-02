"""Frogger image + art-card.img: Now Playing's pages. Opens Now Playing (the cover page), presses
Select four times (Apple's page, scrubbing, rating, the cover page again), Menu (a screen with the
title bar), then main menu > Now Playing. Each step is shot 60 ms after the press (cyc_N_soon.png,
to catch half-drawn transitions) and once it's settled (cyc_N.png); also one contact sheet."""
import struct, zlib
from ipod3g import Pod, W

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
shots = []


def step(name, key, settle_us=1_200_000):
    p.press(key, hold_us=100_000, after_us=60_000); shots.append(p.screen())
    p.shot(f"cyc_{name}_soon.png", 2)
    p.run(settle_us); shots.append(p.screen())
    p.shot(f"cyc_{name}.png", 2)


step("1_open", "select", 2_000_000)
for n, name in enumerate(("2_apple", "3_scrub", "4_rating", "5_cover"), 2):
    step(name, "select")
step("6_menu", "menu")
p.scroll(8)
step("7_back", "select", 2_000_000)

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

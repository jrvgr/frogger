"""Frogger image: Apple's heap ends where the payload's 1 MiB starts (loader/patches.c,
HEAP_PATCHES), and playback leaves that 1 MiB alone. Fills the payload area past _bss_end
with a pattern, plays two songs from the art card, then checks the heap Apple set up
(0x37b388: start, length, end, from 0x91e90) and the pattern.

    heaptop.py           # Frogger image (osos-frogger.img)
    heaptop.py stock     # stock 2.3, for comparison: its heap runs to 0x2000000"""
import struct, sys
from ipod3g import Pod, W, OSOS, ROOT

TOP, END = 0x1f00000, 0x2000000
stock = sys.argv[1:] == ["stock"]
if stock:
    image = OSOS
else:
    syms = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
    fill = syms["_bss_end"]
    ram = bytearray(open(W + "/osos-frogger.img", "rb").read())
    ram[fill:END] = bytes([0xa5]) * (END - fill)
    image = W + "/osos-heaptop.img"
    open(image, "wb").write(ram)
p = Pod(osos=image, disk=W + "/art-card.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
start, length, end = rd(0x37b388), rd(0x37b38c), rd(0x37b390)
print("heap %#x + %#x = %#x" % (start, length, end))
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()      # Music > Songs
p.press("select", after_us=4_000_000)
p.press("next", after_us=4_000_000)
print(p.shot("heaptop_np.png", 2))
if stock:
    sys.exit(0 if end == END else 1)
left = bytes(p.m.mem_read(fill, END - fill))
bad = [i for i in range(len(left)) if left[i] != 0xa5]
print("payload area past _bss_end (%#x-%#x): %d bytes changed" % (fill, END, len(bad)))
sys.exit(0 if end == TOP and not bad else 1)

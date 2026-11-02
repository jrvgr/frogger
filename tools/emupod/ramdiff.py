"""RAM words that change when Select toggles Settings row ROW, and stay changed; then who writes the best candidate."""
import struct, sys
from ipod3g import Pod
row = int(sys.argv[1]) if len(sys.argv) > 1 else 8
p = Pod(); p.press("select"); p.settle()
p.scroll(2); p.press("select"); p.settle(); p.scroll(row); p.settle()
N = 0x2000000
def snap(): return p.m.mem_read(0, N)
def toggle(): p.press("select", after_us=300_000); p.settle()
a = snap(); toggle(); b = snap(); toggle(); c = snap()
# words that flip on each toggle and come back: a == c != b
cand = []
for off in range(0, N, 4):
    if a[off:off+4] != b[off:off+4] and a[off:off+4] == c[off:off+4]:
        cand.append(off)
print(len(cand), "words flip with the toggle")
for off in cand[:60]:
    print(hex(off), a[off:off+4].hex(), "->", b[off:off+4].hex())

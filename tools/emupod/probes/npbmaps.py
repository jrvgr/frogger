"""Sizes of the bitmaps Now Playing loads (headers read from the pointer the lookup returns)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.m.hook_start([0x81044, 0x81048, 0x8100c], None, 0)
p.m.hook_start([0x8100c], None, 0); p.press("select", after_us=1_500_000)
seen = {}
for t, pc, r, _ in p.m.hook_log():
    if r[1] == 0x424d6170: seen[r[2] & 0xffff] = (r[0], r[3])
print({hex(k): (hex(v[0]), hex(v[1])) for k, v in seen.items()})

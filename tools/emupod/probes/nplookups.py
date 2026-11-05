"""Bundle lookups (0x8100c: fourcc, id) while the Now Playing screen opens."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
from collections import Counter
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.m.hook_start([0x8100c], None, 0); p.press("select", after_us=1_500_000)
c = Counter()
for t, pc, r, _ in p.m.hook_log():
    c[(r[1].to_bytes(4, "big").decode("latin1"), hex(r[2] & 0xffff))] += 1
for k, n in sorted(c.items()): print(k, n)

"""Every CPU instruction run during 100 ms after playback starts (the stuck idle loop)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.press("select", after_us=800_000)
p.m.hook_start(list(range(0, 0x181d20, 4)), None, 0, True); p.run(100_000)
c = sorted(p.m.hook_counts().items())
print(len(c), "addresses")
for pc, n in c[:80]: print(hex(pc), n)

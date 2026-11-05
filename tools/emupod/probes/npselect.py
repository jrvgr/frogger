"""Bytecode functions run by Select (and Menu) on the Now Playing screen."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "re"))
from ipod3g import Pod, ROOT
from tcmd import TCmd
t = TCmd(str(ROOT / "build/fw/osos.img"))
def fns(log):
    seen = []
    for a in log:
        i = t.index_of(a - t.code)
        if not seen or seen[-1] != i: seen.append(i)
    return seen
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.press("select", after_us=1_500_000)            # play: Now Playing
for label in ("select 1", "select 2", "select 3"):
    p.m.hook_start([0x9bab8], None, 0); p.press("select", after_us=1_500_000)
    print(label, fns([r[0] for _, _, r, _ in p.m.hook_log()])[:30]); p.shot("nps_%s.png" % label[-1], 1)

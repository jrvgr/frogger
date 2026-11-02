"""When does a bytecode function run? Log VM pcs through open Settings / scroll / toggle Clicker."""
import sys
sys.path.insert(0, "../re")
from ipod3g import Pod, ROOT
from tcmd import TCmd
t = TCmd(str(ROOT / "build/fw/osos.img"))
CODE = t.code
def fns(log):
    seen = []
    for a in log:
        i = t.index_of(a - CODE)
        if not seen or seen[-1] != i: seen.append(i)
    return seen
p = Pod(); p.press("select"); p.settle(); p.scroll(2)
for label, act in [("open Settings", lambda: p.press("select")), ("scroll to Clicker", lambda: p.scroll(int(sys.argv[1]) if len(sys.argv) > 1 else 8)),
                   ("toggle", lambda: p.press("select")), ("back out", lambda: p.press("menu"))]:
    p.m.hook_start([0x9bab8], None, 0); act(); p.settle()
    seq = fns([r[0] for _, _, r, _ in p.m.hook_log()])
    print(label, "->", seq[:40], "(fn 401 ran)" if 401 in seq else "")

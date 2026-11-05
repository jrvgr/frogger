"""VM trace while Select is pressed on Settings row N (0 = About). Prints instructions, marks jumps."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import sys
from ipod3g import Pod
CODE = 0x192948
row = int(sys.argv[1]); limit = int(sys.argv[2]) if len(sys.argv) > 2 else 120
p = Pod(); p.press("select"); p.settle()
p.scroll(2); p.press("select"); p.settle()          # Settings
p.scroll(row); p.settle(); p.shot("set_before.png", 1)
p.m.hook_start([0x9bab8], None, 0)
p.press("select", after_us=200_000)
log = [r[0] for t, pc, r, _ in p.m.hook_log()]
p.settle(); p.shot("set_after.png", 1)
print(len(log), "instructions")
prev = None
for a in log[:limit]:
    b = p.m.mem_read(a, 3)
    mark = "" if prev is None or a in (prev + 1, prev + 3) else "  <-"
    print("%5x  %s%s" % (a - CODE, b.hex(" "), mark)); prev = a

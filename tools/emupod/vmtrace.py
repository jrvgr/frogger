"""Log every bytecode instruction the TCmd VM runs while Select opens main-menu row N."""
import sys, struct
from ipod3g import Pod
CODE = 0x192948
ITEM = int(sys.argv[1]) if len(sys.argv) > 1 else 3
p = Pod(); p.press("select"); p.settle(); p.scroll(ITEM - 1); p.settle()
p.m.hook_start([0x9bab8], None, 0)
p.press("select", after_us=300_000)
log = [(t, r[0]) for t, pc, r, _ in p.m.hook_log()]
print(len(log), "instructions")
mem = lambda a, n: p.m.mem_read(a, n)
prev = None
for t, a in log[:int(sys.argv[2]) if len(sys.argv) > 2 else 60]:
    gap = "" if prev is None or a == prev + 1 or a == prev + 3 else "   <- jump"
    print("%9d %6x  %s%s" % (t, a - CODE, mem(a, 3).hex(" "), gap)); prev = a

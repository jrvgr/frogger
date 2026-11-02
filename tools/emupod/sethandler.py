"""Calls to the native settings handler 0xdafc4(obj, r1, item_id, msg*) while opening Settings and toggling row ROW."""
import sys
from collections import Counter
from ipod3g import Pod
row = int(sys.argv[1]) if len(sys.argv) > 1 else 8
p = Pod(); p.press("select"); p.settle()
p.scroll(2)
def calls(label, fn):
    p.m.hook_start([0xdafc4], None, 0); fn()
    c = Counter()
    for t, pc, r, _ in p.m.hook_log():
        msg = int.from_bytes(p.m.mem_read(r[3], 2), "little") if 0x1000000 <= r[3] < 0x2000000 or r[3] < 0x500000 else None
        c[(hex(r[2]), hex(msg) if msg is not None else hex(r[3]), hex(r[1]), hex(r[14]))] += 1
    print(label); [print("  id %s msg %s r1 %s lr %s  x%d" % (*k, n)) for k, n in sorted(c.items())]
calls("open Settings", lambda: (p.press("select"), p.settle()))
p.scroll(row); p.settle()
calls("toggle row %d" % row, lambda: (p.press("select"), p.settle()))

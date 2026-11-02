"""Which store instructions write ADDR(s) while Select toggles Settings row ROW.

    whowrites.py ROW 0x420a34 [0x1dced8c ...]
"""
import re, sys
from ipod3g import Pod
row = int(sys.argv[1]); targets = [int(a, 0) for a in sys.argv[2:]]
pat = re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(str[a-z]*)\s+(r\d+|sl|fp|ip|lr), \[(r\d+|sl|fp|ip|sp|lr)(?:, #(-?\d+))?\]")
REG = {"sl": 10, "fp": 11, "ip": 12, "sp": 13, "lr": 14}
reg = lambda s: REG[s] if s in REG else int(s[1:])
stores = {}
for line in open(str(__import__("ipod3g").ROOT / "build/osos.dis")):
    m = pat.match(line)
    if m: stores[int(m.group(1), 16)] = (m.group(2), reg(m.group(3)), reg(m.group(4)), int(m.group(5) or 0))
def fresh():
    p = Pod(); p.press("select"); p.settle()
    p.scroll(2); p.press("select"); p.settle(); p.scroll(row); p.settle(); return p
p = fresh()
p.m.hook_start(list(stores), None, 0, True); p.press("select", after_us=300_000)
few = [pc for pc, n in p.m.hook_counts().items() if n <= 8]
print(len(few), "stores ran at most 8 times")
p.settle()                                  # the toggle back runs the same path
p.m.hook_start(few, None, 0); p.press("select", after_us=300_000)
for t, pc, r, _ in p.m.hook_log():
    op, src, base, off = stores[pc]
    ea = (r[base] + off) & 0xffffffff
    if any(abs(ea - a) < 4 for a in targets):
        print("%x  %s r%d -> [%x]  value %x  lr %x" % (pc, op, src, ea, r[src], r[14]))

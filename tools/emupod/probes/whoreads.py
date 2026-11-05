"""Which loads read the settings object's Clicker byte (obj+0x33) while Settings is drawn."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import re
from ipod3g import Pod, ROOT
pat = re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(ldr[a-z]*)\s+(r\d+|sl|fp|ip|lr), \[(r\d+|sl|fp|ip|sp|lr)(?:, #(-?\d+))?\]")
REG = {"sl": 10, "fp": 11, "ip": 12, "sp": 13, "lr": 14}
reg = lambda s: REG[s] if s in REG else int(s[1:])
loads = {}
for line in open(str(ROOT / "build/osos.dis")):
    m = pat.match(line)
    if m: loads[int(m.group(1), 16)] = (m.group(2), reg(m.group(3)), reg(m.group(4)), int(m.group(5) or 0))
p = Pod(); p.press("select"); p.settle(); p.scroll(2)
# 1) the settings object: toggle Clicker once from inside Settings
p.press("select"); p.settle(); p.scroll(8); p.settle()
p.m.hook_start([0xdafc4], None, 0); p.press("select"); p.settle()
obj = p.m.hook_log()[0][2][0]; print("settings object", hex(obj))
p.press("menu"); p.settle()                                   # back to the main menu
# 2) count loads while Settings opens, then log the rare ones
p.m.hook_start(list(loads), None, 0, True); p.press("select"); p.settle()
rare = [pc for pc, n in p.m.hook_counts().items() if n <= 40]
p.press("menu"); p.settle()
p.m.hook_start(rare, None, 0); p.press("select"); p.settle()
for t, pc, r, _ in p.m.hook_log():
    op, dst, base, off = loads[pc]
    ea = (r[base] + off) & 0xffffffff
    if obj + 0x30 <= ea <= obj + 0x37:
        print("%x  %s [obj+%#x]  lr %x" % (pc, op, ea - obj, r[14]))

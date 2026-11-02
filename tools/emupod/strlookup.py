from collections import Counter
from ipod3g import Pod
F = [0x8100c, 0x87590, 0x875c4, 0x874cc]
p = Pod(); p.press("select"); p.settle(); p.scroll(2)
p.m.hook_start(F, None, 0); p.press("select"); p.settle()
c = Counter()
for t, pc, r, _ in p.m.hook_log():
    fc = r[1].to_bytes(4, "big").decode("latin1") if 0x20202020 <= r[1] < 0x7f7f7f7f else hex(r[1])
    c[(hex(pc), fc, hex(r[2]) if r[2] in (0xff8d, 0xff8f, 0x279d, 0x279e) else "other", hex(r[14]))] += 1
for k, n in sorted(c.items()): print(k, n)

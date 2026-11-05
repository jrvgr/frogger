"""Every instruction (pc, cpsr unknown) in the window where the CPU ends up masked; print the tail."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import sys
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.m.set_pin(0, 0x02, False); p.m.edge(0, 0x02); p.run(150_000)
p.m.set_pin(0, 0x02, True); p.m.edge(0, 0x02)
while p.m.stats()["now_us"] < 15_725_000:
    p.run(1000)
CODE = list(range(0, 0x181d20, 4)) + [0x18, 0x1c]
log = []
for i in range(4000):
    p.m.hook_start(CODE, None, 0); p.run(20)
    chunk = [(t, pc, r) for t, pc, r, _ in p.m.hook_log()]
    log = (log + chunk)[-20000:]
    if any(pc == 0x13c478 for _, pc, _ in chunk):
        break
print(len(log), "instructions logged; first idle-loop entry:")
idx = next(i for i, (t, pc, r) in enumerate(log) if pc == 0x13c478)
for t, pc, r in log[max(0, idx - int(sys.argv[1]) if len(sys.argv) > 1 else idx - 80):idx + 3]:
    print("%d %6x  r0 %8x r1 %8x sp %8x lr %8x" % (t, pc, r[0], r[1], r[13], r[14]))

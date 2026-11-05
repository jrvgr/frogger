"""When does the CPU end up permanently masked after playback starts? Sample cpsr/pc every 2 ms."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.m.set_pin(0, 0x02, False); p.m.edge(0, 0x02); p.run(150_000)
p.m.set_pin(0, 0x02, True); p.m.edge(0, 0x02)
samples = []
for i in range(500):
    p.run(2000); r = p.m.cpu_regs(); s = p.m.stats()
    samples.append((s["now_us"], r[15], r[14], r[16], s["irqs"], s["ide_irqs"]))
last_open = max(i for i, x in enumerate(samples) if not x[3] & 0x80)
for t, pc, lr, cpsr, irqs, ide in samples[max(0, last_open - 8):last_open + 6]:
    print("%.4f pc %x lr %x cpsr %x irqs %d ide %d" % (t / 1e6, pc, lr, cpsr, irqs, ide))

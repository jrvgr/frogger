"""What's the machine doing once playback starts (the emulator 'hang')."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import struct
from collections import Counter
from ipod3g import Pod
p = Pod(); p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
rd = lambda a: struct.unpack("<I", p.m.mem_read(a, 4))[0]
def state(tag):
    s = p.m.stats(); r = p.m.cpu_regs()
    print(tag, "t=%.2fs irqs=%d ticks=%d pend=%x cpu pc=%x cpsr=%x cop pc=%x asleep=%s fiqs=%d" % (
        s["now_us"] / 1e6, s["irqs"], s["ticks"], s["irq_pending"], r[15], r[16], p.m.cop_regs()[15], s["cop_asleep"], s["audio_fiqs"]),
        "| ICU stat %x en %x pri? %x | CPU_CTL %x COP_CTL %x" % (rd(0xcf001000), rd(0xcf001020), rd(0xcf00102c), rd(0xcf004054), rd(0xcf004058)))
state("before play")
p.m.lcd_take()
p.press("select", after_us=100_000)
for i in range(8):
    p.run(250_000); state("+%.2f" % (0.1 + 0.25 * (i + 1)))
pcs = Counter()
for _ in range(300):
    p.run(1000); pcs[hex(p.m.cop_regs()[15])] += 1
print("cop pcs", pcs.most_common(8))

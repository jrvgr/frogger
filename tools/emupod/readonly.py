"""Frogger image: hold > Add to Queue and hold > Add to Playlist > On-The-Go in Songs, then
compare Apple's image ([0, 0x346368)) with what it was after boot. It must not change: on a
device that memory is read-only once the OS runs (a write there is a data abort), but emupod
allows it, so this is how to catch one (docs/re-notes.md)."""
import sys
from ipod3g import Pod, W
p = Pod(osos=W + "/osos-frogger.img")
END = 0x346368
snap = bytes(p.m.mem_read(0, END))
p.press("select"); p.settle(); p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.press("select", hold_us=2_000_000); p.settle(); p.press("select", after_us=1_500_000); p.settle()   # Add to Queue
p.scroll(1); p.settle(); p.run(500_000)
p.press("select", hold_us=2_000_000); p.settle(); p.scroll(1); p.settle(); p.run(500_000)
p.press("select", after_us=1_500_000); p.settle(); p.press("select", after_us=1_500_000); p.settle()  # Add to Playlist > On-The-Go
p.press("menu"); p.settle(); p.press("menu"); p.settle()
now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(END) if snap[i] != now[i]]
print("changed bytes in Apple's image:", len(diff))
runs = []
for i in diff:
    if runs and i == runs[-1][1] + 1: runs[-1][1] = i
    else: runs.append([i, i])
for a, b in runs[:20]: print("  %06x-%06x" % (a, b))
print(p.shot("ro_end.png", 1))
sys.exit(1 if diff else 0)

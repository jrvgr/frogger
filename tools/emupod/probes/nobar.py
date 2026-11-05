"""The cover page without the title bar, by hand, with the firmware's own SetVisible (0xb4450) doing
the redraws: hide the bar container, open the clips (screen container and Now Playing to top 0),
move the title and art up, hide and show Now Playing so it redraws; then put it all back and show
the bar again. Screenshots nobar_np.png (cover page) and nobar_after.png (back on the main menu).
docs/nowplaying.md has the object layout."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import struct
import sys
from ipod3g import Pod, W  # noqa: E402

SET_VISIBLE = 0xb4450
SENTINEL = 0x35f100                           # a pc in free RAM where a call harness run stops
p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()      # Music > Songs
p.press("select", after_us=2_000_000)                                         # play: Now Playing
ram = bytes(p.m.mem_read(0, 0x2000000))
u = lambda a: struct.unpack_from("<I", ram, a)[0]
i32 = lambda a: struct.unpack_from("<i", ram, a)[0]
rect = lambda o: [i32(o + 0x58 + 4 * k) for k in range(4)]


def setrect(o, r):
    p.m.mem_write(o + 0x58, list(struct.pack("<4i", *r)))


def fw(addr, *args):
    """Call a firmware function on the live machine, then put the CPU back."""
    regs, cpsr = p.m.call_regs()
    r = list(regs); r[:len(args)] = args; r[14] = SENTINEL; r[15] = addr
    p.m.set_cpu_regs(r, cpsr | 0xc0)
    status, n = p.m.call_run(SENTINEL, 2_000_000)
    p.m.set_cpu_regs(list(regs), cpsr)
    return status


art = ram.find(struct.pack("<4i", 36, 52, 92, 108)) - 0x58
view = u(art + 0x10); screens = u(view + 0x10); root = u(screens + 0x10)
bar = u(u(root + 0x70))
kids = [u(u(view + 0x70) + 4 * k) for k in range(u(view + 0x6c))]
saved = {o: rect(o) for o in [screens, view] + kids}
print("hide bar", fw(SET_VISIBLE, bar, 0))
for o in (screens, view):
    r = rect(o); setrect(o, [0] + r[1:])
for o in kids:
    if (u(o + 0x1c) & 0xffff) == 0x3319 or o == art:
        r = rect(o); setrect(o, [r[0] - 18, r[1], r[2] - 18, r[3]])
print("redraw Now Playing", fw(SET_VISIBLE, view, 0), fw(SET_VISIBLE, view, 1))
p.run(500_000); p.shot(W + "/nobar_np.png", 2)
for o, r in saved.items():
    setrect(o, r)
print("show bar", fw(SET_VISIBLE, bar, 1))
p.press("menu", after_us=1_500_000); p.shot(W + "/nobar_after.png", 2)

"""Executed-instruction counts while Select runs a main-menu item, minus a scroll; grouped by function."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import bisect, json, sys
from ipod3g import Pod, W
ITEM = int(sys.argv[1]) if len(sys.argv) > 1 else 5     # main menu row: 5 = Backlight
CODE = list(range(0, 0x181d20, 4))
pro = sorted(int(x, 16) for x in open(W + "/prologues.txt"))
p = Pod(); p.press("select"); p.settle()
p.scroll(ITEM - 1); p.settle()
def count(fn):
    p.m.hook_start(CODE, None, 0, True); fn(); p.settle()
    c = p.m.hook_counts(); p.m.hook_start([], None, 0); return c
base = count(lambda: (p.scroll(-1), p.scroll(1)))
sel = count(lambda: p.press("select"))
p.shot("hot_after.png", 1)
fun = {}
for pc, n in sel.items():
    extra = n - base.get(pc, 0)
    if extra > 0:
        f = pro[bisect.bisect_right(pro, pc) - 1]
        fun[f] = fun.get(f, 0) + extra
top = sorted(fun.items(), key=lambda kv: -kv[1])[:25]
for f, n in top: print(hex(f), n)
json.dump({hex(k): v for k, v in sel.items()}, open(W + "/hot_sel.json", "w"))

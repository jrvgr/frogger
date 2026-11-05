"""One run, every bytecode step and native function entry for the On-The-Go flows a hold menu
builds on: hold Select on a song, Clear Playlist (open, Cancel) and Save Playlist (open, confirm).
Writes popuptrace.json ({step: [[t, pc, r0, r1, r2, r3, lr, vm_pc], ...]}) and pt_<step>.png;
popupsends.py reads it."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import json
from ipod3g import Pod, W
VM = 0x9bab8
pro = [int(x, 16) for x in open(W + "/prologues.txt")]
p = Pod(osos=W + "/osos-frogger.img")
out = {}
# Functions that also run while idle (drawing, timers, audio) flood the log: leave them out.
p.m.hook_start(pro, None, 0, True); p.run(1_000_000)
idle = p.m.hook_counts(); p.m.hook_start([], None, 0)
pro = [a for a in pro if idle.get(a, 0) < 20]
try:                                                  # and what an earlier run found busy (>150 a step)
    busy = {int(x, 16) for x in open(W + "/popupnoise.txt").read().split()}
    pro = [a for a in pro if a not in busy]
except OSError:
    pass
print(len(idle), "functions run while idle;", len(pro), "hooked")


def trace(name, act):
    p.m.hook_start(pro + [VM], None, 0)
    act(); p.settle()
    out[name] = [[t, pc, *r[:4], r[14], r[0] if pc == VM else 0] for t, pc, r, _ in p.m.hook_log()]
    p.m.hook_start([], None, 0)
    p.shot("pt_%s.png" % name, 1)
    print(name, len(out[name]), "entries")


def otg():                                            # Songs > Music > main menu > Music > Playlists > On-The-Go
    for _ in range(2):
        p.press("menu", after_us=1_500_000); p.settle()
    for _ in range(3):
        p.scroll(-6); p.settle(); p.run(500_000)
        p.press("select", after_us=1_500_000); p.settle()


p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
trace("hold", lambda: p.press("select", hold_us=2_000_000))
otg(); p.shot("pt_otg.png", 1)
p.scroll(1); p.settle(); p.run(500_000)
trace("clear_open", lambda: p.press("select", after_us=1_500_000))
trace("clear_cancel", lambda: p.press("select", after_us=1_500_000))
p.scroll(1); p.settle(); p.run(500_000)                                       # Save Playlist (row 2)
trace("save_open", lambda: p.press("select", after_us=1_500_000))
p.scroll(1); p.settle(); p.run(500_000)
trace("save_confirm", lambda: p.press("select", after_us=1_500_000))
p.press("menu", after_us=1_500_000); p.settle(); p.shot("pt_after_save.png", 1)
p.press("menu", after_us=1_500_000); p.settle(); p.shot("pt_playlists.png", 1)
json.dump(out, open(W + "/popuptrace.json", "w"))

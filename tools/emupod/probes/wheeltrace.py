"""What scrolling a list runs (for jump by letter). Builds letters-card.img (letters.py's: 60 songs whose
titles and artists start with letters spread over the alphabet, all on TONEA.mp3), opens Music > Songs
and records three wheel clicks down: every bytecode step, every native method (entered from the
VM's dispatcher, lr 0xa18a8) and every function entry that doesn't also run while idle.
Writes wheeltrace.json ({"scroll": [[t, pc, r0, r1, r2, r3, lr, vm_pc], ...]}) and wt_*.png.

    wheeltrace.py [--card-only]"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import json
from ipod3g import Pod, W
from letters import CARD as card, card as make_card

make_card()
if "--card-only" in sys.argv:
    sys.exit()

VM = 0x9bab8
pro = [int(x, 16) for x in open(W + "/prologues.txt")]
p = Pod(osos=W + "/osos-frogger.img", disk=card)
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()       # Music > Songs
p.shot("wt_songs.png", 1)
p.m.hook_start(pro, None, 0, True); p.run(1_000_000)
idle = p.m.hook_counts(); p.m.hook_start([], None, 0)
pro = [a for a in pro if idle.get(a, 0) == 0]
p.m.hook_start(pro + [VM], None, 0)
p.scroll(3); p.settle()
log = p.m.hook_log(); p.m.hook_start([], None, 0)
p.shot("wt_scrolled.png", 1)
print(len(log), "entries")
json.dump({"scroll": [[t, pc, *r[:4], r[14], r[0] if pc == VM else 0] for t, pc, r, _ in log]},
          open(W + "/wheeltrace.json", "w"))

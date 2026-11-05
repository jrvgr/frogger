"""Count function entries while each Music submenu opens. Usage: lists.py"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import json, time
from ipod3g import Pod, W
PCS = [int(x, 16) for x in open(W + "/prologues.txt")]
p = Pod(); p.press("select")          # Language -> main menu
p.press("select"); p.settle()         # Music
ITEMS = ["Playlists", "Artists", "Albums", "Songs", "Genres", "Composers"]
out = {}
for i, name in enumerate(ITEMS):
    if i: p.scroll(1)
    p.settle()
    t = time.time()
    p.m.hook_start(PCS, None, 0, True)
    p.press("select", after_us=1_500_000); p.settle()
    out[name] = {hex(k): v for k, v in p.m.hook_counts().items()}
    p.m.hook_start([], None, 0)
    p.shot("list_%s.png" % name, 1)
    print(name, len(out[name]), "functions", "%.0fs" % (time.time() - t))
    p.press("menu"); p.settle()
json.dump(out, open(W + "/list_counts.json", "w"))

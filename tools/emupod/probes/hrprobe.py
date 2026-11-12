"""Hidden row groundwork: per Music list (Artists, Albums, Genres, Composers) the list widget's words
(which property it draws), the arrays' keys against the track fields, the getter's calls (property,
row) and 0x816a8's callers. Output: build/emupod-work/hrprobe.json. Usage: hrprobe.py"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702
import json, struct
from ipod3g import Pod, W
import hmcard

SONGS = [("Moon", "Art One", "Alpha", 1, "Rock", "Comp A"), ("Apple", "Art One", "Alpha", 2, "Rock", "Comp A"),
         ("Kite", "Art One", "Beta", 1, "Jazz", "Comp B"), ("Delta", "Art One", "Beta", 2, "Jazz", "Comp B"),
         ("Echo", "Art Two", "Gamma", 1, "Pop", "Comp C"), ("Bravo", "Art Two", "Gamma", 2, "Pop", "Comp C")]
card = hmcard.make("hrprobe-card.img", songs=SONGS)
SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(pathlib.Path(W).parent / "payload/payload.sym") if len(l.split()) == 3}
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
out = {}
p.press("select"); p.settle()
for row, name in [(1, "Artists"), (2, "Albums"), (4, "Genres"), (5, "Composers")]:
    p.press("select"); p.settle(); p.scroll(-8); p.scroll(row); p.settle()
    p.m.hook_start([0x7998c, 0x816a8, 0xe19f8, 0xab204, 0xab0f4])
    p.press("select", after_us=1_500_000); p.settle()
    p.scroll(1); p.settle()
    lw = rd(SYM["letter_widget"])
    p.press("select", hold_us=2_000_000); p.settle()        # hold: the popup
    p.scroll(1); p.settle()
    pw = rd(SYM["letter_widget"])
    log = p.m.hook_log()
    p.m.hook_start([])
    p.press("menu"); p.settle()
    ui = rd(0x43580c); lib = rd(ui + 0x1c)
    arrays = {off: [rd(rd(lib + off) + 4 * i) for i in range(rd(lib + off + 4))] if rd(lib + off) else [] for off in (0x878, 0x880, 0x888, 0x890)}
    out[name] = {"widget": hex(lw), "popup_widget": hex(pw),
                 "widget_words": [hex(rd(lw + 4 * i)) for i in range(0x60)],
                 "popup_words": [hex(rd(pw + 4 * i)) for i in range(0x60)],
                 "vtable": hex(rd(lw)), "vt": {hex(o): hex(rd(lw) + rd(rd(lw) + o)) for o in (0x11c, 0x120, 0x138, 0x158, 0x15c, 0x164)},
                 "cursor_vt": {hex(o): hex(rd(rd(lw + 0x90)) + rd(rd(rd(lw + 0x90)) + o)) for o in (0x11c, 0x120)},
                 "level": rd(lib + 0x86c), "filters": [hex(rd(lib + o)) for o in (0x40, 0x58, 0x5c, 0x60, 0x64)],
                 "arrays": {hex(k): [hex(x) for x in v] for k, v in arrays.items()},
                 "uicache": [hex(rd(ui + 0x12f8 + 4 * i)) for i in range(5)], "uirows": [hex(rd(ui + 0x1618 + 4 * i)) for i in range(4)],
                 "calls": [(hex(pc), [hex(x) for x in r[:4]], hex(r[14]), hex(rd(r[13])) if pc == 0x7998c else "") for t, pc, r, v in log][:400]}
    p.shot("hrprobe_%s.png" % name, 1)
    p.press("menu"); p.settle()
    p.press("menu"); p.settle()
json.dump(out, open(W + "/hrprobe.json", "w"), indent=1)
print("ok")

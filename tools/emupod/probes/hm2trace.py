"""One run, for the hold menu's Go to Album / Go to Artist and Now Playing: every bytecode step
and native function entry while browsing Albums > an album, Artists > an artist > an album, back
out with Menu, then Songs, playing a song and holding Select on Now Playing. Before and after
each step it saves the library object and the UI object's browse state, and the track records.
Card: hmcard.py (hm2-card.img). Writes hm2trace.json and h2_<step>.png."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import json, struct
from ipod3g import Pod, W
import hmcard

VM = 0x9bab8
card = hmcard.make("hm2-card.img")
pro = [int(x, 16) for x in open(W + "/prologues.txt")]
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
words = lambda a, n: list(struct.unpack("<%dI" % n, bytes(p.m.mem_read(a, 4 * n))))
p.m.hook_start(pro, None, 0, True); p.run(1_000_000)
idle = p.m.hook_counts(); p.m.hook_start([], None, 0)
pro = [a for a in pro if idle.get(a, 0) < 20]
try:
    busy = {int(x, 16) for x in open(W + "/popupnoise.txt").read().split()}
    pro = [a for a in pro if a not in busy]
except OSError:
    pass
out = {"steps": []}


def state():
    ui = rd(0x43580c)
    lib = rd(ui + 0x1c)
    return {"ui": ui, "lib": lib, "libw": words(lib, 0x900 // 4), "uiw": words(ui + 0x1000, 0x700 // 4)}


def trace(name, act):
    before = state()
    p.m.hook_start(pro + [VM], None, 0)
    act(); p.settle()
    log = [[t, pc, *r[:4], r[14], r[0] if pc == VM else 0] for t, pc, r, _ in p.m.hook_log()]
    p.m.hook_start([], None, 0)
    out["steps"].append({"name": name, "log": log, "before": before, "after": state()})
    p.shot("h2_%s.png" % name, 1)
    print(name, len(log), "entries")


p.press("select"); p.settle()                       # English
p.press("select"); p.settle()                       # Music
p.scroll(2)
trace("albums_open", lambda: p.press("select", after_us=1_500_000))
p.scroll(1)
trace("album_pick", lambda: p.press("select", after_us=1_500_000))
trace("album_back", lambda: p.press("menu", after_us=1_500_000))
trace("albums_back", lambda: p.press("menu", after_us=1_500_000))
p.scroll(-1)
trace("artists_open", lambda: p.press("select", after_us=1_500_000))
trace("artist_pick", lambda: p.press("select", after_us=1_500_000))
p.scroll(1)
trace("artist_album_pick", lambda: p.press("select", after_us=1_500_000))
trace("artist_album_back", lambda: p.press("menu", after_us=1_500_000))
trace("artist_back", lambda: p.press("menu", after_us=1_500_000))
trace("artists_back", lambda: p.press("menu", after_us=1_500_000))
p.scroll(2)
trace("songs_open", lambda: p.press("select", after_us=1_500_000))
s = state()
lib = s["lib"]
rows = [rd(rd(lib + 0x898) + 4 * i) for i in range(rd(lib + 0x89c))]
out["songs"] = [{"item": it, "item_words": words(it, 16), "rec": rd(it + 0x20), "rec_words": words(rd(it + 0x20), 0x60)}
                for it in rows]
trace("song_play", lambda: p.press("select", after_us=1_500_000))
trace("np_hold", lambda: p.press("select", hold_us=2_000_000, after_us=1_500_000))
trace("np_menu", lambda: p.press("menu", after_us=1_500_000))
json.dump(out, open(W + "/hm2trace.json", "w"))

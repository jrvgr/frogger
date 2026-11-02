"""Frogger image: the hold menu's "Add to Queue" adds exactly the held row, with hidden songs
above it (they still show in Songs). A card copy hr-card.img with five songs, the first and third
carrying Frogger's hide flag:

    Songs:  A hidden*   B   C hidden*   D   E

1. Nothing playing: hold D > Add to Queue; D must play.
2. For every row: play another song from Songs, Menu, hold the row > Add to Queue; that song
   must still play, and Next must play the held row.
3. Then Select on the playing song (from the queue) opens Now Playing: Menu is back in Songs.

Prints each step's title and exits 1 on the first wrong one; screenshots hr_*.png."""
import contextlib, importlib.util, io, shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W

import itdb as mkdb

TITLES = ["A hidden", "B", "C hidden", "D", "E"]
HIDDEN = {0, 2}
card = W + "/hr-card.img"
shutil.copy(W + "/music-card.img", card)
loc = lambda name: ":iPod_Control:Music:F00:%s.mp3" % name
tones = [("TONEA", 2881119, 180000, 128), ("TONEB", 28802739, 720000, 320)]
tracks = [(100 + i, {"title": t, "artist": "Test Artist", "album": "Test Album", "genre": "Test",
                     "location": loc(tones[i % 2][0])}, *tones[i % 2][1:]) for i, t in enumerate(TITLES)]
ids = [t[0] for t in tracks]
db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", [mkdb.mhit(*t, hidden=i in HIDDEN) for i, t in enumerate(tracks)])),
                mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", ids)]))])
start = struct.unpack_from("<I", Path(card).read_bytes()[:512], 0x1be + 24)[0]
tmp = Path(card).with_suffix(".iTunesDB"); tmp.write_bytes(db)
subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{card}@@{start * 512}",
                str(tmp), "::/iPod_Control/iTunes/iTunesDB"], check=True)
tmp.unlink()

p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
row = 0


lib = rd(rd(0x43580c) + 0x1c)
# Songs' rows as 0x7c460 caches them (lib+0x898, count lib+0x89c): items, sorted by title like
# TITLES, so row i's track record (item+0x20) is the song titled TITLES[i]. (The record keeps
# its title as an index into a string pool, db+0xb0.)
assert rd(lib + 0x89c) == len(TITLES), "Songs shows %d rows" % rd(lib + 0x89c)
NAMES = {rd(rd(rd(lib + 0x898) + 4 * i) + 0x20): t for i, t in enumerate(TITLES)}


def title():
    """The playing song's title, or None."""
    item = rd(rd(rd(lib) + 4) + 0x2a8)
    return item and NAMES.get(rd(item + 0x20), "record %#x" % rd(item + 0x20)) or None


def go(to):
    global row
    if to != row:
        p.scroll(to - row)
    row = to


def check(tag, want):
    got = title()
    print("%-34s %-10s %s" % (tag, got, "ok" if got == want else "WRONG, want %r" % want))
    if got != want:
        p.shot("hr_wrong.png")
        sys.exit(1)


def add_to_queue(r):
    go(r)
    p.press("select", hold_us=2_000_000); p.settle()
    p.press("select", after_us=3_000_000); p.settle()            # the first row: Add to Queue


def playing_list():
    return rd(rd(rd(lib) + 4) + 0x2a4)


add_to_queue(3)
check("idle: hold D", "D")
queue = playing_list()
for r in range(len(TITLES)):
    cur = (r + 2) % len(TITLES)                                   # not the held row, nor what plays
    go(cur); p.press("select", after_us=1_500_000); p.settle()    # play it from Songs
    check("play %s from Songs" % TITLES[cur], TITLES[cur])
    assert playing_list() != queue, "still playing from the queue"
    p.press("menu"); p.settle()
    add_to_queue(r)
    check("  hold %s, Add to Queue" % TITLES[r], TITLES[cur])
    p.press("next", after_us=1_500_000); p.settle()
    check("  Next", TITLES[r])
# The queue cut in after B and plays E: Select on E opens Now Playing (it went to the main
# menu while lib+0x44 still named Songs' list), so Menu comes back to this same screen.
go(len(TITLES) - 1); songs = p.settle()
p.press("select", after_us=1_500_000); p.settle(); p.shot("hr_select_playing.png")
check("Select on the playing E", TITLES[-1])
p.press("menu"); p.settle()
if p.screen() != songs:
    print("Select on the playing song didn't open Now Playing"); p.shot("hr_wrong.png"); sys.exit(1)
print(p.shot("hr_songs.png"))

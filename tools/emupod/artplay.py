"""Frogger image + art-card.img (mkart.py): the cover page's cover follows the song (payload/art.c,
nowplaying.c). Plays Tone A from Songs, then Next (Tone B) and Previous (Tone A again). Each time
the cover page must show that song's cover from FroggerArt (mkart.COVERS: track 1 the gradient,
track 2 the checkerboard), 72x72 and centred, pixel for pixel, with art.c's buffer holding the
same picture and np_art_gen counting the change. Shots art_play_1.png (Tone A), art_play_2.png
(Tone B), art_play_3.png (Tone A again). Exits 1 on a wrong step."""
import struct, sys
from ipod3g import Pod, W, ROOT
import mkart

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
SIZE, LEFT = mkart.SIZE, (160 - mkart.SIZE) // 2
fails = []

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
np_page = lambda: rd(SYM["np"] + 4 * 18)            # 0 the cover page, 1 Apple's


def check(what, ok, msg=""):
    print("  %-60s %s" % (what, "ok" if ok else "WRONG " + msg))
    if not ok:
        fails.append(what)
        p.shot("art_play_wrong.png", 2)


def cover_top(s, level):
    """The row the cover `level` starts on, on screen s, centred; None if it isn't there."""
    want = [bytes(level(x, y) for x in range(SIZE)) for y in range(SIZE)]
    for top in range(128 - SIZE):
        if all(s[(top + y) * 160 + LEFT:(top + y) * 160 + LEFT + SIZE] == want[y] for y in range(SIZE)):
            return top
    return None


def showing(tag, track, gen_before):
    s = p.settle()
    print(p.shot("art_play_%s.png" % tag, 2))
    top = cover_top(s, mkart.COVERS[track])
    other = cover_top(s, mkart.COVERS[1 - track])
    check("%s: the cover page" % tag, np_page() == 0, "page %d" % np_page())
    check("%s: track %d's cover on screen, 72x72, centred" % (tag, track + 1), top is not None and other is None,
          "found at %s, the other cover at %s" % (top, other))
    px = bytes(p.m.mem_read(SYM["art"] + 28, mkart.BYTES))      # art.px (after its 28-byte BMap header)
    check("%s:   art.c's buffer holds it" % tag, px == mkart.image(mkart.COVERS[track]))
    gen = rd(SYM["np_art_gen"])
    check("%s:   np_art_gen counted the change" % tag, gen > gen_before, "%d, was %d" % (gen, gen_before))
    return top, gen


p.press("select"); p.settle()                                                  # English
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()      # Music > Songs
gen = rd(SYM["np_art_gen"])
p.press("select", after_us=2_000_000)                                          # Tone A
top, gen = showing("1", 0, gen)
p.press("next", after_us=2_000_000)                                            # Tone B
top2, gen = showing("2", 1, gen)
check("2:   in the same place", top2 == top, "row %s, was %s" % (top2, top))
p.press("prev", after_us=2_000_000)                                            # at 0:00: Tone A again
showing("3", 0, gen)
sys.exit(1 if fails else 0)

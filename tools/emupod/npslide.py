"""Frogger image + art-card.img (mkart.py): Now Playing's page switches slide (payload/nowplaying.c,
np_drawn). Plays Tone A; Select (the cover page to Apple's), Select twice (scrubbing, rating) and
Select again (back to the cover page), with the screen read every 10 ms. Each switch must pass
through frames that are neither page (the slide), going forward with the cover page moving out
to the left, and coming back end on the cover page. Frames: npslide_fwd_NN.png,
npslide_back_NN.png. Exits 1 on a wrong one."""
import sys
from ipod3g import Pod, W
from emupod.recording import png

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
p.press("select"); p.settle()                                               # English
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()   # Music > Songs
p.press("select", after_us=2_000_000)                                       # Tone A: Now Playing
fails = []


def film(tag):
    """Select, and the distinct screens in the 600 ms after it."""
    before = p.settle()
    frames = [before]
    p.press("select", after_us=0)
    for _ in range(60):
        p.e.run_for(10_000)
        s = p.screen()
        if s != frames[-1]:
            frames.append(s)
    after = p.settle()
    for k, s in enumerate(frames):
        open("%s/npslide_%s_%02d.png" % (W, tag, k), "wb").write(png(s, 2))
    return before, frames, after


def check(what, ok):
    print("  %-52s %s" % (what, "ok" if ok else "WRONG"))
    if not ok:
        fails.append(what)


def column(s, x):
    return bytes(s[y * 160 + x] for y in range(128))


cover, frames, apple = film("fwd")
mid = [s for s in frames[1:] if s not in (cover, apple)]
print("forward: %d frames, %d between the pages" % (len(frames), len(mid)))
check("Select slides to Apple's page (4+ frames between)", len(mid) >= 4)
check("  the cover page moves out to the left", any(column(s, 0) == column(cover, 40) for s in mid))
p.press("select"); p.settle()                                               # scrubbing
_, _, rating = film("rating")
check("rating (Apple's own bar slide, unchanged)", rating != apple)
rating, frames, back = film("back")
mid = [s for s in frames[1:] if s not in (rating, back)]
print("back: %d frames, %d between the pages" % (len(frames), len(mid)))
check("Select from rating slides to the cover page (4+ between)", len(mid) >= 4)
check("  it ends on the cover page", back[:160 * 60] == cover[:160 * 60])
sys.exit(1 if fails else 0)

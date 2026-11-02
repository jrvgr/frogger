"""Frogger image + art-card.img: a scrub from the cover page. Opens Now Playing (the cover page),
presses Select twice (Apple's page, scrubbing), moves the knob, then ends the scrub: with Select
(fn 172 goes straight back to normal once the knob has moved) and, in a second run, with the 5 s
timeout. Both should bring the cover page back (npscrub_select.png, npscrub_timeout.png); exits 1
if either shows Apple's page (its title bar) instead. (emupod opens once per process, so each
ending runs in its own: `npscrub.py select` or `npscrub.py timeout` runs just that one.)"""
import subprocess, sys
from ipod3g import Pod, W


def scrub(end):
    p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
    p.press("select"); p.settle()
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
    p.press("select", after_us=2_000_000)                  # play: Now Playing, the cover page
    cover = p.screen()
    p.press("select", after_us=300_000)                    # Apple's page
    p.press("select", after_us=300_000)                    # scrubbing
    p.wheel(-20, after_us=300_000)                         # move the knob
    if end == "select":
        p.press("select", after_us=1_500_000)
    else:
        p.run(6_000_000)
    p.shot(f"npscrub_{end}.png", 2)
    # The cover page has no title bar: its top rows match the cover page's as it opened.
    s = p.screen()
    return s[:160 * 18] == cover[:160 * 18]


if len(sys.argv) > 1:
    back = scrub(sys.argv[1])
    print(sys.argv[1], "cover page" if back else "Apple's page")
    sys.exit(0 if back else 1)
fails = [end for end in ("select", "timeout") if subprocess.run([sys.executable, __file__, end]).returncode]
sys.exit(1 if fails else 0)

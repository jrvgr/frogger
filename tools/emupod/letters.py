"""Frogger image + letters-card.img (wheeltrace.py --card-only makes it): jump by letter
(payload/letters.c). In Songs (or Artists: letters.py artists), scroll slowly, then spin fast
down and up, then waits, spins again and scrolls slowly; prints the wheel's step before and after letter_hook for each
move, and shoots where the list lands (lt_*.png: the title shows the letter after a fast spin and
the list's name again once the wheel has been still for 0.8 s, and after the slow move; the fast
shots are taken 0.2 s after the spin)."""
import sys
from ipod3g import Pod, W
LIST = 1 if sys.argv[1:] == ["artists"] else 3                  # Music: 1 Artists, 3 Songs

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/letters-card.img")
p.press("select"); p.settle(); p.press("select"); p.settle(); p.scroll(LIST); p.press("select"); p.settle()
p.shot("lt_0_list.png", 1)


def moves(tag, act, settle=True):
    p.m.hook_start([0x9106c, 0x91070], None, 0)
    act()
    if settle:
        p.settle()
    log = p.m.hook_log(); p.m.hook_start([], None, 0)
    steps, before = [], None
    for t, pc, r, _ in log:
        v = r[4] - (1 << 32) if r[4] & 0x80000000 else r[4]
        if pc == 0x9106c:
            before = v
        else:
            steps.append("%d>%d" % (before, v) if before != v else str(v))
    print("%-10s %s" % (tag, " ".join(steps)))
    print("          ", p.shot("lt_%s.png" % tag, 1))


moves("slow", lambda: p.scroll(3))
moves("fast_down", lambda: p.wheel(-60, gap_us=1_500, after_us=200_000), settle=False)
moves("fast_down2", lambda: p.wheel(-60, gap_us=1_500, after_us=200_000), settle=False)
moves("fast_up", lambda: p.wheel(60, gap_us=1_500, after_us=200_000), settle=False)
moves("still", lambda: p.run(2_000_000))                        # the title comes back by itself
moves("fast_again", lambda: p.wheel(-60, gap_us=1_500, after_us=200_000), settle=False)
moves("slow_after", lambda: p.scroll(1))                       # and on a slow move

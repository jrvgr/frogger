"""Frogger image: jump by letter (payload/letters.c), on letters-card.img (made here: 60 songs whose
titles start with letters spread over the alphabet, all on TONEA.mp3; probes/wheeltrace.py traces
the same card). In Music > Songs, with the list's row read from the widget (its cursor's +0x8c):

1. A slow scroll moves row by row, and the title stays "Songs".
2. Fast spins down (twice), then up: each lands on the first song of a letter (further down, then
   up) and the title shows that one letter (letter_text, and one glyph wide on screen).
3. The wheel still for 2 s: the title is "Songs" again, the row unchanged.
4. A fast spin, then a slow move: the slow move goes one row and brings the title back.
5. Settings > Jump by Letter off (prefs flags bit 17): a fast spin moves rows as Apple's own
   wheel handler says (letter_hook leaves every step as it is), and the title stays "Songs".

Prints letter_hook's steps (before>after) per move; shots lt_*.png. Exits 1 on a wrong step.

    letters.py [--card-only]"""
import shutil, struct, sys
from pathlib import Path
from ipod3g import Pod, W, ROOT

CARD = W + "/letters-card.img"
WORDS = ["Aerial", "Alpine", "Amber", "Bassline", "Blue Notes", "Breaks", "Circles", "Cold Front",
         "Daybreak", "Deep Space", "Echoes", "Elevate", "Fade", "Fractal", "Glide", "Gravity", "Horizon",
         "Hydro", "Inner City", "Island", "Jazz Note", "Jungle", "Kinetic", "Lagoon", "Liquid", "Lunar",
         "Midnight", "Mirage", "Nebula", "Nightfall", "Ocean", "Orbit", "Pulse", "Quasar", "Rainfall",
         "Reflex", "Rollers", "Silhouette", "Skyline", "Solar", "Spectrum", "Tidal", "Timeless",
         "Undertow", "Urban", "Velvet", "Vortex", "Warmth", "Waves", "Xenon", "Yearning", "Zenith",
         "Zero G", "Atlantis", "Bloom", "Cascade", "Drift", "Ember", "Flow", "Glow"]
ARTISTS = ["Alix Perez", "Bukem", "Calibre", "Doc Scott", "Etherwood", "Fracture", "Goldie",
           "Hybris", "Intense", "Jubei", "Klute", "Lenzman", "Marcus Intalex", "Nookie", "Omni Trio",
           "Peshay", "Qumulus", "Random Movement", "Seba", "Tokyo Prose", "Utah Jazz", "Villem",
           "Wax Doctor", "Xtrah", "Youngsta", "Zero T"]
# Songs' rows' first letters: the list is sorted by title, so only where each letter starts matters.
LETTERS = sorted(w[0] for w in WORDS)
ROW_LETTERS = 10                                    # in Settings: after Show Hidden (9)
BIT_NO_LETTERS = 17


def card():
    import itdb as mkdb
    import hmcard
    shutil.copy(W + "/music-card.img", CARD)
    tracks = [(200 + i, {"title": w, "artist": ARTISTS[i % len(ARTISTS)], "album": "Album %d" % (i % 7),
                         "genre": "Test", "location": ":iPod_Control:Music:F00:TONEA.mp3"}, 2881119, 180000, 128)
              for i, w in enumerate(WORDS)]
    db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", [mkdb.mhit(*t) for t in tracks])),
                    mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", [t[0] for t in tracks])]))])
    tmp = Path(CARD).with_suffix(".iTunesDB"); tmp.write_bytes(db)
    hmcard.mtools(CARD, "mcopy", "-o", str(tmp), "::/iPod_Control/iTunes/iTunesDB")
    tmp.unlink()
    print("wrote", CARD, len(tracks), "songs")


def main():
    SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
    fails = []
    p = Pod(osos=W + "/osos-frogger.img", disk=CARD)
    rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]

    def check(what, ok, msg=""):
        print("  %-62s %s" % (what, "ok" if ok else "WRONG " + msg))
        if not ok:
            fails.append(what)
            p.shot("lt_wrong.png", 1)

    def row():
        return rd(rd(rd(SYM["letter_widget"]) + 0x90) + 0x8c)     # the widget's cursor's row

    def first_of_letter(r):
        return r == 0 or LETTERS[r - 1] != LETTERS[r]

    def title_bar():
        return p.screen()[:19 * 160]

    def glyph_width(bar):
        """How many columns of the title's middle (30..130: no play icon, no battery) have ink."""
        return sum(1 for x in range(30, 130) if any(bar[y * 160 + x] >= 2 for y in range(2, 17)))

    def move(tag, act):
        """act(); letter_hook's steps (0x9106c: r4 before, 0x91070: after) and the row after."""
        p.m.hook_start([0x9106c, 0x91070], None, 0)
        act()
        log = p.m.hook_log(); p.m.hook_start([], None, 0)
        steps, before = [], None
        for _, pc, r, _ in log:
            v = r[4] - (1 << 32) if r[4] & 0x80000000 else r[4]
            if pc == 0x9106c:
                before = v
            else:
                steps.append((before, v))
        print("%-11s row %2d %s  %s" % (tag, row(), LETTERS[row()],
                                         " ".join("%d>%d" % s if s[0] != s[1] else str(s[0]) for s in steps)))
        p.shot("lt_%s.png" % tag, 1)
        return steps

    fast = lambda d: lambda: p.wheel(60 * d, gap_us=1_500, after_us=200_000)

    p.press("select"); p.settle(); p.press("select"); p.settle(); p.scroll(3); p.press("select")   # Music > Songs
    p.settle(); p.shot("lt_0_list.png", 1)
    songs_title = title_bar()

    move("slow", lambda: (p.scroll(3), p.settle()))              # (letter_widget: the list the wheel moved)
    check("1. a slow scroll: from the first row three down, of 60", row() == 3 and
          rd(rd(SYM["letter_widget"]) + 0x9c) == len(WORDS), "row %d" % row())
    check("   the title stays Songs", title_bar() == songs_title)

    def jumped(tag, was, down):
        r = row()
        letter = chr(rd(SYM["letter_text"]) & 0xff)
        check("%s: on the first song of a letter (%s)" % (tag, LETTERS[r]), first_of_letter(r), "row %d" % r)
        check("%s:   %s" % (tag, "further down" if down else "further up"),
              (LETTERS[r] > LETTERS[was]) if down else (r < was), "row %d, was %d" % (r, was))
        check("%s:   the title is the letter %s" % (tag, LETTERS[r]),
              letter == LETTERS[r] and title_bar() != songs_title and 0 < glyph_width(title_bar()) <= 12,
              "letter_text %r, %d columns" % (letter, glyph_width(title_bar())))
        return r

    for tag in ("fast_down", "fast_down2"):
        was = row()
        move(tag, fast(-1))
        jumped("2. " + tag, was, True)
    was = row()
    move("fast_up", fast(1))
    jumped("2. fast_up", was, False)

    at = row()
    move("still", lambda: p.run(2_000_000))
    check("3. still for 2 s: the title is Songs again", title_bar() == songs_title)
    check("3.   the row unchanged", row() == at, "row %d, was %d" % (row(), at))

    move("fast_again", fast(-1))
    at = row()
    check("4. a fast spin: the letter in the title", title_bar() != songs_title)
    move("slow_after", lambda: (p.scroll(1), p.settle()))
    check("4. then a slow move: one row", row() == at + 1, "row %d, was %d" % (row(), at))
    check("4.   and the title is Songs again", title_bar() == songs_title)

    # Settings > Jump by Letter: off
    for _ in range(2):
        p.press("menu"); p.settle()
    p.scroll(-20); p.settle(); p.scroll(2); p.settle(); p.run(300_000); p.press("select"); p.settle()
    p.scroll(-30); p.settle(); p.scroll(ROW_LETTERS); p.settle(); p.run(300_000)
    p.press("select"); p.settle(); p.shot("lt_settings.png", 1)
    flags = rd(rd(rd(rd(0x43580c) + 0x1c)) + 0xb04)
    check("5. Jump by Letter off: saved (prefs flags bit 17)", flags >> BIT_NO_LETTERS & 1, hex(flags))
    p.press("menu"); p.settle(); p.scroll(-20); p.settle()
    p.press("select"); p.settle(); p.scroll(-20); p.settle(); p.scroll(3); p.settle(); p.run(300_000)
    p.press("select"); p.settle()                                                  # Music > Songs
    p.scroll(-60); p.settle()
    steps = move("off_fast", fast(-1))
    check("5.   a fast spin: every step as Apple's", steps and all(a == b for a, b in steps),
          " ".join("%d>%d" % s for s in steps if s[0] != s[1]))
    check("5.   the list moved", row() > 0, "row %d" % row())
    check("5.   the title stays Songs", title_bar() == songs_title)
    return fails


if __name__ == "__main__":
    card()
    if "--card-only" in sys.argv:
        sys.exit()
    sys.exit(1 if main() else 0)

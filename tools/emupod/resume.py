"""Frogger image + resume-card.img (mkresume.py): Resume Mixes (payload/resume.c). One run per
step, each its own process (emupod opens once per process), on a copy of the card.

    resume.py leave    # play Long Mix (25 min), scrub into it, Next (Tone A): its bookmark is
                       # where it was left; pick it again: it starts 5 s before
    resume.py sleep    # card with a mhit bookmark (120 s, mkresume.py --bookmark 120000): Long
                       # Mix starts at 115 s; pause, sleep (hold Play): Play Counts holds 115 s
    resume.py reboot   # boot sleep's card: it starts at 110 s (Play Counts beats the mhit); scrub
                       # to the end: the next song plays, Long Mix's bookmark is 0
    resume.py queue    # Tone A playing, Add to Queue on Long Mix, Next: it starts at 115 s
    resume.py off      # Settings > Resume Mixes Off: Long Mix starts at 0
    resume.py          # all of them, in that order

(A scrub, then sleep, never sleeps in emupod: so sleep starts from a bookmark instead.)
Prints the player's position and Long Mix's bookmark at each step; exits 1 if one is off.
"""
import shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W

SYM = Path(W).parent / "payload/payload.sym"
LONG_MS = 25 * 60 * 1000
fails = []


def check(what, ok):
    print("  %-52s %s" % (what, "ok" if ok else "WRONG"))
    if not ok:
        fails.append(what)


def play_counts(card):
    """The Play Counts file on `card`: (plays, last played, bookmark ms, rating) per track."""
    start = struct.unpack_from("<I", open(card, "rb").read(512), 0x1be + 16 + 8)[0]
    data = subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-i", f"{card}@@{start * 512}",
                           "::/iPod_Control/iTunes/Play Counts", "-"], capture_output=True).stdout
    if data[:4] != b"mhdp":
        return []
    hlen, elen, n = struct.unpack_from("<III", data, 4)
    return [struct.unpack_from("<4I", data, hlen + i * elen) for i in range(n)]


def run(step):
    card = W + "/resume-%s-run.img" % ("sleep" if step == "reboot" else step)    # reboot boots sleep's
    if step != "reboot":
        shutil.copyfile(W + ("/resume-card.img" if step == "leave" else "/resume-bm-card.img"), card)
    p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
    rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
    syms = {l.split()[2]: int(l.split()[0], 16) for l in SYM.read_text().splitlines() if len(l.split()) == 3}
    if step != "reboot":
        p.press("select"); p.settle()                       # first run: Language -> English
    if step == "off":                                       # Frogger! > Resume Mixes: Off
        p.scroll(2); p.press("select"); p.settle(); p.scroll(11); p.run(500_000)
        p.press("select"); p.settle(); p.shot("resume_off_setting.png")
        p.press("menu"); p.settle(); p.scroll(-2); p.run(500_000)
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
    lib = rd(rd(0x43580c) + 0x1c)
    player = rd(rd(lib) + 4)

    def state(tag):
        item = rd(player + 0x2a8)
        track = rd(item + 0x20) if item else 0
        pos, flags = rd(player + 0x2164), rd(player + 0x2380)
        print("%-28s track len %7d ms  pos %7d ms  flags %#x  ours %s" % (
            tag, rd(track + 0x54) if track else 0, pos, flags, rd(syms["resume_track"]) == track != 0))
        return track, pos

    def scrub(steps):
        p.press("select", after_us=300_000)                 # Apple's page
        p.press("select", after_us=300_000)                 # scrubbing
        p.wheel(steps, after_us=800_000)                    # (a Select right after the wheel gets lost)
        p.press("select", after_us=1_500_000)               # done

    def play_row(row):
        p.press("menu", after_us=1_000_000); p.settle()        # Now Playing -> Songs
        p.scroll(-3)                                            # to the top
        if row:
            p.scroll(row)
        p.run(500_000)                                          # (a Select right after the wheel gets lost)
        p.press("select", after_us=2_000_000); p.settle()

    if step == "leave":
        p.press("select", after_us=2_000_000); p.settle()   # Long Mix, row 0
        mix, pos = state("playing Long Mix")
        check("Long Mix is flagged, starts at 0", rd(syms["resume_track"]) == mix and pos < 2000)
        scrub(-60)
        _, at = state("scrubbed")
        check("the scrub moved it", at > 30_000)
        p.press("next", after_us=2_000_000); p.settle()
        state("Next: Tone A")
        bm = rd(mix + 0x60)
        print("  Long Mix bookmark %d ms" % bm)
        check("bookmark = where it was left", abs(bm - at) < 3000)
        play_row(0)
        _, pos = state("picked Long Mix again")
        check("starts 5 s before the bookmark", abs(pos - (bm - 5000)) < 1500)
    elif step == "sleep":
        p.press("select", after_us=2_000_000); p.settle()   # Long Mix, row 0
        mix, pos = state("playing Long Mix")
        check("starts 5 s before its mhit bookmark (120 s)", pos == 115_000)
        w0 = p.m.stats()["ata_writes"]
        p.press("play", after_us=1_000_000)                     # pause
        for _ in range(3):
            p.press("menu"); p.settle()
        p.press("play", hold_us=4_000_000, after_us=20_000_000) # hold Play: sleep
        print("  disk writes going to sleep:", p.m.stats()["ata_writes"] - w0)
        print("  Long Mix bookmark %d ms" % rd(mix + 0x60))
        check("bookmark = where it was paused (resume_flush)", rd(mix + 0x60) == pos)
        counts = play_counts(card)
        print("  Play Counts:", counts)
        check("Play Counts holds it", len(counts) == 3 and counts[2][2] == pos)
    elif step == "queue":
        p.scroll(1); p.run(500_000)
        p.press("select", after_us=2_000_000); p.settle()   # Tone A
        p.press("menu", after_us=1_000_000); p.settle()
        p.scroll(-3); p.run(500_000)                        # Long Mix
        p.press("select", hold_us=2_000_000); p.settle()    # hold menu
        p.press("select", after_us=3_000_000); p.settle()   # Add to Queue
        p.press("next", after_us=2_000_000); p.settle()
        mix, pos = state("Next: Long Mix from Up Next")
        check("Up Next's Long Mix starts at its bookmark - 5 s", rd(syms["resume_track"]) == mix and pos == 115_000)
    elif step == "off":
        p.press("select", after_us=2_000_000); p.settle()   # Long Mix
        mix, pos = state("Resume Off: Long Mix")
        check("not flagged, starts at 0", rd(syms["resume_track"]) == 0 and pos == 0)
    else:
        p.press("select", after_us=2_000_000); p.settle()
        mix, pos = state("after reboot: Long Mix")
        check("the bookmark came back from Play Counts (115 s)", pos == 110_000)
        scrub(-900)
        now, at = state("scrubbed to the end")             # it ends and the next song starts
        p.press("next", after_us=2_000_000); p.settle()
        state("Next")
        print("  Long Mix bookmark %d ms" % rd(mix + 0x60))
        check("played to the end: bookmark 0", (now != mix or at + 15_000 >= LONG_MS) and rd(mix + 0x60) == 0)
    p.shot("resume_%s.png" % step)


if len(sys.argv) > 1:
    run(sys.argv[1])
    sys.exit(1 if fails else 0)
codes = [subprocess.run([sys.executable, __file__, s]).returncode for s in ("leave", "sleep", "reboot", "queue", "off")]
sys.exit(1 if any(codes) else 0)

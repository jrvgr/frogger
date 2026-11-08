#!/usr/bin/env python3
"""Frogger image + skips-card.img (made here): skip counts (payload/skips.c). The card has
"Short Tone" (10 s), Tone A (3 min) and Tone B long (12 min), in that order in the iTunesDB and
in Songs. emupod doesn't play on (the position stays put), so scrubs stand in for listening.
One run per step, each its own process, on a copy of the card.

    skips.py first    # Short Tone, Next at 0 s: none; Tone A at 27 s, Next: none; Tone B, Prev at
                      # 5 s: none; Tone B at 10 s, pick Tone A: a skip; Tone A at 6 s, Next: a
                      # skip
    skips.py save     # Tone A at 6 s, Next: a skip; FroggerSkips (version 2, by key) is written only with Apple's
                      # Play Counts (counts_hook: the 'prwp' event a second or two after the song
                      # change, or sleep), never
                      # on a UI tick while the player loads the next song
    skips.py reboot   # boot save's card: the skip came back from the file
    skips.py end      # Short Tone scrubbed to its end (Tone A starts): none
    skips.py          # all of them, in that order

Exits 1 if a check is off.
"""
import shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W
import mkresume as mk

SYM = Path(W).parent / "payload/payload.sym"
CARD = Path(W) / "skips-card.img"
RUN = Path(W) / "skips-run.img"
fails = []


def check(what, ok):
    print("  %-52s %s" % (what, "ok" if ok else "WRONG"))
    if not ok:
        fails.append(what)


def make_card():
    mp3 = Path(W) / "TONES.mp3"
    if not mp3.exists():
        mk.nix(["sox", "lame"], "sh", "-c", f"sox -n -r 44100 -c 1 -t wav - synth 10 sine 550 vol 0.3"
               f" | lame --quiet -b 32 -m m - {mp3}")
    shutil.copyfile(Path(W) / "music-card.img", CARD)
    start = struct.unpack_from("<I", CARD.read_bytes()[:512], 0x1be + 16 + 8)[0]
    img = f"{CARD}@@{start * 512}"
    tracks = [
        (100, {"title": "Short Tone", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONES.mp3"}, mp3.stat().st_size, 10000, 32),
        (101, {"title": "Tone A", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEA.mp3"}, 2881119, 180000, 128),
        (102, {"title": "Tone B long", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEB.mp3"}, 28802739, 720000, 320),
    ]
    ids = [t[0] for t in tracks]
    db = mk.mhbd([mk.mhsd(1, mk.mhl(b"mhlt", [mk.mhit(*t) for t in tracks])),
                  mk.mhsd(2, mk.mhl(b"mhlp", [mk.mhyp("iPod", ids)]))])
    tmp = Path(W) / "skips-iTunesDB"
    tmp.write_bytes(db)
    mk.nix(["mtools"], "mcopy", "-o", "-i", img, str(tmp), "::/iPod_Control/iTunes/iTunesDB")
    mk.nix(["mtools"], "mcopy", "-o", "-i", img, str(mp3), "::/iPod_Control/Music/F00/TONES.mp3")
    tmp.unlink()


def skips_file(card):
    """FroggerSkips on `card`: (header fields, [(dbid, id, size, length, count, last)])."""
    start = struct.unpack_from("<I", open(card, "rb").read(512), 0x1be + 16 + 8)[0]
    data = subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-i", f"{card}@@{start * 512}",
                           "::/iPod_Control/iTunes/FroggerSkips", "-"], capture_output=True).stdout
    if len(data) < 20:
        return None, []
    h = struct.unpack_from("<IHHIII", data, 0)
    return h, [struct.unpack_from("<QIIIII", data, 20 + i * h[2]) for i in range(h[4]) if 20 + (i + 1) * h[2] <= len(data)]


def boot(first, card=RUN):
    p = Pod(osos=W + "/osos-frogger.img", disk=str(card), persist=True)
    rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
    syms = {l.split()[2]: int(l.split()[0], 16) for l in SYM.read_text().splitlines() if len(l.split()) == 3}
    if first:
        p.press("select"); p.settle()                       # first run: Language -> English
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
    player = rd(rd(rd(0x43580c) + 0x1c)) + 4
    player = rd(player)

    def state(tag):
        item = rd(player + 0x2a8)
        track = rd(item + 0x20) if item else 0
        print("%-34s track len %7d ms  pos %6d ms" % (tag, rd(track + 0x54) if track else 0, rd(player + 0x2164)))
        return rd(track + 0x54) if track else 0, rd(player + 0x2164)

    def skips():
        n = rd(syms["n_skip"])
        return {rd(syms["skip"] + 16 * i): rd(syms["skip"] + 16 * i + 8) for i in range(min(n, 8))}

    def play_row(row):
        p.press("menu", after_us=1_000_000); p.settle()     # Now Playing -> Songs
        p.scroll(-3)
        if row:
            p.scroll(row)
        p.run(500_000)
        p.press("select", after_us=500_000)

    def play_to(ms):                                        # emupod doesn't play on: scrub there
        for _ in range(12):
            if rd(player + 0x2164) >= ms:
                return
            scrub(-8)

    def scrub(steps):
        p.press("select", after_us=300_000)                 # Apple's page
        p.press("select", after_us=300_000)                 # scrubbing
        p.wheel(steps, after_us=800_000)
        p.press("select", after_us=1_500_000)               # done

    return p, state, skips, play_row, play_to, scrub


if not CARD.exists():
    make_card()

def first():
    shutil.copyfile(CARD, RUN)
    p, state, skips, play_row, play_to, scrub = boot(True)
    p.press("select", after_us=500_000)                         # Short Tone (row 0)
    state("Short Tone")
    p.press("next", after_us=1_000_000); p.settle()
    state("Next at 0 s: Tone A")
    check("Next in the first 2 s: no skip", skips() == {})
    play_to(25000); _, at = state("Tone A")
    p.press("next", after_us=1_000_000); p.settle()
    state("Next: Tone B")
    check("Next after %d s: no skip" % (at // 1000), at >= 20000 and skips() == {})
    play_to(5000); state("Tone B")
    p.press("prev", after_us=1_000_000); p.settle()
    state("Prev at ~5 s")
    check("Prev: no skip", skips() == {})
    play_to(5000); state("Tone B")
    play_row(1); state("picked Tone A")
    check("a pick at ~5 s: Tone B skipped", skips() == {2: 1})
    play_to(5000); state("Tone A")
    p.press("next", after_us=1_000_000); p.settle()
    state("Next at ~5 s: Tone B")
    check("Next at ~5 s: Tone A skipped", skips() == {2: 1, 1: 1})


def save():
    shutil.copyfile(CARD, RUN)
    p, state, skips, play_row, play_to, scrub = boot(True)
    syms = {l.split()[2]: int(l.split()[0], 16) for l in SYM.read_text().splitlines() if len(l.split()) == 3}
    p.scroll(1); p.run(500_000); p.press("select", after_us=500_000)        # Tone A
    play_to(5000); state("Tone A")
    p.m.hook_start([syms["skips_save"]], None, 0)
    p.press("next", after_us=500_000)
    p.run(5_000_000)                                        # Apple's 'prwp' comes 0.5-2 s later
    froms = [r[14] for t, pc, r, _ in p.m.hook_log()]
    p.m.hook_start([], None, 0)
    check("Next at ~5 s: Tone A skipped", skips() == {1: 1})
    hook = syms["counts_hook"]
    check("  saved only with Apple's Play Counts (counts_hook), not on a tick",
          froms and all(hook <= lr < hook + 0x20 for lr in froms))
    h, e = skips_file(RUN)
    print("  FroggerSkips:", h and [hex(x) for x in h], e)
    check("FroggerSkips: header FRGS v2, 28-byte entries", h is not None and h[:3] == (0x53475246, 2, 28))
    check("  Tone A (dbid 0x1000 + 101, id 101, its size and length), 1 skip, a time",
          [x[:5] for x in e] == [(0x1000 + 101, 101, 2881119, 180000, 1)] and all(x[5] > 0xb0000000 for x in e))
    p.shot("skips_save.png")


def end():                                                  # its own run: after this scrub, emupod won't sleep
    shutil.copyfile(CARD, RUN.with_name("skips-end-run.img"))
    p, state, skips, play_row, play_to, scrub = boot(True, RUN.with_name("skips-end-run.img"))
    p.press("select", after_us=500_000)                     # Short Tone (row 0)
    for _ in range(4):
        scrub(-200)
        length, at = state("Short Tone scrubbed")
        if length != 10000:
            break
    check("Short Tone ended, Tone A plays", length == 180000)
    check("a song that ends: no skip", skips() == {})


def reboot():
    p, state, skips, play_row, play_to, scrub = boot(False)
    check("read back after a reboot", skips() == {1: 1})
    p.shot("skips_reboot.png")


if sys.argv[1:] == ["first"]:
    first()
elif sys.argv[1:] == ["save"]:
    save()
elif sys.argv[1:] == ["reboot"]:
    reboot()
elif sys.argv[1:] == ["end"]:
    end()
else:
    codes = [subprocess.run([sys.executable, __file__, s]).returncode for s in ("first", "save", "reboot", "end")]
    sys.exit(1 if any(codes) else 0)
sys.exit(1 if fails else 0)

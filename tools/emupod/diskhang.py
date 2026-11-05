"""Frogger image: the disk stops answering as a song starts, and comes back.
Arms emupod's ATA fault (ata_hang: the next read leaves the drive BSY with no interrupt, every
command after it ignored, until a soft reset), the way an SD adapter drops out on a supply dip,
then plays the first song from Songs. Apple's driver times the read out after 10 s and, on stock
2.3, never reaches the disk again. With disk.c the drive is soft-reset, re-inited (SET FEATURES,
SET MULTIPLE) and the read retried.

1. music-card.img, Tone A: checks that the reset happened, that the setup was redone, that the
   music cache filled after the fault, and that Next still loads Tone B from the disk.
2. art-card.img (FroggerArt): the hang hits the cover read, which runs on Frogger's cover task
   (art.c), not the UI's loop. Song 2 is played with the fault armed; while the drive is still
   hung, Menu leaves Now Playing and the wheel moves Songs' highlight (the UI isn't waiting on the
   disk); after the recovery song 2's cover is up, the one a run without the fault read (art.px,
   art_shown). `diskhang.py art` runs this part alone.
Exits 1 if any of that is missing (diskhang.png, diskhang_art.png: the screens at the end)."""
import sys
from ipod3g import Pod, W, ROOT

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
READS = (0x20, 0x21, 0xc4, 0xc8)
fails = []


def songs(p):
    p.press("select"); p.settle()
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs


def cover(p):
    import struct
    shown = struct.unpack("<I", bytes(p.m.mem_read(SYM["art_shown"], 4)))[0]
    return shown, bytes(p.m.mem_read(SYM["art"] + 28, 20 * 72))       # past the BMap header


def refill():
    """1. The refill's read hangs (no FroggerArt on the card)."""
    p = Pod(osos=W + "/osos-frogger.img")
    songs(p)
    p.m.ata_hang(0, 0)                                  # the next read hangs the drive
    p.press("select", after_us=2_000_000)               # play Tone A
    p.run(25_000_000)                                   # 10 s timeout, the reset, the refill
    log = p.m.ata_log()
    s = p.m.stats()
    hang = next((i for i, e in enumerate(log) if e[4].startswith("HANG")), None)
    after = log[hang + 1:] if hang is not None else []
    reads = [e for e in after if e[0] in READS and e[4] == "ok"]
    setup = {e[0] for e in after if e[4] == "ok"} & {0xef, 0xc6}
    print("hangs %d, drive resets %d; after the hang: %d commands, %d reads ok, setup %s" % (
        s["ata_hangs"], s["ata_resets"], len(after), len(reads), sorted(hex(c) for c in setup)))
    n = len(log)
    p.press("next", after_us=3_000_000); p.settle()     # Tone B: not in the cache yet
    more = [e for e in p.m.ata_log()[n:] if e[0] in READS and e[4] == "ok"]
    print("reads after Next:", len(more))
    p.shot("diskhang.png", 2)
    if hang is None:
        fails.append("the fault never fired")
    if s["ata_resets"] < 1:
        fails.append("no soft reset")
    if setup != {0xef, 0xc6}:
        fails.append("setup not redone")
    if len(reads) < 100:
        fails.append("the cache did not fill after the fault")
    if not more:
        fails.append("Next read nothing")

def art():
    """2. The cover read hangs: the UI goes on, the cover comes after the recovery."""
    p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
    songs(p)
    p.scroll(1); p.press("select", after_us=3_000_000); p.settle()
    want = cover(p)                                     # song 2's cover, read without a fault
    p.press("menu"); p.settle(); p.scroll(-1)
    p.press("select", after_us=3_000_000); p.settle()
    other = cover(p)                                    # song 1's, up now
    p.press("menu"); p.settle(); p.scroll(1)
    p.m.ata_hang(0, 0)
    t0 = p.m.now_us()
    p.press("select", after_us=1_000_000)               # play song 2: its cover read hangs
    p.press("menu", after_us=500_000)                   # back to Songs
    before = p.screen()
    moved = p.scroll(-1) and p.screen() != before       # the highlight up to song 1
    t1 = p.m.now_us()
    s = p.m.stats()
    hung = s["ata_hangs"] >= 1 and s["ata_resets"] == 0
    print("UI during the hang: highlight moved %s, %.1f s after the hang began, drive still hung %s" % (
        moved, (t1 - t0) / 1e6, hung))
    if not s["ata_hangs"]:
        fails.append("art: the fault never fired")
    elif not (moved and hung):
        fails.append("art: the UI did not run during the hang")
    p.run(30_000_000)                                   # the timeout, the reset, the retry
    p.settle()
    got = cover(p)
    s = p.m.stats()
    print("after the recovery: resets %d, art_shown %#x (song 2 %#x, song 1 %#x), pixels %s" % (
        s["ata_resets"], got[0], want[0], other[0], "song 2's" if got[1] == want[1] else "NOT song 2's"))
    p.shot("diskhang_art.png", 2)
    if want[0] >= 0xff00 or other[0] == want[0]:
        fails.append("art: songs 1 and 2 have no covers of their own (art-card.img?)")
    elif got != want:
        fails.append("art: song 2's cover did not load after the recovery")


if len(sys.argv) > 1 and sys.argv[1] == "art":
    art()
else:
    refill()
    import subprocess                               # one emupod machine per process
    r = subprocess.run([sys.executable, __file__, "art"], capture_output=True, text=True)
    print(r.stdout, end="")
    fails += [l[len("FAIL "):] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
    if r.returncode not in (0, 1):
        fails.append("art run crashed: " + r.stderr[-300:])
if len(sys.argv) > 1:
    for f in fails:
        print("FAIL " + f)
else:
    print("FAILED: " + "; ".join(fails) if fails else "ok")
sys.exit(1 if fails else 0)

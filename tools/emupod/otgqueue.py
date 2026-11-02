"""Frogger image: Up Next on On-The-Go (payload/queue.c). One scenario per run (emupod opens once
per process); each prints the player's list (OTG or the Songs copy) and item after every step.

    otgqueue.py idle     # nothing playing: hold Tone B -> it plays at once, from On-The-Go
    otgqueue.py next     # play Tone A from Songs, hold Tone A (queued), Next -> On-The-Go's Tone A,
                      # Next -> back in Songs at Tone B; then hold On-The-Go in Playlists: cleared
    otgqueue.py cleared  # play Tone A, queue Tone A, clear before it plays, Next -> Songs' Tone B
"""
import struct, sys
from ipod3g import Pod, W

p = Pod(osos=W + "/osos-frogger.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
lib = rd(rd(0x43580c) + 0x1c)
otg, player = rd(lib + 0x48), rd(rd(lib) + 4)


def state(tag):
    lst, it = rd(player + 0x2a4), rd(player + 0x2a8)
    print("%-26s list=%-10s item=%-10s otg=%d" % (tag, "OTG" if lst == otg else hex(lst), hex(it),
                                                  rd(rd(otg + 0x24) + 0x2c)))


def hold():
    p.press("select", hold_us=2_000_000); p.settle()


def playlists():
    for _ in range(2):                                   # Songs > Music > main menu
        p.press("menu", after_us=1_500_000); p.settle()
    for _ in range(2):                                   # Music, then Playlists: On-The-Go highlighted
        p.scroll(-6); p.settle(); p.run(500_000)         # (a Select right after the wheel gets lost)
        p.press("select", after_us=1_500_000); p.settle()


what = sys.argv[1] if len(sys.argv) > 1 else "next"
if what == "idle":
    p.scroll(1); hold(); p.run(1_000_000); state("held Tone B")
else:
    p.press("select", after_us=1_500_000); p.settle(); state("playing Tone A (Songs)")
    p.press("menu"); p.settle(); hold(); state("queued Tone A")
    if what == "cleared":
        playlists(); hold(); state("cleared On-The-Go")
        p.press("next", after_us=1_500_000); p.settle(); state("Next")
    else:
        p.press("next", after_us=1_500_000); p.settle(); state("Next: the queue")
        p.press("next", after_us=1_500_000); p.settle(); state("Next: back to Songs")
        playlists(); hold(); state("held On-The-Go")
p.shot("queue_%s.png" % what)

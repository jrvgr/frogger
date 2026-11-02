"""Frogger image: the hold menu (payload/holdmenu.c) and the queue (payload/queue.c). One
scenario per run (emupod opens once per process):

    holdmenu.py          # in Songs: hold Tone A -> the popup; Add to Queue (plays, from the
                         # queue); hold Tone B, Menu -> nothing added; hold Tone B, Add to
                         # Playlist -> the Playlists picker (playlists.py goes on from there)
    holdmenu.py next     # play Tone A from Songs; queue Tone A; Next -> the queue's Tone A;
                         # Next -> back in Songs at Tone B; then Playlists (shot: no queue there)

Prints On-The-Go's count and what plays after each step; screenshots hm_*.png."""
import struct, sys
from ipod3g import Pod, W

p = Pod(osos=W + "/osos-frogger.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
lib = rd(rd(0x43580c) + 0x1c)
otg, player = rd(lib + 0x48), rd(rd(lib) + 4)
shots = []


def state(tag):
    lst, it = rd(player + 0x2a4), rd(player + 0x2a8)
    print("%-34s otg=%d  playing=%s" % (tag, rd(rd(otg + 0x24) + 0x2c), "nothing" if not it else
                                        ("OTG" if lst == otg else "list %x" % lst)))


def shot(name):
    shots.append(p.shot("hm_%s.png" % name, 1))


def hold():
    p.press("select", hold_us=2_000_000); p.settle()


if sys.argv[1:] == ["next"]:
    p.press("select", after_us=1_500_000); p.settle(); state("playing Tone A (Songs)")
    p.press("menu"); p.settle()
    hold(); p.press("select", after_us=1_500_000); p.settle(); state("queued Tone A")
    p.press("next", after_us=1_500_000); p.settle(); state("Next: the queue")
    p.press("next", after_us=1_500_000); p.settle(); state("Next: back to Songs"); shot("n_back")
    for _ in range(3):
        p.press("menu", after_us=1_500_000); p.settle()
    p.scroll(-6); p.settle(); p.run(500_000); p.press("select", after_us=1_500_000); p.settle()
    p.scroll(-6); p.settle(); p.run(500_000); p.press("select", after_us=1_500_000); p.settle()
    shot("n_playlists")
    print("\n".join(shots)); sys.exit()

state("start")
hold(); shot("1_popup"); state("held Tone A")
p.press("select", after_us=1_500_000); p.settle(); shot("2_queued"); state("Add to Queue")
p.scroll(1); p.settle(); p.run(500_000)
hold(); shot("3_popup_b"); state("held Tone B")
p.press("menu", after_us=1_500_000); p.settle(); shot("4_menu_back"); state("Menu")
hold(); p.scroll(1); p.settle(); p.run(500_000); shot("5_second_item")
p.press("select", after_us=1_500_000); p.settle(); shot("6_picker"); state("Add to Playlist (picker)")
print("\n".join(shots))

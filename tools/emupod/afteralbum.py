"""Frogger image + hmcard.py's card (aa-card.img): Play After Album (payload/holdmenu.c, queue.c).
One run, checking as it goes (exits 1 on the first wrong step; screenshots aa_*.png):

1. Albums > Alpha > Moon: Alpha plays from its first song.
2. Albums: hold Gamma; the popup's second row is Play After Album. Pick it: Moon still
   plays, and the queue waits.
3. Next: Apple, Next: Zebra (Alpha goes on while the queue waits), Next: Echo, Next: Bravo.
4. Albums: hold Beta > Play After Album with nothing waiting and the queue playing (Bravo):
   Kite and Delta join its end. Next: Kite.
5. Nothing in Apple's image changed (read-only on a device)."""
import struct, sys
from ipod3g import Pod, W, ROOT
import hmcard

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
card = hmcard.make("aa-card.img")
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
END = 0x346368
snap = bytes(p.m.mem_read(0, END))
p.press("select"); p.settle(); p.press("select"); p.settle()           # English, Music
lib = rd(rd(0x43580c) + 0x1c)
player = rd(rd(lib) + 4)
TITLE = {}


def check(tag, ok, msg=""):
    """Also: nothing in Apple's image changed (read-only on a device)."""
    now = bytes(p.m.mem_read(0, END))
    diff = [i for i in range(0, END, 4) if snap[i:i + 4] != now[i:i + 4]]
    if diff:
        msg += " (and Apple's image changed: %s)" % [(hex(a), snap[a:a + 4].hex(), now[a:a + 4].hex()) for a in diff[:4]]
        ok = False
    print("%-52s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        p.shot("aa_wrong.png"); sys.exit(1)


def song_titles():
    return [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]


def playing():
    it = rd(player + 0x2a8)
    return it and TITLE.get(rd(it + 0x20))


def go(n):
    if n:
        p.scroll(n); p.settle(); p.run(300_000)


def hold(shot):
    p.press("select", hold_us=2_000_000); p.settle(); p.shot("aa_%s.png" % shot, 1)


def pick(n):
    go(n); p.press("select", after_us=1_500_000); p.settle()


def menu():
    p.press("menu", after_us=1_500_000); p.settle()


def nxt():
    p.press("next", after_us=1_500_000); p.settle()
    return playing()


go(3); p.press("select"); p.settle()                                   # Songs: learn the titles
for i in range(rd(lib + 0x89c)):
    TITLE[rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)] = hmcard.BY_TITLE[i]
check("Songs", song_titles() == hmcard.BY_TITLE, str(song_titles()))
menu(); go(-1); p.press("select", after_us=1_500_000); p.settle()        # Albums
check("Albums", rd(lib + 0x894) == 3, "albums %d" % rd(lib + 0x894))
pick(1)                                                                # Alpha
check("Alpha's songs", song_titles() == ["Moon", "Apple", "Zebra"], str(song_titles()))
pick(0); p.shot("aa_1_np.png", 1)                                      # Moon: Now Playing
check("1. Alpha plays: Moon", playing() == "Moon", str(playing()))

menu(); menu()                                                         # Alpha's songs, Albums (on Alpha)
go(2); hold("2_popup")                                                 # Gamma
check("2. the popup opens", rd(SYM["hm"]) == 1)                # hm.open
pick(1); p.shot("aa_2_after.png", 1)                                   # Play After Album
check("  Moon still plays", playing() == "Moon", str(playing()))
check("  the queue waits for Alpha to end", rd(SYM["q"] + 4 * 9) == 1, "wait_album %d" % rd(SYM["q"] + 4 * 9))
check("3. Next: Apple", nxt() == "Apple", str(playing()))
check("   Next: Zebra", nxt() == "Zebra", str(playing()))
check("   Next: Echo (Gamma)", nxt() == "Echo", str(playing()))
check("   Next: Bravo", nxt() == "Bravo", str(playing()))

go(-1); hold("4_popup")                                                # Beta (from Gamma)
pick(1)
check("4. Beta joins the queue playing: Bravo still", playing() == "Bravo", str(playing()))
check("   Next: Kite", nxt() == "Kite", str(playing()))
check("   Next: Delta", nxt() == "Delta", str(playing()))

now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(END) if snap[i] != now[i]]
check("5. Apple's image unchanged", not diff, "%d bytes, first %#x" % (len(diff), diff[0] if diff else 0))

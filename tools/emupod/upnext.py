"""Frogger image + hmcard.py's card (un-card.img): Up Next (payload/queue.c, holdmenu.c, browse.c).
One run, checking as it goes (exits 1 on the first wrong step; screenshots un_*.png):

1. Songs: play Apple, then Add to Queue Delta, Echo, Kite, Moon, Zebra; Apple still plays.
2. Select on Apple: Now Playing. Hold: the popup has five rows, the first "Up Next".
   Up Next: the songs list holds the five queued songs in queue order. Menu: Now Playing again,
   and the songs list is Songs' again (the browse state put back).
3. Up Next again; hold Kite > Remove from Queue: the list is Delta, Echo, Moon, Zebra, still Up Next.
4. Select on Echo: Echo plays (Delta is skipped), back on Now Playing. Next: Moon (Kite was
   removed). Up Next (now from the queue playing): Zebra; Select: Zebra. Next: back in Songs'
   list at Bravo, the song after Apple.
5. Queue Delta and Echo again (Bravo playing); Now Playing > Up Next > hold Delta > Clear Queue:
   back on Now Playing, nothing waiting (the popup has no Up Next row), Next: Delta from Songs.
6. Menu from Now Playing: Songs, all seven. Nothing in Apple's image changed."""
import struct, sys
from ipod3g import Pod, W, ROOT
import hmcard

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
HM, UP, Q = SYM["hm"], SYM["up"], SYM["q"]
card = hmcard.make("un-card.img")
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
        p.shot("un_wrong.png"); sys.exit(1)


def song_titles():
    return [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]


def playing():
    it = rd(player + 0x2a8)
    return it and TITLE.get(rd(it + 0x20))


def hold(shot):
    p.press("select", hold_us=2_000_000); p.settle(); p.shot("un_%s.png" % shot, 1)


def pick(n, after=1_500_000):
    if n:
        p.scroll(n); p.settle(); p.run(300_000)
    p.press("select", after_us=after); p.settle()


row = 0


def go(to):
    global row
    if to != row:
        p.scroll(to - row); p.settle(); p.run(300_000)
    row = to


def queue(title):
    go(hmcard.BY_TITLE.index(title))
    p.press("select", hold_us=2_000_000); p.settle()
    p.press("select", after_us=2_000_000); p.settle()                  # the first row: Add to Queue


def popup_rows():
    return rd(HM + 11 * 4)                                              # hm.vis


def waiting():
    return rd(UP + 12)                                                  # up.n, as the last popup or pick saw it


p.scroll(3); p.press("select"); p.settle()                             # Songs
for i in range(rd(lib + 0x89c)):
    TITLE[rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)] = hmcard.BY_TITLE[i]
check("Songs", song_titles() == hmcard.BY_TITLE, str(song_titles()))
songs_list = rd(lib + 0x898)
p.press("select", after_us=1_500_000); p.settle()                      # Apple: Now Playing
check("Apple plays", playing() == "Apple", str(playing()))
p.press("menu", after_us=1_500_000); p.settle()
songs_player_list = rd(player + 0x2a4)
for t in ("Delta", "Echo", "Kite", "Moon", "Zebra"):
    queue(t)
check("queued five, Apple still plays", playing() == "Apple", str(playing()))
qlist = rd(Q)
check("  the queue holds them", qlist and rd(rd(qlist + 0x24) + 0x2c) == 5)

go(0); p.press("select", after_us=1_500_000); p.settle(); np_screen = p.shot("un_2_np.png", 1) and p.screen()
hold("2_popup")
check("NP popup: five rows, Up Next first", popup_rows() == 0x3b, "%#x" % popup_rows())
pick(0); p.shot("un_2_upnext.png", 1)
check("Up Next: the five, in queue order", song_titles() == ["Delta", "Echo", "Kite", "Moon", "Zebra"], str(song_titles()))
p.press("menu", after_us=1_500_000); p.settle(); p.shot("un_2_back.png", 1)
check("  Menu: Now Playing", p.screen() == np_screen)
check("  the songs list is Songs' again", song_titles() == hmcard.BY_TITLE, str(song_titles()))

hold("3_popup"); pick(0)                                               # Up Next
p.scroll(2); p.settle(); p.run(300_000)                                # Kite
hold("3_hold")
check("Up Next popup: Remove from Queue, Clear Queue", popup_rows() == 0x3, "%#x" % popup_rows())
pick(0); p.shot("un_3_removed.png", 1)                                 # Remove from Queue
check("Remove Kite: Delta, Echo, Moon, Zebra", song_titles() == ["Delta", "Echo", "Moon", "Zebra"], str(song_titles()))
check("  still Up Next", rd(UP) == 1 and rd(HM + 14 * 4) == 1, "open %d depth %d" % (rd(UP), rd(HM + 14 * 4)))

p.scroll(-1); p.settle(); p.run(300_000)                               # Echo (the cursor stayed on row 2)
p.press("select", after_us=1_500_000); p.settle(); p.shot("un_4_picked.png", 1)
check("Select Echo: Echo plays", playing() == "Echo", str(playing()))
check("  back on Now Playing (Up Next closed)", rd(UP) == 0 and rd(HM + 12 * 4) == 0)
check("  the songs list is Songs' again", song_titles() == hmcard.BY_TITLE, str(song_titles()))
p.press("next", after_us=1_500_000); p.settle()
check("  Next: Moon (Kite removed)", playing() == "Moon", str(playing()))
hold("4_popup"); pick(0); p.shot("un_4_upnext.png", 1)                # Up Next, the queue playing
check("Up Next while the queue plays: Zebra", song_titles() == ["Zebra"], str(song_titles()))
p.press("select", after_us=1_500_000); p.settle()
check("  Select Zebra: Zebra plays", playing() == "Zebra" and rd(player + 0x2a4) == qlist, str(playing()))
p.press("next", after_us=1_500_000); p.settle()
check("  Next: back in Songs at Bravo", playing() == "Bravo" and rd(player + 0x2a4) != qlist,
      "%s, list %#x (queue %#x)" % (playing(), rd(player + 0x2a4), qlist))

p.press("menu", after_us=1_500_000); p.settle()                        # Songs
# Where Songs' cursor is now isn't known (the queue's songs were held on several rows): go to the top.
p.scroll(-8); p.settle(); p.run(300_000); row = 0
for t in ("Delta", "Echo"):
    queue(t)
check("queued Delta, Echo; Bravo plays", playing() == "Bravo", str(playing()))
go(1); p.press("select", after_us=1_500_000); p.settle()               # Bravo: Now Playing
np_screen = p.screen()
hold("5_popup"); pick(0); p.shot("un_5_upnext.png", 1)
check("Up Next: Delta, Echo", song_titles() == ["Delta", "Echo"], str(song_titles()))
hold("5_hold"); pick(1, 2_500_000); p.shot("un_5_cleared.png", 1)     # Clear Queue
check("Clear Queue: back on Now Playing", rd(UP) == 0 and rd(HM + 12 * 4) == 0 and p.screen() == np_screen,
      "open %d go %d" % (rd(UP), rd(HM + 12 * 4)))
hold("5_popup2")
check("  the popup has no Up Next row", popup_rows() == 0x3a and waiting() == 0, "%#x" % popup_rows())
p.press("menu", after_us=1_500_000); p.settle()                        # the popup goes
p.press("next", after_us=1_500_000); p.settle()
check("  Next: Delta, from Songs", playing() == "Delta" and rd(player + 0x2a4) != qlist, str(playing()))

p.press("menu", after_us=1_500_000); p.settle(); p.shot("un_6_songs.png", 1)
check("Menu: Songs, all seven", song_titles() == hmcard.BY_TITLE, str(song_titles()))
now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(END) if snap[i] != now[i]]
check("Apple's image unchanged", not diff, "%d bytes, first %#x" % (len(diff), diff[0] if diff else 0))

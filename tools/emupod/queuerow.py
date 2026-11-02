"""Frogger image + hmcard.py's card (qr-card.img): the main menu's Queue row (holdmenu.c, hm_main).
One run, checking as it goes (exits 1 on the first wrong step; screenshots qr_*.png):

1. Boot: the main menu is pointed at hm_main (23 items, Queue after Music). Nothing waits, so the
   row after Music is Playlists (Select there opens Playlists, not the Queue list).
2. Songs: play Apple, Add to Queue Delta, Echo, Kite. Back to the main menu: the row after Music
   is Queue; Select opens the Queue list (Delta, Echo, Kite; depth 1, as Now Playing's).
3. Menu: the main menu again (same pixels), the Queue list closed, Songs' list put back.
4. Queue again, Select on Echo: Echo plays, back on the main menu (same pixels; Kite still waits).
5. Queue again (Kite), hold Kite > Clear Queue: back on the main menu, nothing waits, and the row
   after Music is Playlists again (the same screen as in 1, below the title bar).
6. Nothing in Apple's image changed, at every step."""
import struct, sys
from ipod3g import Pod, W, ROOT
import hmcard

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
HM, UP, MAIN = SYM["hm"], SYM["up"], SYM["hm_main"]
card = hmcard.make("qr-card.img")
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
END = 0x346368
snap = bytes(p.m.mem_read(0, END))
TITLE = {}
BAR = 160 * 20                                          # the title bar's rows (the play icon comes and goes)


def check(tag, ok, msg=""):
    """Also: nothing in Apple's image changed (read-only on a device)."""
    now = bytes(p.m.mem_read(0, END))
    diff = [i for i in range(0, END, 4) if snap[i:i + 4] != now[i:i + 4]]
    if diff:
        msg += " (and Apple's image changed: %s)" % [(hex(a), snap[a:a + 4].hex(), now[a:a + 4].hex()) for a in diff[:4]]
        ok = False
    print("%-56s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        p.shot("qr_wrong.png"); sys.exit(1)


def titles():
    return [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]


def playing():
    it = rd(player + 0x2a8)
    return it and TITLE.get(rd(it + 0x20))


def press(key, shot=None):
    p.press(key, after_us=1_500_000); p.settle()
    if shot:
        p.shot("qr_%s.png" % shot, 1)


def scroll(n):
    p.scroll(n); p.settle(); p.run(300_000)


def after_music():
    """From the main menu: the row after Music, picked."""
    scroll(-12); scroll(1); press("select")


state = lambda: "open %d go %d pending %d depth %d n %d" % (rd(UP), rd(HM + 12 * 4), rd(HM + 13 * 4), rd(HM + 14 * 4), rd(UP + 12))

p.press("select"); p.settle()                                          # English: the main menu
lib = rd(rd(0x43580c) + 0x1c)
player = rd(rd(lib) + 4)
entry = struct.unpack("<3I", bytes(p.m.mem_read(0x182210, 12)))
check("1. main menu at hm_main, 23 items", entry == (0x2512, MAIN - (0x181d20 + 0x313c), 4 + 23 * 40) and rd(MAIN) == 23,
      str(entry))
p.shot("qr_1_menu.png", 1)
after_music(); p.shot("qr_1_after_music.png", 1)
playlists = p.screen()
check("  nothing waits: after Music is Playlists", rd(UP) == 0 and rd(HM + 12 * 4) == 0, state())
press("menu")

scroll(-12); press("select"); scroll(3); press("select")                # Music > Songs
for i in range(rd(lib + 0x89c)):
    TITLE[rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)] = hmcard.BY_TITLE[i]
check("2. Songs", titles() == hmcard.BY_TITLE, str(titles()))
press("select")                                                        # Apple: Now Playing
press("menu")
row = 0
for t in ("Delta", "Echo", "Kite"):
    to = hmcard.BY_TITLE.index(t)
    scroll(to - row); row = to
    p.press("select", hold_us=2_000_000); p.settle()
    p.press("select", after_us=2_000_000); p.settle()                  # Add to Queue
check("  queued Delta, Echo, Kite; Apple plays", playing() == "Apple" and rd(UP + 12) == 0, str(playing()))
press("menu"); press("menu", "2_menu")                                 # Songs > Music > main menu
scroll(-12); scroll(1); menu_px = p.screen(); p.shot("qr_2_on_queue.png", 1)
press("select", "2_queue")
check("  after Music is Queue: the list, in queue order", titles() == ["Delta", "Echo", "Kite"], str(titles()))
check("  open, depth 1", rd(UP) == 1 and rd(HM + 12 * 4) == 2 and rd(HM + 13 * 4) == 0 and rd(HM + 14 * 4) == 1, state())

press("menu", "3_back")
check("3. Menu: the main menu (same pixels)", p.screen() == menu_px)
check("  the list closed", rd(UP) == 0 and rd(HM + 12 * 4) == 0, state())
scroll(-12); press("select"); scroll(-12); scroll(3); press("select", "3_songs")
check("  Music > Songs: all seven", titles() == hmcard.BY_TITLE, str(titles()))
press("menu"); press("menu"); scroll(-12); scroll(1)                   # back on Queue
check("  back on the main menu's Queue row (same pixels)", p.screen() == menu_px)

press("select"); scroll(1)                                             # Queue > Echo
press("select", "4_picked")
check("4. Select Echo: Echo plays", playing() == "Echo", str(playing()))
check("  back on the main menu (same pixels)", p.screen() == menu_px)
check("  the list closed", rd(UP) == 0 and rd(HM + 12 * 4) == 0, state())

press("select", "5_queue")
check("5. Queue: Kite", titles() == ["Kite"], str(titles()))
p.press("select", hold_us=2_000_000); p.settle(); p.shot("qr_5_hold.png", 1)
check("  hold: Remove from Queue, Clear Queue", rd(HM + 11 * 4) == 0x3, "%#x" % rd(HM + 11 * 4))
p.scroll(1); p.settle(); p.run(300_000)
p.press("select", after_us=2_000_000); p.settle(); p.shot("qr_5_cleared.png", 1)
check("  Clear Queue: nothing waits, list closed", rd(UP + 12) == 0 and rd(UP) == 0 and rd(HM + 12 * 4) == 0, state())
check("  Echo still plays", playing() == "Echo", str(playing()))
p.shot("qr_5_menu.png", 1)
after_music(); p.shot("qr_5_after_music.png", 1)
check("  after Music is Playlists again", p.screen()[BAR:] == playlists[BAR:] and rd(UP) == 0, state())
press("menu")
check("6. Apple's image unchanged throughout", True)

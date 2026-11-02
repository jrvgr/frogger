"""Frogger image + hmcard.py's card (hm2-card.img): the hold menu's newer rows (payload/holdmenu.c).
One run, checking as it goes (exits 1 on the first wrong step; screenshots h2v_*.png):

1. Songs: hold Delta; the popup has six rows. Go to Album: Beta's songs (Kite, Delta). Menu:
   Songs again, all seven, the cursor on Delta.
2. Hold Delta > Go to Artist: Art One's albums (All, Alpha, Beta). Menu: Songs, on Delta.
3. Hold Apple (Alpha, track 2) > Play Album Next, nothing playing: Apple plays, Next Zebra.
4. Albums: hold Gamma > Hide: Albums shows All, Alpha, Beta; FroggerHidden lists Echo and Bravo.
5. Now Playing (Apple): hold Select; the popup has four rows. Go to Album: Alpha's songs;
   Menu: back on Now Playing.
6. Nothing in Apple's image changed (read-only on a device).

    holdmenu2.py reboot   # afterwards, in a new process: boot that card again; Albums still
                          # leaves Gamma out (FroggerHidden read back), Songs still has Echo"""
import struct, sys
from ipod3g import Pod, W
import hmcard

if sys.argv[1:] == ["reboot"]:
    p = Pod(osos=W + "/osos-frogger.img", disk=W + "/hm2-card.img")
    rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
    p.press("select"); p.settle(); p.scroll(2); p.press("select"); p.settle()      # (the language is set by now): Music > Albums
    lib = rd(rd(0x43580c) + 0x1c)
    print("after a restart, Albums has %d albums (want 2: Gamma stays hidden)" % rd(lib + 0x894))
    p.shot("h2v_6_reboot.png", 1)
    sys.exit(rd(lib + 0x894) != 2)
card = hmcard.make("hm2-card.img")
p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
END = 0x346368
snap = bytes(p.m.mem_read(0, END))
p.press("select"); p.settle(); p.press("select"); p.settle()           # English, Music
ui = rd(0x43580c); lib = rd(ui + 0x1c)
TITLE = {}


def fail(msg):
    print("WRONG:", msg); p.shot("h2v_wrong.png"); sys.exit(1)


def check(tag, ok, msg=""):
    now = bytes(p.m.mem_read(0, END))
    diff = [i for i in range(0, END, 4) if snap[i:i + 4] != now[i:i + 4]]
    if diff:
        msg += " (and Apple's image changed: %s)" % [(hex(a), snap[a:a + 4].hex(), now[a:a + 4].hex()) for a in diff[:4]]
        ok = False
    print("%-44s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        fail(tag)


def song_titles():
    return [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]


def playing():
    it = rd(rd(rd(lib) + 4) + 0x2a8)
    return it and TITLE.get(rd(it + 0x20))




def hold(shot):
    p.press("select", hold_us=2_000_000); p.settle(); p.shot("h2v_%s.png" % shot, 1)


def pick(n, after=1_500_000):
    if n:
        p.scroll(n); p.settle(); p.run(300_000)
    p.press("select", after_us=after); p.settle()


p.scroll(3); p.press("select"); p.settle()                             # Songs
for i in range(rd(lib + 0x89c)):
    TITLE[rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)] = hmcard.BY_TITLE[i]
check("Songs", song_titles() == hmcard.BY_TITLE, str(song_titles()))
songs = p.screen()
p.scroll(2); p.settle(); p.run(300_000); on_delta = p.settle()
hold("1_popup")
pick(3); p.shot("h2v_1_album.png", 1)                                  # Go to Album
check("Go to Album: Beta's songs", song_titles() == ["Kite", "Delta"], str(song_titles()))
p.press("menu", after_us=1_500_000); p.settle(); p.shot("h2v_1_back.png", 1)
check("Menu: Songs again", song_titles() == hmcard.BY_TITLE, str(song_titles()))
check("  on Delta, as it was", p.screen() == on_delta)

hold("2_popup"); pick(4); p.shot("h2v_2_artist.png", 1)                # Go to Artist
check("Go to Artist: Art One's albums", rd(lib + 0x894) == 2, "albums %d" % rd(lib + 0x894))
p.press("menu", after_us=1_500_000); p.settle()
check("Menu: Songs again, on Delta", song_titles() == hmcard.BY_TITLE and p.screen() == on_delta)

p.scroll(-2); p.settle(); p.run(300_000); p.shot("h2v_3_apple.png", 1)        # Apple
hold("3_popup"); pick(1, 3_000_000)                                    # Play Album Next
ql = rd(rd(rd(lib) + 4) + 0x2a4); print("  queue list %#x count %d" % (ql, rd(rd(ql + 0x24) + 0x2c) if ql else -1))
check("Play Album Next: Apple plays", playing() == "Apple", str(playing()))
p.press("next", after_us=1_500_000); p.settle()
check("  Next: Zebra", playing() == "Zebra", str(playing()))
p.press("prev", after_us=1_500_000); p.settle(); p.press("prev", after_us=1_500_000); p.settle()
print("  (now playing %s)" % playing())

p.press("menu", after_us=1_500_000); p.settle()                        # Music
p.scroll(-1); p.settle(); p.run(300_000); p.press("select", after_us=1_500_000); p.settle()   # Albums
check("Albums", rd(lib + 0x894) == 3, "albums %d" % rd(lib + 0x894))
p.scroll(3); p.settle(); p.run(300_000)                                # Gamma
hold("4_popup"); pick(3); p.shot("h2v_4_hidden.png", 1)                # Hide
check("Hide Gamma: Albums has Alpha, Beta", rd(lib + 0x894) == 2, "albums %d" % rd(lib + 0x894))

p.press("menu", after_us=1_500_000); p.settle()                        # Music
p.scroll(1); p.settle(); p.run(300_000); p.press("select", after_us=1_500_000); p.settle()    # Songs
p.press("select", after_us=1_500_000); p.settle(); p.shot("h2v_5_np.png", 1)                 # Apple: Now Playing
np_song = playing()
hold("5_popup"); pick(1); p.shot("h2v_5_album.png", 1)                 # Go to Album (2nd of four)
check("NP Go to Album: Alpha's songs", song_titles() == ["Moon", "Apple", "Zebra"], str(song_titles()))
p.press("menu", after_us=1_500_000); p.settle(); p.shot("h2v_5_back.png", 1)
check("  Menu: Now Playing, still %s" % np_song, playing() == np_song)

now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(END) if snap[i] != now[i]]
check("Apple's image unchanged", not diff, "%d bytes, first %#x" % (len(diff), diff[0] if diff else 0))
out = hmcard.mtools(card, "mtype", "::/iPod_Control/iTunes/FroggerHidden", capture_output=True).stdout
n = struct.unpack_from("<I", out, 12)[0] if len(out) >= 20 else -1
size = struct.unpack_from("<H", out, 6)[0] if len(out) >= 20 else 0     # 12 (version 2), 8 (1)
ids = sorted(struct.unpack_from("<I", out, 24 + size * i)[0] for i in range(max(n, 0)))
ok = out[:4] == b"FRGH" and ids == sorted([hmcard.TID["Echo"], hmcard.TID["Bravo"]])
print("%-44s %s" % ("FroggerHidden: Echo, Bravo", "ok" if ok else "WRONG %r %s" % (out[:4], ids)))
sys.exit(not ok)

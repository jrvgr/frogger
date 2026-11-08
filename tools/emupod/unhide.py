"""Frogger image + hmcard.py's card with Kite and Delta (album Beta) flagged by Crate
(uh-card.img): the hold menu's Show, which un-hides (payload/holdmenu.c, hide.c). One run,
checking as it goes (exits 1 on a wrong step; screenshots uh_*.png):

1. Settings > Show Hidden on. Songs lists all seven.
2. Hold Apple: the last row says Hide. Hold Kite (Crate's flag): it says Show; Show: Kite shown,
   the list as it was (seven songs, the cursor on Kite).
3. Hold Apple > Hide (the disk asleep: FroggerHidden written by the save task, nothing read on the UI's
   thread, On-The-Go not marked to be saved), then hold Apple again: Show; Show. Hold Kite > Hide (hidden again), then
   Show again.
4. Albums: hold Beta (Kite shown, Delta hidden): Hide. Hold Gamma > Hide; hold Gamma: Show.
   Artists: hold Art Two: Show; Show: Echo and Bravo shown. Hold Art One: Hide.
5. Songs: hold Moon > Hide; Albums: hold Gamma > Hide.
6. Settings > Show Hidden off: Albums has Alpha and Beta (Kite shown), Artists only Art One.
   Apple's image unchanged. FroggerHidden (version 3, by key): Kite shown; Moon, Echo, Bravo hidden.

    unhide.py reboot   # afterwards, in a new process: boot that card again (Show Hidden
                       # off: emupod keeps no prefs); Albums still has Alpha and Beta,
                       # Artists Art One (the file read back)
    unhide.py v1       # then: that card with a version 1 file (Echo, Bravo): Albums has Alpha

(Songs, and an album's songs, list hidden songs anyway: hide.c.)"""
import struct, sys
from pathlib import Path
from ipod3g import Pod, W
import hmcard

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(Path(W).parent / "payload/payload.sym") if len(l.split()) == 3}
HM_SHOW = SYM["hm"] + 20 * 4       # hm.show (holdmenu.c, its last word)
SHOW_ALL = SYM["hide_state"] + 1
END = 0x346368
REBOOT = sys.argv[1:] == ["reboot"]
V1 = sys.argv[1:] == ["v1"]
card = W + "/uh-card.img" if REBOOT or V1 else hmcard.make("uh-card.img", hidden=("Kite", "Delta"))
if V1:      # a version 1 file (before Show) with the same stamp: Echo and Bravo hidden
    old = hmcard.mtools(card, "mtype", "::/iPod_Control/iTunes/FroggerHidden", capture_output=True).stdout
    tmp = Path(W) / "uh-v1.bin"
    tmp.write_bytes(struct.pack("<IHHIII4I", 0x48475246, 1, 8, struct.unpack_from("<I", old, 8)[0], 2, 0,
                                5, hmcard.TID["Echo"], 6, hmcard.TID["Bravo"]))
    hmcard.mtools(card, "mcopy", "-o", str(tmp), "::/iPod_Control/iTunes/FroggerHidden")
p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
rb = lambda a: bytes(p.m.mem_read(a, 1))[0]
snap = bytes(p.m.mem_read(0, END))
TITLE = {}
lib = 0


def fail(msg):
    print("WRONG:", msg); p.shot("uh_wrong.png"); sys.exit(1)


def check(tag, ok, msg=""):
    print("%-48s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        fail(tag)


def titles():
    return [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]


def hidden():
    t = struct.unpack("<16384I", bytes(p.m.mem_read(SYM["table"], 4 * 16384)))
    return sorted(TITLE[r] for r in t if r in TITLE)


def hold(shot):
    p.press("select", hold_us=2_000_000); p.settle(); p.shot("uh_%s.png" % shot, 1)
    return rd(HM_SHOW)


def pick(n):
    p.scroll(n); p.settle(); p.run(300_000)
    p.press("select", after_us=1_500_000); p.settle()


def close():
    p.press("menu", after_us=1_500_000); p.settle()


def music(row):             # from the main menu, on Music: one of its rows
    p.press("select"); p.settle(); p.scroll(-8); p.scroll(row); p.settle(); p.run(300_000)
    p.press("select", after_us=1_500_000); p.settle()


def show_hidden(on):        # from the main menu, on Music; back there
    p.scroll(2); p.press("select"); p.settle(); p.scroll(-14); p.scroll(9); p.settle()
    p.press("select"); p.settle()
    check("Settings > Show Hidden %s" % ("on" if on else "off"), rb(SHOW_ALL) == on, str(rb(SHOW_ALL)))
    p.press("menu"); p.settle(); p.scroll(-2); p.settle()


def songs():                # from the main menu, on Music
    global lib
    music(3)
    lib = rd(rd(0x43580c) + 0x1c)
    if not TITLE:
        for i in range(rd(lib + 0x89c)):
            TITLE[rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)] = hmcard.BY_TITLE[i]


def to_menu(n):
    for _ in range(n):
        p.press("menu", after_us=1_500_000); p.settle()


def counts(shot):           # from the main menu: Albums' and Artists' counts (without All)
    global lib
    music(2)
    lib = rd(rd(0x43580c) + 0x1c)
    albums = rd(lib + 0x894)
    p.shot(shot % "albums", 1)
    to_menu(2); music(1)
    artists = rd(lib + 0x884)
    p.shot(shot % "artists", 1)
    to_menu(2)
    check("  Albums: Alpha, Beta; Artists: Art One", (albums, artists) == (2, 1), str((albums, artists)))


if V1:
    p.press("select"); p.settle()
    music(2)
    lib = rd(rd(0x43580c) + 0x1c)
    check("version 1 file: Albums has only Alpha", rd(lib + 0x894) == 1, str(rd(lib + 0x894)))
    sys.exit(0)
if REBOOT:
    check("after a restart, Show Hidden off", rb(SHOW_ALL) == 0, str(rb(SHOW_ALL)))
    p.press("select"); p.settle()                                       # English (emupod keeps no prefs); Music
    counts("uh_7_%s.png")
    sys.exit(0)

p.press("select"); p.settle()                                           # English; main menu on Music
show_hidden(1)
songs()
check("Songs: all seven", titles() == hmcard.BY_TITLE and hidden() == ["Delta", "Kite"], "%s %s" % (titles(), hidden()))
check("hold Apple: Hide", hold("1_apple") == 0); close()
p.scroll(4); p.settle(); p.run(300_000); on_kite = p.settle()           # Kite
check("hold Kite (Crate's flag): Show", hold("2_kite") == 1); pick(5)
check("Show: Kite shown", hidden() == ["Delta"], str(hidden()))
check("  the list as it was, on Kite", titles() == hmcard.BY_TITLE and p.screen() == on_kite)

p.scroll(-4); p.settle(); p.run(300_000)                                # Apple
check("hold Apple > Hide", hold("3_apple") == 0)
p.run(4_000_000)                    # the disk goes to sleep (STANDBY), as on a device a few seconds on
p.m.hook_start([0x9bab0, 0x40474, 0xc788c])                             # VM steps (the UI's thread), fw_create, disk reads
pick(5)
check("  Apple hidden, still listed", hidden() == ["Apple", "Delta"] and len(titles()) == 7, str(hidden()))
p.run(3_000_000)
log = p.m.hook_log()
ui = {r[13] >> 16 for t, pc, r, v in log if pc == 0x9bab0}             # the UI's stack (64 KiB pages)
creates = [r[13] for t, pc, r, v in log if pc == 0x40474]
ui_reads = [hex(r[13]) for t, pc, r, v in log if pc == 0xc788c and r[13] >> 16 in ui]
# On a device, the save (its stat of the iTunesDB for the stamp, the create) woke the sleeping disk
# on the UI's thread, and an SD adapter that drops out on a wake froze the UI for the 10 s timeout.
check("  FroggerHidden written by the save task, no disk read on the UI's thread",
      len(creates) == 1 and creates[0] >> 16 not in ui and not ui_reads,
      "creates %s, UI stack %s, its reads %s" % ([hex(c) for c in creates], [hex(u << 16) for u in ui], ui_reads[:4]))
check("  On-The-Go not marked to be saved by the add", rb(rd(lib) + 0xb42) == 0, str(rb(rd(lib) + 0xb42)))
check("hold Apple: Show", hold("3_apple2") == 1); pick(5)
check("  Apple shown", hidden() == ["Delta"], str(hidden()))
p.scroll(4); p.settle(); p.run(300_000)                                 # Kite
check("hold Kite > Hide", hold("3_kite") == 0); pick(5)
check("  Kite hidden again", hidden() == ["Delta", "Kite"], str(hidden()))
check("hold Kite: Show", hold("3_kite2") == 1); pick(5)
check("  Kite shown again", hidden() == ["Delta"], str(hidden()))

to_menu(2); music(2)                                                    # Albums
check("Albums: three", rd(lib + 0x894) == 3, str(rd(lib + 0x894)))
p.scroll(2); p.settle(); p.run(300_000)                                 # Beta
check("hold Beta (one hidden, one shown): Hide", hold("4_beta") == 0); close()
p.scroll(1); p.settle(); p.run(300_000)                                 # Gamma
check("hold Gamma > Hide", hold("4_gamma") == 0); pick(4)
check("  Echo, Bravo hidden, Gamma listed", hidden() == ["Bravo", "Delta", "Echo"] and rd(lib + 0x894) == 3, str(hidden()))
check("hold Gamma: Show", hold("4_gamma2") == 1); close()
to_menu(2); music(1)                                                    # Artists
p.scroll(2); p.settle(); p.run(300_000)                                 # Art Two
check("hold Art Two: Show", hold("4_art2") == 1); pick(2)
check("  Echo, Bravo shown", hidden() == ["Delta"], str(hidden()))
p.scroll(-1); p.settle(); p.run(300_000)                                # Art One
check("hold Art One: Hide", hold("4_art1") == 0); close()

to_menu(2); songs()
p.scroll(-8); p.scroll(5); p.settle(); p.run(300_000)                   # Moon
check("hold Moon > Hide", hold("5_moon") == 0); pick(5)
to_menu(2); music(2)
p.scroll(3); p.settle(); p.run(300_000)                                 # Gamma
check("Albums: hold Gamma > Hide", hold("5_gamma") == 0); pick(4)
check("  Moon, Echo, Bravo (and Delta) hidden", hidden() == ["Bravo", "Delta", "Echo", "Moon"], str(hidden()))
to_menu(2)
show_hidden(0)
counts("uh_6_%s.png")

now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(0, END, 4) if snap[i:i + 4] != now[i:i + 4]]
check("Apple's image unchanged", not diff, "%d words, first %#x" % (len(diff), diff[0] if diff else 0))
out = hmcard.mtools(card, "mtype", "::/iPod_Control/iTunes/FroggerHidden", capture_output=True).stdout
ver, size, _, n = struct.unpack_from("<HHII", out, 4) if len(out) >= 20 else (0, 0, 0, 0)
ents = {}
for i in range(n if size == 24 else 0):
    dbid, tid, _, _, flags = struct.unpack_from("<QIIII", out, 20 + 24 * i)
    ents[[t for t, v in hmcard.TID.items() if v == tid and dbid == 0x1000 + v][0]] = "shown" if flags & 1 else "hidden"
check("FroggerHidden v3: Kite shown; Moon, Echo, Bravo", out[:4] == b"FRGH" and ver == 3
      and ents == {"Kite": "shown", "Moon": "hidden", "Echo": "hidden", "Bravo": "hidden"}, "%r v%d %s" % (out[:4], ver, ents))

"""Frogger image + a card with hidden songs in every list (hidden-row-card.img): the Hidden row at the
top of Music › Artists, Albums, Genres and Composers (payload/hiddenrow.c). One run, checking as it
goes (exits 1 on a wrong step; screenshots hrow_*.png):

    Moon, Apple   Art One    Alpha  Rock  Comp A
    Kite*, Delta  Art One    Beta   Jazz  Comp B
    Xray*         Art One    Solo   Rock  Comp A
    Echo*, Bravo* Art Two    Gamma  Pop   Comp C
    Zulu*         Art Three  Omega  Pop   Comp D       (* hidden)

1. Albums: "Hidden (3)" on top, then All, Alpha, Beta. Select it: Gamma, Omega, Solo (no All, title
   Hidden); Select Solo: its song Xray. Menu: the Hidden list again; Menu: the whole list, on the
   Hidden row.
2. Genres: "Hidden (1)"; its list is Pop, whose artists (Select) are Art Three and Art Two. Composers:
   "Hidden (2)", Comp C and Comp D.
3. Artists: "Hidden (2)". Holding it opens nothing. The Hidden list: Art Three, Art Two; Art Three's
   albums (Omega). Hold Art Two: Show; Show: Echo, Bravo shown, the Hidden list has Art Three.
   Menu: "Hidden (1)", All, Art One, Art Two. Hold Art Two (row 3): Hide; Hide: Echo, Bravo hidden
   again, Art Two gone. The Hidden list again: Show both: empty. Menu: no Hidden row.
4. Settings > Show Hidden on: Albums lists all five, no Hidden row.
5. Apple's image unchanged."""
import struct, sys
from pathlib import Path
from ipod3g import Pod, W
import hmcard

SONGS = [("Moon", "Art One", "Alpha", 1, "Rock", "Comp A"), ("Apple", "Art One", "Alpha", 2, "Rock", "Comp A"),
         ("Kite", "Art One", "Beta", 1, "Jazz", "Comp B"), ("Delta", "Art One", "Beta", 2, "Jazz", "Comp B"),
         ("Xray", "Art One", "Solo", 1, "Rock", "Comp A"),
         ("Echo", "Art Two", "Gamma", 1, "Pop", "Comp C"), ("Bravo", "Art Two", "Gamma", 2, "Pop", "Comp C"),
         ("Zulu", "Art Three", "Omega", 1, "Pop", "Comp D")]
card = hmcard.make("hidden-row-card.img", hidden=("Kite", "Xray", "Echo", "Bravo", "Zulu"), songs=SONGS)
SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(Path(W).parent / "payload/payload.sym") if len(l.split()) == 3}
HR = SYM["hr"]                      # hiddenrow.c: shift[4], mode, depth, gen, widget, picked
HM_OPEN = SYM["hm"]                 # holdmenu.c: hm.open, its first word
HM_SHOW = SYM["hm"] + 20 * 4        # hm.show
SHOW_ALL = SYM["hide_state"] + 1
REVEAL = SYM["hide_state"] + 2
END = 0x346368
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
rb = lambda a: bytes(p.m.mem_read(a, 1))[0]
snap = bytes(p.m.mem_read(0, END))
TITLE = {}                          # track record -> title
lib = 0
LIST = {"genres": 0x878, "artists": 0x880, "composers": 0x888, "albums": 0x890}
KEY = {"genres": 0x38, "artists": 0x28, "composers": 0x34, "albums": 0x30}
NAME = {}                           # (list, key) -> name, from the songs


def fail(msg):
    print("WRONG:", msg); p.shot("hrow_wrong.png"); sys.exit(1)


def check(tag, ok, msg=""):
    print("%-56s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        fail(tag)


def library():
    global lib
    lib = rd(rd(0x43580c) + 0x1c)
    if not TITLE:                   # the songs' records, from tracks.c's table (database order)
        recs = [rd(SYM["track_rec"] + 4 * i) for i in range(len(SONGS))]
        for r, s in zip(recs, SONGS):
            TITLE[r] = s[0]
            for k, i in (("artists", 1), ("albums", 2), ("genres", 4), ("composers", 5)):
                NAME[k, rd(r + KEY[k])] = s[i]


def items(kind):                    # the level's array, as names
    a, n = rd(lib + LIST[kind]), rd(lib + LIST[kind] + 4)
    return [NAME.get((kind, rd(a + 4 * i)), "?") for i in range(n)] if a else []


def widget():                       # the list on screen: the wheel moves it (letters.c notes it)
    p.wheel(-6, after_us=300_000)
    p.wheel(6, after_us=300_000)
    return rd(SYM["letter_widget"])


def rows():
    return rd(widget() + 0x9c)


def text():
    return bytes(p.m.mem_read(SYM["hiddenrow_text"], 16)).split(b"\0")[0].decode()


def hidden():
    t = struct.unpack("<16384I", bytes(p.m.mem_read(SYM["table"], 4 * 16384)))
    return sorted(TITLE[r] for r in t if r in TITLE)


def top():
    p.scroll(-12); p.settle(); p.run(300_000)


def select(row=None, shot=None):
    if row is not None:
        top(); p.scroll(row); p.settle(); p.run(300_000)
    p.press("select", after_us=1_500_000); p.settle()
    if shot:
        p.shot("hrow_%s.png" % shot, 1)


def menu(n=1):
    for _ in range(n):
        p.press("menu", after_us=1_500_000); p.settle()


def hold(shot):
    p.press("select", hold_us=2_000_000); p.settle(); p.shot("hrow_%s.png" % shot, 1)
    return rd(HM_SHOW)


def pick(n):
    p.scroll(n); p.settle(); p.run(300_000)
    p.press("select", after_us=1_500_000); p.settle()


def music(row, shot):               # from the main menu, on Music: one of its rows
    p.press("select"); p.settle(); p.scroll(-8); p.scroll(row); p.settle(); p.run(300_000)
    select(shot=shot)
    library()


def normal(kind, n_hidden, n_items, shot):
    check("%s: \"Hidden (%d)\" on top, All, then %d" % (kind.capitalize(), n_hidden, n_items),
          rows() == n_items + 2 and text() == "Hidden (%d)" % n_hidden and rb(REVEAL) == 0,
          "%d rows, %r, reveal %d" % (rows(), text(), rb(REVEAL)))
    p.shot("hrow_%s.png" % shot, 1)


p.press("select"); p.settle()                                           # English; main menu on Music

music(2, "1_albums")                                                    # Albums
normal("albums", 3, 2, "1_albums")
check("  its array: Alpha, Beta", items("albums") == ["Alpha", "Beta"], str(items("albums")))
select(0, "1_hidden")
check("Select Hidden: Gamma, Omega, Solo, no All, titled Hidden", items("albums") == ["Gamma", "Omega", "Solo"]
      and rows() == 3 and rb(REVEAL) == 1 and rd(SYM["letter_title"]) == 0x3f35,
      "%s %d rows, title %#x" % (items("albums"), rows(), rd(SYM["letter_title"])))
select(2, "1_solo")
songs = [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]
check("  Select Solo: Xray", songs == ["Xray"], str(songs))
menu()
check("  Menu: the Hidden list again", items("albums") == ["Gamma", "Omega", "Solo"] and rows() == 3,
      "%s %d" % (items("albums"), rows()))
menu()
p.shot("hrow_1_back.png", 1)
normal("albums", 3, 2, "1_back")
check("  Menu: the whole list again, titled Albums", items("albums") == ["Alpha", "Beta"]
      and rd(SYM["letter_title"]) == 0xffffffe9, "%s %#x" % (items("albums"), rd(SYM["letter_title"])))
menu(2)

music(4, "2_genres")                                                    # Genres
normal("genres", 1, 2, "2_genres")
select(0, "2_hidden")
check("Select Hidden: Pop", items("genres") == ["Pop"] and rows() == 1, "%s %d" % (items("genres"), rows()))
select(0, "2_pop")
check("  Select Pop: Art Three, Art Two", items("artists") == ["Art Three", "Art Two"], str(items("artists")))
menu(2)
check("  Menu, Menu: the whole list", items("genres") == ["Jazz", "Rock"] and rb(REVEAL) == 0, str(items("genres")))
menu(2)
music(5, "2_composers")                                                 # Composers
normal("composers", 2, 2, "2_composers")
select(0, "2_chidden")
check("Select Hidden: Comp C, Comp D", items("composers") == ["Comp C", "Comp D"] and rows() == 2,
      "%s %d" % (items("composers"), rows()))
menu(3)

music(1, "3_artists")                                                   # Artists
normal("artists", 2, 1, "3_artists")
top()
hold("3_holdrow")
check("hold the Hidden row: no popup, still the list", rd(HM_OPEN) == 0 and rb(REVEAL) == 0
      and items("artists") == ["Art One"] and rows() == 3, "%d %s %d" % (rd(HM_OPEN), items("artists"), rows()))
select(0, "3_hidden")
check("Select Hidden: Art Three, Art Two", items("artists") == ["Art Three", "Art Two"] and rows() == 2,
      "%s %d" % (items("artists"), rows()))
select(0, "3_three")
check("  Select Art Three: Omega", items("albums") == ["Omega"], str(items("albums")))
menu()
p.shot("hrow_3_menu.png", 1)
top(); p.scroll(1); p.settle(); p.run(300_000)                          # Art Two
check("  hold Art Two: Show", hold("3_show") == 1); pick(2)
check("  Show: Echo, Bravo shown; the list: Art Three", hidden() == ["Kite", "Xray", "Zulu"]
      and items("artists") == ["Art Three"] and rows() == 1, "%s %s %d" % (hidden(), items("artists"), rows()))
menu()
normal("artists", 1, 2, "3_back")
check("  the whole list: Art One, Art Two", items("artists") == ["Art One", "Art Two"], str(items("artists")))
top(); p.scroll(3); p.settle(); p.run(300_000)                          # Art Two, under Hidden and All
check("hold Art Two (row 3): Hide", hold("3_hide") == 0); pick(2)
check("  Hide: Echo, Bravo hidden again, Art Two gone", hidden() == ["Bravo", "Echo", "Kite", "Xray", "Zulu"]
      and items("artists") == ["Art One"], "%s %s" % (hidden(), items("artists")))
normal("artists", 2, 1, "3_hidden2")
select(0, "3_hidden3")
top()
check("  hold Art Three: Show", hold("3_show2") == 1); pick(2)
top()
check("  hold Art Two: Show", hold("3_show3") == 1); pick(2)
w = rd(HR + 16)                                                         # hr.widget: the wheel can't move an empty list
check("  the Hidden list empty", items("artists") == [] and rd(w + 0x9c) == 0 and hidden() == ["Kite", "Xray"],
      "%s %d %s" % (items("artists"), rd(w + 0x9c), hidden()))
menu()
p.shot("hrow_3_none.png", 1)
check("  Menu: no Hidden row, All and three artists", rows() == 4 and rb(HR + 1) == 0
      and items("artists") == ["Art One", "Art Three", "Art Two"], "%d %s" % (rows(), items("artists")))
menu(2)

p.scroll(2); p.press("select"); p.settle(); p.scroll(-14); p.scroll(9); p.settle()     # Settings > Show Hidden
p.press("select"); p.settle()
check("Settings > Show Hidden on", rb(SHOW_ALL) == 1, str(rb(SHOW_ALL)))
p.press("menu"); p.settle(); p.scroll(-2); p.settle()
music(2, "4_albums")
check("  Albums: All and all five, no Hidden row", rows() == 6
      and items("albums") == ["Alpha", "Beta", "Gamma", "Omega", "Solo"], "%d %s" % (rows(), items("albums")))

now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(0, END, 4) if snap[i:i + 4] != now[i:i + 4]]
check("Apple's image unchanged", not diff, "%d words, first %#x" % (len(diff), diff[0] if diff else 0))

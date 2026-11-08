#!/usr/bin/env python3
"""Frogger image + dbid-card.img (made here from resume-card.img): Frogger's files outlast a sync
by another app (payload/tracks.c, docs/file-formats.md). The card's iTunesDB "A" has, in this
order, Tone A, Tone B long, Long Mix (25 min), Tone A again (the same file as Tone A: same size
and length) and Gone, ids 101-105, each with a dbid of its own, plus a synced playlist Mix (Tone
A); FroggerArt version 2 gives song i of A cover i. One run per step, each its own process:

    dbid.py write    # boot A: hide Gone and Tone B long, add Tone A again to Mix, skip Tone A
                     # again (Next at ~5 s), leave Long Mix part way (Next): FroggerHidden v3,
                     # FroggerSkips v2, FroggerBookmarks and FroggerPlaylist_0000000000ABCDF0 on
                     # the card, every song by its dbid
    dbid.py resync   # then, as another app's sync would: a new iTunesDB "B" with the songs in
                     # another order and new track ids (Tone A again 201, Long Mix 202, Tone B
                     # long 203, Tone A 204; Gone is gone, Mix synced as Tone A only), Play
                     # Counts deleted. Boot B: Tone B long is the one song hidden, Tone A again
                     # has the skip, Long Mix its bookmark, Mix has Tone A and Tone A again, and
                     # every song's cover is the one it had in A
    dbid.py old      # write's card again with A, and files of the old versions with A's stamp
                     # (FroggerHidden v2: Tone A again; FroggerSkips v1: Tone B long 2 skips;
                     # FroggerArt v1, covers 4 3 2 1 0): all three apply, and FroggerSkips is
                     # written again as version 2
    dbid.py          # all three, in that order

Exits 1 if a check is off (screenshots dbid_*.png)."""
import os, shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W
import hmcard, mkart
import mkresume as mk

from ipod3g import ROOT
sys.path.insert(0, str(ROOT / "tools"))
import podinfo  # noqa: E402  (the file formats)

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(Path(W).parent / "payload/payload.sym") if len(l.split()) == 3}
CARD, RUN, OLD = W + "/dbid-card.img", W + "/dbid-run.img", W + "/dbid-old.img"
LOC = ":iPod_Control:Music:F00:%s.mp3"
TONE_A, TONE_B = (2881119, 180000, 128), (28802739, 720000, 320)
# title: (file, (size, ms, kbps), dbid, id in A, id in B, cover)
SONGS = {"Tone A": ("TONEA", TONE_A, 0x5eed000100000001, 101, 204, 0),
         "Tone B long": ("TONEB", TONE_B, 0x5eed000100000002, 102, 203, 1),
         "Long Mix": ("TONEL", None, 0x5eed000100000003, 103, 202, 2),
         "Tone A again": ("TONEA", TONE_A, 0x5eed000100000004, 104, 201, 3),
         "Gone": ("TONEB", TONE_B, 0x5eed000100000005, 105, None, 4)}
A = ["Tone A", "Tone B long", "Long Mix", "Tone A again", "Gone"]    # database order (ids ascending)
B = ["Tone A again", "Long Mix", "Tone B long", "Tone A"]
MIX_PID = 0xabcdf0
fails = []


def check(what, ok, got=""):
    print("  %-60s %s" % (what, "ok" if ok else "WRONG %s" % (got,)))
    if not ok:
        fails.append(what)


def database(order, ids):
    long_size = (Path(W) / "TONEL.mp3").stat().st_size
    tracks = []
    for title in order:
        f, tone, dbid = SONGS[title][:3]
        size, ms, kbps = tone or (long_size, mk.LONG_MS, 32)
        tracks.append(mk.mhit(SONGS[title][ids], {"title": title, "artist": "Test Artist", "album": "Test Album",
                                                  "genre": "Test", "location": LOC % f}, size, ms, kbps, dbid=dbid))
    tids = [SONGS[t][ids] for t in order]
    return mk.mhbd([mk.mhsd(1, mk.mhl(b"mhlt", tracks)),
                    mk.mhsd(2, mk.mhl(b"mhlp", [mk.mhyp("iPod", tids),
                                                mk.mhyp("Mix", [SONGS["Tone A"][ids]], master=False, pid=MIX_PID)]))])


def put(card, name, data):
    """A file into iPod_Control/iTunes with the time now (nix sets SOURCE_DATE_EPOCH, which mtools
    would stamp every file with: then a new iTunesDB has the old one's stamp, 0x77600)."""
    tmp = Path(card).with_suffix("." + name.replace(" ", "_"))
    tmp.write_bytes(data)
    env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
    hmcard.mtools(card, "mcopy", "-o", "-m", str(tmp), "::/iPod_Control/iTunes/" + name, env=env)
    tmp.unlink()


def get(card, name):
    r = subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-i",
                        f"{card}@@{hmcard.partition(card) * 512}", name if name.startswith("::") else "::/iPod_Control/iTunes/" + name, "-"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else b""


def make_card():
    shutil.copyfile(W + "/resume-card.img", CARD)
    put(CARD, "iTunesDB", database(A, 3))
    mkart.put(CARD, covers=5, table=[SONGS[t][5] for t in A])


class Run:
    def __init__(self, card, order):
        self.p = p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
        self.order = order
        if not get(card, "::/iPod_Control/Device/Preferences"):
            p.press("select"); p.settle()                       # first run: Language -> English
        self.title = {self.rd(SYM["track_rec"] + 4 * i): t for i, t in enumerate(order)}

    def rd(self, a):
        return struct.unpack("<I", bytes(self.p.m.mem_read(a, 4)))[0]

    def lib(self):
        return self.rd(self.rd(0x43580c) + 0x1c)

    def music(self, row):                                       # from the main menu, on Music
        p = self.p
        p.press("select"); p.settle(); p.scroll(-8); p.scroll(row); p.settle(); p.run(300_000)
        p.press("select", after_us=1_500_000); p.settle()

    def row(self, n):                                           # a list's row n
        p = self.p
        p.scroll(-8); p.scroll(n); p.settle(); p.run(300_000)

    def menu(self, n=1):
        for _ in range(n):
            self.p.press("menu", after_us=1_500_000); self.p.settle()

    def hold(self, pick):                                       # the hold menu's row `pick`
        p = self.p
        p.press("select", hold_us=2_000_000); p.settle()
        p.scroll(pick); p.settle(); p.run(300_000)
        p.press("select", after_us=1_500_000); p.settle()

    def hidden(self):
        t = struct.unpack("<16384I", bytes(self.p.m.mem_read(SYM["table"], 4 * 16384)))
        return sorted(self.title[r] for r in t if r in self.title)

    def skips(self):
        n = self.rd(SYM["n_skip"])
        return {self.order[self.rd(SYM["skip"] + 16 * i)]: self.rd(SYM["skip"] + 16 * i + 8) for i in range(min(n, 8))}

    def bookmark(self, title):
        return self.rd(self.rd(SYM["track_rec"] + 4 * self.order.index(title)) + 0x60)

    def pos(self):
        player = self.rd(self.rd(self.lib()) + 4)
        return self.rd(player + 0x2164)

    def scrub(self, steps):
        p = self.p
        p.press("select", after_us=300_000)                     # Apple's page
        p.press("select", after_us=300_000)                     # scrubbing
        p.wheel(steps, after_us=800_000)
        p.press("select", after_us=1_500_000)                   # done

    def play_to(self, ms):                                      # emupod doesn't play on: scrub there
        for _ in range(12):
            if self.pos() >= ms:
                return
            self.scrub(-8)

    def cover(self):
        self.p.run(1_000_000); self.p.settle()
        return self.rd(SYM["art_shown"])


def by_title(titles):
    return sorted(titles)


def write():
    make_card()
    shutil.copyfile(CARD, RUN)
    r = Run(RUN, A)
    p = r.p
    songs = by_title(A)                                         # Gone, Long Mix, Tone A, Tone A again, Tone B long
    r.music(3)                                                  # Songs
    r.row(songs.index("Gone")); r.hold(5)                       # Hide
    r.row(songs.index("Tone B long")); r.hold(5)
    check("hidden: Gone, Tone B long", r.hidden() == ["Gone", "Tone B long"], r.hidden())
    r.row(songs.index("Tone A again"))
    p.press("select", hold_us=2_000_000); p.settle()            # Add to Playlist > Mix
    p.scroll(2); p.settle(); p.run(500_000); p.press("select", after_us=1_500_000); p.settle()
    p.scroll(-6); p.settle(); p.run(500_000); p.press("select", after_us=2_000_000); p.settle()
    p.shot("dbid_added.png", 1)
    r.row(songs.index("Tone A again")); p.press("select", after_us=2_000_000); p.settle()
    r.play_to(5000); at = r.pos()
    p.press("next", after_us=1_000_000); p.settle()
    p.run(5_000_000)                                            # Apple's 'prwp': Play Counts, FroggerSkips
    check("Next at %d ms: Tone A again skipped" % at, r.skips() == {"Tone A again": 1}, r.skips())
    r.menu(); r.row(songs.index("Long Mix")); p.press("select", after_us=2_000_000); p.settle()
    r.scrub(-60); at = r.pos()
    p.press("next", after_us=2_000_000); p.settle()
    p.run(5_000_000)
    bm = r.bookmark("Long Mix")
    check("Long Mix left at %d ms: its bookmark" % at, at > 30_000 and abs(bm - at) < 3000, bm)
    p.shot("dbid_write.png", 1)
    del r, p
    files = {n: get(RUN, n) for n in ("FroggerHidden", "FroggerSkips", "FroggerBookmarks", "FroggerPlaylist_%016X" % MIX_PID)}
    dbid_of = {SONGS[t][2]: t for t in A}

    def songs_in(data, magic):
        try:
            f = podinfo.FroggerFile(data, magic)
        except ValueError as e:
            return None, str(e)
        return f, [(dbid_of.get(e[0].dbid, hex(e[0].dbid)), *e[1:]) for e in f.entries]
    f, e = songs_in(files["FroggerHidden"], podinfo.HIDDEN)
    check("FroggerHidden v3: Gone, Tone B long hidden", f and f.version == 3 and sorted(e) == [("Gone", 0), ("Tone B long", 0)], e)
    f, e = songs_in(files["FroggerSkips"], podinfo.SKIPS)
    check("FroggerSkips v2: Tone A again, 1", f and f.version == 2 and [x[:2] for x in e] == [("Tone A again", 1)], e)
    f, e = songs_in(files["FroggerBookmarks"], podinfo.BOOKMARKS)
    check("FroggerBookmarks v1: Long Mix at its bookmark", f and f.version == 1 and e == [("Long Mix", bm)], e)
    f, e = songs_in(files["FroggerPlaylist_%016X" % MIX_PID], podinfo.PLAYLIST)
    check("FroggerPlaylist_0000000000ABCDF0: Tone A, Tone A again", f and f.id == MIX_PID
          and e == [("Tone A",), ("Tone A again",)], e)
    Path(W, "dbid-bookmark").write_text(str(bm))


def resync():
    put(RUN, "iTunesDB", database(B, 4))
    hmcard.mtools(RUN, "mdel", "::/iPod_Control/iTunes/Play Counts")     # read and deleted by the syncing app
    bm = int(Path(W, "dbid-bookmark").read_text())
    r = Run(RUN, B)
    p = r.p
    check("hidden: Tone B long only", r.hidden() == ["Tone B long"], r.hidden())
    check("skips: Tone A again, 1", r.skips() == {"Tone A again": 1}, r.skips())
    check("Long Mix's bookmark from FroggerBookmarks (%d ms)" % bm,
          r.bookmark("Long Mix") == bm and all(r.bookmark(t) == 0 for t in B if t != "Long Mix"),
          [r.bookmark(t) for t in B])
    r.music(0)                                                  # Playlists: FroggerPlaylist files read
    p.press("select", after_us=1_500_000); p.settle()           # Mix
    lib = r.lib()
    mix = [r.title.get(r.rd(r.rd(r.rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(r.rd(lib + 0x89c))]
    p.shot("dbid_mix.png", 1)
    check("Mix: Tone A, Tone A again", mix == ["Tone A", "Tone A again"], mix)
    r.menu(3)                                                   # Mix, Playlists, Music
    r.music(3)
    covers = {}
    for i, t in enumerate(by_title(B)):
        r.row(i); p.press("select", after_us=2_000_000)
        covers[t] = r.cover()
        p.shot("dbid_cover_%d.png" % i, 1)
        r.menu()
    check("covers by dbid: each song's from A", covers == {t: SONGS[t][5] for t in B}, {t: hex(c) for t, c in covers.items()})


def old():
    shutil.copyfile(W + "/dbid-write-copy.img", OLD)            # write's card: A, and files with A's stamp
    stamp = struct.unpack_from("<I", get(OLD, "FroggerHidden"), 8)[0]
    pos = {t: i for i, t in enumerate(A)}
    put(OLD, "FroggerHidden", struct.pack("<IHHIII3I", 0x48475246, 2, 12, stamp, 1, 0,
                                          pos["Tone A again"], SONGS["Tone A again"][3], 0))
    put(OLD, "FroggerSkips", struct.pack("<IHHIII4I", 0x53475246, 1, 16, stamp, 1, 0,
                                         pos["Tone B long"], SONGS["Tone B long"][3], 2, 0xe0000000))
    imgs = [mkart.image(mkart.PATTERNS[i]) for i in range(5)]
    put(OLD, "FroggerArt", mkart.froggerart_v1([4, 3, 2, 1, 0], imgs))
    r = Run(OLD, A)
    p = r.p
    check("FroggerHidden v2 (by position): Tone A again hidden", r.hidden() == ["Tone A again"], r.hidden())
    check("FroggerSkips v1: Tone B long, 2", r.skips() == {"Tone B long": 2}, r.skips())
    r.music(3)
    songs = by_title(A)
    r.row(songs.index("Tone A")); p.press("select", after_us=2_000_000)
    got = r.cover()
    check("FroggerArt v1: Tone A (position 0) has cover 4", got == 4, hex(got))
    p.press("next", after_us=1_000_000); p.settle()             # a song change: Play Counts, FroggerSkips
    p.run(5_000_000)
    del r, p
    try:
        f = podinfo.FroggerFile(get(OLD, "FroggerSkips"), podinfo.SKIPS)
        e = [(x[0].dbid, x[1]) for x in f.entries] if f.keyed else "version %d" % f.version
    except ValueError as err:
        f, e = None, str(err)
    check("FroggerSkips written again as v2: Tone B long's dbid, 2", f and f.version == 2
          and e == [(SONGS["Tone B long"][2], 2)], e)


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        write()
        shutil.copyfile(RUN, W + "/dbid-write-copy.img")
    elif sys.argv[1:] == ["resync"]:
        resync()
    elif sys.argv[1:] == ["old"]:
        old()
    else:
        codes = [subprocess.run([sys.executable, __file__, s]).returncode for s in ("write", "resync", "old")]
        sys.exit(1 if any(codes) else 0)
    sys.exit(1 if fails else 0)

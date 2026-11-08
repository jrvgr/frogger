"""Frogger image: the hold menu's Add to Playlist into a playlist made on the iPod (payload/playlist.c,
holdmenu.c), and that it lasts. On a copy of music-card.img, pl-own-card.img, written back:

1. Songs: hold Tone A > Add to Playlist > On-The-Go: On-The-Go has Tone A.
2. On-The-Go > Save Playlist: "New Playlist 1" (+0x124 = 1) holds Tone A, On-The-Go is empty.
3. Songs: hold Tone B long > Add to Playlist > New Playlist 1: it holds both songs.
4. Sleep. iPod_Control/iTunes/OTGPlaylistInfo_1 holds the two songs, in Apple's format
   (docs/re-notes.md, "Playlists made on the iPod"): an mhpo header, 4-byte entries, count 2,
   the iTunesDB's stamp, references [0, 1] (each song's place in the master playlist).
5. A restart (its own process): New Playlist 1 is read back from the file with both songs, and
   opening it in Music > Playlists lists Tone A and Tone B long.

Prints the playlists' song counts after each step; shots plo_*.png. Exits 1 on a wrong step.
(playlists.py has the other ways in: synced playlists, albums, artists, song orders.)

    ownplaylist.py            # all of it
    ownplaylist.py restart    # step 5 only, on the card step 4 left"""
import shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W
import hmcard

CARD = W + "/pl-own-card.img"
TITLES = ["Tone A", "Tone B long"]                   # music-card.img's songs, by title
fails = []


def check(what, ok, msg=""):
    print("  %-62s %s" % (what, "ok" if ok else "WRONG " + msg))
    if not ok:
        fails.append(what)


class Session:
    def __init__(self, persist):
        self.p = Pod(osos=W + "/osos-frogger.img", disk=CARD, persist=persist)
        self.lib = self.rd(self.rd(0x43580c) + 0x1c)

    def rd(self, a):
        return struct.unpack("<I", bytes(self.p.m.mem_read(a, 4)))[0]

    def lists(self, tag):
        """{playlist index: (song count, its +0x124 N)}, On-The-Go's count; printed."""
        rd, lib = self.rd, self.lib
        arr, n = rd(lib + 0x870), rd(lib + 0x874)
        out = {i: (rd(rd(rd(arr + 4 * i) + 0x24) + 0x2c), rd(rd(arr + 4 * i) + 0x124)) for i in range(n)}
        otg = rd(rd(rd(lib + 0x48) + 0x24) + 0x2c)
        print("%-34s lists %s  otg=%d" % (tag, " ".join("%d:%d(N=%d)" % (i, c, k) for i, (c, k) in out.items()), otg))
        return out, otg

    def own(self, tag):
        """New Playlist 1's index and song count, or (None, 0)."""
        out, _ = self.lists(tag)
        for i, (count, n) in out.items():
            if n == 1:
                return i, count
        return None, 0

    def sel(self, after=1_500_000):
        self.p.press("select", after_us=after); self.p.settle()

    def wheel(self, n):
        self.p.scroll(n); self.p.settle(); self.p.run(500_000)

    def menu(self, times=1):
        for _ in range(times):
            self.p.press("menu", after_us=1_500_000); self.p.settle()

    def shot(self, name):
        print(self.p.shot("plo_%s.png" % name, 1))

    def rows(self):
        """The records of the rows of the list on screen (lib+0x898, count +0x89c)."""
        rd, lib = self.rd, self.lib
        return [rd(rd(rd(lib + 0x898) + 4 * i) + 0x20) for i in range(rd(lib + 0x89c))]

    def add_to_playlist(self, pick_row, tag):
        """Hold the song, the popup's third row (Add to Queue, Play Album Next, Add to Playlist),
        then the picker's row pick_row."""
        self.p.press("select", hold_us=2_000_000); self.p.settle()
        self.wheel(2); self.sel(); self.shot(tag + "_picker")
        self.wheel(-6); self.wheel(pick_row); self.sel(2_000_000); self.shot(tag + "_back")


def add():
    shutil.copy(W + "/music-card.img", CARD)
    s = Session(persist=True)
    s.sel()                                                         # Language: English
    s.sel(); s.wheel(3); s.sel()                                    # Music > Songs, Tone A
    s.lists("start")
    s.add_to_playlist(1, "a")                                       # picker rows: Mix, On-The-Go
    _, otg = s.lists("Tone A > On-The-Go")
    check("1. Add to Playlist > On-The-Go: it has Tone A", otg == 1, "otg %d" % otg)
    s.menu(); s.wheel(-6); s.sel(); s.wheel(-6); s.wheel(1); s.sel(); s.shot("otg")   # Music > Playlists > On-The-Go
    s.wheel(2); s.sel(); s.wheel(1); s.sel(2_000_000)              # Save Playlist > confirm
    i, count = s.own("saved New Playlist 1")
    _, otg = s.lists("")
    check("2. Save Playlist: New Playlist 1 with Tone A", i is not None and count == 1, "index %s, %d songs" % (i, count))
    check("2.   On-The-Go empty", otg == 0, "otg %d" % otg)
    s.shot("saved")
    s.menu(); s.wheel(-6); s.wheel(3); s.sel(); s.wheel(1)          # Music > Songs, Tone B long
    s.add_to_playlist(1, "b")                                       # picker rows: Mix, New Playlist 1, On-The-Go
    i, count = s.own("Tone B > New Playlist 1")
    check("3. Add to Playlist > New Playlist 1: both songs", count == 2, "%d songs" % count)
    s.menu(3)
    s.p.press("play", hold_us=3_000_000, after_us=10_000_000)       # sleep: the disk written
    del s
    out = Path(CARD).with_suffix(".otg")
    try:
        hmcard.mtools(CARD, "mcopy", "-n", "::/iPod_Control/iTunes/OTGPlaylistInfo_1", str(out), capture_output=True)
        f = out.read_bytes(); out.unlink()
    except subprocess.CalledProcessError:
        f = b""
    ok = len(f) >= 0x14 and f[:4] == b"mhpo"
    check("4. OTGPlaylistInfo_1 written, an mhpo header", ok, repr(f[:8]))
    if ok:
        hlen, entry, n, stamp = struct.unpack_from("<IIII", f, 4)
        refs = list(struct.unpack_from("<%dI" % n, f, hlen)) if len(f) >= hlen + 4 * n else None
        print("  OTGPlaylistInfo_1: header %#x, entry %d, count %d, stamp %#x, refs %s" % (hlen, entry, n, stamp, refs))
        check("4.   two 4-byte entries after a 0x14-byte header, a stamp", (hlen, entry, n) == (0x14, 4, 2) and stamp,
              "header %#x entry %d count %d stamp %#x" % (hlen, entry, n, stamp))
        check("4.   Tone A then Tone B long: references [0, 1]", refs == [0, 1], str(refs))
        check("4.   nothing after them", len(f) == hlen + 4 * n, "%d bytes" % len(f))


def restart():
    s = Session(persist=False)
    s.sel(); s.wheel(3); s.sel()                                    # Music > Songs
    names = dict(zip(s.rows(), TITLES))
    i, count = s.own("after a restart")
    check("5. after a restart: New Playlist 1 with both songs", count == 2, "index %s, %d songs" % (i, count))
    if i is None:
        return
    s.menu(); s.wheel(-6); s.sel()                                  # Music > Playlists
    s.wheel(-6); s.wheel(i - 1); s.sel(); s.shot("restart")         # row r is the playlist [r + 1]
    got = [names.get(r, "record %#x" % r) for r in s.rows()]
    check("5.   opened, it lists Tone A and Tone B long", got == TITLES, str(got))


if __name__ == "__main__":
    if sys.argv[1:] == ["restart"]:
        restart()
    else:
        add()
        if not fails and subprocess.run([sys.executable, __file__, "restart"]).returncode:
            fails.append("restart")
    sys.exit(1 if fails else 0)

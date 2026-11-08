#!/usr/bin/env python3
"""Album artists (payload/artist.c): a song's album artist (iTunesDB mhod 22, which stock 2.3
ignores) stands in for its artist, so a compilation's songs stay under one name. Two card copies:

    aa-card.img      Tone A (artist Peshay) and Tone B long (Doc Scott) on "Blue Notes", both with
                     album artist "LTJ Bukem" (Tone A's mhod before its artist's, Tone B's after),
                     and Tone C (Calibre, no album artist) on "Other"
    aa-ref-card.img  the same with artist "LTJ Bukem" on both Blue Notes songs and no album artists

Three runs, each its own process (emupod opens once per process): Frogger on aa-card ("frog"),
stock 2.3 on aa-card ("stock": Frogger off, as it were) and stock on aa-ref-card ("ref": what the
grouping should look like). Each opens Music > Songs (reads the songs' artist, the track record's
+0x28), Artists, the third row's (after All and Calibre) albums, its album, plays the first song (Now Playing,
Apple's page); each list's row count comes from its widget (+0x9c). Checks:

1. Frogger: Artists lists All, Calibre and LTJ Bukem, as ref does (the same rows, pixel for
   pixel); stock lists All, Calibre, Doc Scott and Peshay.
2. Frogger: Tone A and Tone B have the same artist, Tone C another; stock: three.
3. Frogger: LTJ Bukem's albums (All, Blue Notes) and Blue Notes' two songs, as ref shows them.
4. Frogger: Now Playing's artist line says LTJ Bukem, as ref's does.

Shots aa_<run>_*.png. Exits 1 on a wrong step.

    tools/emupod/albumartist.py              # all three runs and the checks
    tools/emupod/albumartist.py run frog     # one run (frog, stock or ref): writes aa_frog.json
"""
import json, shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W, OSOS
import itdb as mkdb
import hmcard

mkdb.MHOD_TYPES["albumartist"] = 22
CARDS = {"frog": "aa-card.img", "stock": "aa-card.img", "ref": "aa-ref-card.img"}
loc = lambda name: ":iPod_Control:Music:F00:%s.mp3" % name


def cards():
    """aa-card.img and aa-ref-card.img, from hide-card.img."""
    for name, aa in (("aa-card.img", True), ("aa-ref-card.img", False)):
        a = {"albumartist": "LTJ Bukem", "artist": "Peshay"} if aa else {"artist": "LTJ Bukem"}
        b = {"artist": "Doc Scott", "albumartist": "LTJ Bukem"} if aa else {"artist": "LTJ Bukem"}
        tracks = [
            (101, {"title": "Tone A", **a, "album": "Blue Notes", "genre": "Test", "location": loc("TONEA")},
             2881119, 180000, 128),
            (102, {"title": "Tone B long", **b, "album": "Blue Notes", "genre": "Test", "location": loc("TONEB")},
             28802739, 720000, 320),
            (103, {"title": "Tone C", "artist": "Calibre", "album": "Other", "genre": "Test", "location": loc("TONEA")},
             2881119, 180000, 128),
        ]
        ids = [t[0] for t in tracks]
        db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", [mkdb.mhit(*t) for t in tracks])),
                        mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", ids)]))])
        card = Path(W) / name
        shutil.copyfile(W + "/hide-card.img", card)
        tmp = card.with_suffix(".iTunesDB")
        tmp.write_bytes(db)
        hmcard.mtools(str(card), "mcopy", "-o", str(tmp), "::/iPod_Control/iTunes/iTunesDB")
        tmp.unlink()


def run(tag):
    """One run: what the checks need, into aa_<tag>.json."""
    p = Pod(osos=W + "/osos-frogger.img" if tag == "frog" else OSOS, disk=W + "/" + CARDS[tag])
    rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
    lib = rd(rd(0x43580c) + 0x1c)
    out = {}

    def down_one():
        """Down a row; the list's row count, from the widget the wheel moves (0x9106c, in the wheel
        handler: r5 the list widget, +0x9c its rows; as letters.c reads it)."""
        p.m.hook_start([0x9106c], None, 0)
        p.scroll(1)
        log = p.m.hook_log(); p.m.hook_start([], None, 0)
        return rd(log[-1][2][5] + 0x9c) if log else 0

    def screen(name):
        p.shot(f"aa_{tag}_{name}.png", 1)
        out[name + "_screen"] = p.screen().hex()

    def sel(after_us=1_000_000):
        p.settle(); p.run(500_000)                      # (a key straight after the wheel can go unseen)
        p.press("select", after_us=after_us); p.settle()

    sel(); sel()                                                            # English, Music
    p.scroll(3); sel()                                                      # Songs: Tone A, Tone B long, Tone C
    # Songs' rows as 0x7c460 caches them (lib+0x898, count +0x89c; holdrow.py): item +0x20 the
    # track record, record +0x28 its artist (an index)
    out["artist_ids"] = [rd(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20) + 0x28) for i in range(rd(lib + 0x89c))]
    p.press("menu"); p.settle(); p.scroll(-8)
    p.scroll(1); sel(); screen("artists")                                   # Music > Artists: All, ...
    out["artists"] = down_one(); p.scroll(1); sel()                         # the third row: LTJ Bukem / Doc Scott
    screen("albums")
    out["albums"] = down_one(); sel()                                       # its album (after All)
    screen("songs")
    out["songs"] = down_one(); p.scroll(-1)
    sel(2_000_000)                                                          # play the first song
    if tag == "frog":
        sel(1_500_000)                                                      # the cover page > Apple's
    screen("np")
    (Path(W) / f"aa_{tag}.json").write_text(json.dumps(out))


def body(hexscreen):
    """A screen without the title bar's ends (Frogger's battery percent, the play icon)."""
    s = bytes.fromhex(hexscreen)
    return b"".join(s[y * 160 + 30:y * 160 + 130] for y in range(19)) + s[19 * 160:]


def main():
    cards()
    for tag in CARDS:
        subprocess.run([sys.executable, __file__, "run", tag], check=True)
    r = {tag: json.loads((Path(W) / f"aa_{tag}.json").read_text()) for tag in CARDS}
    frog, stock, ref = r["frog"], r["stock"], r["ref"]
    fails = []

    def check(what, ok, msg=""):
        print("  %-66s %s" % (what, "ok" if ok else "WRONG " + msg))
        if not ok:
            fails.append(what)

    check("1. Frogger: Artists has three rows (All, Calibre, LTJ Bukem)", frog["artists"] == 3, str(frog["artists"]))
    check("1.   the same as ref's, pixel for pixel", body(frog["artists_screen"]) == body(ref["artists_screen"]))
    check("1. stock: four (All, Calibre, Doc Scott, Peshay)", stock["artists"] == 4, str(stock["artists"]))
    a, b, c = frog["artist_ids"]
    check("2. Frogger: Tone A and Tone B one artist, Tone C another", a == b != c, str(frog["artist_ids"]))
    check("2. stock: three artists", len(set(stock["artist_ids"])) == 3, str(stock["artist_ids"]))
    check("3. Frogger: LTJ Bukem's albums: All, Blue Notes", frog["albums"] == 2 and
          body(frog["albums_screen"]) == body(ref["albums_screen"]), "%d rows" % frog["albums"])
    check("3.   Blue Notes: both songs", frog["songs"] == 2 and body(frog["songs_screen"]) == body(ref["songs_screen"]),
          "%d rows" % frog["songs"])
    check("3. stock: Doc Scott's Blue Notes has one song", stock["songs"] == 1, "%d rows" % stock["songs"])
    check("4. Frogger: Now Playing (Apple's page) says LTJ Bukem, as ref", body(frog["np_screen"]) == body(ref["np_screen"]))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"]:
        run(sys.argv[2])
    else:
        main()

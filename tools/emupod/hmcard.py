"""A test card for the hold menu's album and artist actions (holdmenu2.py, nphold.py): seven
songs on two artists and three albums, with track numbers that sort differently from the titles.

    Art One   Alpha   1 Moon   2 Apple  3 Zebra
              Beta    1 Kite   2 Delta
    Art Two   Gamma   1 Echo   2 Bravo

Songs (by title): Apple, Bravo, Delta, Echo, Kite, Moon, Zebra. The audio is the test card's two
tones, taken in turn. make(name, hidden=()) copies music-card.img to name with this iTunesDB
(hidden: titles that get Frogger's hide flag) and returns its path."""
import itdb as mkdb
import shutil, struct, subprocess
from pathlib import Path
from ipod3g import W

SONGS = [("Moon", "Art One", "Alpha", 1), ("Apple", "Art One", "Alpha", 2), ("Zebra", "Art One", "Alpha", 3),
         ("Kite", "Art One", "Beta", 1), ("Delta", "Art One", "Beta", 2),
         ("Echo", "Art Two", "Gamma", 1), ("Bravo", "Art Two", "Gamma", 2)]
BY_TITLE = sorted(s[0] for s in SONGS)
TID = {s[0]: 100 + i for i, s in enumerate(SONGS)}      # track ids, in database order


def partition(card):
    return struct.unpack_from("<I", Path(card).read_bytes()[:512], 0x1be + 24)[0]


def mtools(card, cmd, *args, **kw):
    """An mtools command on the card's data partition, e.g. mtools(card, "mdir", "::/iPod_Control")."""
    return subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", cmd, "-i", f"{card}@@{partition(card) * 512}",
                           *args], check=True, **kw)


def make(name, hidden=(), songs=SONGS):
    """songs: (title, artist, album, track number[, genre, composer]) each; genre "Test" and no composer
    when left out."""
    card = W + "/" + name
    shutil.copy(W + "/music-card.img", card)
    tones = [("TONEA", 2881119, 180000, 128), ("TONEB", 28802739, 720000, 320)]
    mhits = []
    tid = {s[0]: 100 + i for i, s in enumerate(songs)}
    for i, (title, artist, album, n, *more) in enumerate(songs):
        tone = tones[i % 2]
        fields = {"title": title, "artist": artist, "album": album, "genre": more[0] if more else "Test"}
        if len(more) > 1:
            fields["composer"] = more[1]
        fields["location"] = ":iPod_Control:Music:F00:%s.mp3" % tone[0]
        h = bytearray(mkdb.mhit(tid[title], fields, *tone[1:], hidden=title in hidden))
        struct.pack_into("<II", h, 0x2c, n, 3)             # track number, of
        mhits.append(bytes(h))
    ids = [tid[s[0]] for s in songs]
    db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", mhits)), mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", ids)]))])
    tmp = Path(card).with_suffix(".iTunesDB")
    tmp.write_bytes(db)
    mtools(card, "mcopy", "-o", str(tmp), "::/iPod_Control/iTunes/iTunesDB")
    tmp.unlink()
    return card

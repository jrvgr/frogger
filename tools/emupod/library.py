#!/usr/bin/env python3
"""Big library cards, for the checks that have to see what a full iPod costs (perf.py, uidisk.py,
stall.py): the test cards hold two songs, an iPod holds thousands, and a list, a lookup or a cover
that's free on two songs can take seconds on 5,000.

    generated   (the default, and CI's) a made-up library: 5,000 songs on 400 albums by 800 artists,
                40 compilations under "Various Artists", long titles, 20 playlists, a FroggerArt
                cover for 9 albums in 10; seeded, so every run makes the same card
    DIR         your own: DIR/iTunesDB as it is (with FroggerArt, FroggerHidden and FroggerSkips if
                there), e.g. build/device-library copied off your iPod. Private: it stays in
                build/, is never the default, and CI never uses it

The audio is stub MP3s (10 s of tone): the generated library has one per album, your own gets one at
each location its iTunesDB names. Pick the library with FROGGER_LIBRARY (or pytest --library):

    tools/emupod/library.py                               # build/emupod-work/lib-generated-card.img
    tools/emupod/library.py build/device-library          # build/emupod-work/lib-device-library-card.img
    FROGGER_LIBRARY=build/device-library pytest -n auto -m perf

card() makes the card when it's missing or older than what it's made from, and returns its path.
Needs mkcards.py's blank-card.img, and sox, lame and mtools (nix develop .#emu).
"""
import argparse, fcntl, hashlib, os, random, shutil, struct, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
W = ROOT / "build/emupod-work"
sys.path.insert(0, str(HERE))
import itdb  # noqa: E402
import mkart  # noqa: E402

itdb.MHOD_TYPES["albumartist"] = 22
VERSION = 1                     # bump when the generated library changes: cards made before are remade
SONGS, ALBUMS, ARTISTS, COMPILATIONS, PLAYLISTS = 5000, 400, 800, 40, 20
LOC = ":iPod_Control:Music:F%02d:A%03d.mp3"     # one stub per album: 32 MB in all, more than the music cache holds
WORDS = ("amber glass river night north velvet echo paper signal harbour quiet ember silver lantern "
         "orbit meadow cinder hollow static winter summer copper violet golden broken electric "
         "midnight ocean desert garden mirror shadow thunder crystal falling rising distant "
         "secret neon gravity satellite wildfire kingdom horizon parallel weather").split()
ACCENTS = ["Café", "Señor", "Über", "Déjà", "Mötley", "Björk", "Naïve", "Håkan"]


def name(rng, lo, hi):
    w = [rng.choice(WORDS) for _ in range(rng.randint(lo, hi))]
    if rng.random() < 0.08:
        w[0] = rng.choice(ACCENTS)
    return " ".join(x.capitalize() for x in w)


def which():
    """FROGGER_LIBRARY: "generated" (the default) or a directory with an iTunesDB."""
    return os.environ.get("FROGGER_LIBRARY", "generated") or "generated"


def label(lib=None):
    lib = lib or which()
    return "generated" if lib == "generated" else Path(lib).name


def stub():
    """build/emupod-work/STUB.mp3: 10 s of a 64 kbps tone; (path, bytes)."""
    mp3 = W / "STUB.mp3"
    if not mp3.exists():
        tmp = mp3.with_suffix(".tmp")
        subprocess.run(["sh", "-c", "sox -n -r 44100 -c 2 -t wav - synth 10 sine 523 vol 0.3 2>/dev/null"
                        f" | lame --quiet --id3v1-only -b 64 - {tmp}"], check=True)
        tmp.rename(mp3)
    return mp3, mp3.stat().st_size


def generate():
    """(iTunesDB, FroggerArt, {location: None}) for the made-up library."""
    rng = random.Random(1)
    _, size = stub()
    artists = list(dict.fromkeys(name(rng, 1, 3) for _ in range(ARTISTS * 2)))[:ARTISTS]
    albums = []                         # (album artist or None, album, [track artists])
    for i in range(ALBUMS):
        title = name(rng, 1, 4)
        if i % 10 == 3:                 # long ones: past the row's width, and the title bar's
            title = name(rng, 8, 12)
        if i < COMPILATIONS:
            albums.append(("Various Artists", title, rng.sample(artists, 12), True))
        else:
            a = artists[(i - COMPILATIONS) * (ARTISTS - 1) // (ALBUMS - COMPILATIONS)]
            albums.append((None, title, [a], False))
    # every artist on at least one song: the ones no album took get guest spots on compilations
    used = {x for al in albums for x in al[2]}
    spare = [a for a in artists if a not in used]
    for i, a in enumerate(spare):
        albums[i % COMPILATIONS][2].append(a)
    per = [SONGS // ALBUMS] * ALBUMS
    for i in range(SONGS - sum(per)):
        per[i] += 1
    tracks, table, covers = [], [], []
    tid = 1000
    for i, ((aa, album, who, comp), n) in enumerate(zip(albums, per)):
        cover = None
        if i % 10 != 7:                 # 9 albums in 10 have a cover
            seed = i
            cover = len(covers)
            covers.append(mkart.image(lambda x, y, s=seed: ((x * (s % 7 + 1) + y * (s % 5 + 1)) // 18 + s) % 4))
        for k in range(n):
            title = name(rng, 2, 5) if rng.random() > 0.1 else name(rng, 9, 14)
            f = {"title": title, "artist": who[k % len(who)], "album": album, "genre": rng.choice(
                ["Rock", "Electronic", "Jazz", "Pop", "Hip-Hop", "Classical", "Ambient", "Folk"]),
                 "location": LOC % (i % 50, i)}
            if aa:
                f["albumartist"] = aa
            h = bytearray(itdb.mhit(tid, f, size, 10_000, 64))
            h[0x1e] = int(comp)                                       # compilation
            struct.pack_into("<II", h, 0x2c, k + 1, n)               # track number, of
            tracks.append((tid, bytes(h)))
            table.append(cover if cover is not None else 0xffff)
            tid += 1
    ids = [t for t, _ in tracks]
    lists = [itdb.mhyp("iPod", ids)]
    for p in range(PLAYLISTS):
        n = rng.choice([8, 25, 60, 150, 400, 1200])
        lists.append(itdb.mhyp(name(rng, 1, 3) + " Mix", rng.sample(ids, n), master=False))
    db = itdb.mhbd([itdb.mhsd(1, itdb.mhl(b"mhlt", [h for _, h in tracks])), itdb.mhsd(2, itdb.mhl(b"mhlp", lists))])
    files = dict.fromkeys(LOC % (i % 50, i) for i in range(ALBUMS))
    return db, mkart.froggerart(table, covers), files


def locations(db):
    """Every track's location (mhod type 2) in an iTunesDB."""
    out, i = [], 0
    while True:
        i = db.find(b"mhit", i)
        if i < 0:
            return out
        hlen, tlen, nmhod = struct.unpack_from("<III", db, i + 4)
        j = i + hlen
        for _ in range(nmhod):
            if db[j:j + 4] != b"mhod":
                break
            mh, ml, kind = struct.unpack_from("<III", db, j + 4)
            if kind == 2:
                slen = struct.unpack_from("<I", db, j + 0x18 + 4)[0]
                out.append(db[j + 0x28:j + 0x28 + slen].decode("utf-16-le"))
            j += ml
        i += tlen


def source_key(lib):
    if lib == "generated":
        return "generated v%d" % VERSION
    h = hashlib.sha256()
    for n in ("iTunesDB", "FroggerArt", "FroggerHidden", "FroggerSkips"):
        f = Path(lib) / n
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()


def mt(card, *args):
    start = struct.unpack_from("<I", Path(card).read_bytes()[:512], 0x1be + 24)[0]
    subprocess.run([args[0], "-i", f"{card}@@{start * 512}", *args[1:]], check=True, stdout=subprocess.DEVNULL)


def build(lib, out):
    stage = W / ("lib-%s" % label(lib))
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "iTunes").mkdir(parents=True)
    mp3, _ = stub()
    if lib == "generated":
        db, art, files = generate()
        (stage / "iTunes/iTunesDB").write_bytes(db)
        (stage / "iTunes/FroggerArt").write_bytes(art)
    else:
        src = Path(lib)
        if not (src / "iTunesDB").exists():
            sys.exit(f"{src}/iTunesDB: not found (FROGGER_LIBRARY is a folder with your iPod's iTunes files)")
        for n in ("iTunesDB", "FroggerArt", "FroggerHidden", "FroggerSkips"):
            if (src / n).exists():
                shutil.copyfile(src / n, stage / "iTunes" / n)
        files = dict.fromkeys(locations((src / "iTunesDB").read_bytes()))
    for loc in files:
        parts = [p for p in loc.split(":") if p]
        if [x.lower() for x in parts[:2]] != ["ipod_control", "music"]:
            continue
        dest = stage.joinpath("Music", *parts[2:])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.link(mp3, dest)
    tmp = out.with_suffix(".tmp")
    shutil.copyfile(W / "blank-card.img", tmp)             # 256 MB: room for 2,500 stubs
    mt(tmp, "mmd", "::/iPod_Control")
    mt(tmp, "mcopy", "-s", str(stage / "iTunes"), str(stage / "Music"), "::/iPod_Control/")
    shutil.rmtree(stage)
    tmp.rename(out)
    print("wrote %s: %s, %d audio files" % (out, label(lib), len(files)))


def card(lib=None):
    """The card for lib (default FROGGER_LIBRARY), made under a lock when it's missing or stale."""
    lib = lib or which()
    if lib != "generated" and not Path(lib).is_absolute():
        lib = str(ROOT / lib)
    out = W / ("lib-%s-card.img" % label(lib))
    key = out.with_suffix(".key")
    want = source_key(lib)
    with open(W / ".library.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not out.exists() or not key.exists() or key.read_text() != want:
            build(lib, out)
            key.write_text(want)
    return str(out)


def boot(stock=False, lib=None, limit_us=120_000_000):
    """A Pod on the library's card, at the main menu: stock 2.3 (build/fw/osos.img, the loader skipped)
    or the Frogger image. A big database takes a while to load (5,000 songs: about 40 s emulated)."""
    from ipod3g import Pod, OSOS
    p = Pod(osos=OSOS if stock else str(W / "osos-frogger.img"), disk=card(lib), boot_us=0)
    while not any(p.screen()):                              # blank until the database is in
        p.run(1_000_000)
        if p.m.now_us() > limit_us:
            sys.exit("the library's card never got to the Language menu (%d s)" % (limit_us // 1_000_000))
    p.settle()
    p.run(1_000_000)
    p.press("select")                                       # Language: English, the main menu
    p.settle()
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("library", nargs="?", default=None, help='"generated" (default: FROGGER_LIBRARY or generated) or a folder')
    print(card(ap.parse_args().library))

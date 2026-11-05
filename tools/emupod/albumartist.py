#!/usr/bin/env python3
"""Album artists (payload/artist.c) in emupod. Puts a database on a copy of a test card
(`aa-card.img`) where both tones have album artist "LTJ Bukem": Tone A (artist Peshay) with the
album-artist mhod before its artist, Tone B (Doc Scott) after it. Then boots the Frogger image (or
--stock) and shoots Music › Artists, LTJ Bukem's albums and Now Playing (aa_<tag>_*.png).
Stock lists Doc Scott and Peshay; Frogger lists LTJ Bukem › Blue Notes with both songs.

    tools/emupod/albumartist.py [--stock] [--card build/emupod-work/hide-card.img]
"""
import argparse, shutil, struct, subprocess
from pathlib import Path
from ipod3g import Pod, W, OSOS

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--stock", action="store_true")
p.add_argument("--card", default=W + "/hide-card.img")
args = p.parse_args()

# The database: itdb.py's records plus mhod type 22.
import itdb as mkdb
mkdb.MHOD_TYPES["albumartist"] = 22
card = Path(W) / "aa-card.img"
shutil.copyfile(args.card, card)
mbr = card.read_bytes()[:512]
start = struct.unpack_from("<I", mbr, 0x1be + 16 + 8)[0]   # the second partition: the FAT32 volume
loc = lambda name: ":iPod_Control:Music:F00:%s.mp3" % name
tracks = [
    (101, {"title": "Tone A", "albumartist": "LTJ Bukem", "artist": "Peshay", "album": "Blue Notes",
           "genre": "Test", "location": loc("TONEA")}, 2881119, 180000, 128),
    (102, {"title": "Tone B long", "artist": "Doc Scott", "albumartist": "LTJ Bukem", "album": "Blue Notes",
           "genre": "Test", "location": loc("TONEB")}, 28802739, 720000, 320),
]
ids = [t[0] for t in tracks]
db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", [mkdb.mhit(*t) for t in tracks])),
                mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", ids), mkdb.mhyp("Mix", ids, master=False)]))])
tmp = card.with_suffix(".iTunesDB")
tmp.write_bytes(db)
subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{card}@@{start * 512}",
                str(tmp), "::/iPod_Control/iTunes/iTunesDB"], check=True)
tmp.unlink()

tag = "stock" if args.stock else "frog"
pod = Pod(osos=OSOS if args.stock else W + "/osos-frogger.img", disk=str(card))
pod.press("select"); pod.settle(); pod.press("select"); pod.settle()          # Music
pod.scroll(1); pod.press("select"); pod.settle(); pod.shot(f"aa_{tag}_artists.png", 1)
pod.scroll(1); pod.press("select"); pod.settle(); pod.shot(f"aa_{tag}_albums.png", 1)   # the first artist
pod.press("select"); pod.settle(); pod.press("select", after_us=2_000_000)            # All › play the first song
pod.press("select", after_us=1_500_000); pod.shot(f"aa_{tag}_np.png", 1)            # Apple's page: the artist line
print("wrote", ", ".join(f"aa_{tag}_{n}.png" for n in ("artists", "albums", "np")), "in", W)

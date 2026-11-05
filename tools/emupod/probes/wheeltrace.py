"""What scrolling a list runs (for jump by letter). Builds letters-card.img: 60 songs whose titles
and artists start with letters spread over the alphabet (all on TONEA.mp3), opens Music > Songs
and records three wheel clicks down: every bytecode step, every native method (entered from the
VM's dispatcher, lr 0xa18a8) and every function entry that doesn't also run while idle.
Writes wheeltrace.json ({"scroll": [[t, pc, r0, r1, r2, r3, lr, vm_pc], ...]}) and wt_*.png.

    wheeltrace.py [--card-only]"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import json, shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W

card = W + "/letters-card.img"
WORDS = ["Aerial", "Alpine", "Amber", "Bassline", "Blue Notes", "Breaks", "Circles", "Cold Front",
         "Daybreak", "Deep Space", "Echoes", "Elevate", "Fade", "Fractal", "Glide", "Gravity", "Horizon",
         "Hydro", "Inner City", "Island", "Jazz Note", "Jungle", "Kinetic", "Lagoon", "Liquid", "Lunar",
         "Midnight", "Mirage", "Nebula", "Nightfall", "Ocean", "Orbit", "Pulse", "Quasar", "Rainfall",
         "Reflex", "Rollers", "Silhouette", "Skyline", "Solar", "Spectrum", "Tidal", "Timeless",
         "Undertow", "Urban", "Velvet", "Vortex", "Warmth", "Waves", "Xenon", "Yearning", "Zenith",
         "Zero G", "Atlantis", "Bloom", "Cascade", "Drift", "Ember", "Flow", "Glow"]
ARTISTS = ["Alix Perez", "Bukem", "Calibre", "Doc Scott", "Etherwood", "Fracture", "Goldie",
           "Hybris", "Intense", "Jubei", "Klute", "Lenzman", "Marcus Intalex", "Nookie", "Omni Trio",
           "Peshay", "Qumulus", "Random Movement", "Seba", "Tokyo Prose", "Utah Jazz", "Villem",
           "Wax Doctor", "Xtrah", "Youngsta", "Zero T"]

import itdb as mkdb
shutil.copy(W + "/music-card.img", card)
tracks = [(200 + i, {"title": w, "artist": ARTISTS[i % len(ARTISTS)], "album": "Album %d" % (i % 7),
                     "genre": "Test", "location": ":iPod_Control:Music:F00:TONEA.mp3"}, 2881119, 180000, 128)
          for i, w in enumerate(WORDS)]
db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", [mkdb.mhit(*t) for t in tracks])),
                mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", [t[0] for t in tracks])]))])
mbr = Path(card).read_bytes()[:512]
start = struct.unpack_from("<I", mbr, 0x1be + 24)[0]
tmp = Path(card).with_suffix(".iTunesDB"); tmp.write_bytes(db)
subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{card}@@{start * 512}",
                str(tmp), "::/iPod_Control/iTunes/iTunesDB"], check=True)
tmp.unlink()
print("wrote", card, len(tracks), "songs")
if "--card-only" in sys.argv:
    sys.exit()

VM = 0x9bab8
pro = [int(x, 16) for x in open(W + "/prologues.txt")]
p = Pod(osos=W + "/osos-frogger.img", disk=card)
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()       # Music > Songs
p.shot("wt_songs.png", 1)
p.m.hook_start(pro, None, 0, True); p.run(1_000_000)
idle = p.m.hook_counts(); p.m.hook_start([], None, 0)
pro = [a for a in pro if idle.get(a, 0) == 0]
p.m.hook_start(pro + [VM], None, 0)
p.scroll(3); p.settle()
log = p.m.hook_log(); p.m.hook_start([], None, 0)
p.shot("wt_scrolled.png", 1)
print(len(log), "entries")
json.dump({"scroll": [[t, pc, *r[:4], r[14], r[0] if pc == VM else 0] for t, pc, r, _ in log]},
          open(W + "/wheeltrace.json", "w"))

#!/usr/bin/env python3
"""Make the test cards the emupod scripts boot, from Apple's ipsw, into build/emupod-work:

    blank-card.img     emupod's tools/synth_card.py: an MBR, the ipsw's firmware partition, an empty FAT32
    music-card.img     plus two sine-tone MP3s (TONEA 3 min 128 kbps, TONEB 12 min 320 kbps) and an iTunesDB:
                       Tone A, Tone B long, the master playlist and "Mix"
    hide-card.img      the same, Tone A by "Hidden Artist" on "Hidden Album" with Frogger's hide flag
    art-card.img       hide-card.img with a FroggerArt of test pictures (mkart.py)
    resume-card.img    music-card.img plus a 25-minute "Long Mix" (mkresume.py), and resume-bm-card.img with
                       its bookmark at 2:00
    lib-generated-card.img  a big made-up library: 5,000 songs, covers (library.py; the perf, uidisk
                       and stall checks)

Most scripts copy one of these and write their own iTunesDB (hmcard.py). The tones' sizes are the ones
the scripts' iTunesDBs give (lame with an ID3v1 tag), so every card agrees. Needs mkfs.fat, mtools, sox
and lame on PATH (nix develop .#emu).

    tools/emupod/mkcards.py [--ipsw firmware/iPod_2.2.3.ipsw]
"""
import argparse, shutil, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "build/emupod-work"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mkresume import mhit, mhyp, mhsd, mhl, mhbd       # noqa: E402  the iTunesDB records

TONES = [("TONEA", 180, 440, 128, 2881119), ("TONEB", 720, 660, 320, 28802739)]   # name, s, Hz, kbps, bytes


def run(*cmd, **kw):
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def fat(card):
    start = struct.unpack_from("<I", Path(card).read_bytes()[:512], 0x1be + 16 + 8)[0]
    return f"{card}@@{start * 512}"


def tones():
    for name, secs, hz, kbps, size in TONES:
        mp3 = W / f"{name}.mp3"
        if not mp3.exists():
            run("sh", "-c", f"sox -n -r 44100 -c 2 -t wav - synth {secs} sine {hz} vol 0.3 2>/dev/null"
                f" | lame --quiet --id3v1-only --tt '{name}' -b {kbps} - {mp3}")
        if mp3.stat().st_size != size:
            sys.exit(f"{mp3}: {mp3.stat().st_size} bytes, the iTunesDBs say {size} (another lame?)")


def database(hide):
    artist, album = ("Hidden Artist", "Hidden Album") if hide else ("Test Artist", "Test Album")
    tracks = [
        (101, {"title": "Tone A", "artist": artist, "album": album, "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEA.mp3"}, TONES[0][4], 180000, 128),
        (102, {"title": "Tone B long", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEB.mp3"}, TONES[1][4], 720000, 320),
    ]
    records = []
    for t in tracks:
        rec = bytearray(mhit(*t))
        struct.pack_into("<I", rec, 0x6c, 0)
        if hide and t[0] == 101:
            rec[0x98:0x9c] = b"HIDE"                        # Frogger's hide flag (payload/hide.h)
        records.append(bytes(rec))
    ids = [t[0] for t in tracks]
    return mhbd([mhsd(1, mhl(b"mhlt", records)),
                 mhsd(2, mhl(b"mhlp", [mhyp("iPod", ids), mhyp("Mix", ids, master=False)]))])


def music_card(blank, out, hide):
    shutil.copyfile(blank, out)
    img = fat(out)
    for d in ("iPod_Control", "iPod_Control/iTunes", "iPod_Control/Music", "iPod_Control/Music/F00"):
        run("mmd", "-i", img, "::/" + d)
    db = W / (out.stem + "-iTunesDB")
    db.write_bytes(database(hide))
    run("mcopy", "-o", "-i", img, db, "::/iPod_Control/iTunes/iTunesDB")
    db.unlink()
    for name, *_ in TONES:
        run("mcopy", "-o", "-i", img, W / f"{name}.mp3", f"::/iPod_Control/Music/F00/{name}.mp3")
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ipsw", default=str(ROOT / "firmware/iPod_2.2.3.ipsw"))
    a = ap.parse_args()
    W.mkdir(parents=True, exist_ok=True)
    blank = W / "blank-card.img"
    run(sys.executable, ROOT / "third_party/emupod/tools/synth_card.py", a.ipsw, blank)
    tones()
    music_card(blank, W / "music-card.img", hide=False)
    music_card(blank, W / "hide-card.img", hide=True)
    here = Path(__file__).resolve().parent
    run(sys.executable, here / "mkart.py")
    run(sys.executable, here / "mkresume.py")
    run(sys.executable, here / "mkresume.py", "--bookmark", "120000", "--out", W / "resume-bm-card.img")
    run(sys.executable, here / "library.py", "generated")


if __name__ == "__main__":
    main()

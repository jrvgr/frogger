#!/usr/bin/env python3
"""A test card for Resume Mixes (payload/resume.c): music-card.img's two tones plus
"Long Mix", a 25-minute sine-tone MP3 (32 kbps mono, made with sox and lame), in an iTunesDB of
three tracks. Optionally gives Long Mix a bookmark in its mhit (+0x6c), the way Crate would
carry one over from the Play Counts file.

    tools/emupod/mkresume.py [--bookmark MS] [--out build/emupod-work/resume-card.img]
"""
import argparse, shutil, struct, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "build/emupod-work"
MHOD_TYPES = {"title": 1, "location": 2, "album": 3, "artist": 4, "genre": 5}
LONG_MS = 25 * 60 * 1000


def mhod(kind, text):
    s = text.encode("utf-16-le")
    body = struct.pack("<IIII", 1, len(s), 0, 0) + s
    return struct.pack("<4sIII8x", b"mhod", 0x18, 0x18 + len(body), MHOD_TYPES[kind]) + body


def mhit(tid, fields, size, ms, bitrate, bookmark=0, dbid=None):
    mh = b"".join(mhod(k, v) for k, v in fields.items())
    h = bytearray(0x9c)
    struct.pack_into("<4sIIIII", h, 0, b"mhit", 0x9c, 0x9c + len(mh), len(fields), tid, 1)
    struct.pack_into("<I", h, 0x18, 0x4d503320)          # 'MP3 '
    h[0x1c] = 1; h[0x1d] = 1
    struct.pack_into("<IIIIIII", h, 0x24, size, ms, 1, 1, 2026, bitrate, 44100 << 16)
    struct.pack_into("<I", h, 0x6c, bookmark)            # bookmark time, ms
    struct.pack_into("<Q", h, 0x70, 0x1000 + tid if dbid is None else dbid)   # the dbid
    return bytes(h) + mh


def mhip(tid, pos):
    body = struct.pack("<4sIIIII", b"mhod", 0x18, 0x2c, 100, 0, 0) + struct.pack("<I16x", pos)
    h = bytearray(0x4c)
    struct.pack_into("<4sIIIIII", h, 0, b"mhip", 0x4c, 0x4c + len(body), 1, 0, 0, tid)
    return bytes(h) + body


def mhyp(name, tids, master=True, pid=None):
    t = mhod("title", name)
    items = b"".join(mhip(tid, i + 1) for i, tid in enumerate(tids))
    h = bytearray(0x6c)
    struct.pack_into("<4sIIIII", h, 0, b"mhyp", 0x6c, 0x6c + len(t) + len(items), 1, len(tids), int(master))
    struct.pack_into("<Q", h, 0x1c, pid if pid is not None else 0xabcdef if master else 0xabcdf0)
    struct.pack_into("<H", h, 0x28, 1)
    return bytes(h) + t + items


def mhsd(kind, body):
    h = bytearray(0x60); struct.pack_into("<4sIII", h, 0, b"mhsd", 0x60, 0x60 + len(body), kind)
    return bytes(h) + body


def mhl(tag, items):
    h = bytearray(0x5c); struct.pack_into("<4sII", h, 0, tag, 0x5c, len(items))
    return bytes(h) + b"".join(items)


def mhbd(sds):
    body = b"".join(sds)
    h = bytearray(0x68)
    struct.pack_into("<4sIIIII", h, 0, b"mhbd", 0x68, 0x68 + len(body), 1, 9, len(sds))
    struct.pack_into("<Q", h, 0x18, 0x1122334455667788)
    struct.pack_into("<H", h, 0x20, 2)
    return bytes(h) + body


def nix(pkgs, *cmd):
    subprocess.run(["nix", "shell", *("nixpkgs#" + p for p in pkgs), "-c", *cmd], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bookmark", type=int, default=0)
    ap.add_argument("--out", default=str(W / "resume-card.img"))
    args = ap.parse_args()
    mp3 = W / "TONEL.mp3"
    if not mp3.exists():
        nix(["sox", "lame"], "sh", "-c", f"sox -n -r 44100 -c 1 -t wav - synth {LONG_MS // 1000} sine 330 vol 0.3"
            f" | lame --quiet -b 32 -m m - {mp3}")
    shutil.copyfile(W / "music-card.img", args.out)
    start = struct.unpack_from("<I", Path(args.out).read_bytes()[:512], 0x1be + 16 + 8)[0]
    img = f"{args.out}@@{start * 512}"
    tracks = [
        (101, {"title": "Tone A", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEA.mp3"}, 2881119, 180000, 128),
        (102, {"title": "Tone B long", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEB.mp3"}, 28802739, 720000, 320),
        (103, {"title": "Long Mix", "artist": "Test DJ", "album": "Mixes", "genre": "Test",
               "location": ":iPod_Control:Music:F00:TONEL.mp3"}, mp3.stat().st_size, LONG_MS, 32, args.bookmark),
    ]
    ids = [t[0] for t in tracks]
    db = mhbd([mhsd(1, mhl(b"mhlt", [mhit(*t) for t in tracks])),
               mhsd(2, mhl(b"mhlp", [mhyp("iPod", ids), mhyp("Mix", ids, master=False)]))])
    tmp = W / "resume-iTunesDB"
    tmp.write_bytes(db)
    nix(["mtools"], "mcopy", "-o", "-i", img, str(tmp), "::/iPod_Control/iTunes/iTunesDB")
    nix(["mtools"], "mcopy", "-o", "-i", img, str(mp3), "::/iPod_Control/Music/F00/TONEL.mp3")
    tmp.unlink()
    print(f"wrote {args.out}: Long Mix {LONG_MS // 60000} min, bookmark {args.bookmark} ms")

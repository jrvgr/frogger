#!/usr/bin/env python3
"""Write a FroggerArt file (docs/file-formats.md) with test covers and put it on a copy of a test
card, for the cover page in emupod. Crate (or tools/coverart.py) writes the real one. Version 2
(the default) names each song of the card's iTunesDB by key; --v1 writes version 1, a cover per
track position. Song i of the database gets cover i % the number of covers.

    tools/emupod/mkart.py [--card build/emupod-work/hide-card.img] [--out build/emupod-work/art-card.img]
                          [--covers N] [--v1]
"""
import argparse, shutil, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from podinfo import Database  # noqa: E402

SIZE = 72
ROW = (SIZE // 4 + 3) & ~3
BYTES = ROW * SIZE
PATTERNS = [lambda x, y: (x + y) * 4 // (2 * SIZE),                  # diagonal gradient
            lambda x, y: 3 * (((x // 7) + (y // 7)) & 1),            # checkerboard
            lambda x, y: 3 * ((y // 6) & 1),                         # stripes
            lambda x, y: 3 if (x - 36) ** 2 + (y - 36) ** 2 < 600 else 0,   # a disc
            lambda x, y: x * 4 // SIZE]                              # left to right
# The default card's covers: track 1 the gradient, track 2 the checkerboard (artplay.py checks the
# screen against these).
COVERS = PATTERNS[:2]


def image(level):
    """level(x, y) -> 0..3 (3 = black), as BMap rows."""
    px = bytearray(BYTES)
    for y in range(SIZE):
        for x in range(SIZE):
            px[y * ROW + x // 4] |= level(x, y) << (6 - 2 * (x & 3))
    return bytes(px)


def froggerart_v1(table, images):
    head = struct.pack("<IHHIIII", 0x41475246, 1, SIZE, len(table), len(images), BYTES, 0)
    t = b"".join(struct.pack("<H", i) for i in table)
    t += bytes(-(len(head) + len(t)) % 4)
    return head + t + b"".join(images)


def froggerart(entries, images):
    """Version 2: entries are (podinfo.Key, image index)."""
    head = struct.pack("<IHHIIII", 0x41475246, 2, SIZE, len(entries), len(images), BYTES, 0)
    return head + b"".join(k.pack() + struct.pack("<HH", i, 0) for k, i in entries) + b"".join(images)


def mtools(card, *args, **kw):
    start = struct.unpack_from("<I", Path(card).read_bytes()[:512], 0x1be + 16 + 8)[0]   # the FAT32 volume
    return subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", args[0], "-i", f"{card}@@{start * 512}", *args[1:]],
                          check=True, **kw)


def put(card, v1=False, covers=2, table=None):
    """FroggerArt on `card` for its iTunesDB: song i gets cover table[i] (default i % covers)."""
    tmp = Path(card).with_suffix(".iTunesDB")
    mtools(card, "mcopy", "-o", "::/iPod_Control/iTunes/iTunesDB", str(tmp))
    db = Database(str(tmp))
    tmp.unlink()
    imgs = [image(PATTERNS[i % len(PATTERNS)]) for i in range(covers)]
    table = table or [i % covers for i in range(len(db.tracks))]
    data = froggerart_v1(table, imgs) if v1 else froggerart([(db.key(t), table[t.pos]) for t in db.tracks], imgs)
    tmp = Path(card).with_suffix(".FroggerArt")
    tmp.write_bytes(data)
    mtools(card, "mcopy", "-o", str(tmp), "::/iPod_Control/iTunes/FroggerArt")
    tmp.unlink()
    return len(db.tracks), data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card", default=str(ROOT / "build/emupod-work/hide-card.img"))
    p.add_argument("--out", default=str(ROOT / "build/emupod-work/art-card.img"))
    p.add_argument("--covers", type=int, default=2)
    p.add_argument("--v1", action="store_true", help="version 1, by track position")
    args = p.parse_args()
    shutil.copyfile(args.card, args.out)
    n, data = put(args.out, args.v1, args.covers)
    print(f"wrote {args.out}: FroggerArt v{1 if args.v1 else 2} {len(data)} bytes, {n} tracks, {args.covers} images")

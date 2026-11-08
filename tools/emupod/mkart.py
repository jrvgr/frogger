#!/usr/bin/env python3
"""Write a FroggerArt file (payload/nowplaying.h) with test covers, one per track position, and
put it on a copy of a test card, for the cover page in emupod. Crate writes the real one.

    tools/emupod/mkart.py [--card build/emupod-work/hide-card.img] [--out build/emupod-work/art-card.img]
"""
import argparse, os, shutil, struct, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIZE = 72
ROW = (SIZE // 4 + 3) & ~3
BYTES = ROW * SIZE
# The test covers, as level(x, y) -> 0..3 (3 = black): track 1 a diagonal gradient, track 2 a
# checkerboard (artplay.py checks the screen against these).
COVERS = [lambda x, y: (x + y) * 4 // (2 * SIZE),
          lambda x, y: 3 * (((x // 7) + (y // 7)) & 1)]


def image(level):
    """level(x, y) -> 0..3 (3 = black), as BMap rows."""
    px = bytearray(BYTES)
    for y in range(SIZE):
        for x in range(SIZE):
            px[y * ROW + x // 4] |= level(x, y) << (6 - 2 * (x & 3))
    return bytes(px)


def froggerart(table, images):
    head = struct.pack("<IHHIIII", 0x41475246, 1, SIZE, len(table), len(images), BYTES, 0)
    t = b"".join(struct.pack("<H", i) for i in table)
    t += bytes(-(len(head) + len(t)) % 4)
    return head + t + b"".join(images)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card", default=str(ROOT / "build/emupod-work/hide-card.img"))
    p.add_argument("--out", default=str(ROOT / "build/emupod-work/art-card.img"))
    p.add_argument("--tracks", type=int, default=2)
    args = p.parse_args()
    covers = [image(level) for level in COVERS]
    data = froggerart([i % len(covers) for i in range(args.tracks)], covers)
    shutil.copyfile(args.card, args.out)
    mbr = Path(args.out).read_bytes()[:512]
    start = struct.unpack_from("<I", mbr, 0x1be + 16 + 8)[0]      # the second partition: the FAT32 volume
    tmp = Path(args.out).with_suffix(".FroggerArt")
    tmp.write_bytes(data)
    subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{args.out}@@{start * 512}",
                    str(tmp), "::/iPod_Control/iTunes/FroggerArt"], check=True)
    os.remove(tmp)
    print(f"wrote {args.out}: FroggerArt {len(data)} bytes, {args.tracks} tracks, {len(covers)} images")

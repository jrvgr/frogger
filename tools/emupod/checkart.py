#!/usr/bin/env python3
"""Check a FroggerArt file the way payload/art.c reads it (version 2 by key, version 1 by
position), and draw its covers into a PNG (in the LCD's four greys) to look at the dithering.

    tools/emupod/checkart.py FroggerArt [--itunesdb iTunesDB | --tracks N] [--png covers.png]
"""
import argparse, struct, sys, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from podinfo import Database, FroggerArt  # noqa: E402

GREYS = [(0xc6, 0xd0, 0xc0), (0x8c, 0x95, 0x88), (0x50, 0x56, 0x4e), (0x10, 0x12, 0x10)]    # 0 = background … 3 = black


def png(rows, w, h):
    raw = b"".join(b"\0" + bytes(c for px in r for c in px) for r in rows)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("file")
p.add_argument("--itunesdb", help="the database it's for: which songs get which cover")
p.add_argument("--tracks", type=int, help="version 1: the database's track count (the payload checks they match)")
p.add_argument("--png")
a = p.parse_args()
art = FroggerArt(open(a.file, "rb").read())
S, ROW, BYTES = art.SIZE, art.ROW, art.BYTES
if art.version == 1:
    if a.tracks is not None:
        assert len(art.table) == a.tracks, f"{len(art.table)} positions for {a.tracks} tracks"
    assert all(i == art.NONE or i < len(art.images) for i in art.table)
    print(f"ok: version 1, {len(art.table)} tracks, {len(art.images)} images, "
          f"{sum(i != art.NONE for i in art.table)} tracks with a cover")
else:
    assert all(i < len(art.images) for _, i in art.table)
    print(f"ok: version 2, {len(art.table)} songs, {len(art.images)} images")
if a.itunesdb:
    db = Database(a.itunesdb)
    covers = art.covers(db)
    print(f"for {a.itunesdb}: {len(covers)} of {len(db.tracks)} songs have a cover")
    for t in db.tracks:
        print("  %d\t%s\t%s" % (t.id, covers.get(t.pos, "-"), t.title))
if a.png and art.images:
    per, scale = 8, 2
    n_img = len(art.images)
    cols, lines = min(per, n_img), (n_img + per - 1) // per
    W, H = cols * (S + 4) * scale, lines * (S + 4) * scale
    canvas = [[GREYS[0]] * W for _ in range(H)]
    for n, img in enumerate(art.images):
        ox, oy = (n % per) * (S + 4) * scale, (n // per) * (S + 4) * scale
        for y in range(S):
            for x in range(S):
                level = (img[y * ROW + x // 4] >> (6 - 2 * (x & 3))) & 3
                for dy in range(scale):
                    for dx in range(scale):
                        canvas[oy + y * scale + dy][ox + x * scale + dx] = GREYS[level]
    open(a.png, "wb").write(png(canvas, W, H))
    print("wrote", a.png)

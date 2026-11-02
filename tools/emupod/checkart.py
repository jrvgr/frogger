#!/usr/bin/env python3
"""Check a FroggerArt file the way payload/art.c reads it, and draw its covers into a PNG
(in the LCD's four greys) to look at the dithering.

    tools/emupod/checkart.py FroggerArt [--tracks N] [--png covers.png]
"""
import argparse, struct, zlib

SIZE, MAGIC, NONE = 72, 0x41475246, 0xffff
ROW = (SIZE // 4 + 3) & ~3
BYTES = ROW * SIZE
GREYS = [(0xc6, 0xd0, 0xc0), (0x8c, 0x95, 0x88), (0x50, 0x56, 0x4e), (0x10, 0x12, 0x10)]    # 0 = background … 3 = black


def png(rows, w, h):
    raw = b"".join(b"\0" + bytes(c for px in r for c in px) for r in rows)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("file")
p.add_argument("--tracks", type=int, help="the database's track count (the payload checks they match)")
p.add_argument("--png")
a = p.parse_args()
d = open(a.file, "rb").read()
magic, version, size, positions, images, image_bytes, _ = struct.unpack_from("<IHHIIII", d, 0)
assert magic == MAGIC and version == 1 and size == SIZE and image_bytes == BYTES, (hex(magic), version, size, image_bytes)
if a.tracks is not None:
    assert positions == a.tracks, f"{positions} positions for {a.tracks} tracks"
table = struct.unpack_from(f"<{positions}H", d, 24)
off = (24 + 2 * positions + 3) & ~3
assert len(d) == off + images * BYTES, f"{len(d)} bytes, expected {off + images * BYTES}"
assert all(i == NONE or i < images for i in table)
used = sorted({i for i in table if i != NONE})
print(f"ok: {positions} tracks, {images} images ({len(used)} used), {sum(i != NONE for i in table)} tracks with a cover")
if a.png and images:
    per, scale = 8, 2
    cols, lines = min(per, images), (images + per - 1) // per
    W, H = cols * (SIZE + 4) * scale, lines * (SIZE + 4) * scale
    canvas = [[GREYS[0]] * W for _ in range(H)]
    for n in range(images):
        img = d[off + n * BYTES:off + (n + 1) * BYTES]
        ox, oy = (n % per) * (SIZE + 4) * scale, (n // per) * (SIZE + 4) * scale
        for y in range(SIZE):
            for x in range(SIZE):
                level = (img[y * ROW + x // 4] >> (6 - 2 * (x & 3))) & 3
                for dy in range(scale):
                    for dx in range(scale):
                        canvas[oy + y * scale + dy][ox + x * scale + dx] = GREYS[level]
    open(a.png, "wb").write(png(canvas, W, H))
    print("wrote", a.png)

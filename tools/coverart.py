#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["pillow"]
# ///
"""Write the covers for Frogger's cover page (FroggerArt) without Crate.

Finds a picture for each song on the mounted iPod, scales it to fill 72×72, stretches the
levels and dithers it to the LCD's four greys (Floyd–Steinberg), and writes
iPod_Control/iTunes/FroggerArt. Where a song's picture comes from, first match wins:

  1. --map FILE: pictures picked by hand, one line each: what, a tab (or " = "), the picture.
     What is a track id (podinfo.py IPOD tracks), "Artist - Album" or "Album".
  2. The picture embedded in the song on the iPod (ID3 APIC in MP3s, covr in AAC/M4A), or in
     another song of its album.
  3. --library DIR: your music folders. A song there with the same album and artist (from its
     tags) lends its embedded picture, or the cover.jpg / folder.jpg / front.jpg (or the only
     picture) in its folder.
  4. --covers DIR: a folder of pictures named "Album.jpg" or "Artist - Album.jpg" (.png ...).

Needs Python 3 and Pillow; any OS. `uv run tools/coverart.py ...` installs Pillow by itself,
nix develop has it, or pip install pillow.

    tools/coverart.py /Volumes/IPOD                         # or E:\\ on Windows, /media/... on Linux
    tools/coverart.py /Volumes/IPOD --library ~/Music       # --library, --covers can repeat
    tools/coverart.py /Volumes/IPOD --map covers.txt
    tools/coverart.py /Volumes/IPOD --png covers.png        # also draw them, to look at the dithering
    tools/coverart.py /Volumes/IPOD --out FroggerArt        # write it somewhere else

Run it again after every sync: the file is indexed by track position, so it is only right for
the iTunesDB it was made from (the cover page shows a refresh arrow otherwise). Layout:
payload/nowplaying.h; tools/emupod/checkart.py checks a file the way the payload reads it."""

import argparse
import io
import os
import struct
import sys

try:
    from PIL import Image, ImageOps
except ImportError:
    raise SystemExit("coverart.py needs Pillow: pip install pillow (or run it in nix develop)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from podinfo import Database, itunes  # noqa: E402

SIZE, MAGIC, VERSION, NONE = 72, 0x41475246, 1, 0xffff
ROW = (SIZE // 4 + 3) & ~3
BYTES = ROW * SIZE
GREYS = [(0xc6, 0xd0, 0xc0), (0x8c, 0x95, 0x88), (0x50, 0x56, 0x4e), (0x10, 0x12, 0x10)]    # 0 = background … 3 = black
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")
AUDIO_EXTS = (".mp3", ".m4a", ".m4p", ".m4b", ".aac", ".mp4")
FOLDER_NAMES = ("cover", "folder", "front", "album", "albumart", "albumartsmall")


# Tags and embedded pictures

class Tags:
    def __init__(self):
        self.album = self.artist = self.album_artist = ""
        self.picture = None


def id3_tags(f, want_picture):
    """An MP3's ID3v2 tag: album, artists and the front cover (or else the first picture)."""
    tags = Tags()
    head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return tags
    major, flags = head[3], head[5]
    tag = f.read(synchsafe(head[6:10]))
    if flags & 0x80 and major < 4:                  # unsynchronised tag (2.4 does it per frame)
        tag = tag.replace(b"\xff\x00", b"\xff")
    pics, off = [], 0
    if flags & 0x40 and major >= 3:                 # extended header
        off = synchsafe(tag[0:4]) if major == 4 else 4 + struct.unpack(">I", tag[0:4])[0]
    idlen, hlen = (3, 6) if major == 2 else (4, 10)
    text = {b"TALB": "album", b"TAL": "album", b"TPE1": "artist", b"TP1": "artist",
            b"TPE2": "album_artist", b"TP2": "album_artist"}
    while off + hlen <= len(tag) and tag[off] != 0:
        fid = tag[off:off + idlen]
        if major == 2:
            fsize = int.from_bytes(tag[off + 3:off + 6], "big")
        elif major == 4:
            fsize = synchsafe(tag[off + 4:off + 8])
        else:
            fsize = struct.unpack(">I", tag[off + 4:off + 8])[0]
        body = tag[off + hlen:off + hlen + fsize]
        if major == 4 and len(tag) > off + 9:
            fflags = tag[off + 9]
            if fflags & 0x01:                       # data length indicator
                body = body[4:]
            if fflags & 0x02:
                body = body.replace(b"\xff\x00", b"\xff")
        if fid in text and body:
            setattr(tags, text[fid], id3_text(body))
        elif fid in (b"APIC", b"PIC") and want_picture:
            pic = apic(body, major)
            if pic:
                pics.append(pic)
        off += hlen + fsize
    pics.sort(key=lambda p: p[0] != 3)              # picture type 3: front cover
    tags.picture = pics[0][1] if pics else None
    return tags


def synchsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def id3_text(body):
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(body[0], "latin-1")
    return body[1:].decode(codec, "replace").split("\0")[0].strip()


def apic(body, major):
    if len(body) < 4:
        return None
    enc = body[0]
    if major == 2:                                  # PIC: a 3-letter format, not a MIME type
        i = 4
    else:
        i = body.index(b"\0", 1) + 1
    kind = body[i]
    i += 1
    if enc in (1, 2):                               # UTF-16 description: ends at an aligned 00 00
        while i + 1 < len(body) and body[i:i + 2] != b"\0\0":
            i += 2
        i += 2
    else:
        i = body.index(b"\0", i) + 1
    return kind, body[i:]


def mp4_tags(f, want_picture):
    """An MP4/M4A's moov.udta.meta.ilst: album, artists and the first covr picture."""
    tags = Tags()
    end = f.seek(0, os.SEEK_END)
    ilst = mp4_find(f, 0, end, [b"moov", b"udta", b"meta", b"ilst"])
    if not ilst:
        return tags
    fields = {b"\xa9alb": "album", b"\xa9ART": "artist", b"aART": "album_artist"}
    for name, start, stop in mp4_boxes(f, *ilst):
        if name in fields or (name == b"covr" and want_picture):
            data = mp4_find(f, start, stop, [b"data"])
            if not data:
                continue
            f.seek(data[0] + 8)                     # data: type, locale
            value = f.read(data[1] - data[0] - 8)
            if name == b"covr":
                tags.picture = value
            else:
                setattr(tags, fields[name], value.decode("utf-8", "replace").strip())
    return tags


def mp4_boxes(f, start, end):
    """(name, body start, end) for each box from start to end."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, name = struct.unpack(">I4s", f.read(8))
        hlen = 8
        if size == 1:
            size, hlen = struct.unpack(">Q", f.read(8))[0], 16
        elif size == 0:
            size = end - pos
        if size < hlen:
            return
        yield name, pos + hlen + (4 if name == b"meta" else 0), pos + size     # meta is a full box
        pos += size


def mp4_find(f, start, end, path):
    for name, body, stop in mp4_boxes(f, start, end):
        if name == path[0]:
            return (body, stop) if len(path) == 1 else mp4_find(f, body, stop, path[1:])
    return None


def read_tags(path, want_picture=True):
    try:
        with open(path, "rb") as f:
            magic = f.read(12)
            f.seek(0)
            if magic[:3] == b"ID3":
                return id3_tags(f, want_picture)
            if magic[4:8] == b"ftyp":
                return mp4_tags(f, want_picture)
    except (OSError, ValueError, IndexError, struct.error):
        pass
    return Tags()


def embedded(path):
    return read_tags(path).picture


# Pictures to the LCD

def dither(data):
    """Picture bytes → a FroggerArt image (BMap rows, 2 bits, 3 = black), or None if it won't open."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("L")
    except Exception:
        return None
    img = ImageOps.fit(img, (SIZE, SIZE), Image.LANCZOS)          # fill the square, crop the rest
    px = [float(v) for v in img.tobytes()]           # "L": one byte a pixel (getdata goes in Pillow 14)
    ranked = sorted(px)
    lo, hi = ranked[len(ranked) // 100], ranked[-1 - len(ranked) // 100]
    if hi - lo < 64:                                # hardly any contrast: stretching would only add noise
        lo, hi = 0.0, 255.0
    span = hi - lo
    level = [min(max((v - lo) / span, 0.0), 1.0) * 3 for v in px]  # 0 = black … 3 = white
    out = bytearray(BYTES)
    for y in range(SIZE):
        for x in range(SIZE):
            i = y * SIZE + x
            q = min(max(round(level[i]), 0), 3)
            err = level[i] - q
            for dx, dy, w in ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < SIZE and ny < SIZE:
                    level[ny * SIZE + nx] += err * w / 16
            out[y * ROW + x // 4] |= (3 - q) << (6 - 2 * (x & 3))
    return bytes(out)


def froggerart(table, images):
    head = struct.pack("<IHHIIII", MAGIC, VERSION, SIZE, len(table), len(images), BYTES, 0)
    t = b"".join(struct.pack("<H", i) for i in table)
    t += bytes(-(len(head) + len(t)) % 4)
    return head + t + b"".join(images)


def preview(images, path):
    per, scale = 8, 2
    cols, lines = min(per, len(images)), (len(images) + per - 1) // per
    sheet = Image.new("RGB", (cols * (SIZE + 4) * scale, lines * (SIZE + 4) * scale), GREYS[0])
    for n, img in enumerate(images):
        cover = Image.new("RGB", (SIZE, SIZE))
        cover.putdata([GREYS[(img[y * ROW + x // 4] >> (6 - 2 * (x & 3))) & 3]
                       for y in range(SIZE) for x in range(SIZE)])
        sheet.paste(cover.resize((SIZE * scale, SIZE * scale), Image.NEAREST),
                    ((n % per) * (SIZE + 4) * scale, (n // per) * (SIZE + 4) * scale))
    sheet.save(path)


# Where pictures come from

def key(*parts):
    return " - ".join(p.casefold().strip() for p in parts)


def song_path(root, location):
    """":iPod_Control:Music:F00:X.mp3" → the file under the mounted iPod, on any OS."""
    return os.path.join(root, *[p for p in location.split(":") if p])


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def cover_files(folders):
    """--covers: "album" and "artist - album" → picture file."""
    found = {}
    for folder in folders:
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            if ext.lower() in IMAGE_EXTS:
                found.setdefault(key(stem), os.path.join(folder, name))
    return found


def read_map(path):
    """--map: "track id", "artist - album" or "album" → picture file. Relative pictures are
    from the map's folder."""
    found, base = {}, os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            what, sep, pic = line.partition("\t") if "\t" in line else line.rpartition(" = ")
            if not sep:
                raise SystemExit(f"{path}:{n}: expected what<tab>picture or what = picture")
            pic = os.path.join(base, os.path.expanduser(pic.strip()))
            if not os.path.exists(pic):
                raise SystemExit(f"{path}:{n}: no picture at {pic}")
            found[key(what)] = pic
    return found


class Library:
    """--library: your music folders, as album (and artist - album) → where its picture is: a
    song with one embedded, or a cover file in a song's folder. Pictures are read when used."""

    def __init__(self, folders, log=print):
        self.found = {}
        songs = 0
        for folder in folders:
            for dirpath, _, names in os.walk(folder):
                audio = [n for n in names if n.lower().endswith(AUDIO_EXTS)]
                if not audio:
                    continue
                cover = folder_cover(dirpath, names)
                for name in audio:
                    path = os.path.join(dirpath, name)
                    tags = read_tags(path)
                    songs += 1
                    if not tags.album or not (tags.picture or cover):
                        continue
                    source = ("song", path) if tags.picture else ("file", cover)
                    for artist in (tags.album_artist, tags.artist):
                        if artist:
                            self.found.setdefault(key(artist, tags.album), source)
                    self.found.setdefault(key(tags.album), source)
        log(f"library: {songs} songs, pictures for {len(self.found)} albums and artists")

    def get(self, *k):
        source = self.found.get(key(*k))
        if not source:
            return None
        kind, path = source
        return embedded(path) if kind == "song" else read_file(path)


def folder_cover(dirpath, names):
    pictures = [n for n in names if n.lower().endswith(IMAGE_EXTS)]
    for n in pictures:
        if os.path.splitext(n)[0].lower() in FOLDER_NAMES:
            return os.path.join(dirpath, n)
    return os.path.join(dirpath, pictures[0]) if len(pictures) == 1 else None


def build(root, db, picked=None, library=None, covers=None, log=print):
    """(table, images): an image index per track position, identical pictures shared."""
    picked, covers = picked or {}, covers or {}
    on_ipod, by_album, by_album_name = {}, {}, {}
    for t in db.tracks:
        pic = embedded(song_path(root, t.location)) if t.location else None
        if pic:
            on_ipod[t.pos] = pic
            if t.album:
                by_album.setdefault(key(t.artist, t.album), pic)
                by_album_name.setdefault(key(t.album), pic)

    def picture(t):
        path = picked.get(key(str(t.id))) or (t.album and (picked.get(key(t.artist, t.album)) or picked.get(key(t.album))))
        if path:
            return read_file(path)
        pic = on_ipod.get(t.pos) or (t.album and by_album.get(key(t.artist, t.album)))
        if pic or not t.album:
            return pic
        pic = library and (library.get(t.artist, t.album) or library.get(t.album))
        if pic:
            return pic
        path = covers.get(key(t.artist, t.album)) or covers.get(key(t.album))
        if path:
            return read_file(path)
        return by_album_name.get(key(t.album))     # a compilation: another artist's song has it

    images, index, table, decoded = [], {}, [], {}
    for t in db.tracks:
        pic = picture(t)
        if not pic:
            table.append(NONE)
            continue
        if pic not in decoded:
            decoded[pic] = dither(pic)
            if decoded[pic] is None:
                log(f"can't read the picture of {t.title} ({t.artist}, {t.album})", file=sys.stderr)
        img = decoded[pic]
        if img is None:
            table.append(NONE)
            continue
        if img not in index:
            if len(images) >= NONE:
                raise SystemExit("too many different covers")
            index[img] = len(images)
            images.append(img)
        table.append(index[img])
    return table, images


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ipod", help="the mounted iPod, e.g. /Volumes/IPOD or E:\\")
    ap.add_argument("--map", help="pictures picked by hand: track id, 'Artist - Album' or 'Album', a tab, the picture")
    ap.add_argument("--library", action="append", default=[], help="a music folder to take album pictures from")
    ap.add_argument("--covers", action="append", default=[], help="a folder of pictures: Album.jpg or 'Artist - Album.jpg'")
    ap.add_argument("--out", help="where to write FroggerArt (default: on the iPod)")
    ap.add_argument("--png", help="also draw the covers into this PNG")
    a = ap.parse_args(argv)
    db_path = itunes(a.ipod, "iTunesDB")
    if not os.path.exists(db_path):
        raise SystemExit(f"no iTunesDB at {db_path}: is the iPod mounted?")
    db = Database(db_path)
    picked = read_map(a.map) if a.map else None
    library = Library(a.library) if a.library else None
    table, images = build(a.ipod, db, picked, library, cover_files(a.covers))
    out = a.out or itunes(a.ipod, "FroggerArt")
    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        f.write(froggerart(table, images))
    os.replace(tmp, out)
    with_cover = sum(i != NONE for i in table)
    print(f"wrote {out}: {len(images)} covers, {with_cover} of {len(table)} songs have one")
    if a.png and images:
        preview(images, a.png)
        print("wrote", a.png)


if __name__ == "__main__":
    main()

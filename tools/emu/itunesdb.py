#!/usr/bin/env python3
"""Run osos's iTunesDB track loader (0xc4a68) on a generated database.

The loader reads an mhlt and its mhit/mhod records through two file
helpers, which are stubbed here to read from a buffer:

    0x57504  read(obj, buf, len) -> 0     0x376a4  skip(obj, len) -> 0

The track allocator (0xac908) hands out zeroed scratch records, and the
string reader (0xc62f8) is stubbed to decode the UTF-16 mhod string and
record which track field it was meant for. The sort-flag hooks that
need the real string pools are stubbed out. Everything else, including
the visible check and the mhod type switch, is Apple's code.

    tools/emu/itunesdb.py                 # built-in test database
    tools/emu/itunesdb.py --image build/patched/osos.img
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osos import Osos  # noqa: E402

LOAD_TRACKS = 0xc4a68
READ, SKIP, ALLOC_TRACK, READ_STRING = 0x57504, 0x376a4, 0xac908, 0xc62f8
SORT_FLAG_HOOKS = (0x4408c, 0x43dd8, 0x43e30, 0x44038)

PARSER = 0x500000        # parser object; the loader uses PARSER + 0x40000 too
TRACKS = 0x5a0000        # scratch track records handed out by ALLOC_TRACK
TRACK_SIZE = 0x400

# Track-record offset -> field name, from the mhod switch at 0xc4e64.
FIELDS = {0x24: "title", 0x1b8: "location", 0x30: "album", 0x28: "artist", 0x38: "genre",
          0x3c: "filetype", 0x40: "eq", 0x44: "comment", 0x48: "category", 0x4c: "type10",
          0x34: "composer"}
MHOD_TYPES = {"title": 1, "location": 2, "album": 3, "artist": 4, "genre": 5,
              "filetype": 6, "comment": 8, "category": 9, "composer": 12}


def mhod(kind, text):
    s = text.encode("utf-16-le")
    body = struct.pack("<IIII", 1, len(s), 0, 0) + s
    return struct.pack("<4sIII8x", b"mhod", 0x18, 0x18 + len(body), MHOD_TYPES[kind]) + body


def mhit(track_id, fields, visible=1):
    mhods = b"".join(mhod(k, v) for k, v in fields.items())
    head = bytearray(0x9c)
    struct.pack_into("<4sIIIII", head, 0, b"mhit", 0x9c, 0x9c + len(mhods), len(fields), track_id, visible)
    return bytes(head) + mhods


def mhlt(tracks):
    head = bytearray(0x5c)
    struct.pack_into("<4sII", head, 0, b"mhlt", 0x5c, len(tracks))
    return bytes(head) + b"".join(tracks)


SAMPLE = [
    (1, {"title": "Hey Jude", "artist": "The Beatles", "album": "1", "genre": "Rock"}, 1),
    (2, {"title": "Podcast ep", "artist": "Spotify", "album": "Spotify", "genre": "Spotify"}, 0),
    (3, {"title": "Clair de lune", "artist": "Debussy", "album": "Suite", "composer": "Debussy"}, 1),
]


def load(image, db):
    emu = Osos(image)
    state = {"pos": 0, "next_track": TRACKS, "tracks": [], "strings": {}}

    def read(emu, obj, buf, n, _):
        emu.write(buf, db[state["pos"]:state["pos"] + n].ljust(n, b"\0"))
        state["pos"] += n
        return 0

    def skip(emu, obj, n, *_):
        state["pos"] += n if n < 0x80000000 else n - (1 << 32)
        return 0

    def alloc_track(emu, *_):
        rec = state["next_track"]
        state["next_track"] += TRACK_SIZE
        emu.write(rec, bytes(TRACK_SIZE))
        state["tracks"].append(rec)
        return rec

    def read_string(emu, *_):
        field = emu.u32(emu.sp() + 4)
        pos, length = struct.unpack_from("<II", db, state["pos"])
        text = db[state["pos"] + 16:state["pos"] + 16 + length].decode("utf-16-le")
        state["pos"] += 16 + length
        state["strings"][field] = text
        return 0

    emu.stub(READ, read)
    emu.stub(SKIP, skip)
    emu.stub(ALLOC_TRACK, alloc_track)
    emu.stub(READ_STRING, read_string)
    for hook in SORT_FLAG_HOOKS:
        emu.stub(hook, lambda *a: 0)

    rc = emu.call(LOAD_TRACKS, PARSER)
    tracks = []
    for rec in state["tracks"]:
        t = {"id": emu.u32(rec + 0x1c)}
        for field, text in state["strings"].items():
            if rec <= field < rec + TRACK_SIZE:
                t[FIELDS.get(field - rec, hex(field - rec))] = text
        tracks.append(t)
    return rc, tracks, state["pos"]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", default="build/fw/osos.img")
    args = p.parse_args(argv)
    db = mhlt([mhit(i, f, v) for i, f, v in SAMPLE])
    rc, tracks, pos = load(args.image, db)
    print(f"loader returned {rc:#x}, consumed {pos} of {len(db)} bytes, {len(tracks)} tracks loaded")
    for t in tracks:
        print("  " + ", ".join(f"{k}={v}" for k, v in t.items()))
    return 0 if rc == 0 and pos == len(db) else 1


if __name__ == "__main__":
    sys.exit(main())

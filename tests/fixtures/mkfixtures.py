#!/usr/bin/env python3
"""Write the sample files in tests/fixtures/ (docs/file-formats.md has every format):

    iTunesDB                            Apple, Bravo (no dbid), Long Mix (25 min); the master
                                        playlist and Mix (persistent id 0xabcdf0)
    FroggerHidden.v1 .v2 .v3            hidden/shown songs; v3 by key, v1/v2 by position
    FroggerSkips.v1 .v2                 skip counts
    FroggerBookmarks.v1                 where Long Mix was left
    FroggerPlaylist_0000000000ABCDF0    Mix's songs by key (version 1)
    FroggerPlaylist_1.mhpo              the old FroggerPlaylist_I, Apple's On-The-Go format
    Play Counts                         Apple's, with Long Mix's bookmark
    FroggerArt.v1 .v2                   two covers

The keyed files also name a song that isn't in the iTunesDB (dbid 0xdead), which a reader drops.
tests/test_fixtures.py reads them with tools/podinfo.py and checks this script still writes the
same bytes.

    python3 tests/fixtures/mkfixtures.py
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/emupod"))
import mkresume as mk  # noqa: E402  the iTunesDB records
from podinfo import Key  # noqa: E402
from mkart import froggerart, froggerart_v1, image  # noqa: E402

STAMP = 0xc0ffee01                  # the iTunesDB's stamp the old versions were written for
LONG_MS = 25 * 60 * 1000
APPLE = Key(0x5eed0000000000a1, 101, 1000, 180000)
BRAVO = Key(0, 102, 2000, 240000)  # no dbid: matched by id, size and length
LONG = Key(0x5eed0000000000a3, 103, 3000, LONG_MS)
GONE = Key(0xdead, 104, 4000, 200000)
MIX = 0xabcdf0


def database():
    tracks = [mk.mhit(k.id, {"title": t, "artist": "Someone", "album": "Test"}, k.size, k.ms, 128, dbid=k.dbid)
              for k, t in ((APPLE, "Apple"), (BRAVO, "Bravo"), (LONG, "Long Mix"))]
    return mk.mhbd([mk.mhsd(1, mk.mhl(b"mhlt", tracks)),
                    mk.mhsd(2, mk.mhl(b"mhlp", [mk.mhyp("iPod", [101, 102, 103]),
                                                mk.mhyp("Mix", [101], master=False, pid=MIX)]))])


def header(magic, version, entry_size, count, stamp=STAMP):
    return struct.pack("<4sHHIII", magic, version, entry_size, stamp, count, 0)


def keyed(magic, version, entries, *fields):
    """A keyed version: the header, then per entry its Key and the u32 `fields`."""
    size = 20 + 4 * len(fields)
    return header(magic, version, size, len(entries), 0x0badf00d) + b"".join(
        k.pack() + struct.pack("<%dI" % len(rest), *rest) for k, *rest in entries)


def files():
    covers = [image(lambda x, y: 3 * (((x // 9) + (y // 9)) & 1)), image(lambda x, y: x * 4 // 72)]
    out = {
        "iTunesDB": database(),
        "FroggerHidden.v1": header(b"FRGH", 1, 8, 1) + struct.pack("<2I", 0, 101),
        "FroggerHidden.v2": header(b"FRGH", 2, 12, 2) + struct.pack("<6I", 0, 101, 0, 2, 103, 1),
        "FroggerHidden.v3": keyed(b"FRGH", 3, [(APPLE, 0), (BRAVO, 1), (GONE, 0)], "flags"),
        "FroggerSkips.v1": header(b"FRGS", 1, 16, 1) + struct.pack("<4I", 1, 102, 3, 0xe0000000),
        "FroggerSkips.v2": keyed(b"FRGS", 2, [(BRAVO, 3, 0xe0000000), (GONE, 1, 0xe0000100)], "count", "last"),
        "FroggerBookmarks.v1": keyed(b"FRGB", 1, [(LONG, 120000), (GONE, 5000)], "ms"),
        "FroggerPlaylist_%016X" % MIX: struct.pack("<4sHHIIQ", b"FRGP", 1, 20, 0x0badf00d, 3, MIX)
        + b"".join(k.pack() for k in (APPLE, BRAVO, GONE)),
        "FroggerPlaylist_1.mhpo": struct.pack("<4sIIII", b"mhpo", 0x14, 4, 2, STAMP) + struct.pack("<2I", 2, 0),
        "Play Counts": struct.pack("<4sIII", b"mhdp", 0x60, 0x10, 3) + bytes(0x60 - 16)
        + b"".join(struct.pack("<4I", 0, 0, ms, 0) for ms in (0, 0, 90000)),
        "FroggerArt.v1": froggerart_v1([0, 0xffff, 1], covers),
        "FroggerArt.v2": froggerart([(APPLE, 0), (LONG, 1), (GONE, 0)], covers),
    }
    return out


if __name__ == "__main__":
    for name, data in files().items():
        (HERE / name).write_bytes(data)
        print("wrote", HERE / name, len(data), "bytes")

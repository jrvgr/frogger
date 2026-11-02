#!/usr/bin/env python3
"""Check the hidden-songs payload (payload/) on Apple's own code in Unicorn.

1. Loads the payload and its hooks into osos, as the loader does.
2. Runs the track loader (0xc4a68) and the playlist loader (0xc4244) on a
   generated database, some of whose tracks carry the hide flag (mhit+0x98
   = "HIDE"). File reads come from a buffer and the allocators hand out
   scratch memory (as in itunesdb.py); the record walks and the hooks are
   Apple's code and ours. Then it asks the payload which tracks it hid.
3. Runs the item loop of the browse list builder (0xf2024 to 0xf2140) over
   the master playlist and over another playlist. The loop stores 1 at
   track+0x1c for every item it keeps and 0 for every item it drops.

    nix develop -c tools/emu/hide.py
"""

import argparse
import os
import struct
import sys
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from osos import Osos, STACK_TOP  # noqa: E402
from mkpayload import hooks, symbols  # noqa: E402
import itunesdb  # noqa: E402

LOAD_TRACKS, LOAD_PLAYLISTS = 0xc4a68, 0xc4244
READ, SKIP, READ_STRING, ALLOC_TRACK = 0x57504, 0x376a4, 0xc62f8, 0xac908
NEW_PLAYLIST, FIND_TRACK, ADD_ITEM, IDENTITY = 0x530d0, 0x70138, 0x363cc, 0x57534
# Everything else the two loaders call (sorting, indexes, string pools)
# returns 0 here.
OTHER_CALLS = (0x40350, 0x4069c, 0x53eec, 0x5eb7c, 0x5ec2c, 0x70884, 0x78d60, 0x7cb58,
               0x93b14, 0xa065c, 0xa9ea0, 0xc9414, 0xce7c4, 0xdc5ec, 0xdc9cc) + itunesdb.SORT_FLAG_HOOKS
BROWSE_ITEMS, BROWSE_DONE = 0xf2024, 0xf2140

PARSER = 0x500000        # parser object; the loaders also use PARSER + 0x40000
LIBRARY = 0x55f000       # the object every track record points back to (+0)
HEAP = 0x560000          # scratch objects (playlists, items, lists)
TRACKS = 0x580000        # track records, 0x200 bytes each
TRACK_SIZE = 0x200
HIDE_OFFSET, HIDE_MAGIC = 0x98, b"HIDE"


def mhit(track_id, title, hidden=False):
    rec = bytearray(itunesdb.mhit(track_id, {"title": title, "artist": "Someone"}))
    if hidden:
        rec[HIDE_OFFSET:HIDE_OFFSET + 4] = HIDE_MAGIC
    return bytes(rec)


def mhod_name(name):
    s = name.encode("utf-16-le")
    body = struct.pack("<IIII", 1, len(s), 0, 0) + s
    return struct.pack("<4sIII8x", b"mhod", 0x18, 0x18 + len(body), 1) + body


def mhip(track_id):
    head = bytearray(0x4c)
    struct.pack_into("<4sIIIHHII", head, 0, b"mhip", 0x4c, 0x4c, 0, 0, 0, 0, track_id)
    return bytes(head)


def mhyp(name, track_ids, master=False):
    body = mhod_name(name) + b"".join(mhip(t) for t in track_ids)
    head = bytearray(0x6c)
    struct.pack_into("<4sIIIIB", head, 0, b"mhyp", 0x6c, 0x6c + len(body), 1, len(track_ids), int(master))
    return bytes(head) + body


def mhlp(playlists):
    head = bytearray(0x5c)
    struct.pack_into("<4sII", head, 0, b"mhlp", 0x5c, len(playlists))
    return bytes(head) + b"".join(playlists)


# Tracks 2 and 4 are flagged; 2 is also in a playlist.
TRACK_LIST = [(1, "One", False), (2, "Two", True), (3, "Three", False), (4, "Four", True), (5, "Five", False)]
PLAYLISTS = [("iPod", [1, 2, 3, 4, 5], True), ("Discover Weekly", [2, 3])]
HIDDEN = {2, 4}


class Harness:
    def __init__(self, image, build):
        self.emu = Osos(image)
        build = Path(build)
        self.syms = symbols(build / "payload/payload.sym")
        blob = (build / "payload/payload.bin").read_bytes()
        base = self.syms["track_hook"]
        self.emu.write(base, blob + bytes(self.syms["_bss_end"] - base - len(blob)))
        for addr, orig, repl, _ in hooks(self.syms):
            assert self.emu.u32(addr) == orig, f"{addr:#x} is not the expected instruction"
            self.emu.write(addr, struct.pack("<I", repl))
        self.heap = HEAP
        self._stub()

    def alloc(self, size):
        addr = self.heap
        self.heap += (size + 15) & ~15
        self.emu.write(addr, bytes(size))
        return addr

    def _run(self, func, data):
        self.data, self.pos = data, 0
        rc = self.emu.call(func, PARSER)
        return rc, self.pos

    def load(self, tracks, playlists):
        """Load an mhlt and an mhlp, like a database (re)load after a sync."""
        self.tracks, self.playlists = {}, []
        self.next_track = TRACKS
        rc, pos = self._run(LOAD_TRACKS, itunesdb.mhlt([mhit(*t) for t in tracks]))
        assert rc == 0, f"track loader returned {rc:#x}"
        self.tracks = {self.emu.u32(rec + 0x1c): rec for rec in self.records}
        rc, pos = self._run(LOAD_PLAYLISTS, mhlp([mhyp(*p) for p in playlists]))
        assert rc == 0, f"playlist loader returned {rc:#x}"

    def _stub(self):
        emu = self.emu

        def read(emu, obj, buf, n, _):
            emu.write(buf, self.data[self.pos:self.pos + n].ljust(n, b"\0"))
            self.pos += n
            return 0

        def skip(emu, obj, n, *_):
            self.pos += n if n < 0x80000000 else n - (1 << 32)
            return 0

        def read_string(emu, *_):
            _, length = struct.unpack_from("<II", self.data, self.pos)
            self.pos += 16 + length
            return 0

        def alloc_track(emu, *_):
            rec = self.next_track
            self.next_track += TRACK_SIZE
            emu.write(rec, struct.pack("<I", LIBRARY) + bytes(TRACK_SIZE - 4))
            self.records.append(rec)
            return rec

        def new_playlist(emu, *_):
            pl = self.alloc(0x200)
            emu.write(pl + 0x24, struct.pack("<I", self.alloc(0x40)))
            emu.write(emu.u32(emu.sp() + 8), struct.pack("<I", pl))
            self.playlists.append(pl)
            return 0

        self.records = []
        emu.stub(READ, read)
        emu.stub(SKIP, skip)
        emu.stub(READ_STRING, read_string)
        emu.stub(ALLOC_TRACK, alloc_track)
        emu.stub(NEW_PLAYLIST, new_playlist)
        emu.stub(FIND_TRACK, lambda emu, db, track_id, *a: self.tracks.get(track_id, 0))
        emu.stub(ADD_ITEM, lambda emu, *a: self.alloc(0x40))
        emu.stub(IDENTITY, lambda emu, r0, *a: r0)
        for func in OTHER_CALLS:
            emu.stub(func, lambda *a: 0)

    def hidden(self):
        return {i for i, rec in self.tracks.items() if self.emu.call(self.syms["hide_track"], rec)}

    def master(self):
        return self.emu.u32(self.syms["hide_state"] + 4)

    def set_show_all(self, on):
        self.emu.write(self.syms["hide_state"] + 1, bytes([int(on)]))

    def browse(self, owner, ids):
        """Run the browse item loop over `ids` as items of playlist `owner`;
        returns the ids it kept."""
        emu = self.emu
        recs = {i: self.tracks[i] for i in ids}
        items = self.alloc(12 + 4 * len(ids))
        emu.write(items, struct.pack("<I", len(ids)))
        for k, i in enumerate(ids):
            item = self.alloc(0x40)
            emu.write(item, struct.pack("<I", owner))
            emu.write(item + 0x20, struct.pack("<I", recs[i]))
            emu.write(items + 12 + 4 * k, struct.pack("<I", item))
            emu.write(recs[i] + 0x1c, struct.pack("<I", 0xff))
        sp = STACK_TOP - 0x100
        emu.write(sp, bytes(0x84))  # no query, no checked-only, no field filter
        emu.uc.reg_write(UC_ARM_REG_SP, sp)
        emu.uc.reg_write(UC_ARM_REG_R7, items)
        emu.uc.reg_write(UC_ARM_REG_R4, 0)
        emu.uc.reg_write(UC_ARM_REG_R5, 0)
        emu.uc.emu_start(BROWSE_ITEMS, BROWSE_DONE, count=100_000)
        kept = {i: emu.u32(recs[i] + 0x1c) for i in ids}
        for i in ids:  # put the ids back (the loop reuses that word)
            emu.write(recs[i] + 0x1c, struct.pack("<I", i))
        assert set(kept.values()) <= {0, 1}, kept
        return {i for i, v in kept.items() if v}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", default="build/fw/osos.img")
    p.add_argument("--build", default="build")
    args = p.parse_args(argv)
    h = Harness(args.image, args.build)
    h.load(TRACK_LIST, PLAYLISTS)
    ids = sorted(h.tracks)
    hidden = h.hidden()
    print(f"loaded {len(ids)} tracks; hidden: {sorted(hidden)} (expected {sorted(HIDDEN)})")
    print(f"master playlist object: {h.master():#x} (expected {h.playlists[0]:#x})")
    library = h.browse(h.master(), ids)
    playlist = h.browse(h.playlists[1], [2, 3])
    h.set_show_all(True)
    everything = h.browse(h.master(), ids)
    print(f"library browse keeps {sorted(library)}")
    print(f"'Discover Weekly' keeps {sorted(playlist)}")
    print(f"library browse with show_all keeps {sorted(everything)}")
    ok = (hidden == HIDDEN and h.master() == h.playlists[0] and library == set(ids) - HIDDEN
          and playlist == {2, 3} and everything == set(ids))
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

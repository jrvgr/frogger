#!/usr/bin/env python3
"""Dump the UI resource bundle inside osos (firmware 2.3: at 0x181d20).

The bundle holds the menus, strings, views and the UI bytecode (TCmd):

    +0  version (3)     +4  data offset     +8  type count
    +12 per type: fourcc (stored byte-reversed), count, flags, index offset
    index entries: id, offset from bundle + data offset, size

    tools/re/resources.py types
    tools/re/resources.py strings Artists       # string ids for a text
    tools/re/resources.py menus                 # every Menu and its items
"""

import argparse
import struct
import sys

BUNDLE = 0x181d20
MENU_ITEM = 40  # bytes per item after a 4-byte count


class Bundle:
    def __init__(self, path, base=BUNDLE):
        self.d = open(path, "rb").read()
        self.base = base
        version, self.data, ntypes = self.words(base, 3)
        if version != 3:
            raise ValueError(f"no resource bundle at {base:#x}")
        self.types = {}
        for t in range(ntypes):
            a = base + 12 + 16 * t
            fourcc = self.d[a:a + 4][::-1].decode("latin1")
            count, _flags, index = self.words(a + 4, 3)
            self.types[fourcc] = [self.words(base + index + 12 * i, 3) for i in range(count)]
        self.strs = {rid & 0xffff: self.text(rid) for rid, _, _ in self.types.get("Str ", [])}

    def words(self, addr, n):
        return struct.unpack_from(f"<{n}I", self.d, addr)

    def addr(self, fourcc, rid):
        for r, off, size in self.types[fourcc]:
            if r == rid:
                return self.base + self.data + off, size
        raise KeyError(f"{fourcc} {rid:#x}")

    def text(self, rid):
        a, size = self.addr("Str ", rid)
        return self.d[a:a + size].split(b"\0")[0].decode("latin1")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", default="build/fw/osos.img")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("types")
    s = sub.add_parser("strings")
    s.add_argument("text", nargs="?")
    sub.add_parser("menus")
    args = p.parse_args(argv)
    b = Bundle(args.image)

    if args.cmd == "types":
        for fourcc, entries in b.types.items():
            first = b.addr(fourcc, entries[0][0])[0] if entries else 0
            print(f"{fourcc!r}: {len(entries)} resources, first at {first:#x}")
    elif args.cmd == "strings":
        for rid, text in b.strs.items():
            if args.text is None or text == args.text:
                print(f"{rid:#06x}: {text!r}")
    elif args.cmd == "menus":
        for rid, _, size in b.types["Menu"]:
            a, _ = b.addr("Menu", rid)
            count = b.words(a, 1)[0]
            print(f"Menu {rid & 0xffff:#06x} @ {a:#x}, {count} items")
            for i in range(min(count, (size - 4) // MENU_ITEM)):
                w = b.words(a + 4 + MENU_ITEM * i, 10)
                label = b.strs.get(w[8], "")
                print(f"  {' '.join(f'{x:08x}' for x in w)}  {label!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Quick cross-references for Apple's osos image, without opening Ghidra.

osos runs at address 0 (see docs/re-notes.md), so addresses here are
image offsets. ARM mode only; the OS has no Thumb code that matters here.

    tools/re/xref.py callers 0x1335d8          # who calls lcd_write_reg
    tools/re/xref.py loads 0xc0001000 0xc0002000   # pc-relative literal loads in a range
    tools/re/xref.py words 0xba390             # where a value is stored as a data word
    tools/re/xref.py strings iTunesDB          # a C string and the code that loads its address
"""

import argparse
import bisect
import struct
import sys
from collections import defaultdict


class Image:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        self.n = len(self.d) & ~3
        self.w = struct.unpack_from(f"<{self.n // 4}I", self.d)
        # STMDB sp!, {..., lr}: good enough as a function start marker.
        self.starts = [i * 4 for i, x in enumerate(self.w) if x & 0xFFFF4000 == 0xE92D4000]
        self.loads = []
        for i, x in enumerate(self.w):
            # LDR Rd, [PC, #+/-imm12]
            if x & 0x0F7F0000 == 0x051F0000 and x >> 28 != 0xF:
                a = i * 4
                off = x & 0xFFF
                lit = a + 8 + (off if x & (1 << 23) else -off)
                if 0 <= lit < self.n:
                    self.loads.append((a, self.w[lit // 4]))

    def func_of(self, a):
        k = bisect.bisect_right(self.starts, a) - 1
        return self.starts[k] if k >= 0 else 0

    def branches_to(self, target):
        out = []
        for i, x in enumerate(self.w):
            if x & 0x0E000000 == 0x0A000000 and x >> 28 != 0xF:  # B / BL, any condition
                off = x & 0xFFFFFF
                if off & 0x800000:
                    off -= 1 << 24
                if i * 4 + 8 + off * 4 == target:
                    out.append(i * 4)
        return out


def num(s):
    return int(s, 0)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", default="build/fw/osos.img")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("callers")
    s.add_argument("addr", nargs="+", type=num)
    s = sub.add_parser("loads")
    s.add_argument("lo", type=num)
    s.add_argument("hi", type=num)
    s = sub.add_parser("words")
    s.add_argument("value", nargs="+", type=num)
    s = sub.add_parser("strings")
    s.add_argument("text", nargs="+")
    args = p.parse_args(argv)
    img = Image(args.image)

    if args.cmd == "callers":
        for t in args.addr:
            cs = img.branches_to(t)
            print(f"{t:#x}: " + (", ".join(f"{c:#x} (in {img.func_of(c):#x})" for c in cs) or "no direct callers"))
    elif args.cmd == "loads":
        byf = defaultdict(list)
        for a, v in img.loads:
            if args.lo <= v < args.hi:
                byf[img.func_of(a)].append((a, v))
        for f in sorted(byf):
            print(f"{f:#x}: " + ", ".join(f"{a:#x}->{v:#x}" for a, v in byf[f]))
    elif args.cmd == "words":
        for v in args.value:
            hits = [i * 4 for i, x in enumerate(img.w) if x == v]
            print(f"{v:#x}: " + ", ".join(f"{h:#x}" for h in hits))
    elif args.cmd == "strings":
        for t in args.text:
            needle = t.encode() + b"\0"
            o = img.d.find(needle)
            while o != -1:
                refs = [a for a, v in img.loads if v == o]
                print(f"{t!r} @ {o:#x}: " + (", ".join(f"{a:#x} (in {img.func_of(a):#x})" for a in refs) or "no literal refs"))
                o = img.d.find(needle, o + 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Disassemble the TCmd UI bytecode in osos (firmware 2.3). See docs/tcmd.md.

    tools/re/tcmd.py info                 # container layout
    tools/re/tcmd.py fn 110               # one function by index
    tools/re/tcmd.py at 0x4f0e            # the function holding a code offset
    tools/re/tcmd.py all > build/tcmd.txt # everything
    tools/re/tcmd.py check                # how many functions decode to their exact length

Offsets are from the code base (0x192948), the same numbers the VM trace prints
(tools/emupod/probes/settrace.py).
"""

import argparse
import struct
import sys

TCMD = 0x191dcc  # the TCmd resource (id 0x2380) in the 2.3 bundle

# The VM's per-opcode table, copied from RAM (0x373ab0, filled at boot; it is not in the
# image). Each entry: b0 = (pops << 4) | length (length 1 or 3; 0xf = variable), b1 = a
# group byte, h = operand kind in the low nibble (1 branch offset, 2 tagged constant /
# selector, 3 raw 16-bit, 6/7 load/store slot) with a storage class above it.
OPS = [
    (0x01, 0x00, 0x0000), (0x01, 0x01, 0x0000), (0x11, 0x00, 0x0000), (0x11, 0x01, 0x0000),  # 00
    (0x11, 0x00, 0x0000), (0x11, 0x00, 0x0000), (0x03, 0x00, 0x0001), (0x13, 0x00, 0x0001),  # 04
    (0x13, 0x00, 0x0001), (0x13, 0x01, 0x0052), (0x23, 0x01, 0x0062), (0x31, 0x01, 0x0070),  # 08
    (0x11, 0x02, 0x0000), (0x21, 0x04, 0x0000), (0x13, 0x11, 0x0052), (0x21, 0x21, 0x0000),  # 0c
    (0x21, 0x31, 0x0000), (0x21, 0x41, 0x0000), (0x21, 0x51, 0x0000), (0x21, 0x51, 0x0000),  # 10
    (0x21, 0x61, 0x0000), (0x21, 0x61, 0x0000), (0x21, 0x61, 0x0000), (0x21, 0x61, 0x0000),  # 14
    (0x21, 0x71, 0x0000), (0x21, 0x71, 0x0000), (0x21, 0x71, 0x0000), (0x21, 0x81, 0x0000),  # 18
    (0x21, 0x81, 0x0000), (0x21, 0x91, 0x0000), (0x21, 0x91, 0x0000), (0x21, 0x91, 0x0000),  # 1c
    (0x11, 0xa1, 0x0000), (0x11, 0xa1, 0x0000), (0x11, 0xa1, 0x0000), (0xf3, 0xa1, 0x0003),  # 20
    (0x03, 0xa1, 0x0092), (0x13, 0xa1, 0x00a2), (0x21, 0xa1, 0x00b0), (0x11, 0xa1, 0x0000),  # 24
    (0x11, 0xa1, 0x0000), (0x03, 0xa1, 0x0212), (0x13, 0xa1, 0x0222), (0x21, 0xa1, 0x0230),  # 28
    (0x03, 0xa1, 0x0112), (0x13, 0xa1, 0x0122), (0x21, 0xa1, 0x0130), (0x03, 0xa1, 0x0612),  # 2c
    (0x13, 0xa1, 0x0622), (0x21, 0xa1, 0x0630), (0x03, 0xa1, 0x0512), (0x13, 0xa1, 0x0522),  # 30
    (0x21, 0xa1, 0x0530), (0x13, 0xb1, 0x0022), (0x23, 0x11, 0x0062), (0x21, 0xb1, 0x0030),  # 34
    (0x31, 0x11, 0x0070), (0x01, 0x01, 0x0000), (0xf3, 0xb1, 0x0003), (0x03, 0xc1, 0x0012),  # 38
    (0x03, 0xc1, 0x0002), (0x03, 0xc1, 0x0002), (0x01, 0xc1, 0x0000), (0x01, 0xc1, 0x0000),  # 3c
    (0x01, 0xc1, 0x0000), (0x01, 0xc1, 0x0000), (0x01, 0xc1, 0x0000), (0x01, 0xc1, 0x0000),  # 40
    (0x13, 0x00, 0x0001), (0x13, 0x00, 0x0001), (0x1f, 0x00, 0x0004), (0x1f, 0x00, 0x0005),  # 44
    (0x21, 0x51, 0x0000), (0x21, 0x51, 0x0000), (0x03, 0x01, 0x0002), (0x01, 0x00, 0x0000),  # 48
    (0x03, 0x00, 0x0012), (0x11, 0x00, 0x0000), (0x13, 0x00, 0x0822), (0x21, 0x00, 0x0830),  # 4c
    (0x03, 0xc1, 0x0002), (0x11, 0x00, 0x0000), (0x11, 0xa1, 0x0000), (0x01, 0x00, 0x0000),  # 50
    (0x03, 0xc1, 0x0016), (0x13, 0x11, 0x0056), (0x03, 0xc1, 0x0017), (0x13, 0x11, 0x0057),  # 54
    (0x03, 0xc1, 0x0003), (0x21, 0xa1, 0x0000), (0x01, 0x00, 0x0000), (0x13, 0x00, 0x0022),  # 58
    (0x21, 0x00, 0x0030), (0x03, 0x00, 0x0003), (0x03, 0x01, 0x0003), (0x03, 0xa1, 0x0216),  # 5c
    (0x03, 0xa1, 0x0217), (0x03, 0xa1, 0x0116), (0x03, 0xa1, 0x0117), (0x03, 0xa1, 0x0616),  # 60
    (0x03, 0xa1, 0x0617), (0x03, 0xa1, 0x0516), (0x03, 0xa1, 0x0517), (0x11, 0x01, 0x0000),  # 64
    (0x03, 0x01, 0x1052), (0x13, 0x01, 0x1062), (0x21, 0x04, 0x1030), (0x21, 0x00, 0x0000),  # 68
    (0x03, 0x01, 0x0012), (0x23, 0x11, 0x0052), (0x11, 0x00, 0x0000), (0x21, 0x61, 0x0000),  # 6c
    (0x21, 0x61, 0x0000), (0x01, 0x00, 0x0000), (0x03, 0x01, 0x0001), (0x11, 0x00, 0x0000),  # 70
    (0x01, 0x01, 0x0000), (0x03, 0x00, 0x0003), (0x01, 0x00, 0x0000), (0x13, 0x00, 0x0001),  # 74
    (0x13, 0x00, 0x0001), (0xf3, 0xb1, 0x0003), (0x31, 0x10, 0x0070), (0x01, 0x00, 0x0000),  # 78
    (0x01, 0x00, 0x0000), (0x03, 0x00, 0x0042), (0x03, 0x00, 0x0052), (0x03, 0x00, 0x0012),  # 7c
]

# Names seen in VM traces; everything else prints as opNN. "?" = a guess from the table.
NAMES = {
    0x02: "drop", 0x05: "return", 0x06: "jump", 0x07: "jump_if_false?", 0x08: "jump_if_true?",
    0x35: "lookup", 0x39: "args", 0x3a: "send", 0x3b: "push_const", 0x3c: "push_const2?",
    0x3d: "push_const3?", 0x42: "push_self?", 0x43: "push_nil", 0x44: "branch44?",
    0x45: "branch45?", 0x46: "switch?", 0x47: "switch?", 0x51: "drop51?", 0x54: "push_arg",
    0x56: "push_local", 0x57: "store_local", 0x58: "push_int", 0x6c: "push_global",
    0x6d: "store_global", 0x79: "send79?",
}


class TCmd:
    def __init__(self, path):
        d = self.d = open(path, "rb").read()
        self.size, _, npool = struct.unpack_from("<IHH", d, TCMD)
        self.pool_at = TCMD + 8
        self.pool = struct.unpack_from(f"<{npool}I", d, self.pool_at)
        p = self.pool_at + 4 * npool
        self.nfn, tlen = struct.unpack_from("<HH", d, p)
        self.tlist = struct.unpack_from(f"<{tlen}H", d, p + 4)
        self.table = p + 4 + 2 * tlen + (2 if tlen % 2 else 0)
        self.offs = struct.unpack_from(f"<{self.nfn + 1}I", d, self.table)
        self.code = self.table + 4 * (self.nfn + 1)

    def header(self, i):
        """id, two zero halfwords (flags?), handler count, body length."""
        return struct.unpack_from("<5H", self.d, self.code + self.offs[i])

    def index_of(self, off):
        return max(i for i in range(self.nfn) if self.offs[i] <= off)

    def insns(self, i):
        start = self.offs[i] + 10
        end = self.offs[i + 1]
        o = start
        while o < end:
            op = self.d[self.code + o]
            if op >= 0x80:
                yield o, op, None, 1, "bad"
                o += 1
                continue
            n = OPS[op][0] & 15
            if n == 3:
                arg = struct.unpack_from(">H", self.d, self.code + o + 1)[0]
                yield o, op, arg, 3, None
            elif n == 1:
                yield o, op, None, 1, None
            else:
                yield o, op, None, 1, "variable length, not decoded"
                return
            o += n

    def show(self, i, out=sys.stdout):
        fid, a, b, subs, length = self.header(i)
        print(f"fn {i} @ {self.offs[i]:#x}  id {fid:#06x}  flags {a:#x} {b:#x}  handlers {subs}  len {length:#x}", file=out)
        for o, op, arg, n, note in self.insns(i):
            name = NAMES.get(op, f"op{op:02x}")
            if arg is None:
                text = name
            elif OPS[op][2] & 15 == 1:
                text = f"{name} -> {(o + (arg - 0x10000 if arg & 0x8000 else arg)):#x}"
            else:
                text = f"{name} {arg:#06x}"
            raw = self.d[self.code + o:self.code + o + n].hex(" ")
            print(f"  {o:5x}  {raw:<9} {text}" + (f"   ; {note}" if note else ""), file=out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", default="build/fw/osos.img")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    f = sub.add_parser("fn")
    f.add_argument("index", type=int)
    a = sub.add_parser("at")
    a.add_argument("offset", type=lambda s: int(s, 0))
    sub.add_parser("all")
    sub.add_parser("check")
    args = p.parse_args(argv)
    t = TCmd(args.image)
    if args.cmd == "info":
        print(f"TCmd @ {TCMD:#x}: word0 {t.size:#x}, pool {len(t.pool)} words @ {t.pool_at:#x}, "
              f"{t.nfn} functions, table @ {t.table:#x}, code @ {t.code:#x}, tlist {t.tlist}")
    elif args.cmd == "fn":
        t.show(args.index)
    elif args.cmd == "at":
        t.show(t.index_of(args.offset))
    elif args.cmd == "all":
        for i in range(t.nfn):
            t.show(i)
    elif args.cmd == "check":
        ok = bad = 0
        for i in range(t.nfn):
            last = list(t.insns(i))
            if last and last[-1][4] is None and last[-1][0] + last[-1][3] == t.offs[i + 1]:
                ok += 1
            else:
                bad += 1
        print(f"{ok} functions decode to their end, {bad} don't (variable-length ops or padding)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

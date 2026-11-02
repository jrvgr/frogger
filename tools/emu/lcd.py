#!/usr/bin/env python3
"""Run osos's lcd_update_rect (0xd2db4) on a test framebuffer and decode
what it sends to the LCD.

The framebuffer at 0x3835a0 is 160x128 at 2 bpp, 40 bytes per row. The
routine walks 8-pixel column groups, sets R11 (RAM address) and streams
two-byte words to R12, one per row. This script rebuilds the panel's view
from that stream and compares it with the framebuffer, so a patched image
(e.g. dark mode) can be checked without a device.

    tools/emu/lcd.py                 # stock image: panel must equal framebuffer
    tools/emu/lcd.py --expect-invert --image build/patched/osos.img
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osos import Osos  # noqa: E402

LCD_UPDATE_RECT = 0xd2db4
FRAMEBUFFER = 0x3835a0
WIDTH, HEIGHT, STRIDE = 160, 128, 40
LCD_CMD, LCD_DATA = 0xc0001008, 0xc0001010
RECT = 0x5e0000  # scratch struct: y0, x0, y1, x1 (inclusive)


def decode(writes):
    """Turn LCD command/data writes into {(group, row): 16-bit word}."""
    panel = {}
    stream = [(a, v & 0xFF) for a, _, v in writes if a in (LCD_CMD, LCD_DATA)]
    i, reg, addr = 0, None, 0
    while i + 1 < len(stream):
        (a1, hi), (a2, lo) = stream[i], stream[i + 1]
        i += 2
        if a1 == LCD_CMD:
            reg = lo
        elif reg == 0x11:  # R11: RAM address = row << 5 | (20 - group)
            addr = hi << 8 | lo
        elif reg == 0x12:  # R12: RAM data, address auto-advances to the next row
            row, group = addr >> 5, 20 - (addr & 0x1F)
            panel[(group, row)] = hi << 8 | lo
            addr += 0x20
    return panel


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", default="build/fw/osos.img")
    p.add_argument("--expect-invert", action="store_true", help="panel must be the inverse of the framebuffer")
    p.add_argument("--seed", type=int, default=3)
    args = p.parse_args(argv)

    emu = Osos(args.image)
    fb = bytes(random.Random(args.seed).randrange(256) for _ in range(STRIDE * HEIGHT))
    emu.write(FRAMEBUFFER, fb)
    emu.write(RECT, b"".join(v.to_bytes(4, "little") for v in (0, 0, HEIGHT - 1, WIDTH - 1)))
    emu.call(LCD_UPDATE_RECT, 0, RECT)

    panel = decode(emu.writes)
    bad = 0
    for row in range(HEIGHT):
        for group in range(WIDTH // 8):
            base = FRAMEBUFFER + row * STRIDE + group * 2
            want = fb[base - FRAMEBUFFER] << 8 | fb[base - FRAMEBUFFER + 1]
            if args.expect_invert:
                want ^= 0xFFFF
            got = panel.get((group, row))
            if got != want:
                bad += 1
                if bad <= 5:
                    print(f"row {row} group {group}: panel {got if got is None else hex(got)} want {want:#06x}")
    words = len(panel)
    print(f"{len(emu.writes)} MMIO writes, {words} panel words decoded, {bad} mismatches")
    return 1 if bad or words != HEIGHT * WIDTH // 8 else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Boot a firmware partition the way the iPod 3G's flash code does, up to
the moment Apple's OS would start, and check what the Frogger loader did.

The flash code copies osos to 0x28000000 and jumps to its entryOffset.
With Frogger installed that is the loader: it copies itself up, reads the
buttons, patches osos and jumps to 0x28000000. We stop there and compare
RAM with what the hooks and payload should look like.

    tools/emu/boot.py PARTITION [--menu]     # --menu: hold Menu (stock boot)
"""

import argparse
import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_PC

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fwtool  # noqa: E402

DRAM, DRAM_SIZE = 0x28000000, 32 << 20
GPIOA_INPUT_VAL = 0xcf000030
BTN_MENU = 0x10


def boot(partition, menu=False):
    """Returns (pc where it stopped, osos as it is in RAM)."""
    fw = fwtool.parse(bytes(partition))
    osos = next(i for i in fw["images"] if i["id"] == "osos")
    image = fwtool.image_bytes(partition, osos)
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(DRAM, DRAM_SIZE)
    uc.mem_write(DRAM, bytes(image))
    uc.mem_map(0xc4000000, 0x1000)
    uc.mem_write(0xc4000000, struct.pack("<I", 0x55555555))     # the CPU
    uc.mem_map(0xcf000000, 0x1000)
    buttons = 0xff & ~(BTN_MENU if menu else 0)                 # active low

    def gpio(uc, access, addr, size, value, user):
        uc.mem_write(GPIOA_INPUT_VAL, bytes([buttons]))
    uc.hook_add(UC_HOOK_MEM_READ, gpio, begin=GPIOA_INPUT_VAL, end=GPIOA_INPUT_VAL)
    uc.emu_start(DRAM + osos["entryOffset"], DRAM, count=20_000_000)
    return uc.reg_read(UC_ARM_REG_PC), bytes(uc.mem_read(DRAM, DRAM_SIZE))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("partition")
    p.add_argument("--menu", action="store_true")
    args = p.parse_args(argv)
    _, part = fwtool.load_partition(args.partition)
    pc, ram = boot(part, args.menu)
    print(f"jumped to {pc:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

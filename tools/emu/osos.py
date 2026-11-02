"""Run single functions from Apple's osos image in Unicorn.

osos is linked at 0 (docs/re-notes.md), so the image is mapped at 0 with
RAM up to 0x600000 for .data/.bss and the uncached heap, and the
Frogger payload's 1 MiB at the top of the 3G's 32 MiB (payload/payload.lds). MMIO is mapped
as plain memory with hooks: reads return what `mmio_read` says (0 by
default) and every write is logged in `self.writes` as (addr, size, value).
"""

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

RAM_SIZE = 0x600000
PAYLOAD_RAM = (0x1f00000, 0x100000)
STACK_TOP = 0x5f0000
RETURN_MAGIC = 0x5ffff0  # lr for the called function; reaching it ends the run

SCATTER_COPIES = (  # (image offset, destination, length) from 0x24320
    (0x31f260, 0x40000000, 0x58),
    (0x31f2b8, 0x40000058, 0x136c),
    (0x34535c, 0x400179e0, 0x128),
    (0x344320, 0x4001764c, 0xb4),
    (0x313da0, 0x36fc00, 0xb448),
)

MMIO_PAGES = (
    0xc0001000,  # LCD1: control +0, command +8, data +0x10
    0xcf001000,  # timers (µs timer at +0x110)
    0xc4000000,  # PROCESSOR_ID
)


class Osos:
    def __init__(self, image="build/fw/osos.img"):
        self.image = open(image, "rb").read()
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0, RAM_SIZE)
        self.uc.mem_map(*PAYLOAD_RAM)
        self.uc.mem_write(0, self.image)
        for page in MMIO_PAGES:
            self.uc.mem_map(page, 0x1000)
        # What the scatter loader (0x24320) sets up at boot: IRAM vectors and
        # code (float helpers and other hot paths live there) and .data.
        self.uc.mem_map(0x40000000, 0x18000)
        for src, dst, length in SCATTER_COPIES:
            self.uc.mem_write(dst, self.image[src:src + length])
        self.writes = []
        self.reads = {}  # addr -> value returned for MMIO reads
        self.reads[0xc4000000] = 0x55555555  # run as the CPU, not the COP
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._on_write, begin=0xc0000000, end=0xcfffffff)
        self.uc.hook_add(UC_HOOK_MEM_READ, self._on_read, begin=0xc0000000, end=0xcfffffff)
        self.stubs = {}

    def stub(self, func, handler):
        """Replace func with handler(emu, r0, r1, r2, r3) -> r0. Stack
        arguments are at emu.sp() when the handler runs."""
        self.stubs[func] = handler
        self.uc.hook_add(UC_HOOK_CODE, self._on_stub, begin=func, end=func)

    def _on_stub(self, uc, addr, size, user):
        args = [uc.reg_read(UC_ARM_REG_R0 + i) for i in range(4)]
        ret = self.stubs[addr](self, *args)
        uc.reg_write(UC_ARM_REG_R0, (ret or 0) & 0xFFFFFFFF)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def sp(self):
        return self.uc.reg_read(UC_ARM_REG_SP)

    def u32(self, addr):
        return int.from_bytes(self.read(addr, 4), "little")

    def _on_write(self, uc, access, addr, size, value, user):
        self.writes.append((addr, size, value))

    def _on_read(self, uc, access, addr, size, value, user):
        uc.mem_write(addr, self.mmio_read(addr).to_bytes(4, "little")[:size])

    def mmio_read(self, addr):
        if addr == 0xcf001110:  # µs timer: tick so timeouts can expire
            self.reads[addr] = self.reads.get(addr, 0) + 1
        return self.reads.get(addr, 0)

    def write(self, addr, data):
        self.uc.mem_write(addr, bytes(data))

    def read(self, addr, n):
        return bytes(self.uc.mem_read(addr, n))

    def call(self, func, *args, max_insns=50_000_000):
        """Call func(args...) with the ARM calling convention; returns r0."""
        regs = [UC_ARM_REG_R0 + i for i in range(4)]
        if len(args) > 4:
            raise ValueError("only register arguments are supported")
        for reg, value in zip(regs, args):
            self.uc.reg_write(reg, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_SP, STACK_TOP)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN_MAGIC)
        try:
            self.uc.emu_start(func, RETURN_MAGIC, count=max_insns)
        except UcError as e:
            pc = self.uc.reg_read(UC_ARM_REG_PC)
            raise RuntimeError(f"emulation stopped at {pc:#x}: {e}") from e
        return self.uc.reg_read(UC_ARM_REG_R0)

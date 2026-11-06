#!/usr/bin/env python3
"""DEBUG=1 Frogger image + a copy of hide-card.img: the debug record (payload/debug.c) comes out
whole in iPod_Control/iTunes/FroggerDebug. Two boots: the first makes a record (Hide on a song,
so there are notes as well as a trail), the second starts from a RAM image that carries the
record at DEBUG_ADDR, as a reset leaves it, and writes the file on its first tick; then the file
on the card is compared with the text the record should give. A second pair of boots does the
same with a record filled to the brim (every trail entry and note used, a crash), many blocks
of text.

    debugrecord.py          # both
    debugrecord.py session  # the record a session makes
    debugrecord.py full     # the filled record

Each boot is its own process (emupod runs one per process): `boot1 NAME` saves the first boot's
record to debugrecord-NAME.bin, `boot2 NAME` boots from it.

Skips (exit 77, runtests.SKIP) on a normal build: the payload has no debug_tick then; CI runs it
after a `make -C loader DEBUG=1`. Exits 1 if a check is off.
"""
import shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W, ROOT

SKIP = 77

SYM = ROOT / "build/payload/payload.sym"
CARD = Path(W) / "hide-card.img"
RUN = Path(W) / "debugrecord-run.img"
IMAGE = Path(W) / "osos-debugrecord.img"

ADDR, END = 0x358000, 0x360000
MAGIC, TRAIL, NOTES, STACK = 0x46524442, 3400, 256, 32
N_OFF = 4 * (6 + 14 + STACK)                    # n, nn after magic..lr, regs, stack
NOTES_OFF = N_OFF + 8
TRAIL_OFF = NOTES_OFF + 16 * NOTES
fails = []


def check(what, ok):
    print("  %-60s %s" % (what, "ok" if ok else "WRONG"))
    if not ok:
        fails.append(what)


def expected(rec):
    """The text write_record makes of the record `rec` (DEBUG_ADDR's bytes)."""
    w = lambda o: struct.unpack_from("<I", rec, o)[0]
    hx = lambda v: "%08x" % v
    kinds = ["?", "undefined instruction", "?", "prefetch abort", "data abort"]
    out = ["Frogger debug, record 2, boot %d" % w(4)]
    kind = w(8)
    if kind:
        out.append("crash: %s (kind %d)" % (kinds[kind if kind < 5 else 0], kind))
        out.append("spsr %s  sp %s  lr %s" % (hx(w(12)), hx(w(16)), hx(w(20))))
        regs = [w(24 + 4 * i) for i in range(14)]
        for r in range(0, 12, 4):
            out.append("   ".join("r%d%s%s" % (i, "  " if i < 10 else " ", hx(regs[i])) for i in range(r, r + 4)))
        out.append("r12 %s   abort lr %s" % (hx(regs[12]), hx(regs[13])))
        out.append("stack:")
        st = [w(80 + 4 * i) for i in range(STACK)]
        for r in range(0, STACK, 8):
            out.append("".join(" " + hx(v) for v in st[r:r + 8]))
    else:
        out.append("no crash recorded")
    n, nn = w(N_OFF), w(N_OFF + 4)
    out.append("notes, oldest first (%d in all): ms tag a b @trail entry (low 12 bits)" % nn)
    for i in range(nn - min(nn, NOTES), nn):
        t = struct.unpack_from("<4I", rec, NOTES_OFF + 16 * (i % NOTES))
        tag = "".join(chr(c) if 32 <= c < 127 else "?" for c in struct.pack("<I", t[0]))
        out.append("%d %s %s %s @%d" % (t[3] >> 12, tag, hx(t[1]), hx(t[2]), t[3] & 0xfff))
    out.append("vm trail, oldest first; c0de000K abort-lr, spsr lr, sp r0 is a crash (%d in all):"
               " pc [-> pc it went on with]" % n)
    for i in range(n - min(n, TRAIL), n):
        pc, to = struct.unpack_from("<2I", rec, TRAIL_OFF + 8 * (i % TRAIL))
        out.append(hx(pc) + ("" if to == pc else " -> " + hx(to)))
    return "".join(s + "\n" for s in out)


def rec_file(what):
    return Path(W) / f"debugrecord-{what}.bin"


def read_file(card, name):
    start = struct.unpack_from("<I", open(card, "rb").read(512), 0x1be + 16 + 8)[0]
    return subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-n", "-i", f"{card}@@{start * 512}",
                           f"::/iPod_Control/iTunes/{name}", "-"], capture_output=True).stdout


def second_boot(what):
    """Boot on RUN from a RAM image carrying the saved record; FroggerDebug must be its text."""
    rec = rec_file(what).read_bytes()
    ram = bytearray((Path(W) / "osos-frogger.img").read_bytes())
    ram[ADDR:ADDR + len(rec)] = rec
    IMAGE.write_bytes(ram)
    want = expected(rec)
    p = Pod(osos=str(IMAGE), disk=str(RUN), persist=True)
    p.settle()
    p.run(3_000_000)
    after = bytes(p.m.mem_read(ADDR, 8))
    del p
    got = read_file(RUN, "FroggerDebug").decode("latin-1")
    print("%s: %d trail entries, %d notes; FroggerDebug %d bytes, %d expected"
          % (what, struct.unpack_from("<I", rec, N_OFF)[0], struct.unpack_from("<I", rec, N_OFF + 4)[0],
             len(got), len(want)))
    if got != want:
        i = next((i for i in range(min(len(got), len(want))) if got[i] != want[i]), min(len(got), len(want)))
        print("  first difference at byte %d:\n    got  %r\n    want %r" % (i, got[i - 40:i + 80], want[i - 40:i + 80]))
    check(f"{what}: FroggerDebug is the whole record", got == want)
    check(f"{what}: the boot counter went on (a new record started)",
          struct.unpack_from("<2I", after) == (MAGIC, struct.unpack_from("<I", rec, 4)[0] + 1))


def session():
    shutil.copyfile(CARD, RUN)
    p = Pod(osos=W + "/osos-frogger.img", disk=str(RUN), persist=True)
    p.press("select"); p.settle()                           # first run: Language -> English
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()     # Music > Songs
    p.scroll(2)
    p.press("select", hold_us=1_500_000, after_us=1_500_000); p.settle()          # hold menu
    p.scroll(-8); p.scroll(3)
    for _ in range(3):
        p.wheel(1, after_us=300_000)
    p.press("menu"); p.settle()
    p.press("next", after_us=500_000); p.press("prev", after_us=500_000)
    rec = bytes(p.m.mem_read(ADDR, END - ADDR))
    del p
    n, nn = struct.unpack_from("<2I", rec, N_OFF)
    check("first boot: a record with a trail", struct.unpack_from("<I", rec)[0] == MAGIC and n > 0)
    rec_file("session").write_bytes(rec)


def full():
    shutil.copyfile(CARD, RUN)
    rec = bytearray(END - ADDR)
    struct.pack_into("<6I", rec, 0, MAGIC, 41, 4, 0x600000d3, 0x40017f20, 0x1e4a8)
    struct.pack_into("<14I", rec, 24, *[0x11111111 * (i % 15) + i for i in range(14)])
    struct.pack_into("<%dI" % STACK, rec, 80, *[0xdead0000 + i for i in range(STACK)])
    n, nn = 3 * TRAIL + 123, NOTES + 77
    struct.pack_into("<2I", rec, N_OFF, n, nn)
    tags = [b"hide", b"save", b"HmEn", b"\x01x\x7fy"]
    for i in range(NOTES):
        struct.pack_into("<4I", rec, NOTES_OFF + 16 * i, struct.unpack("<I", tags[i % 4])[0],
                         0x1000 * i + 7, 0xffffffff - i, (123456 + 997 * i) << 12 | (i * 13) & 0xfff)
    for i in range(TRAIL):
        pc = 0x18e000 + 3 * i
        struct.pack_into("<2I", rec, TRAIL_OFF + 8 * i, pc, pc if i % 5 else 0x1f4000 + i)
    rec_file("full").write_bytes(rec)


if __name__ == "__main__":
    syms = {l.split()[2] for l in SYM.read_text().splitlines() if len(l.split()) == 3}
    if "debug_tick" not in syms:
        print("not a DEBUG=1 build (no debug_tick in payload.sym): skipped")
        sys.exit(SKIP)
    if sys.argv[1:2] == ["boot1"]:
        {"session": session, "full": full}[sys.argv[2]]()
    elif sys.argv[1:2] == ["boot2"]:
        second_boot(sys.argv[2])
    else:
        code = 0
        for s in sys.argv[1:] or ["session", "full"]:
            for step in ("boot1", "boot2"):
                r = subprocess.run([sys.executable, __file__, step, s]).returncode
                code |= r
                if r:
                    break
        print("\nsome checks WRONG" if code else "\nall ok")
        sys.exit(code)
    print("\n%d wrong" % len(fails) if fails else "\nall ok")
    sys.exit(1 if fails else 0)

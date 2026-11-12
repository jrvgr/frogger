"""Probe (issue 22): every codec write (0x140614: reg, value, caller) and the codec driver's entry points,
for a Headphones click before any song since boot, then a song's start, a pause and a paused click."""
import struct
from ipod3g import Pod, W, ROOT

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
p = Pod(osos=W + "/osos-frogger.img", disk=W + "/ck-card.img")
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
p.press("select"); p.settle()
lib = rd(rd(0x43580c) + 0x1c)
fl = rd(rd(lib) + 0xb04)
p.m.mem_write(rd(lib) + 0xb04, list(struct.pack("<I", fl & ~(3 << 30) | 1 | 1 << 30)))
NAMES = {0x140614: "wm", 0x13fc38: "codec_open", 0x13fd30: "play_open", 0x13fcf0: "close", 0x14014c: "reset",
         0x125788: "f125788", 0x125538: "f125538", 0x14b0b8: "sleep", 0x140260: "rate", 0x1404ac: "path_on",
         0x13fff8: "path_off", 0x13ff40: "hp_mute", 0x13ff7c: "hp_unmute", 0x1258b8: "i2s_play", 0x12588c: "i2s_stop",
         SYM["click_tone"]: "click_tone", SYM["click_paused"] if "click_paused" in SYM else 1: "click_paused"}

def trace(tag, fn):
    p.m.hook_start(list(NAMES), None, 0)
    fn()
    log = p.m.hook_log(); p.m.hook_start([], None, 0)
    print("==", tag, "gpio28 %#x" % rd(0xcf000028))
    for t, pc, r, _ in log:
        n = NAMES[pc]
        extra = "R%d=%03x" % (r[0], r[1] & 0x1ff) if n == "wm" else "r0=%#x r1=%#x" % (r[0], r[1])
        print("  %9.3f ms %-12s %s lr=%#x" % (t / 1000, n, extra, r[14]))

def clicks():
    p.scroll(2); p.settle(); p.run(300_000); p.scroll(-2); p.settle(); p.run(300_000)

trace("clicks before any song", clicks)
trace("clicks again, 3 s later", lambda: (p.run(3_000_000), clicks()))
def play():
    p.press("select"); p.settle(); p.scroll(3); p.settle(); p.run(300_000); p.press("select"); p.settle()
    p.press("select", after_us=200_000)
    while not p.m.audio_on():
        p.run(20_000)
    p.run(1_000_000)
trace("first song", play)
trace("pause", lambda: (p.press("play", after_us=500_000), p.settle()))
trace("paused clicks", clicks)
print({k: rd(SYM["clicker_" + k]) for k in ("mixed", "paused", "fallback", "opened")})

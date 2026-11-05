"""Frogger image: Settings > Flash Storage (payload/flash.c). The drive's IDENTIFY comes from
emupod's EMUPOD_ATA_ID, so each run is a process of its own:

1. A flash IDENTIFY (word 217 = 1, as an SSD or a bridge that reports it): Select on the row steps
   Off, Auto, On, Off (prefs bits 28-29) and the value shown changes each time; with Auto, Tone A's
   music-cache refill ends and the drive gets its STANDBY about 1 s later (Apple: 2 s or more).
2. The same IDENTIFY with the switch Off: Apple's hold, 2 s or more.
3. A hard drive's IDENTIFY (word 217 = 4200 rpm, a Toshiba model) with Auto: left alone (Apple's hold),
   and flash_detected says no.
4. emupod's plain IDENTIFY (no rotation rate, model "openpod disk") with On: the short hold.

`flash.py run NAME` runs one of them. stats() is what probes/flashplay.py uses too: the drive's
STANDBYs, the gap from the last command to each, and the time awake (from the first command after a
STANDBY, or from the start, to the next STANDBY). Exits 1 if a check fails."""
import os, struct, subprocess, sys
from ipod3g import Pod, W, ROOT

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
ISSUE = 0x1416f0                # writes a command to the drive (r0 the ATA object, the byte at +0x1e)
ROW = 18                        # Flash Storage in Settings, after Clicker (8) and the other Frogger rows
SHIFT = 28
IDS = {
    "flash": "w217=1,model=SanDisk SDSSDP064G",
    "hdd": "w217=4200,model=TOSHIBA MK4004GAH",
    "plain": "",
}
RUNS = {                        # name: (IDENTIFY, mode, short hold expected)
    "ui": ("flash", None, True),
    "off": ("flash", 0, False),
    "hdd": ("hdd", 1, False),
    "on": ("plain", 2, True),
}


def rd(p, a):
    return struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]


def prefs(p):
    return rd(p, rd(p, rd(p, 0x43580c) + 0x1c))


def set_mode(p, mode):
    a = prefs(p) + 0xb04
    p.m.mem_write(a, list(struct.pack("<I", rd(p, a) & ~(3 << SHIFT) | mode << SHIFT)))


def mode(p):
    return rd(p, prefs(p) + 0xb04) >> SHIFT & 3


def watch(p):
    p.m.hook_start([ISSUE], 0, 0x1c)


def stats(p, t_from=0):
    """The drive's power from the hook log (watch) and emupod's power log: (standbys, gaps, awake_s)."""
    cmds = [(t, v >> 16 & 0xff) for t, pc, r, v in p.m.hook_log() if pc == ISSUE and t >= t_from]
    standbys = [t for t, c in cmds if c == 0xe0]
    gaps, awake, up, last = [], 0.0, None, None
    for t, c in cmds:
        if c == 0xe0:
            if last is not None:
                gaps.append((t - last) / 1e6)
            if up is not None:
                awake += (t - up) / 1e6
            up = last = None
            continue
        if up is None:
            up = t
        last = t
    if up is not None:
        awake += (p.m.now_us() - up) / 1e6
    return standbys, gaps, awake


def songs(p, lang=True):
    """From the language menu (or the main menu's top): Music > Songs."""
    if lang:
        p.press("select"); p.settle()
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()


def settings_row(p):
    """From the language menu: the main menu, Frogger! (Settings), down to Flash Storage."""
    p.press("select"); p.settle()
    p.scroll(-20); p.settle(); p.scroll(2); p.settle(); p.run(300_000); p.press("select"); p.settle()
    p.scroll(-30); p.settle(); p.run(300_000)
    p.scroll(ROW); p.settle(); p.run(300_000)


def run(name):
    ident, want_mode, short = RUNS[name]
    p = Pod(osos=W + "/osos-frogger.img")
    fails = []
    seen, rpm = p.m.mem_read(SYM["flash_id_seen"], 1)[0], struct.unpack("<H", bytes(p.m.mem_read(SYM["flash_id_rpm"], 2)))[0]
    model = bytes(p.m.mem_read(SYM["flash_id_model"], 40)).split(b"\0")[0].decode("ascii", "replace")
    print("%s: IDENTIFY seen %d, word 217 %d, model %r" % (name, seen, rpm, model))
    if not seen:
        fails.append("%s: flash_id never ran" % name)
    if name == "ui":
        settings_row(p)
        steps, shots = [], [p.settle()]
        for _ in range(3):
            p.press("select"); shots.append(p.settle()); steps.append(mode(p))
            if len(steps) == 1:
                p.shot("flash_auto.png", 1)
        p.shot("flash_settings.png", 1)
        print("Select x3: modes %s, screen changed each time %s" % (steps, all(a != b for a, b in zip(shots, shots[1:]))))
        if steps != [1, 2, 0]:
            fails.append("ui: Select steps %s, not Auto, On, Off" % steps)
        if not all(a != b for a, b in zip(shots, shots[1:])):
            fails.append("ui: the row's value did not change on screen")
        p.press("select"); p.settle()                   # Auto again, for the play
        p.press("menu"); p.settle(); p.scroll(-20); p.settle()     # the main menu, at Music
        want_mode = 1
    else:
        set_mode(p, want_mode)
    if mode(p) != want_mode:
        fails.append("%s: mode %d, not %d" % (name, mode(p), want_mode))
    songs(p, name != "ui")
    watch(p)
    p.press("select", after_us=1_000_000)               # Tone A: one refill fills the cache
    p.run(25_000_000)
    standbys, gaps, awake = stats(p)
    print("%s (mode %d): standbys %d, last command to STANDBY %s s, awake %.2f s" % (
        name, want_mode, len(standbys), ["%.2f" % g for g in gaps], awake))
    if not gaps:
        fails.append("%s: no STANDBY after the refill" % name)
    elif short and not 0.9 <= gaps[-1] <= 1.3:
        fails.append("%s: STANDBY %.2f s after the last command, not about 1 s" % (name, gaps[-1]))
    elif not short and gaps[-1] < 1.9:
        fails.append("%s: STANDBY %.2f s after the last command: Apple's hold was cut" % (name, gaps[-1]))
    for f in fails:
        print("FAIL " + f)
    return fails


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "run":
        sys.exit(1 if run(sys.argv[2]) else 0)
    fails = []
    for name, (ident, _, _) in RUNS.items():
        env = dict(os.environ, EMUPOD_ATA_ID=IDS[ident])
        r = subprocess.run([sys.executable, __file__, "run", name], env=env, capture_output=True, text=True)
        print(r.stdout, end="")
        fails += [l[len("FAIL "):] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
        if r.returncode not in (0, 1):
            fails.append("%s crashed: %s" % (name, r.stderr[-300:]))
    print("FAILED: " + "; ".join(fails) if fails else "ok")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

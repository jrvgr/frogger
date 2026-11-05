"""Flash Storage over a long play: Tone B (12 min, 28.8 MB, bigger than the music cache) from boot,
with the switch Off and On (flash IDENTIFY, word 217 = 1). Prints the drive's STANDBYs, the gap from
the last command to each, the time awake from power-on and the commands sent, per run. Numbers in
docs/power-and-emupod.md, Part D.

    python3 probes/flashplay.py [SECONDS]       # emulated seconds of play, default 760
"""
import os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if len(sys.argv) > 2 and sys.argv[1] == "run":
    from ipod3g import Pod, W
    import flash
    mode, secs = int(sys.argv[2]), int(sys.argv[3])
    p = Pod(osos=W + "/osos-frogger.img", boot_us=1_000_000)
    flash.watch(p)                                  # from 1 s: the boot's own disk use counts too
    while True:                                     # the switch as if saved: set as soon as the prefs are up
        ui = flash.rd(p, 0x43580c)
        if ui and flash.rd(p, ui + 0x1c) and flash.rd(p, flash.rd(p, ui + 0x1c)):
            break
        p.run(50_000)
    print("prefs up at %.2f s" % (p.m.now_us() / 1e6))
    flash.set_mode(p, mode)
    p.run(max(0, 9_000_000 - p.m.now_us()))
    flash.songs(p)
    p.scroll(1)
    p.press("select", after_us=1_000_000)           # Tone B
    for _ in range(secs // 10):
        p.run(10_000_000)
    standbys, gaps, awake = flash.stats(p)
    s = p.m.stats()
    print("mode %d: %.0f s emulated, %d STANDBYs (wakes %d), awake %.1f s, gaps %s, reads %d (%d sectors)" % (
        mode, p.m.now_us() / 1e6, len(standbys), max(len(standbys) - 1, 0), awake,
        " ".join("%.2f" % g for g in gaps), s["ata_reads"], s["ata_sectors_read"]))
    print("standbys at", " ".join("%.1f" % (t / 1e6) for t in standbys))
    sys.exit(0)

secs = sys.argv[1] if len(sys.argv) > 1 else "760"
env = dict(os.environ, EMUPOD_ATA_ID="w217=1,model=SanDisk SDSSDP064G")
runs = [subprocess.Popen([sys.executable, __file__, "run", str(mode), secs], env=env) for mode in (0, 2)]
for r in runs:
    r.wait()

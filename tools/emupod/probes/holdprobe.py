"""Probe: what stock 2.3 draws when Hold goes on, when a key is pressed with Hold on and when Hold
goes off (Frogger image, Lock Cover off, art card, a song playing). Shots hp_*.png in
build/emupod-work; prints how many LCD flushes (0xd2db4) each step made."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ipod3g import Pod, W

p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()
p.press("select", after_us=2_000_000); p.settle(); p.shot("hp_0_np.png")
for _ in range(3):
    p.press("menu"); p.settle()
p.shot("hp_0_menu.png")
for what, step in (("hold on", lambda: p.hold(True)), ("key", lambda: p.press("select", after_us=300_000)),
                   ("later", lambda: p.run(3_000_000)), ("hold off", lambda: p.hold(False))):
    p.m.hook_start([0xd2db4], None, 0)
    step()
    p.run(1_000_000)
    print("%-8s lcd flushes %d" % (what, len(p.m.hook_log())))
    p.shot("hp_%s.png" % what.replace(" ", "_"))

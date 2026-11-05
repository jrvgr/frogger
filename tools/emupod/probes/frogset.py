"""Boot the Frogger RAM image, open Settings, scroll to "Show Hidden", toggle it; screenshots."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E401,E702  tools/emupod: ipod3g, hmcard, itdb
import sys
from ipod3g import Pod, W
p = Pod(osos=W + "/osos-frogger.img", disk=W + "/hide-card.img")
p.press("select"); p.settle(); p.scroll(2); p.press("select"); p.settle()
p.scroll(9); p.settle(); p.shot("fs_0.png", 2)
p.press("select"); p.settle(); p.shot("fs_1.png", 2)
p.press("select"); p.settle(); p.shot("fs_2.png", 2)
print("ok")

"""Frogger image: Settings (label still served?) and Now Playing with the test picture."""
from ipod3g import Pod, W
p = Pod(osos=W + "/osos-frogger.img", disk=W + "/hide-card.img")
p.press("select"); p.settle()
p.scroll(2); p.press("select"); p.settle(); p.scroll(9); p.settle(); p.shot("art_settings.png", 1)
p.press("menu"); p.settle(); p.scroll(-2); p.press("select"); p.settle()     # Music
p.scroll(-6); p.scroll(3); p.press("select"); p.settle()                      # Songs
p.press("select", after_us=2_000_000); p.shot("art_np.png", 2)

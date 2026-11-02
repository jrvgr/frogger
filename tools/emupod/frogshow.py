"""Albums before and after switching Show Hidden on (does the cached index follow?)."""
from ipod3g import Pod, W
p = Pod(osos=W + "/osos-frogger.img", disk=W + "/hide-card.img")
def artists(name):
    p.scroll(-2); p.press("select"); p.settle()       # Music (from Settings row in main menu)
    p.scroll(-6); p.scroll(2); p.press("select"); p.settle(); p.shot(name, 1)   # top, then Albums
    p.press("menu"); p.settle(); p.press("menu"); p.settle(); p.scroll(2)
p.press("select"); p.settle(); p.scroll(2)            # main menu, on Settings
artists("sh_artists_before.png")
p.press("select"); p.settle(); p.scroll(9); p.press("select"); p.settle(); p.shot("sh_on.png", 1)
p.press("menu"); p.settle()
artists("sh_artists_after.png")

"""Frogger image + a card with FroggerArt (mkart.py): play song 1, then Next; Now Playing shots
art_play_1.png and art_play_2.png (the gradient, then the checkerboard)."""
from ipod3g import Pod, W
p = Pod(osos=W + "/osos-frogger.img", disk=W + "/art-card.img")
p.press("select"); p.settle()
p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()      # Music > Songs
p.press("select", after_us=2_000_000); print(p.shot("art_play_1.png", 2))
p.press("next", after_us=2_000_000); print(p.shot("art_play_2.png", 2))

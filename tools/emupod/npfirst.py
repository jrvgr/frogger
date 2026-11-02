"""Frogger image + hmcard.py's card (npf-card.img): Now Playing's popup as the first hold after
boot (no list held yet, so hm.from was never set). Songs > Apple plays; hold Select on Now
Playing > Go to Album: Alpha's songs, not a Playlists popup (Add to Queue, Add to Playlist).
Exits 1 on a wrong one (npf_*.png)."""
import struct, sys
from ipod3g import Pod, W
import hmcard

card = hmcard.make("npf-card.img")
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
p.press("select"); p.settle(); p.press("select"); p.settle()           # English, Music
lib = rd(rd(0x43580c) + 0x1c)
p.scroll(3); p.press("select"); p.settle()                             # Songs
TITLE = {rd(rd(rd(lib + 0x898) + 4 * i) + 0x20): hmcard.BY_TITLE[i] for i in range(rd(lib + 0x89c))}
titles = lambda: [TITLE.get(rd(rd(rd(lib + 0x898) + 4 * i) + 0x20)) for i in range(rd(lib + 0x89c))]
p.press("select", after_us=1_500_000); p.settle(); p.shot("npf_np.png", 1)                   # Apple: Now Playing
p.press("select", hold_us=2_000_000); p.settle(); p.shot("npf_popup.png", 1)
p.scroll(1); p.settle(); p.run(300_000)
p.press("select", after_us=1_500_000); p.settle(); p.shot("npf_album.png", 1)                # Go to Album
ok = titles() == ["Moon", "Apple", "Zebra"]
print("%-44s %s" % ("NP Go to Album, first hold: Alpha's songs", "ok" if ok else "WRONG %s" % titles()))
sys.exit(not ok)

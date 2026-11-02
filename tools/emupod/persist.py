"""Does Show Hidden survive a reboot? Run 'set' (switch it On, idle), then 'check' in a new process."""
import shutil, struct, sys
from ipod3g import Pod, W
card = W + "/persist-card.img"
step = sys.argv[1]
if step == "set":
    shutil.copy(W + "/hide-card.img", card)
p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
if step == "set":
    p.press("select"); p.settle()                       # first run: Language -> English
p.scroll(2); p.press("select"); p.settle(); p.scroll(9); p.settle()   # (saved prefs skip the Language screen)
if step == "set":
    w0 = p.m.stats()["ata_writes"]
    p.press("select"); p.settle(); p.shot("persist_set.png", 1)
    p.press("menu"); p.settle(); p.press("menu"); p.settle()
    p.press("play", hold_us=3_000_000, after_us=10_000_000)   # hold Play: sleep, which is when Apple saves its prefs
    print("disk writes after toggling:", p.m.stats()["ata_writes"] - w0)
else:
    p.shot("persist_check.png", 1)
    print("row drawn; see persist_check.png")

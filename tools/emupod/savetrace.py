"""How stock 2.3's Save Playlist makes and keeps a playlist (for Frogger's own playlists).

    savetrace.py save    # copy the test card to save-card.img (written back); add Tone A to
                         # On-The-Go with the hold menu, then On-The-Go > Save Playlist > confirm,
                         # logging the files opened and the native methods; Playlists after it;
                         # sleep (hold Play) so Apple writes what it keeps; list the card's
                         # iPod_Control/iTunes before and after
    savetrace.py check   # boot save-card.img in a new process: is the playlist still there?

Screenshots st_*.png."""
import shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W

card = W + "/save-card.img"
step = sys.argv[1]


def ls(tag):
    mbr = Path(card).read_bytes()[:512]
    start = struct.unpack_from("<I", mbr, 0x1be + 16 + 8)[0]
    out = subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mdir", "-a", "-i", f"{card}@@{start * 512}",
                          "::/iPod_Control/iTunes"], capture_output=True, text=True).stdout
    print("--- iPod_Control/iTunes,", tag); print(out)


if step == "save":
    shutil.copy(W + "/music-card.img", card)
    ls("before")
p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]


def nav_playlists():                               # from the main menu: Music > Playlists
    p.scroll(-6); p.settle(); p.run(500_000); p.press("select", after_us=1_500_000); p.settle()
    p.scroll(-6); p.settle(); p.run(500_000); p.press("select", after_us=1_500_000); p.settle()


if step == "save":
    p.press("select"); p.settle()                  # first run: Language -> English
    p.press("select"); p.settle(); p.scroll(3); p.press("select"); p.settle()      # Music > Songs
    p.press("select", hold_us=2_000_000); p.settle()
    p.scroll(1); p.settle(); p.run(500_000); p.press("select", after_us=1_500_000); p.settle()
    for _ in range(2):
        p.press("menu", after_us=1_500_000); p.settle()
    nav_playlists()
    p.press("select", after_us=1_500_000); p.settle(); p.shot("st_otg.png", 1)       # On-The-Go
    p.scroll(2); p.settle(); p.run(500_000)
    p.press("select", after_us=1_500_000); p.settle(); p.shot("st_popup.png", 1)     # Save Playlist
    p.scroll(1); p.settle(); p.run(500_000)
    p.m.hook_start([0x403fc, 0xd292c], None, 0)
    p.press("select", after_us=2_000_000); p.settle(); p.shot("st_saved.png", 1)     # confirm
    for t, pc, r, _ in p.m.hook_log():
        if pc == 0x403fc:
            name = bytes(p.m.mem_read(r[0] + 4, 64)).split(b"\0")[0]
            print("open %r flags %#x kind %#x (read after the fact)" % (name, r[2], r[3]))
        else:
            print("0xd292c(r0=%x r1=%x)" % (r[0], r[1]))
    p.m.hook_start([], None, 0)
    for _ in range(3):
        p.press("menu", after_us=1_500_000); p.settle()
    p.shot("st_playlists.png", 1)
    lib = rd(rd(0x43580c) + 0x1c)
    print("lib+0x48 (On-The-Go) =", hex(rd(lib + 0x48)), "count", rd(rd(rd(lib + 0x48) + 0x24) + 0x2c))
    for _ in range(3):
        p.press("menu", after_us=1_500_000); p.settle()
    w0 = p.m.stats()["ata_writes"]
    p.press("play", hold_us=3_000_000, after_us=10_000_000)       # sleep: Apple saves what it keeps
    print("disk writes while going to sleep:", p.m.stats()["ata_writes"] - w0)
    del p
    ls("after")
else:
    nav_playlists()
    p.press("select", after_us=1_500_000); p.settle()            # (the second Select gets lost)
    p.shot("st_check.png", 1)
    print("see st_check.png")

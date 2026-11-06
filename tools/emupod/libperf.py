"""Frogger image on a card with a real library (a copy of an iPod's iPod_Control/iTunes: iTunesDB,
and FroggerArt, FroggerHidden, FroggerSkips if there): the cost of browsing with Settings › Hold
Menu on and off, and of the hold menu's actions. For each step: the CPU instructions that ran (not
idle), the VM steps, calls of 0x58440 (the library lists' predicate), disk reads, and disk reads on
the UI's thread (the disk asleep first, as on a device after a few seconds: a read then wakes it,
and the UI waits for that). No audio is needed for browsing. Nothing of the library is kept but the
card, build/emupod-work/libperf-card.img.

    libperf.py DIR            # DIR: the copied iTunes folder (keep a private library out of the repo)
"""
import argparse, shutil, struct, sys
from pathlib import Path
from ipod3g import Pod, W
import hmcard

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("library", help="a copy of iPod_Control/iTunes (iTunesDB at least)")
a = ap.parse_args()
lib_dir = Path(a.library)
card = W + "/libperf-card.img"
shutil.copy(W + "/music-card.img", card)
for name in ("iTunesDB", "FroggerArt", "FroggerHidden", "FroggerSkips"):
    if (lib_dir / name).exists():
        hmcard.mtools(card, "mcopy", "-o", str(lib_dir / name), "::/iPod_Control/iTunes/" + name)

p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
rd = lambda x: struct.unpack("<I", bytes(p.m.mem_read(x, 4)))[0]
p.press("select"); p.settle()                                      # a language (the card has no prefs)
lib = rd(rd(0x43580c) + 0x1c)
VM, PRED, READ = 0x9bab0, 0x58440, 0xc788c


def hold_menu(on):          # Settings › Hold Menu: prefs bit 20 set is Off (settings.h)
    prefs = rd(lib)
    f = rd(prefs + 0xb04)
    p.m.mem_write(prefs + 0xb04, struct.pack("<I", f & ~(1 << 20) if on else f | (1 << 20)))


def step(tag, f, asleep=True):
    if asleep:
        p.run(4_000_000)    # the disk goes to sleep (STANDBY after Apple's holds)
    p.m.hook_start([VM, PRED, READ])
    s0 = p.m.stats(); f(); s1 = p.m.stats()
    log = p.m.hook_log()
    busy = (s1["cpu_instr"] - s1["cpu_skipped"]) - (s0["cpu_instr"] - s0["cpu_skipped"])
    ui = {r[13] >> 16 for t, pc, r, v in log if pc == VM}
    n = {k: sum(1 for t, pc, r, v in log if pc == k) for k in (VM, PRED, READ)}
    uir = sum(1 for t, pc, r, v in log if pc == READ and r[13] >> 16 in ui)
    print("%-40s %11d instr  vm %6d  0x58440 %6d  reads %4d  on the UI %4d" % (tag, busy, n[VM], n[PRED], n[READ], uir),
          flush=True)


def menu(): p.press("menu", after_us=1_500_000); p.settle()
def sel(): p.press("select", after_us=1_500_000); p.settle()
def to(n): p.scroll(-40); p.scroll(n); p.settle(); p.run(300_000)
def hold(): p.press("select", hold_us=2_000_000); p.settle()
def pick(n): to(n); sel()       # a popup row (rows shown, from the top)


def music(n):               # from anywhere: the main menu, Music, its row n (2 Albums, 3 Songs)
    for _ in range(4):
        p.press("menu", after_us=800_000)
    p.settle(); to(0); sel(); to(n)


print("library: %d songs" % rd(lib + 0x89c) if rd(lib + 0x89c) else "library loaded")
for on in (False, True):
    hold_menu(on)
    t = "Hold Menu " + ("on " if on else "off")
    music(2); step(t + ": open Albums", sel)
    step(t + ": scroll 20", lambda: (p.scroll(20), p.settle(), p.run(300_000)))
    step(t + ": Menu", menu)
    music(3); step(t + ": open Songs", sel)
    step(t + ": scroll 20", lambda: (p.scroll(20), p.settle(), p.run(300_000)))
    step(t + ": hold a song", hold)
    if on:
        step(t + ": Go to Album", lambda: pick(3))
        step(t + ": Menu (back to Songs)", menu)
        step(t + ": hold a song", hold)
        step(t + ": Hide", lambda: pick(5))
    step(t + ": Menu", menu)
    step(t + ": Menu (main)", menu)
    step(t + ": Select (Music)", sel)

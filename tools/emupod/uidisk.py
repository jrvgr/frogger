#!/usr/bin/env python3
"""No disk I/O on the UI thread. On an iPod the disk sleeps most of the time, and an SD or CF
adapter can stall for seconds: a read or write the UI waits for is a frozen wheel, or a ~10 s
freeze on Menu. emupod's disk answers at once, so it never shows. This walks the UI on a big
library (library.py) and flags every ATA command issued on the UI thread while a key is handled.

How: emupod logs (hook_start) every command written to the drive (0x141710, the command register
store; 0xddae0, SET FEATURES written straight) with its sp, the entries of the file and block
calls above it (fw_open/fw_read/fw_write/... in docs/addresses.md, the block read 0xc7720 and the
dispatcher 0x9e83c) with their lr, and the UI's quarter-second tick (0xe9664, always on the UI
thread) for the UI stack's sp. A command whose sp is on the UI stack is the UI's; its call site is
the lr of the outermost hooked entry above it on the same stack.

The same walk runs on stock 2.3 (the keys Frogger's popups add are skipped). Stock reads on its UI
thread too (a song's start, the On-The-Go file); a call site stock uses is allowed. A UI-thread
command from any other call site, or from Frogger's code (the payload, 0x1e00000 up), fails.

The scenarios (SCENARIOS), each a boot of its own: browse (Music > Songs, scroll; hold Select >
Menu; a song plays, Next, hold Select > Menu; back to Music, hold Menu > Shuffle > Menu; the main
menu), and the hold menu's rows that save: queue (Add to Queue), hide (Hide), playlist (Add to
Playlist > a playlist). Stock walks browse once per library (Frogger's popup keys skipped); its
call sites are cached in build/emupod-work.

    tools/emupod/uidisk.py                  # every scenario; exit 1 on a UI-thread command stock doesn't issue
    tools/emupod/uidisk.py hide playlist    # some
    tools/emupod/uidisk.py --run stock browse   # one image's log as JSON
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import library  # noqa: E402
from perf import quiet  # noqa: E402

CMD = {0x141710: "cmd", 0xddae0: "setfeatures"}
TICK = 0xe9664
ENTRIES = {0x403fc: "fw_open", 0x404ec: "fw_read", 0x4069c: "fw_seek", 0x40110: "fw_close", 0x40474: "fw_create",
           0x407e8: "fw_write", 0x53a24: "make_path", 0x7b3bc: "find_path", 0xf4ad4: "write_otg_file",
           0xc5a90: "read_otg_file", 0xc7720: "block_read", 0x9e83c: "ata_dispatch"}
PAYLOAD = 0x1e00000
UI_BELOW, UI_ABOVE = 0x4000, 0x800        # the UI stack: from the lowest tick sp down this far, up to the highest + this


def symbols():
    sym = {}
    path = library.ROOT / "build/payload/payload.sym"
    if path.exists():
        for line in open(path):
            f = line.split()
            if len(f) == 3 and f[1] in "tT":
                sym[int(f[0], 16)] = f[2]
    return sorted(sym.items())


def where(addr, syms):
    if addr < PAYLOAD:
        return "%#x" % addr
    best = None
    for a, n in syms:
        if a <= addr:
            best = (a, n)
        else:
            break
    return "%s+%#x (%#x)" % (best[1], addr - best[0], addr) if best else "%#x" % addr


SCENARIOS = {
    "browse": "Menus, lists, hold Select > Menu, Now Playing (play, Next, its hold menu), quick settings > Shuffle",
    "queue": "Hold Select > Add to Queue",
    "hide": "Hold Select > Hide",
    "playlist": "Hold Select > Add to Playlist > a playlist",
}


def walk(stock, scenario):
    """One scenario's keys, the hook log on for them only. {"windows": [(tag, t0, t1)], "log": [...]}"""
    p = library.boot(stock=stock)
    quiet(p)
    windows = []

    def key(tag, k, hold_us=150_000, frogger=False, playing=False):
        if frogger and stock:
            return
        t0, scr = p.m.now_us(), p.screen()
        p.press(k, hold_us=hold_us, after_us=200_000)
        quiet(p, cpu=not playing, start=scr if playing else None)
        windows.append((tag, t0, p.m.now_us()))

    def scroll(tag, n, playing=False):
        t0 = p.m.now_us()
        p.scroll(n)
        quiet(p, cpu=not playing)
        windows.append((tag, t0, p.m.now_us()))

    hold = 1_500_000
    if scenario != "browse":                     # Songs, unwatched
        for k in ("select", None, "select"):
            if k:
                p.press(k)
            else:
                p.scroll(3)
            quiet(p)
        p.scroll(5); quiet(p)
    p.m.hook_start(sorted(set(CMD) | set(ENTRIES) | {TICK}), None, 0)
    if scenario == "browse":
        key("Music", "select")
        scroll("scroll to Songs", 3)
        key("Songs", "select")
        scroll("scroll Songs", 5)
        key("hold Select (popup)", "select", hold)
        key("Menu: popup closes", "menu", frogger=True)
        key("play", "select", playing=True)
        key("Next", "next", playing=True)
        key("hold Select on Now Playing", "select", hold, frogger=True, playing=True)
        key("Menu: popup closes", "menu", frogger=True, playing=True)
        key("Menu: back to Songs", "menu", playing=True)
        key("Menu: back to Music", "menu", playing=True)
        key("hold Menu (quick settings)", "menu", hold, playing=True)
        if not stock:
            scroll("scroll to Shuffle", 1, playing=True)
        key("Shuffle", "select", frogger=True, playing=True)
        key("Menu: quick settings close", "menu", frogger=True, playing=True)
        key("Menu: the main menu", "menu", playing=True)
    else:
        key("hold Select (popup)", "select", hold)
        row = {"queue": 0, "playlist": 2, "hide": 5}[scenario]
        if row:
            scroll("scroll to the row", row)
        key(SCENARIOS[scenario].split("> ", 1)[1].split(" >")[0], "select")
        if scenario == "playlist":
            scroll("scroll to a playlist", 1)
            key("pick a playlist", "select")
        key("Menu", "menu")
        scroll("scroll Songs", 3)
    log = [(t, pc, r[13], r[14]) for t, pc, r, _ in p.m.hook_log()]
    p.m.hook_start([], None, 0)
    return {"windows": windows, "log": log, "full": len(log) >= 50_000}


def analyse(run):
    """[(window tag, time, sp, call site lr, entry name, on the UI)] for every command in a key window."""
    ticks = [sp for _, pc, sp, _ in run["log"] if pc == TICK]
    lo, hi = min(ticks) - UI_BELOW, max(ticks) + UI_ABOVE
    out, recent = [], []
    for t, pc, sp, lr in run["log"]:
        if pc in ENTRIES:
            recent.append((t, pc, sp, lr))
            recent = recent[-256:]
        elif pc in CMD:
            # the outermost call on this stack in the last 2 s: the highest sp, the latest of those
            same = [e for e in recent if sp <= e[2] <= sp + 0x2000 and e[0] >= t - 2_000_000]
            top = max(same, key=lambda e: (e[2], e[0])) if same else (t, pc, sp, lr)
            tag = next((w[0] for w in run["windows"] if w[1] <= t <= w[2]), None)
            if tag:
                out.append((tag, t, sp, top[3], ENTRIES.get(top[1], CMD.get(top[1])), lo <= sp <= hi))
    return out, (lo, hi)


def child(which, scenario):
    r = subprocess.run([sys.executable, __file__, "--run", which, scenario], capture_output=True, text=True, cwd=HERE)
    if r.returncode:
        sys.exit(f"uidisk.py --run {which} {scenario} failed:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def stock_sites():
    """The call sites stock 2.3 issues UI-thread disk commands from on the browse walk, made once per
    library and firmware (cached in build/emupod-work, under a lock: pytest -n runs scenarios at once)."""
    import fcntl
    path = library.W / f"uidisk-stock-{library.label()}.json"
    key = "%s %s" % (Path(library.card()).stat().st_mtime, library.ROOT.joinpath("build/fw/osos.img").stat().st_mtime)
    with open(library.W / ".uidisk.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists() and json.loads(path.read_text()).get("key") == key:
            return json.loads(path.read_text())
        cmds, ui = analyse(child("stock", "browse"))
        got = {"key": key, "ui": ui, "commands": len(cmds), "on_ui": sum(c[5] for c in cmds),
               "allowed": sorted({lr for _, _, _, lr, _, on in cmds if on and lr < PAYLOAD})}
        path.write_text(json.dumps(got))
        return got


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", choices=["stock", "frogger"], help="one image's log as JSON")
    ap.add_argument("scenarios", nargs="*", default=list(SCENARIOS), help=", ".join(SCENARIOS))
    a = ap.parse_args()
    for sc in a.scenarios:
        if sc not in SCENARIOS:
            ap.error("no scenario %r (%s)" % (sc, ", ".join(SCENARIOS)))
    if a.run:
        print(json.dumps(walk(a.run == "stock", a.scenarios[0])))
        return
    library.card()
    stock = stock_sites()
    allowed = set(stock["allowed"])
    with ThreadPoolExecutor(4) as pool:
        runs = list(pool.map(lambda sc: child("frogger", sc), a.scenarios))
    syms = symbols()
    print("stock 2.3, the browse walk: UI stack %#x..%#x, %d commands in key windows, %d on the UI thread; "
          "its UI-thread call sites (allowed): %s" % (*stock["ui"], stock["commands"], stock["on_ui"],
                                                       ", ".join("%#x" % x for x in sorted(allowed)) or "none"))
    lines, failed = ["### Disk I/O on the UI thread, %s library" % library.label(), "",
                     "| Scenario | Disk commands on the UI thread | Call sites (lr), through |", "| --- | ---: | --- |"], []
    for sc, run in zip(a.scenarios, runs):
        cmds, ui = analyse(run)
        bad = {}
        for tag, t, sp, lr, entry, on in cmds:
            if on and (lr >= PAYLOAD or lr not in allowed):
                bad.setdefault((tag, lr, entry), 0)
                bad[(tag, lr, entry)] += 1
        print("%s: UI stack %#x..%#x, %d commands in key windows, %d on the UI thread from new call sites" % (
            sc, *ui, len(cmds), sum(bad.values())))
        for (tag, lr, entry), n in bad.items():
            print("  %-28s %3d  lr %s through %s" % (tag, n, where(lr, syms), entry))
        if bad or run["full"]:
            failed.append(sc)
        sites = sorted({(lr, entry) for _, lr, entry in bad})
        lines.append("| %s | %s | %s |" % (SCENARIOS[sc], sum(bad.values()) or "none",
                                           "; ".join("%s, %s" % (where(lr, syms), e) for lr, e in sites) or ""))
    text = "\n".join(lines) + "\n\nOnly call sites stock 2.3 doesn't use on its UI thread count (stock: %s).\n" % (
        ", ".join("%#x" % x for x in sorted(allowed)) or "none")
    (library.W / ("uidisk-%s-%s.md" % (library.label(), "-".join(a.scenarios)))).write_text(text)
    if failed:
        print("FAILED: disk I/O on the UI thread in " + ", ".join(failed))
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    os.chdir(HERE)
    main()

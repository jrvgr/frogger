#!/usr/bin/env python3
"""The UI keeps answering while the disk stalls. An SD or CF adapter can stop answering for
seconds (a supply dip, a slow card); Apple's player reads on its own task, so stock 2.3's wheel and
menus go on, and Frogger's must too. emupod's disk never stalls unless told to: this tells it to
(emupod's ata_hang, the fault diskhang.py uses) at a random moment while a song loads on a big
library (library.py), then checks, while the drive is still hung, that

- Menu leaves Now Playing within RESPOND_MS of emulated time (plus the click's 150 ms),
- a wheel step moves Songs' highlight within RESPOND_MS,
- holding Select opens the hold menu, and Menu closes it (Frogger),
- the hold menu's rows that save (--rows: queue, Add to Queue, the default; hide; playlist, Add to
  Playlist > a playlist) leave the wheel answering within RESPOND_MS (Frogger),

and that once the stall is over the drive answers again (stock 2.3 never gets it back: disk.c's
reset does, docs/power-and-emupod.md). A trial is one boot (emupod's audio stops after a song's
first seconds, so only the first song loads): a random song, the hang after a random number of
reads (0..60, so anywhere in the music cache's refill), for a random time (3, 6 or 12 s, or until
a reset). A trial whose hang never fired is reported and doesn't count.

    tools/emupod/stall.py [--trials 3] [--seed 1]   # trials in parallel; exit 1 if the UI didn't answer
    tools/emupod/stall.py --trial 5                 # one trial, its own seed
    tools/emupod/stall.py --rows hide,playlist      # those rows during the stall
    tools/emupod/stall.py --stock --trial 5         # stock 2.3, for comparison (no hold menu, no recovery)
    EMUPOD_STALL_SEED=7 pytest -m stall             # other seeds (pytest --stall-seed 7)
"""
import argparse, os, random, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import library  # noqa: E402
from perf import quiet  # noqa: E402

RESPOND_MS = 500
fails = []


def responds(p, wheel=True, limit_ms=RESPOND_MS):
    """Emulated ms until the screen changes after a wheel step down (or a Menu click), None if it
    didn't within limit_ms (plus the click). The wheel steps every 20 ms (2.3 wants 4-6 a row)."""
    before, t0 = p.screen(), p.m.now_us()
    if not wheel:
        p.press("menu", after_us=0)
    while p.m.now_us() - t0 < limit_ms * 1000 + (0 if wheel else 150_000):
        if wheel:
            p.wheel(-1, gap_us=0, after_us=20_000)
        else:
            p.run(20_000)
        if p.screen() != before:
            return (p.m.now_us() - t0) / 1000
    return None


def check(what, ok, detail=""):
    print("  %-56s %s %s" % (what, "ok" if ok else "WRONG", detail))
    if not ok:
        fails.append(what)


ROWS = {"queue": ("Add to Queue", 0), "hide": ("Hide", 5), "playlist": ("Add to Playlist", 2)}


def trial(seed, stock, rows):
    rng = random.Random(seed)
    skip, ms, row = rng.randint(0, 60), rng.choice([0, 3000, 6000, 12000]), rng.randint(0, 40)
    p = library.boot(stock=stock)
    quiet(p)
    p.press("select"); quiet(p); p.scroll(3); quiet(p); p.press("select"); quiet(p)    # Music > Songs
    if row:
        p.scroll(row); quiet(p)
    p.m.ata_hang(skip, ms)
    p.press("select", after_us=0)                           # the song: its refill hits the hang
    t0 = p.m.now_us()
    while not p.m.stats()["ata_hangs"] and p.m.now_us() - t0 < 15_000_000:
        p.run(20_000)
    if not p.m.stats()["ata_hangs"]:
        print("trial %d: the hang (after %d reads) never fired; not counted" % (seed, skip))
        return False
    print("trial %d: song %d; the drive hung %.0f ms after Select (after %d reads), %s" % (
        seed, row + 1, (p.m.now_us() - t0) / 1000, skip, "for %d ms" % ms if ms else "until a reset"))
    t1 = p.m.now_us()
    p.run(300_000)
    t = responds(p, wheel=False)
    check("Menu leaves Now Playing during the stall", t is not None, "(%s ms)" % t)
    p.run(300_000)
    t = responds(p)
    check("a wheel step moves the highlight during the stall", t is not None, "(%s ms)" % t)
    if not stock:
        before = p.screen()
        p.press("select", hold_us=1_500_000, after_us=300_000)
        opened = p.screen() != before
        check("hold Select opens the hold menu during the stall", opened)
        if opened:
            t = responds(p, wheel=False)
            check("Menu closes it", t is not None, "(%s ms)" % t)
        for name, row in (ROWS[r] for r in rows):          # the hold menu's rows that save
            p.press("select", hold_us=1_500_000, after_us=300_000)
            if row:
                p.scroll(row)
            if name == "Add to Playlist":
                p.press("select", after_us=300_000)
                p.scroll(1)                                 # the picker: the first playlist
                p.shot("stall_%d_picker.png" % seed, 1)
            p.press("select", after_us=0)
            t0 = p.m.now_us()
            p.run(300_000)
            t = responds(p)
            check("hold Select > %s: the wheel answers within %d ms after" % (name, RESPOND_MS), t is not None,
                  "(%s)" % ("%.0f ms" % (t + (p.m.now_us() - t0) / 1000 - t) if t is not None else "no"))
    s = p.m.stats()
    still = s["ata_resets"] == 0 and (ms == 0 or p.m.now_us() - t1 < ms * 1000)
    print("  the drive was still hung after the checks: %s" % ("yes" if still else "no (the stall was over sooner)"))
    p.run(40_000_000)                                       # the stall ends, or disk.c resets the drive
    log = p.m.ata_log()
    check("after the stall: the drive answers again", log[-1][4] == "ok",
          "(last command %#x: %s; %d resets)" % (log[-1][0], log[-1][4], p.m.stats()["ata_resets"]))
    p.shot("stall_%d_%s.png" % (seed, "stock" if stock else "frogger"), 1)
    return True


def child(seed, stock, rows):
    r = subprocess.run([sys.executable, __file__, "--trial", str(seed), "--rows", ",".join(rows)] + (["--stock"] if stock else []),
                       capture_output=True, text=True, cwd=HERE)
    return r.returncode, r.stdout + r.stderr[-2000:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--seed", type=int, default=int(os.environ.get("EMUPOD_STALL_SEED", "1")))
    ap.add_argument("--trial", type=int, help="run one trial, with this seed")
    ap.add_argument("--rows", default="queue", help="the hold menu rows to use during the stall: %s" % ", ".join(ROWS))
    ap.add_argument("--stock", action="store_true", help="stock 2.3, for comparison")
    a = ap.parse_args()
    rows = [r for r in a.rows.split(",") if r]
    for r in rows:
        if r not in ROWS:
            ap.error("no row %r (%s)" % (r, ", ".join(ROWS)))
    if a.trial is not None:
        counted = trial(a.trial, a.stock, rows)
        print("FAILED: " + "; ".join(fails) if fails else "ok" if counted else "not counted")
        sys.exit(1 if fails else 0 if counted else 2)
    library.card()
    seeds = range(a.seed * 100, a.seed * 100 + a.trials)
    with ThreadPoolExecutor(min(a.trials, 4)) as pool:
        results = list(pool.map(lambda s: child(s, a.stock, rows), seeds))
    bad = counted = 0
    for code, out in results:
        print(out, end="")
        bad += code not in (0, 2)
        counted += code == 0
    print("%d trials, %d stalled and checked, %d failed" % (a.trials, counted + bad, bad))
    if bad or not counted + bad:
        print("FAILED")
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    os.chdir(HERE)
    main()

#!/usr/bin/env python3
"""The speed budget: how many ARM instructions the iPod's CPU runs for everyday UI actions, stock
2.3 (build/fw/osos.img: what a Menu-held boot or a skipped loader runs) against Frogger (every switch
at its default: all on), on a big library (library.py: the generated card unless FROGGER_LIBRARY
says otherwise). emupod's clock is fast and has no cache misses, so time says little; instructions
are what a 3G spends, and they come out the same on every run.

Each action is measured from the key going down until the CPU is idle and the screen has stopped
changing (quiet()), so drawing, list building and anything the key starts are in it, and so is the
idle cost of that stretch (the ticks, about 0.15 M a second). While a song plays emupod's CPU never
idles (its audio stops after 2000 samples and the player spins), so there it's until the screen
has changed and settled. The same keys go to both: where Frogger
opens a popup (hold Select, hold Menu) stock does its own thing (adds to On-The-Go, the backlight),
and Frogger's popup is closed with Menu, measured on its own.

The budget, per action, in perf-baseline.json ("budget"): Frogger may run at most `ratio` times
stock's instructions plus `slack` (default 1.25 and 0.65 M, 50 ms of a 13 MHz CPU); an action stock
has no match for has a `cap` instead. Over budget exits 1. The table (build/emupod-work/perf-LIB.md,
also printed) shows each action, stock, Frogger, the overhead and the change from the stored
baseline, which only reports.

    tools/emupod/perf.py                   # both images, the table, exit 1 over budget
    tools/emupod/perf.py --update          # the same, and store the numbers as the baseline
    tools/emupod/perf.py --run frogger     # one image's numbers as JSON (what the others call)
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import library  # noqa: E402

BASELINE = HERE / "perf-baseline.json"
MHZ = 13                        # emupod's CPU: 13 instructions a microsecond
DEFAULT = {"ratio": 1.25, "slack": 650_000}
# (name, what) in the order they run; frogger_only: stock does something else, so it has a cap.
ACTIONS = [
    ("select_music", "Select: the main menu into Music"),
    ("select_songs", "Select: into Songs (every song)"),
    ("scroll_10", "Scroll 10 rows down Songs"),
    ("menu_back", "Menu: Songs back to Music"),
    ("select_albums", "Select: into Albums"),
    ("albums_back", "Menu: Albums back to Music"),
    ("select_artists", "Select: into Artists"),
    ("artists_back", "Menu: Artists back to Music"),
    ("hold_select", "Hold Select on a song (Frogger: the hold menu; stock: On-The-Go)"),
    ("popup_close", "Menu: the hold menu closes (Frogger only)"),
    ("menu_back_after_hold", "Menu: Songs back to Music, after a hold"),
    ("hold_menu", "Hold Menu (Frogger: quick settings; stock: the backlight)"),
    ("qs_close", "Menu: quick settings close (Frogger only)"),
    ("music_back_after_qs", "Menu: Music back to the main menu, after quick settings"),
    ("play", "Select on a song: Now Playing"),
    ("song_change", "Next: the song changes"),
    ("np_back", "Menu: Now Playing back to Songs"),
]
FROGGER_ONLY = {"popup_close", "qs_close"}


def quiet(p, step_us=50_000, busy=60_000, calm=4, limit_us=20_000_000, cpu=True, start=None):
    """Run until the CPU is idle (under `busy` instructions a step, `calm` steps in a row) with the
    screen unchanged: a list can take seconds to build without drawing, so the screen alone isn't
    enough. cpu=False: the screen alone (while a song plays emupod's CPU never idles: its audio
    stops after 2000 samples and the player spins); start: a screen to wait to see change first.
    Returns the emulated µs it took."""
    t0 = p.m.now_us()
    last, scr, n = p.m.stats()["cpu_instr"], p.screen(), 0
    while start is not None and scr == start and p.m.now_us() - t0 < limit_us:
        p.run(step_us)
        scr = p.screen()
    while n < calm and p.m.now_us() - t0 < limit_us:
        p.run(step_us)
        now, s = p.m.stats()["cpu_instr"], p.screen()
        n = n + 1 if (now - last < busy or not cpu) and s == scr else 0
        last, scr = now, s
    return p.m.now_us() - t0


def measure(stock):
    """{action: instructions} for one image, in a process of its own (one emupod per process)."""
    p = library.boot(stock=stock)
    quiet(p)
    out = {}

    def act(name, f, playing=False):
        before, t0, scr = p.m.stats()["cpu_instr"], p.m.now_us(), p.screen()
        f()
        quiet(p, cpu=not playing, start=scr if playing else None)
        out[name] = [p.m.stats()["cpu_instr"] - before, p.m.now_us() - t0]
        p.shot("perf_%s_%s.png" % ("stock" if stock else "frogger", name), 1)

    def key(k, hold_us=150_000):
        return lambda: p.press(k, hold_us=hold_us, after_us=200_000)

    def settled_scroll(n):
        p.scroll(n); quiet(p)

    act("select_music", key("select"))
    settled_scroll(3)                                     # Playlists, Artists, Albums, Songs
    act("select_songs", key("select"))
    act("scroll_10", lambda: p.scroll(10))
    act("menu_back", key("menu"))
    settled_scroll(-1)
    act("select_albums", key("select"))
    act("albums_back", key("menu"))
    settled_scroll(-1)
    act("select_artists", key("select"))
    act("artists_back", key("menu"))
    settled_scroll(2)
    p.press("select"); quiet(p)                         # Songs, on the row it was left on
    act("hold_select", key("select", hold_us=1_500_000))
    if not stock:
        act("popup_close", key("menu"))
    act("menu_back_after_hold", key("menu"))
    act("hold_menu", key("menu", hold_us=1_500_000))
    if not stock:
        act("qs_close", key("menu"))
    else:
        p.press("menu", hold_us=1_500_000); quiet(p)    # the backlight back as it was
    act("music_back_after_qs", key("menu"))
    p.press("select"); quiet(p)                         # Music
    p.press("select"); quiet(p)                         # Songs (the row it was left on)
    act("play", key("select"), playing=True)
    act("song_change", key("next"), playing=True)
    act("np_back", key("menu"), playing=True)
    return out


def budget_of(name, budgets):
    b = dict(DEFAULT)
    b.update(budgets.get(name, {}))
    return b


def limit(name, stock, budgets):
    b = budget_of(name, budgets)
    if "cap" in b:
        return b["cap"]
    return int(stock * b["ratio"] + b["slack"])


def compare(stock, frog, saved):
    """(markdown lines, [actions over budget]). stock, frog: {action: [instructions, µs]}."""
    budgets = saved.get("budget", {})
    base = saved.get("frogger", {})
    m = lambda n: "%.1f M" % (n / 1e6)
    pct = lambda a, b: "%+d %%" % round(100 * (a - b) / b) if b else "n/a"
    lines = ["| Action | Stock | Frogger | Overhead | Budget | Time stock / Frogger | vs baseline |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    over = []
    for name, what in ACTIONS:
        if name not in frog:
            continue
        f, fus = frog[name]
        s, sus = stock.get(name, (0, 0))
        lim = limit(name, s, budgets)
        ok = f <= lim
        if not ok:
            over.append(name)
        b = base.get(name, (0, 0))[0]
        lines.append("| %s | %s | %s | %s | %s%s | %s / %.2f s | %s |" % (
            what, m(s) if s else "n/a", m(f), pct(f, s), m(lim), "" if ok else " **over**",
            "%.2f s" % (sus / 1e6) if s else "n/a", fus / 1e6, pct(f, b) if b else "new"))
    return lines, over


def child(which):
    r = subprocess.run([sys.executable, __file__, "--run", which], capture_output=True, text=True, cwd=HERE)
    if r.returncode:
        sys.exit(f"perf.py --run {which} failed:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", choices=["stock", "frogger"])
    ap.add_argument("--update", action="store_true", help="store this run's numbers as the baseline")
    a = ap.parse_args()
    if a.run:
        print(json.dumps(measure(a.run == "stock")))
        return
    library.card()                                        # made once, before the two runs share it
    with ThreadPoolExecutor(2) as pool:
        stock, frog = pool.map(child, ["stock", "frogger"])
    lib = library.label()
    # your own library's numbers stay in build/, out of the tracked file
    path = BASELINE if lib == "generated" else library.W / f"perf-baseline-{lib}.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    if lib != "generated" and BASELINE.exists():
        saved.setdefault("budget", json.loads(BASELINE.read_text()).get("budget", {}))
    lines, over = compare(stock, frog, saved)
    title = "### Speed budget: instructions per action, %s library" % lib
    foot = ["", "Instructions the CPU runs from the key until it's idle and the screen has settled (emupod runs "
            "%d a µs: 1 M is %.0f ms); the time is emulated. Budget: stock × ratio + slack, or a cap "
            "(tools/emupod/perf-baseline.json). Over budget: %s." % (MHZ, 1000 / MHZ, ", ".join(over) or "none")]
    text = "\n".join([title, ""] + lines + foot) + "\n"
    print(text)
    (library.W / f"perf-{lib}.md").write_text(text)
    if a.update:
        saved.update({"stock": stock, "frogger": frog})
        if lib != "generated":
            saved.pop("budget", None)
        path.write_text(json.dumps(saved, indent=1, sort_keys=True) + "\n")
        print("wrote", path)
    if over:
        print("FAILED: over budget: " + ", ".join(over))
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    os.chdir(HERE)
    main()

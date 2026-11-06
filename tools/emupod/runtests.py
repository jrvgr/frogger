#!/usr/bin/env python3
"""Run the emupod scripts that check Frogger (each exits 1 on a wrong step), a few at a time, on a
Frogger image of the loader just built. Needs tools/emupod/setup.sh and mkcards.py done, and
build/fw/osos.img (tools/fwtool.py extract). Logs go to build/emupod-work/logs/. pytest runs the same
checks (tests/test_emupod.py: `pytest -n auto -m emupod`); a new check goes in FEATURES for both.

    tools/emupod/runtests.py [-j 4] [SCRIPT...]    # default: all of CHECKS
"""
import argparse, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "build/emupod-work/logs"
# Each check: what it covers and the payload files it goes through. CI's summary shows them, and
# the payload files no check goes through (tools/emupod/README.md has the same table).
FEATURES = {
    "holdmenu2": ("Hold menu: Go to Album/Artist, Play Album Next, Hide", ["holdmenu.c", "browse.c", "hide.c"]),
    "upnext": ("Up Next: open, remove, play from, clear", ["queue.c", "holdmenu.c", "browse.c"]),
    "unhide": ("Show (un-hide), Settings › Show Hidden, FroggerHidden", ["hide.c", "settings.c"]),
    "quicksettings": ("Quick settings (hold Menu), its Sleep", ["holdmenu.c"]),
    "queuerow": ("The main menu's Queue row", ["queue.c"]),
    "holdrow": ("Add to Queue on any row, hidden songs above it", ["holdmenu.c", "queue.c", "hide.c"]),
    "npfirst": ("Hold menu on Now Playing as the first hold", ["holdmenu.c", "nowplaying.c"]),
    "npslide": ("Now Playing: the page slide", ["nowplaying.c"]),
    "npscrub": ("Now Playing: back to the cover page after a scrub", ["nowplaying.c"]),
    "resume": ("Resume Mixes", ["resume.c"]),
    "readonly": ("Nothing writes Apple's image (read-only on a device)", ["queue.c", "playlist.c"]),
    "skips": ("Skip counts, FroggerSkips", ["skips.c"]),
    "heaptop": ("The payload's memory stays free of Apple's heap", []),
    "battery": ("Battery percentage", ["battery.c"]),
    "switches": ("Settings' feature switches, each off", ["settings.c"]),
    "diskhang": ("The disk coming back after it stops answering (SRST, re-init, retry)", ["disk.c"]),
    "lockcover": ("Lock Cover: Hold on, Hold off, the switch off", ["lock.c"]),
    "flash": ("Settings › Flash Storage: the shorter disk hold, a hard drive left alone in Auto", ["flash.c"]),
    "dbid": ("Frogger's files after another app's sync: hides, skips, covers, bookmarks, playlists", ["tracks.c", "hide.c", "skips.c", "art.c", "resume.c", "playlist.c"]),
    "debugrecord": ("DEBUG=1: the debug record comes out whole in FroggerDebug on the next boot", ["debug.c"]),
}
# A check's exit code when the build it needs isn't the one made (debugrecord.py on a plain build).
SKIP = 77
CHECKS = list(FEATURES)
# Features no check covers yet: the script that shows them, in screenshots only.
UNCHECKED = {
    "Covers changing on Next": "artplay.py",
    "Jump by Letter": "letters.py",
    "Album artists": "albumartist.py",
    "Add to Playlist into a playlist of your own": "playlists.py",
    "The Now Playing cycle": "npcycle.py",
}


def run(name):
    t = time.time()
    with open(LOGS / f"{name}.log", "w") as log:
        code = subprocess.run([sys.executable, str(HERE / f"{name}.py")], cwd=HERE, stdout=log,
                              stderr=subprocess.STDOUT).returncode
    return name, code, time.time() - t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("scripts", nargs="*", default=CHECKS)
    a = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(HERE / "mkimage.py")], check=True)
    failed = []
    with ThreadPoolExecutor(a.j) as pool:
        for name, code, secs in pool.map(run, a.scripts):
            print("%-14s %s  %4.0f s" % (name, {0: "ok", SKIP: "skipped"}.get(code, "FAILED"), secs), flush=True)
            if code and code != SKIP:
                failed.append(name)
    for name in failed:
        print(f"\n--- {name}.log ---")
        print((LOGS / f"{name}.log").read_text()[-4000:])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

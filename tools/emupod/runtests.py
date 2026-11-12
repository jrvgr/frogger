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
    "clicker": ("Clicker: Speaker, Headphones, Both; Click Volume; the piezo while paused", ["clicker.c", "settings.c"]),
    "afteralbum": ("Play After Album: the queue waits for the album playing", ["holdmenu.c", "queue.c"]),
    "unhide": ("Show (un-hide), Settings › Show Hidden, FroggerHidden", ["hide.c", "settings.c"]),
    "hiddenrow": ("The Hidden row atop Artists, Albums, Genres, Composers: its list, Show there, Menu back", ["hiddenrow.c", "browse.c", "holdmenu.c", "hide.c"]),
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
    "artplay": ("Covers changing on Next and Previous", ["art.c", "nowplaying.c"]),
    "npcycle": ("The Now Playing cycle: the cover page, Apple's, scrubbing, rating and back", ["nowplaying.c"]),
    "letters": ("Jump by Letter, the letter in the title; Settings › Jump by Letter off", ["letters.c", "settings.c"]),
    "albumartist": ("Album artists: a compilation's songs under its album artist", ["artist.c"]),
    "ownplaylist": ("Add to Playlist into a playlist of your own, saved and read back", ["playlist.c", "holdmenu.c"]),
}
# A check's exit code when the build it needs isn't the one made (debugrecord.py on a plain build).
SKIP = 77
CHECKS = list(FEATURES)
# Features no check covers yet: the script that shows them, in screenshots only. (None now; CI's
# summary lists any here.)
UNCHECKED = {}


def lock_work():
    """Hold build/emupod-work/.run.lock for this run (released when the process ends): the checks
    rebuild their cards in build/emupod-work, so a second run at the same time (a second pytest or
    runtests.py) would overwrite the first one's cards mid-check and fail checks at random. It waits."""
    import fcntl
    LOGS.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOGS.parent / ".run.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another emupod run is using build/emupod-work; waiting for it to end", file=sys.stderr, flush=True)
        fcntl.flock(f, fcntl.LOCK_EX)
    return f


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
    lock = lock_work()  # noqa: F841 (held till exit)
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

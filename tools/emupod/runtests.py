#!/usr/bin/env python3
"""Run the emupod scripts that check Frogger (each exits 1 on a wrong step), a few at a time, on a
Frogger image of the loader just built. Needs tools/emupod/setup.sh and mkcards.py done, and
build/fw/osos.img (tools/fwtool.py extract). Logs go to build/emupod-work/logs/. pytest runs the same
checks (tests/test_emupod.py: `pytest -n auto -m emupod`); a new check goes in CHECKS for both.

    tools/emupod/runtests.py [-j 4] [SCRIPT...]    # default: all of CHECKS
"""
import argparse, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "build/emupod-work/logs"
CHECKS = ["holdmenu2", "upnext", "unhide", "quicksettings", "queuerow", "holdrow", "npfirst", "npslide",
          "npscrub", "resume", "readonly", "skips", "heaptop", "battery", "switches", "diskhang", "flash"]


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
            print("%-14s %s  %4.0f s" % (name, "ok" if code == 0 else "FAILED", secs), flush=True)
            if code:
                failed.append(name)
    for name in failed:
        print(f"\n--- {name}.log ---")
        print((LOGS / f"{name}.log").read_text()[-4000:])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

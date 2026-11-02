#!/usr/bin/env python3
"""Install the current loader into the test card's firmware partition (a copy) and save the
RAM image the loader leaves, for emupod to boot (it can't run the loader itself, see
docs/re-notes.md "Testing without a device").

    tools/emupod/mkimage.py [--card build/emupod-work/hide-card.img]   # -> build/emupod-work/osos-frogger.img
"""
import argparse, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools/emu")]
from boot import boot

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--card", default=str(ROOT / "build/emupod-work/hide-card.img"))
p.add_argument("--out", default=str(ROOT / "build/emupod-work/osos-frogger.img"))
args = p.parse_args()
work = ROOT / "build/emupod-work"
card = Path(args.card).read_bytes()
(work / "fwpart.img").write_bytes(card[63 * 512:(63 + 65536) * 512])      # firmware partition at sector 63
subprocess.run([sys.executable, str(ROOT / "tools/install.py"), "patch", str(work / "fwpart.img"),
                str(ROOT / "build/loader/frogger-loader.bin"), "-o", str(work / "fwpart-frogger.img")], check=True)
pc, ram = boot((work / "fwpart-frogger.img").read_bytes())
if pc != 0x28000000:
    sys.exit(f"loader stopped at {pc:#x}")
Path(args.out).write_bytes(ram[:0x2000000])   # all of DRAM: the payload sits at the top
print("wrote", args.out)

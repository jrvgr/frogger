"""Device realism: the emupod guards for what a real 3G has and the emulator doesn't (a big library,
a slow CPU, a disk that sleeps and stalls), on the big library card (tools/emupod/library.py;
pytest --library DIR for your own). CONTRIBUTING.md, "Device realism".

    nix develop .#emu -c pytest -n auto -m "perf or uidisk or stall"
    nix develop .#emu -c pytest -n auto -m uidisk --library build/device-library

- perf: the speed budget (perf.py): instructions per UI action, Frogger against stock 2.3.
- uidisk: no disk I/O on the UI thread (uidisk.py), one test per scenario.
- stall: the UI answers while the disk is hung (stall.py), one test per hold-menu row that saves.

Known failures are xfail (not strict: they turn into XPASS when fixed, then drop the mark).
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools/emupod"
LOGS = ROOT / "build/emupod-work/logs"
sys.path.insert(0, str(TOOLS))
import uidisk  # noqa: E402

pytestmark = pytest.mark.emupod

HIDE = ("Hide saves FroggerHidden on the UI thread (hide_flush: make_path, fw_create, fw_write), "
        "the hold-menu device freeze; fixed by #8 (a FroggerSave task)")
PLAYLIST = ("Add to Playlist reads and writes its playlist files on the UI thread (playlist.c: numbered_path, "
            "save_to); known, not fixed yet")
QUEUE = ("Add to Queue makes Apple write the On-The-Go file on the UI thread (0xf4ad4 from 0xf4fb0); "
         "found by this guard, not fixed yet")
KNOWN = {"hide": HIDE, "playlist": PLAYLIST, "queue": QUEUE}


def script(name, *args, log):
    LOGS.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(TOOLS / name), *args], cwd=TOOLS, capture_output=True, text=True)
    out = r.stdout + r.stderr
    (LOGS / f"{log}.log").write_text(out)
    if r.returncode:
        pytest.fail(f"{name} {' '.join(args)} exited {r.returncode}; the end of its output:\n{out[-4000:]}", pytrace=False)
    return out


@pytest.mark.perf
def test_perf(emupod_image, library):
    """Frogger's instructions per action within budget of stock's (perf-baseline.json)."""
    print(script("perf.py", log="perf"))


@pytest.mark.uidisk
@pytest.mark.parametrize("scenario", [pytest.param(s, marks=pytest.mark.xfail(reason=KNOWN[s])) if s in KNOWN else s
                                      for s in uidisk.SCENARIOS])
def test_uidisk(scenario, emupod_image, library):
    """No disk command on the UI thread from a call site stock 2.3 doesn't use."""
    print(script("uidisk.py", scenario, log=f"uidisk-{scenario}"))


@pytest.mark.stall
@pytest.mark.parametrize("rows", [pytest.param(r, marks=pytest.mark.xfail(reason=KNOWN[r])) if r != "queue" else r
                                  for r in ("queue", "hide", "playlist")])
def test_stall(rows, emupod_image, library, request):
    """While the disk is hung: Menu, the wheel and the hold menu answer, then the drive comes back."""
    seed = str(request.config.getoption("stall_seed"))
    print(script("stall.py", "--trials", "2", "--seed", seed, "--rows", rows, log=f"stall-{rows}"))

"""pytest setup for tests/: the `firmware` marker's skips and the emupod checks' shared image.

    nix develop -c pytest                  # unit tests; the firmware ones skip without build/fw
    nix develop .#emu -c pytest -n auto    # everything, emupod checks included (CONTRIBUTING.md)
"""
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FW_IMAGE = "build/fw/osos.img"

# How to make each firmware file, for the skip reason.
HOW = {
    "build/fw/osos.img": "python3 tools/fwtool.py extract firmware/iPod_2.2.3.ipsw -o build/fw",
    "firmware/iPod_2.2.3.ipsw": "Apple's ipsw, never in the repo; CONTRIBUTING.md, Emulator tests",
}


def missing(*paths):
    """The skip reason for the first path (relative to the repo) that doesn't exist, or None."""
    for p in paths:
        if not (ROOT / p).exists():
            how = HOW.get(p)
            return f"needs {p}" + (f" ({how})" if how else "")
    return None


def pytest_addoption(parser):
    parser.addoption("--require-firmware", action="store_true",
                     help="fail, not skip, when a firmware or emupod test's files are missing (CI's emulator job)")


@pytest.hookimpl(trylast=True)  # after -m and -k have deselected
def pytest_collection_modifyitems(config, items):
    for item in items:
        for mark in item.iter_markers("firmware"):
            reason = missing(*(mark.args or (FW_IMAGE,)))
            if reason and config.getoption("require_firmware"):
                raise pytest.UsageError(f"{item.nodeid} {reason} (--require-firmware)")
            if reason:
                item.add_marker(pytest.mark.skip(reason=reason))
                break


def pytest_configure(config):
    # One id for the whole run, shared with pytest-xdist's workers, so the emupod image is made once.
    if not hasattr(config, "workerinput"):
        config.frogger_run = uuid.uuid4().hex
    else:
        config.frogger_run = config.workerinput.get("testrunuid", "worker")


@pytest.fixture(scope="session")
def emupod_image(request):
    """build/emupod-work/osos-frogger.img from the loader just built (tools/emupod/mkimage.py),
    made once per run even with -n: the first worker makes it under a lock, the rest wait."""
    work = ROOT / "build/emupod-work"
    reason = missing("third_party/emupod/emupod/emupod_rs.abi3.so", FW_IMAGE, "build/loader/frogger-loader.bin",
                     "build/emupod-work/hide-card.img")
    if reason:
        reason += "; see CONTRIBUTING.md, Emulator tests (setup.sh, make -C loader, mkcards.py)"
        (pytest.fail if request.config.getoption("require_firmware") else pytest.skip)(reason)
    import fcntl  # here, not at the top: the install/podinfo/coverart tests also run on Windows
    stamp = work / f".mkimage-{request.config.frogger_run}"
    with open(work / ".mkimage.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not stamp.exists():
            for old in work.glob(".mkimage-*"):
                old.unlink()
            r = subprocess.run([sys.executable, str(ROOT / "tools/emupod/mkimage.py")], capture_output=True, text=True)
            if r.returncode:
                pytest.fail("mkimage.py failed:\n" + r.stdout + r.stderr, pytrace=False)
            stamp.touch()
    return work / "osos-frogger.img"

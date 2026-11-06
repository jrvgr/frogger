"""pytest setup for tests/: the `firmware` marker's skips, the emupod checks' shared image and
the device-realism options (CONTRIBUTING.md, "Device realism").

    nix develop -c pytest                  # unit tests; the firmware ones skip without build/fw
    nix develop .#emu -c pytest -n auto    # everything, emupod checks included (CONTRIBUTING.md)
    ... --library build/device-library     # perf/uidisk/stall on your own iTunesDB (never in CI)
    ... --ata-hang 1                       # every emupod check with a random disk hang (seed 1)
"""
import os
import random
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
    parser.addoption("--library", default=os.environ.get("FROGGER_LIBRARY", "generated"),
                     help='the big library for the perf, uidisk and stall checks: "generated" (default) or a folder '
                          "with an iTunesDB, e.g. build/device-library (sets FROGGER_LIBRARY)")
    parser.addoption("--stall-seed", type=int, default=int(os.environ.get("EMUPOD_STALL_SEED", "1")),
                     help="the stall checks' random seed (stall.py --seed)")
    parser.addoption("--ata-hang", type=int, default=None, metavar="SEED",
                     help="run every emupod check with the disk hanging once, at a random read for a random "
                          "time (EMUPOD_ATA_HANG, seeded per check)")


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


@pytest.fixture(autouse=True)
def _ata_hang(request, monkeypatch):
    """--ata-hang SEED: EMUPOD_ATA_HANG="skip,ms" for this test's emupod processes, the same for a
    test on every run with that seed: the disk hangs at the skip-th read for ms (0: until reset)."""
    seed = request.config.getoption("ata_hang")
    if seed is not None and request.node.get_closest_marker("emupod"):
        rng = random.Random("%d %s" % (seed, request.node.nodeid))
        value = "%d,%d" % (rng.randint(0, 400), rng.choice([0, 2000, 5000, 12000]))
        monkeypatch.setenv("EMUPOD_ATA_HANG", value)
        print("EMUPOD_ATA_HANG=" + value)


@pytest.fixture(scope="session")
def library(request):
    """The big library card (tools/emupod/library.py) for --library, made once per run; also sets
    FROGGER_LIBRARY for the scripts."""
    lib = request.config.getoption("library")
    os.environ["FROGGER_LIBRARY"] = lib
    sys.path.insert(0, str(ROOT / "tools/emupod"))
    import library as lb
    if lib != "generated" and not (ROOT / lib / "iTunesDB").exists() and not (Path(lib) / "iTunesDB").exists():
        pytest.fail(f"--library {lib}: no iTunesDB there", pytrace=False)
    return lb.card(lib)


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

"""The emupod checks (tools/emupod/runtests.py's FEATURES), one test each: the script runs as
runtests.py runs it, on a Frogger image of the loader just built, and its output (also in
build/emupod-work/logs/NAME.log) shows when it fails. Slow: run them with -n.

    nix develop .#emu -c pytest -n auto -m emupod
    nix develop .#emu -c pytest -n auto tests/test_emupod.py -k upnext
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools/emupod"))
import runtests  # noqa: E402

pytestmark = pytest.mark.emupod


@pytest.mark.parametrize("name", runtests.CHECKS)
def test_check(name, emupod_image):
    runtests.LOGS.mkdir(parents=True, exist_ok=True)
    _, code, secs = runtests.run(name)
    if code == runtests.SKIP:
        pytest.skip(f"{name}.py needs another build: " + (runtests.LOGS / f"{name}.log").read_text().strip()[-200:])
    if code:
        log = (runtests.LOGS / f"{name}.log").read_text(errors="replace")
        pytest.fail(f"{name}.py exited {code} after {secs:.0f} s; the end of its log:\n{log[-4000:]}", pytrace=False)

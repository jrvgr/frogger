import io
import struct
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "build/fw/osos.img"
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/emu"))

import mkpayload  # noqa: E402

try:
    import unicorn  # noqa: F401
except ImportError:
    unicorn = None


class MkPayloadTest(unittest.TestCase):
    def test_bl_encoding(self):
        self.assertEqual(mkpayload.bl(0xc456c, 0xc62f8), 0xeb000761)  # Apple's own BL there
        self.assertEqual(mkpayload.bl(0x1000, 0x0), 0xebfffbfe)
        with self.assertRaises(ValueError):
            mkpayload.bl(0, 0x4000000)

    @unittest.skipUnless(IMAGE.exists(), "needs build/fw/osos.img")
    def test_hook_sites_match_firmware(self):
        d = IMAGE.read_bytes()
        for addr, orig, name in mkpayload.HOOKS:
            self.assertEqual(struct.unpack_from("<I", d, addr)[0], orig, name)


@unittest.skipUnless(unicorn and IMAGE.exists(), "needs unicorn (nix develop) and build/fw/osos.img")
class HideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["make", "-s", "-C", str(ROOT / "payload")], check=True, stdout=subprocess.DEVNULL)

    def setUp(self):
        import hide
        self.hide = hide
        self.h = hide.Harness(str(IMAGE), str(BUILD))
        self.h.load(hide.TRACK_LIST, hide.PLAYLISTS)

    def test_harness_passes(self):
        with unittest.mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(self.hide.main(["--image", str(IMAGE), "--build", str(BUILD)]), 0)

    def test_flagged_tracks_are_hidden(self):
        self.assertEqual(self.h.hidden(), {2, 4})

    def test_library_browse_drops_them(self):
        self.assertEqual(self.h.browse(self.h.master(), [1, 2, 3, 4, 5]), {1, 3, 5})

    def test_playlists_keep_them(self):
        self.assertEqual(self.h.browse(self.h.playlists[1], [2, 3]), {2, 3})

    def test_show_all_keeps_them(self):
        self.h.set_show_all(True)
        self.assertEqual(self.h.browse(self.h.master(), [1, 2, 3, 4, 5]), {1, 2, 3, 4, 5})

    def test_other_values_at_the_flag_offset_dont_hide(self):
        self.h.load([(1, "One", False), (2, "Two", False)], [("iPod", [1, 2], True)])
        self.assertEqual(self.h.hidden(), set())

    def test_reload_starts_over(self):
        self.h.load([(1, "One", True), (2, "Two", False), (4, "Four", False)], [("iPod", [1, 2, 4], True)])
        self.assertEqual(self.h.hidden(), {1})


if __name__ == "__main__":
    unittest.main()

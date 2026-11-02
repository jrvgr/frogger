import io
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "build/fw/osos.img"
sys.path.insert(0, str(ROOT / "tools/emu"))

try:
    import unicorn  # noqa: F401
except ImportError:
    unicorn = None


@unittest.skipUnless(unicorn and IMAGE.exists(), "needs unicorn (nix develop) and build/fw/osos.img")
class LcdHarnessTest(unittest.TestCase):
    def run_lcd(self, *args):
        import lcd
        with unittest.mock.patch("sys.stdout", io.StringIO()):
            return lcd.main(["--image", str(IMAGE), *args])

    def test_stock_panel_matches_framebuffer(self):
        self.assertEqual(self.run_lcd(), 0)

    def test_stock_is_not_inverted(self):
        self.assertEqual(self.run_lcd("--expect-invert"), 1)


@unittest.skipUnless(unicorn and IMAGE.exists(), "needs unicorn (nix develop) and build/fw/osos.img")
class ItunesDbLoaderTest(unittest.TestCase):
    def test_invisible_tracks_are_dropped(self):
        import itunesdb
        db = itunesdb.mhlt([itunesdb.mhit(i, f, v) for i, f, v in itunesdb.SAMPLE])
        rc, tracks, pos = itunesdb.load(str(IMAGE), db)
        self.assertEqual(rc, 0)
        self.assertEqual(pos, len(db))
        self.assertEqual([t["id"] for t in tracks], [1, 3])
        self.assertEqual(tracks[0]["artist"], "The Beatles")
        self.assertEqual(tracks[1]["composer"], "Debussy")


if __name__ == "__main__":
    unittest.main()

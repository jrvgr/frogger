"""The sample files in tests/fixtures/ (one per format and version, docs/file-formats.md), read
with tools/podinfo.py (and coverart.py's FroggerArt writer checked against them)."""
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/emupod"))
sys.path.insert(0, str(FIX))

import mkfixtures as fx  # noqa: E402
import podinfo  # noqa: E402

try:
    import coverart
except (ImportError, SystemExit):
    coverart = None


def load(name, magic):
    return podinfo.FroggerFile((FIX / name).read_bytes(), magic)


class FixturesTest(unittest.TestCase):
    def setUp(self):
        self.db = podinfo.Database(str(FIX / "iTunesDB"))

    def songs(self, f):
        """Each entry's song as a title (None: not in the database), and the rest of the entry."""
        out = []
        for song, *rest in f.entries:
            t = f.track(self.db, song)
            out.append((t.title if t else None, *rest))
        return out

    def test_fixtures_are_what_mkfixtures_writes(self):
        for name, data in fx.files().items():
            self.assertEqual((FIX / name).read_bytes(), data, name)

    def test_database(self):
        self.assertEqual([(t.title, t.id, t.dbid, t.size, t.ms) for t in self.db.tracks],
                         [("Apple", 101, fx.APPLE.dbid, 1000, 180000), ("Bravo", 102, 0, 2000, 240000),
                          ("Long Mix", 103, fx.LONG.dbid, 3000, fx.LONG_MS)])
        self.assertEqual(self.db.playlists, [(0xabcdef, "iPod"), (fx.MIX, "Mix")])

    def test_key_matching(self):
        find = lambda k: (self.db.find(k) or podinfo.Track(-1, 0, 0, 0, 0, 0, 0)).pos
        self.assertEqual(find(fx.APPLE), 0)
        self.assertEqual(find(fx.APPLE._replace(id=999, size=1)), 0)            # the dbid is enough
        self.assertEqual(find(fx.BRAVO), 1)                                      # no dbid: id, size, length
        self.assertEqual(find(fx.BRAVO._replace(size=1)), -1)                    # ... all three
        self.assertEqual(find(fx.BRAVO._replace(dbid=0x77)), 1)                  # a dbid the database lacks
        self.assertEqual(find(fx.APPLE._replace(dbid=0x77)), -1)                 # both have dbids, they differ
        self.assertEqual(find(fx.GONE), -1)

    def test_hidden_versions(self):
        f = load("FroggerHidden.v1", podinfo.HIDDEN)
        self.assertEqual((f.version, f.keyed, f.stamp, self.songs(f)), (1, False, fx.STAMP, [("Apple",)]))
        f = load("FroggerHidden.v2", podinfo.HIDDEN)
        self.assertEqual((f.version, self.songs(f)), (2, [("Apple", 0), ("Long Mix", 1)]))
        f = load("FroggerHidden.v3", podinfo.HIDDEN)
        self.assertEqual((f.version, f.keyed, f.entry_size), (3, True, 24))
        self.assertEqual(self.songs(f), [("Apple", 0), ("Bravo", 1), (None, 0)])

    def test_skips_versions(self):
        f = load("FroggerSkips.v1", podinfo.SKIPS)
        self.assertEqual((f.version, self.songs(f)), (1, [("Bravo", 3, 0xe0000000)]))
        f = load("FroggerSkips.v2", podinfo.SKIPS)
        self.assertEqual((f.version, f.entry_size, self.songs(f)), (2, 28, [("Bravo", 3, 0xe0000000), (None, 1, 0xe0000100)]))

    def test_bookmarks(self):
        f = load("FroggerBookmarks.v1", podinfo.BOOKMARKS)
        self.assertEqual((f.version, self.songs(f)), (1, [("Long Mix", 120000), (None, 5000)]))

    def test_playlist(self):
        f = load("FroggerPlaylist_0000000000ABCDF0", podinfo.PLAYLIST)
        self.assertEqual((f.version, f.id, self.songs(f)), (1, fx.MIX, [("Apple",), ("Bravo",), (None,)]))

    def test_unknown_versions_are_refused(self):
        data = bytearray((FIX / "FroggerSkips.v2").read_bytes())
        data[4] = 9
        with self.assertRaises(ValueError):
            podinfo.FroggerFile(bytes(data), podinfo.SKIPS)
        with self.assertRaises(ValueError):
            podinfo.FroggerFile((FIX / "FroggerSkips.v2").read_bytes(), podinfo.HIDDEN)

    def test_froggerart_versions(self):
        v1 = podinfo.FroggerArt((FIX / "FroggerArt.v1").read_bytes())
        v2 = podinfo.FroggerArt((FIX / "FroggerArt.v2").read_bytes())
        self.assertEqual((v1.version, v1.covers(self.db)), (1, {0: 0, 2: 1}))
        self.assertEqual((v2.version, v2.covers(self.db)), (2, {0: 0, 2: 1}))
        self.assertEqual(v1.images, v2.images)
        self.assertEqual(len(v2.table), 3)                  # the gone song's entry is there, and unused

    def test_froggerart_v1_needs_its_database(self):
        v1 = podinfo.FroggerArt((FIX / "FroggerArt.v1").read_bytes())
        self.db.tracks.append(self.db.tracks[0])             # one track more: another database
        self.assertEqual(v1.covers(self.db), {})

    @unittest.skipIf(coverart is None, "needs Pillow (nix develop)")
    def test_coverart_writes_version_2(self):
        art = podinfo.FroggerArt((FIX / "FroggerArt.v2").read_bytes())
        self.assertEqual(coverart.froggerart(art.table, art.images), (FIX / "FroggerArt.v2").read_bytes())
        v1 = podinfo.FroggerArt((FIX / "FroggerArt.v1").read_bytes())
        self.assertEqual(coverart.froggerart_v1(v1.table, v1.images), (FIX / "FroggerArt.v1").read_bytes())


class PodinfoOnFixturesTest(unittest.TestCase):
    """podinfo.py on an iPod holding the fixtures under their real names."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.itunes = self.root / "iPod_Control/iTunes"
        self.itunes.mkdir(parents=True)
        for src, name in (("iTunesDB", "iTunesDB"), ("FroggerHidden.v3", "FroggerHidden"),
                          ("FroggerSkips.v2", "FroggerSkips"), ("FroggerBookmarks.v1", "FroggerBookmarks"),
                          ("FroggerPlaylist_0000000000ABCDF0", "FroggerPlaylist_0000000000ABCDF0"),
                          ("FroggerPlaylist_1.mhpo", "FroggerPlaylist_1"), ("FroggerArt.v2", "FroggerArt")):
            shutil.copyfile(FIX / src, self.itunes / name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_podinfo(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            podinfo.main([str(self.root), *args])
        return [line.split("\t") for line in out.getvalue().splitlines()]

    def test_summary(self):
        rows = dict((r[0], r[1]) for r in self.run_podinfo())
        self.assertEqual(rows["FroggerHidden"], "version 3, 3 entries, 2 of them songs in this database")
        self.assertEqual(rows["FroggerSkips"], "version 2, 2 entries, 1 of them songs in this database")
        self.assertEqual(rows["FroggerArt"], "version 2, 2 covers, 2 of 3 songs have one")

    def test_lists(self):
        self.assertEqual([r[:2] + r[3:4] for r in self.run_podinfo("hidden")[1:]],
                         [["101", "hidden", "Apple"], ["102", "shown", "Bravo"], ["104", "hidden", "(not in this database)"]])
        self.assertEqual([r[:2] for r in self.run_podinfo("skips")[1:]], [["102", "3"], ["104", "1"]])
        playlists = self.run_podinfo("playlists")[1:]
        self.assertEqual([r[:3] for r in playlists if r[0].startswith("FroggerPlaylist_0")],
                         [["FroggerPlaylist_0000000000ABCDF0 (Mix)", "101", "Apple"],
                          ["FroggerPlaylist_0000000000ABCDF0 (Mix)", "102", "Bravo"],
                          ["FroggerPlaylist_0000000000ABCDF0 (Mix)", "", "(not in this database)"]])
        self.assertEqual([r[1] for r in playlists if r[0] == "FroggerPlaylist_1"], ["103", "101"])

    def test_bookmarks_play_counts_first(self):
        self.assertEqual([r[:2] for r in self.run_podinfo("bookmarks")[1:]], [["103", "0:02:00"]])
        shutil.copyfile(FIX / "Play Counts", self.itunes / "Play Counts")
        self.assertEqual([r[:2] for r in self.run_podinfo("bookmarks")[1:]], [["103", "0:01:30"]])


if __name__ == "__main__":
    unittest.main()

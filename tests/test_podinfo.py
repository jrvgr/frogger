import contextlib
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/emupod"))

import mkresume as mk  # noqa: E402  (the iTunesDB builders; no emulator needed)
import podinfo  # noqa: E402

TRACKS = [(101, "Apple", 180000), (102, "Bravo", 240000), (103, "Long Mix", 25 * 60 * 1000)]


def database(master=(103, 101, 102)):
    tracks = [mk.mhit(tid, {"title": t, "artist": "Someone", "album": "Test"}, 1000, ms, 128,
                      bookmark=120000 if tid == 103 else 0) for tid, t, ms in TRACKS]
    return mk.mhbd([mk.mhsd(1, mk.mhl(b"mhlt", tracks)),
                    mk.mhsd(2, mk.mhl(b"mhlp", [mk.mhyp("iPod", list(master))]))])


def frogger_file(magic, version, entries):
    size = 4 * len(entries[0])
    head = struct.pack("<IHHIII", magic, version, size, 0x1234, len(entries), 0)
    return head + b"".join(struct.pack("<%dI" % len(e), *e) for e in entries)


class PodinfoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.itunes = self.root / "iPod_Control/iTunes"
        self.itunes.mkdir(parents=True)
        (self.itunes / "iTunesDB").write_bytes(database())

    def tearDown(self):
        self.tmp.cleanup()

    def run_podinfo(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            podinfo.main([str(self.root), *args])
        return [line.split("\t") for line in out.getvalue().splitlines()]

    def test_tracks_and_master_order(self):
        db = podinfo.Database(str(self.itunes / "iTunesDB"))
        self.assertEqual([(t.pos, t.id, t.title) for t in db.tracks], [(0, 101, "Apple"), (1, 102, "Bravo"), (2, 103, "Long Mix")])
        self.assertEqual(db.master, [103, 101, 102])

    def test_hide_and_unhide(self):
        self.run_podinfo("hide", "102")
        self.assertTrue((self.itunes / "iTunesDB.frogger-backup").exists())
        rows = self.run_podinfo("hidden")
        self.assertEqual([(r[0], r[1], r[3]) for r in rows[1:]], [("102", "hidden", "Bravo")])
        data = (self.itunes / "iTunesDB").read_bytes()
        db = podinfo.Database(str(self.itunes / "iTunesDB"))
        self.assertEqual(data[db.by_id[102].offset + 0x98:][:4], b"HIDE")
        self.run_podinfo("unhide", "102")
        self.assertEqual((self.itunes / "iTunesDB").read_bytes(), database())

    def test_frogger_files(self):
        (self.itunes / "FroggerHidden").write_bytes(frogger_file(0x48475246, 2, [(0, 101, 0), (2, 103, 1)]))
        (self.itunes / "FroggerSkips").write_bytes(frogger_file(0x53475246, 1, [(1, 102, 3, 0xe0000000)]))
        rows = self.run_podinfo("hidden")
        self.assertEqual([(r[0], r[1], r[3]) for r in rows[1:]], [("101", "hidden", "Apple"), ("103", "shown", "Long Mix")])
        rows = self.run_podinfo("skips")
        self.assertEqual([(r[0], r[1], r[3]) for r in rows[1:]], [("102", "3", "Bravo")])

    def test_playlists_refer_to_the_master_order(self):
        # Apple's On-The-Go format: mhpo, header 0x14, 4-byte entries, the master playlist's index
        (self.itunes / "OTGPlaylistInfo").write_bytes(struct.pack("<4sIIII", b"mhpo", 0x14, 4, 2, 0) + struct.pack("<II", 0, 2))
        rows = self.run_podinfo("playlists")
        self.assertEqual([(r[1], r[2]) for r in rows[1:]], [("103", "Long Mix"), ("102", "Bravo")])

    def test_bookmarks(self):
        rows = self.run_podinfo("bookmarks")
        self.assertEqual([(r[0], r[1], r[2]) for r in rows[1:]], [("103", "0:02:00", "0:25:00")])


if __name__ == "__main__":
    unittest.main()

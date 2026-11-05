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

try:
    from PIL import Image
    import coverart
except (ImportError, SystemExit):
    coverart = None
import mkresume as mk  # noqa: E402
import podinfo  # noqa: E402


def picture(colour, size=(200, 120)):
    out = io.BytesIO()
    Image.new("L", size, colour).save(out, "PNG")
    return out.getvalue()


def mp3(pic, major=3, album="", artist=""):
    """An ID3v2 tag with text frames and an APIC front cover, then a bit of 'audio'."""
    def frame(fid, body):
        n = len(body)
        size = bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f]) if major == 4 else struct.pack(">I", n)
        return fid + size + b"\0\0" + body
    frames = frame(b"TIT2", b"\0Song") + frame(b"TALB", b"\3" + album.encode()) + frame(b"TPE1", b"\3" + artist.encode())
    frames += frame(b"APIC", b"\0image/png\0\x03cover\0" + pic) if pic else b""
    n = len(frames)
    head = b"ID3" + bytes([major, 0, 0]) + bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])
    return head + frames + b"\xff\xfb" + bytes(64)


def m4a(pic):
    box = lambda name, body: struct.pack(">I", 8 + len(body)) + name + body
    covr = box(b"covr", box(b"data", struct.pack(">II", 14, 0) + pic))
    meta = box(b"meta", b"\0\0\0\0" + box(b"hdlr", bytes(25)) + box(b"ilst", covr))
    return box(b"ftyp", b"M4A \0\0\0\0") + box(b"mdat", bytes(32)) + box(b"moov", box(b"udta", meta))


@unittest.skipIf(coverart is None, "needs Pillow (nix develop)")
class CoverartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.itunes = self.root / "iPod_Control/iTunes"
        self.itunes.mkdir(parents=True)
        music = self.root / "iPod_Control/Music/F00"
        music.mkdir(parents=True)
        (music / "A1.mp3").write_bytes(mp3(picture(0)))            # black, ID3 2.3
        (music / "A2.mp3").write_bytes(b"\xff\xfb")                 # no tag: album's cover
        (music / "B1.m4a").write_bytes(m4a(picture(255)))           # white, MP4
        (music / "C1.mp3").write_bytes(mp3(picture(0), 4))          # black again, ID3 2.4: shared image
        (music / "D1.mp3").write_bytes(b"\xff\xfb")                 # no cover anywhere
        (music / "E1.mp3").write_bytes(b"\xff\xfb")                 # cover from --covers
        (music / "F1.mp3").write_bytes(b"\xff\xfb")                 # cover.jpg in the library
        (music / "G1.mp3").write_bytes(b"\xff\xfb")                 # a library song's picture
        songs = [("A1.mp3", "A"), ("A2.mp3", "A"), ("B1.m4a", "B"), ("C1.mp3", "C"), ("D1.mp3", "D"), ("E1.mp3", "E"),
                 ("F1.mp3", "F"), ("G1.mp3", "G")]
        tracks = [mk.mhit(100 + i, {"title": f, "artist": "Someone", "album": album,
                                    "location": ":iPod_Control:Music:F00:" + f}, 1000, 1000, 128)
                  for i, (f, album) in enumerate(songs)]
        (self.itunes / "iTunesDB").write_bytes(mk.mhbd([mk.mhsd(1, mk.mhl(b"mhlt", tracks))]))
        self.covers = self.root / "covers"
        self.covers.mkdir()
        (self.covers / "Someone - E.png").write_bytes(picture(128))
        self.library = self.root / "library"
        (self.library / "F").mkdir(parents=True)
        (self.library / "F/01.mp3").write_bytes(mp3(b"", album="F", artist="Someone"))
        Image.new("L", (90, 90), 0).save(self.library / "F/cover.jpg")            # JPEG: near black, close to A's
        (self.library / "G").mkdir()
        (self.library / "G/01.mp3").write_bytes(mp3(picture(64), 4, album="G", artist="Someone"))
        self.map = self.root / "covers.txt"
        self.map.write_text("# picked by hand\n105\tcovers/Someone - E.png\nSomeone - B = covers/Someone - E.png\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_embedded_pictures(self):
        music = self.root / "iPod_Control/Music/F00"
        self.assertEqual(coverart.embedded(str(music / "A1.mp3")), picture(0))
        self.assertEqual(coverart.embedded(str(music / "C1.mp3")), picture(0))
        self.assertEqual(coverart.embedded(str(music / "B1.m4a")), picture(255))
        self.assertIsNone(coverart.embedded(str(music / "D1.mp3")))

    def froggerart(self, *args):
        out = self.root / "FroggerArt"
        with contextlib.redirect_stdout(io.StringIO()):
            coverart.main([str(self.root), "--out", str(out), *args])
        d = out.read_bytes()
        magic, version, size, entries, images, image_bytes, _ = struct.unpack_from("<IHHIIII", d, 0)
        self.assertEqual((magic, version, size, image_bytes), (0x41475246, 2, 72, coverart.BYTES))
        off = 24 + 24 * entries                     # version 2: a (key, image) per song with a cover
        self.assertEqual(len(d), off + images * coverart.BYTES)
        db = podinfo.Database(str(self.itunes / "iTunesDB"))
        art = podinfo.FroggerArt(d)
        self.assertEqual(len(art.table), entries)
        self.assertEqual({k.id for k, _ in art.table}, {db.tracks[p].id for p in art.covers(db)})
        covers = art.covers(db)
        return d, tuple(covers.get(p, 0xffff) for p in range(len(db.tracks))), images, off

    def test_froggerart(self):
        d, table, images, off = self.froggerart("--covers", str(self.covers))
        self.assertEqual(table, (0, 0, 1, 0, 0xffff, 2, 0xffff, 0xffff))
        self.assertEqual(images, 3)
        black = (b"\xff" * (coverart.SIZE // 4) + bytes(coverart.ROW - coverart.SIZE // 4)) * coverart.SIZE
        self.assertEqual(d[off:off + coverart.BYTES], black)       # a flat black picture stays black

    def test_library(self):
        _, table, images, _ = self.froggerart("--library", str(self.library))
        self.assertEqual(table[:6], (0, 0, 1, 0, 0xffff, 0xffff))
        self.assertNotIn(0xffff, table[6:])                 # F from cover.jpg, G from the song's tag
        self.assertEqual(len({*table}), images + 1)

    def test_map_comes_first(self):
        _, table, images, _ = self.froggerart("--map", str(self.map))
        self.assertEqual(table[2], table[5])                # B picked by album, E (track 105) by id
        self.assertNotEqual(table[2], table[0])
        self.assertEqual(table[6:], (0xffff, 0xffff))

    def test_song_path(self):
        self.assertEqual(Path(coverart.song_path("/V", ":iPod_Control:Music:F00:X.mp3")),
                         Path("/V/iPod_Control/Music/F00/X.mp3"))

    def test_podinfo_reads_location(self):
        db = podinfo.Database(str(self.itunes / "iTunesDB"))
        self.assertEqual(db.tracks[2].location, ":iPod_Control:Music:F00:B1.m4a")


if __name__ == "__main__":
    unittest.main()

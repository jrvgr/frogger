import io
import json
import struct
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import fwtool  # noqa: E402


def make_partition(version=2):
    """Build a small fake 3G-style partition: STOP banner, ]ih[ header, osos + rsrc."""
    data = bytearray(0x10000)
    data[0:len(fwtool.STOP_SIGN)] = fwtool.STOP_SIGN
    data[0x100:0x104] = b"]ih["
    struct.pack_into("<I", data, 0x104, 0x4000)
    struct.pack_into("<H", data, 0x10A, version)

    osos = bytearray(b"\x00" * 0x20 + b"portalplayer" + bytes(range(256)) * 4)
    rsrc = bytes(b"\x42" * 0x300)
    entries = [(b"soso", 0x5000, osos, 0x28000000), (b"crsr", 0x8000, rsrc, 0)]
    # loadAddr is junk on 1G-3G (2.3 stores 0x048d0040); addr is the real load address.
    fwoffset = 0 if version == 2 else 512
    pos = 0x4200
    for index, (ident, dev_offset, blob, load) in enumerate(entries):
        fwtool.DIR_ENTRY.pack_into(data, pos, b"!ATA", ident, index, dev_offset, len(blob), load, 0,
                                   sum(blob) & 0xFFFFFFFF, 0x210, 0x048D0040)
        data[fwoffset + dev_offset:fwoffset + dev_offset + len(blob)] = blob
        pos += fwtool.DIR_ENTRY.size
    return bytes(data), bytes(osos)


class FwtoolTest(unittest.TestCase):
    def test_parse_v2(self):
        data, osos = make_partition()
        fw = fwtool.parse(data)
        self.assertEqual(fw["version"], 2)
        self.assertEqual([i["id"] for i in fw["images"]], ["osos", "rsrc"])
        self.assertEqual(fw["images"][1]["devOffset"], 0x8000)
        img = fw["images"][0]
        self.assertEqual(img["fileOffset"], 0x5000)
        blob = fwtool.image_bytes(data, img)
        self.assertEqual(blob, osos)
        d = fwtool.describe(img, blob)
        self.assertTrue(d["chksumMatches"])
        self.assertTrue(d["portalplayerTag"])

    def test_parse_v3_offsets_by_a_sector(self):
        data, osos = make_partition(version=3)
        img = fwtool.parse(data)["images"][0]
        self.assertEqual(img["fileOffset"], 0x5000 + 512)
        self.assertEqual(fwtool.image_bytes(data, img), osos)

    def test_extract_from_ipsw(self):
        data, osos = make_partition()
        with tempfile.TemporaryDirectory() as tmp:
            ipsw = Path(tmp) / "fake.ipsw"
            with zipfile.ZipFile(ipsw, "w") as zf:
                zf.writestr("manifest.plist", "<plist/>")
                zf.writestr("Firmware-fake", data)
            out = Path(tmp) / "out"
            with unittest.mock.patch("sys.stdout", io.StringIO()):
                self.assertEqual(fwtool.main(["extract", str(ipsw), "-o", str(out)]), 0)
            self.assertEqual((out / "osos.img").read_bytes(), osos)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["source"], "Firmware-fake")
            self.assertEqual(manifest["images"][0]["addr"], 0x28000000)

    def test_rejects_non_firmware(self):
        with tempfile.NamedTemporaryFile(suffix=".bin") as f:
            f.write(b"not firmware" * 100)
            f.flush()
            with self.assertRaises(fwtool.FirmwareError):
                fwtool.load_partition(f.name)


if __name__ == "__main__":
    unittest.main()

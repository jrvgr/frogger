import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IPSW = ROOT / "firmware/iPod_2.2.3.ipsw"
sys.path.insert(0, str(ROOT / "tools"))

import fwtool  # noqa: E402
import install  # noqa: E402

LOADER = bytes(range(256)) * 5  # 1280 bytes, stands in for frogger-loader.bin
PART_SIZE = 8 << 20             # real partitions have room after aupd


def mbr_disk(part, fat_sectors=2048):
    lba = 63
    disk = bytearray(lba * 512)
    struct.pack_into("<B", disk, 0x1be + 4, 0)
    struct.pack_into("<II", disk, 0x1be + 8, lba, len(part) // 512)
    struct.pack_into("<B", disk, 0x1ce + 4, 0x0b)
    struct.pack_into("<II", disk, 0x1ce + 8, lba + len(part) // 512, fat_sectors)
    disk[510:512] = b"\x55\xaa"
    return disk + part + b"\xfa" * (fat_sectors * 512)


def apm_disk(part):
    disk = bytearray(64 * 512)
    disk[0:2] = b"ER"
    entries = [(b"Apple_partition_map", 1, 63), (b"Apple_MDFW", 64, len(part) // 512), (b"Apple_HFS", 64 + len(part) // 512, 2048)]
    for k, (ptype, start, count) in enumerate(entries, 1):
        e = bytearray(512)
        e[0:2] = b"PM"
        struct.pack_into(">III", e, 4, len(entries), start, count)
        e[48:48 + len(ptype)] = ptype
        disk[k * 512:(k + 1) * 512] = e
    return disk + part + b"\xfa" * (2048 * 512)


@unittest.skipUnless(IPSW.exists(), "needs firmware/iPod_2.2.3.ipsw")
class InstallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, part = fwtool.load_partition(IPSW)
        cls.part = part + bytes(PART_SIZE - len(part))

    def test_stock_status(self):
        self.assertEqual(install.status(self.part), ("stock", 0))

    def test_patch_appends_loader_and_moves_aupd(self):
        new = install.patch(self.part, LOADER)
        fw = fwtool.parse(bytes(new))
        osos, aupd = fw["images"]
        self.assertEqual(osos["entryOffset"], install.OSOS_2_3_LEN)
        self.assertEqual(osos["len"], install.OSOS_2_3_LEN + len(LOADER))
        self.assertEqual(fwtool.byte_sum(fwtool.image_bytes(new, osos)), osos["chksum"])
        self.assertEqual(fwtool.image_bytes(new, osos)[osos["entryOffset"]:], LOADER)
        self.assertEqual(fwtool.image_bytes(new, osos)[:install.OSOS_2_3_LEN],
                         fwtool.image_bytes(self.part, fwtool.parse(self.part)["images"][0]))
        old_aupd = fwtool.parse(self.part)["images"][1]
        self.assertGreaterEqual(aupd["fileOffset"], osos["fileOffset"] + osos["len"])
        self.assertEqual(aupd["fileOffset"] % 512, 0)
        self.assertEqual(fwtool.image_bytes(new, aupd), fwtool.image_bytes(self.part, old_aupd))
        self.assertEqual(fwtool.byte_sum(fwtool.image_bytes(new, aupd)), aupd["chksum"])

    def test_patch_twice_replaces_the_loader(self):
        once = install.patch(self.part, LOADER)
        twice = install.patch(once, LOADER[:1024])
        self.assertEqual(install.status(twice), ("frogger", 1024))

    def test_strip_restores_osos(self):
        back = install.strip(install.patch(self.part, LOADER))
        old, new = fwtool.parse(self.part)["images"][0], fwtool.parse(bytes(back))["images"][0]
        self.assertEqual(install.status(back), ("stock", 0))
        self.assertEqual({k: new[k] for k in ("len", "entryOffset", "chksum")},
                         {k: old[k] for k in ("len", "entryOffset", "chksum")})

    def test_no_room(self):
        _, tight = fwtool.load_partition(IPSW)
        with self.assertRaises(install.InstallError):
            install.patch(tight, LOADER)

    def test_refuses_other_firmware(self):
        bad = bytearray(self.part)
        bad[0x4400 + 0x100] ^= 0xff                     # osos no longer matches its checksum
        with self.assertRaises(install.InstallError):
            install.patch(bad, LOADER)

    def run_disk(self, image):
        with tempfile.TemporaryDirectory() as tmp:
            disk = Path(tmp) / "ipod.img"
            disk.write_bytes(image)
            self.assertEqual(install.disk_status(str(disk)), ("stock", 0))
            backup = install.disk_install(str(disk), LOADER, Path(tmp) / "backups")
            self.assertEqual(install.disk_status(str(disk)), ("frogger", len(LOADER)))
            self.assertEqual(backup.read_bytes(), self.part)
            after = disk.read_bytes()
            self.assertEqual(len(after), len(image))
            start = image.index(self.part[:0x200])
            self.assertEqual(after[:start], image[:start])                       # partition table untouched
            self.assertEqual(after[start + len(self.part):], image[start + len(self.part):])  # data partition untouched
            install.disk_install(str(disk), None, Path(tmp) / "backups")     # disk-remove
            self.assertEqual(install.disk_status(str(disk)), ("stock", 0))
            install.disk_restore(str(disk), backup)
            self.assertEqual(disk.read_bytes(), image)

    def test_partition_device_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dev = Path(tmp) / "rdisk6s2"
            dev.write_bytes(self.part)
            install.disk_install(str(dev), LOADER, Path(tmp) / "b", partition=True)
            self.assertEqual(install.disk_status(str(dev), partition=True), ("frogger", len(LOADER)))
            self.assertEqual(install.main(["disk-remove", "--partition", str(dev), "--backup-dir", str(Path(tmp) / "b")]), 0)
            self.assertEqual(install.disk_status(str(dev), partition=True), ("stock", 0))
            backups = sorted((Path(tmp) / "b").glob("*-stock.bin"))
            self.assertEqual(install.main(["disk-restore", "--partition", str(dev), str(backups[0])]), 0)
            self.assertEqual(dev.read_bytes(), self.part)

    def test_mbr_disk_round_trip(self):
        self.run_disk(bytes(mbr_disk(self.part)))

    def test_apm_disk_round_trip(self):
        self.run_disk(bytes(apm_disk(self.part)))


if __name__ == "__main__":
    unittest.main()


try:
    import unicorn  # noqa: F401
except ImportError:
    unicorn = None

LOADER_BIN = ROOT / "build/loader/frogger-loader.bin"


@unittest.skipUnless(unicorn and IPSW.exists(), "needs unicorn (nix develop) and firmware/iPod_2.2.3.ipsw")
class BootTest(unittest.TestCase):
    """The real loader, installed by install.py, booted in Unicorn."""

    @classmethod
    def setUpClass(cls):
        import subprocess
        subprocess.run(["make", "-s", "-C", str(ROOT / "loader")], check=True, stdout=subprocess.DEVNULL)
        sys.path.insert(0, str(ROOT / "tools/emu"))
        import boot
        import mkpayload
        cls.boot, cls.mkpayload = boot, mkpayload
        _, part = fwtool.load_partition(IPSW)
        cls.stock = fwtool.image_bytes(part, fwtool.parse(part)["images"][0])
        cls.part = install.patch(part + bytes(PART_SIZE - len(part)), LOADER_BIN.read_bytes())

    def test_patches_osos_and_jumps_to_it(self):
        pc, ram = self.boot.boot(self.part)
        self.assertEqual(pc, self.boot.DRAM)
        syms = self.mkpayload.symbols(ROOT / "build/payload/payload.sym")
        for addr, orig, repl, name in self.mkpayload.hooks(syms):
            self.assertEqual(struct.unpack_from("<I", ram, addr)[0], repl, name)
        blob = (ROOT / "build/payload/payload.bin").read_bytes()
        base = syms["track_hook"]
        self.assertEqual(ram[base:base + len(blob)], blob)
        # Settings' bundle index entry now points at the payload's copy with our item (loader/settings.c)
        menu = syms["settings_menu"]
        entry = 0x182258
        self.assertEqual(struct.unpack_from("<3I", ram, entry), (0x278d, menu - (0x181d20 + 0x313c), 4 + 22 * 40))
        self.assertEqual(struct.unpack_from("<I", ram, menu)[0], 22)
        # after Clicker (row 8): Show Hidden, Jump by Letter, Resume Mixes, then the five feature switches
        for row, item in enumerate(range(0x2900, 0x2908), 9):
            self.assertEqual(struct.unpack_from("<I", ram, menu + 4 + row * 40 + 24)[0], item)
        # Now Playing's View index entry points at the copy with the cover art (loader/nowplaying.c):
        # Apple's 9 elements unchanged, then the art BMap (id 0x3f01) as a 10th
        view, np_entry = syms["np_view"], 0x184184
        self.assertEqual(struct.unpack_from("<3I", ram, np_entry), (0x25ee, view - (0x181d20 + 0x313c), 0x34c))
        stock_view = 0x181d20 + 0x313c + 0x1ac94
        self.assertEqual(struct.unpack_from("<I", ram, view)[0], 10)
        self.assertEqual(ram[view + 4:view + 0x300], self.stock[stock_view + 4:stock_view + 0x300])
        self.assertEqual(struct.unpack_from("<4s", ram, view + 0x300 + 8)[0][::-1], b"BMap")
        self.assertEqual(struct.unpack_from("<I", ram, view + 0x300 + 12)[0], 0x3f01)
        # "Settings" -> "Frogger!" in the main menu and the Settings title (loader/patches.c)
        marks = (0x191914, 0x191c80)
        for a in marks:
            self.assertEqual(ram[a:a + 8], b"Frogger!")
        # the heap ends 1 MiB early, for the payload (loader/patches.c, HEAP_PATCHES)
        self.assertEqual(struct.unpack_from("<I", ram, 0x91eac)[0], 0xe24cc601)
        self.assertLessEqual(syms["_bss_end"], 0x2000000)
        self.assertGreaterEqual(base, 0x1f00000)
        # the hold menu's bytecode, copied into Settings, and its popup's list (Menu 0x25ba) pointed at
        # the payload's copy with six rows (loader/patches.c, holdmenu_install)
        code = syms["hm_code"]

        snippets = set(range(0x18e48c, 0x18e4e0 + 0x234, 4))      # HM_SNIPPET: the popup's stock Menu and Settings'
        self.assertEqual(ram[0x18e48c:0x18e48c + 16], ram[code:code + 16])
        popup, popup_entry = syms["hm_popup"], 0x18224c
        self.assertEqual(struct.unpack_from("<3I", ram, popup_entry), (0x25ba, popup - (0x181d20 + 0x313c), 4 + 6 * 40))
        self.assertEqual(struct.unpack_from("<I", ram, popup)[0], 6)
        # the main menu (Menu 0x2512) pointed at the payload's copy, with Queue after Music
        main, main_entry = syms["hm_main"], 0x182210
        self.assertEqual(struct.unpack_from("<3I", ram, main_entry), (0x2512, main - (0x181d20 + 0x313c), 4 + 23 * 40))
        self.assertEqual(struct.unpack_from("<I", ram, main)[0], 23)
        self.assertEqual(struct.unpack_from("<10I", ram, main + 4 + 40)[3:9:5], (0x1ae2, 0x3f1b))
        self.assertEqual(struct.unpack_from("<I", ram, main + 4 + 2 * 40 + 32)[0], 0x25d0)    # Playlists after it
        hooked = ({a for a, *_ in self.mkpayload.HOOKS} | {entry + 4, entry + 8} | {np_entry + 4, np_entry + 8}
                  | {popup_entry + 4, popup_entry + 8}
                  | {main_entry + 4, main_entry + 8}
                  | {a + i for a in marks for i in (0, 4)} | {0x91eac} | snippets)
        diff = [a for a in range(0, install.OSOS_2_3_LEN, 4)
                if ram[a:a + 4] != self.stock[a:a + 4] and a not in hooked]
        self.assertEqual(diff, [])                      # nothing else in osos changed

    def test_menu_boots_stock(self):
        pc, ram = self.boot.boot(self.part, menu=True)
        self.assertEqual(pc, self.boot.DRAM)
        self.assertEqual(ram[:install.OSOS_2_3_LEN], self.stock)

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

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


def fake_partition(size=PART_SIZE):
    """A firmware partition shaped like Apple's 2.3 (osos of the right length, its checksum, aupd
    after it), from made-up bytes: the disk tests run without Apple's firmware, on any OS."""
    part = bytearray(size)
    part[0:len(fwtool.STOP_SIGN)] = fwtool.STOP_SIGN
    part[0x100:0x104] = fwtool.HEADER_MAGIC
    struct.pack_into("<I", part, 0x104, 0x4000)                  # directory at 0x4200
    struct.pack_into("<H", part, 0x10a, 2)
    images = []
    for ident, off, n in ((b"soso", 0x4400, install.OSOS_2_3_LEN), (b"dpua", 0x34a800, 0x9000)):
        blob = bytearray((k * 7 + off) & 0xff for k in range(n))
        if ident == b"soso":
            blob[0x20:0x2c] = b"portalplayer"
        part[off:off + n] = blob
        images.append((ident, off, n, fwtool.byte_sum(blob)))
    for k, (ident, off, n, chk) in enumerate(images):
        fwtool.DIR_ENTRY.pack_into(part, 0x4200 + 40 * k, b"!ATA", ident, 0, off, n, 0x10000000, 0, chk, 0x20000, 0)
    return bytes(part)


class FakeDevice:
    """A file that acts like a Windows raw disk: anything but whole 512-byte sectors at
    sector-aligned offsets fails, as it does there."""

    def __init__(self, path, mode="rb", buffering=-1):
        self.f = open(path, mode, buffering=0)
        self.log = []

    def _check(self, what, n):
        if n % 512:
            raise OSError(22, f"unaligned {what} ({n:#x})")

    def seek(self, pos, whence=0):
        if whence == 0:
            self._check("seek", pos)
        return self.f.seek(pos, whence)

    def read(self, n):
        self._check("read", n)
        self._check("read at", self.f.tell())
        return self.f.read(n)

    def write(self, b):
        self._check("write", len(b))
        self.log.append((self.f.tell(), len(b)))
        return self.f.write(b)

    def fileno(self):
        return self.f.fileno()

    def close(self):
        self.f.close()


class DevicePathTest(unittest.TestCase):
    def test_windows_paths(self):
        self.assertEqual(install.check_device(r"\\.\PhysicalDrive2"), "windows")
        self.assertEqual(install.check_device("//./physicaldrive11"), "windows")
        self.assertIsNone(install.check_device("/dev/sdb"))
        self.assertIsNone(install.check_device("/dev/rdisk4"))
        self.assertIsNone(install.check_device("ipod.img"))
        for bad in ("E:", "e:\\", r"\\.\E:", r"\\?\Volume{1234}", r"\\.\Harddisk1Partition1", r"\\.\PhysicalDrive"):
            with self.assertRaises(install.InstallError, msg=bad):
                install.check_device(bad)
        with self.assertRaises(install.InstallError):
            install.check_device(r"\\.\PhysicalDrive2", partition=True)

    def test_cli_refuses_a_drive_letter(self):
        self.assertEqual(install.main(["disk-status", "E:"]), 1)


@unittest.skipUnless(os.name == "nt", "Windows only")
class WindowsVolumesTest(unittest.TestCase):
    def test_lock_volumes_on_a_disk_that_isnt_there(self):
        # walks every drive letter through the ctypes calls, finds none on disk 999, locks nothing
        self.assertEqual(install._lock_volumes(999), [])


class FakeDeviceTest(unittest.TestCase):
    """The disk commands against image files through FakeDevice: no firmware, any OS."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.part = fake_partition()
        self.devices = []

        def opener(path, mode="rb", buffering=-1):
            dev = FakeDevice(self.images.get(str(path), path), mode)
            self.devices.append(dev)
            return dev
        self.images = {}
        self.locks = []
        self._saved = install._open, install._lock_volumes, install._unlock_volumes
        install._open = opener
        install._lock_volumes = lambda n: self.locks.append(("lock", n)) or [("Z", n)]
        install._unlock_volumes = lambda handles: self.locks.append(("unlock", handles))

    def tearDown(self):
        install._open, install._lock_volumes, install._unlock_volumes = self._saved
        self.tmp.cleanup()

    def test_fake_partition_is_stock_2_3(self):
        self.assertEqual(install.status(self.part), ("stock", 0))
        self.assertEqual(install.status(install.patch(self.part, LOADER)), ("frogger", len(LOADER)))

    def test_fake_device_rejects_unaligned_io(self):
        img = self.dir / "d.img"
        img.write_bytes(bytes(4096))
        dev = FakeDevice(img)
        with self.assertRaises(OSError):
            dev.read(100)
        with self.assertRaises(OSError):
            dev.seek(100)
        dev.close()

    def test_unaligned_reads_go_through_whole_sectors(self):
        img = self.dir / "d.img"
        data = bytes(k & 0xff for k in range(8192))
        img.write_bytes(data)
        disk = install.Disk(str(img))
        try:
            self.assertEqual(disk.read(100, 50), data[100:150])
            self.assertEqual(disk.read(510, 1030), data[510:1540])
            self.assertEqual(disk.read(1024, 512), data[1024:1536])
            self.assertIsNone(disk.sector_size())                # an image file has none
        finally:
            disk.close()

    def round_trip(self, image, path=None, partition=False):
        img = self.dir / "ipod.img"
        img.write_bytes(image)
        path = path or str(img)
        self.images[path] = img
        backups = self.dir / "backups"
        self.assertEqual(install.disk_status(path, partition), ("stock", 0))
        backup = install.disk_install(path, LOADER, backups, partition=partition)
        self.assertEqual(backup.read_bytes(), self.part)
        self.assertEqual(install.disk_status(path, partition), ("frogger", len(LOADER)))
        after = img.read_bytes()
        start = image.index(self.part[:0x200])
        self.assertEqual(after[:start], image[:start])                                     # partition table untouched
        self.assertEqual(after[start + len(self.part):], image[start + len(self.part):])   # data partition untouched
        writes = [w for d in self.devices for w in d.log]
        self.assertTrue(writes)
        self.assertTrue(all(off % 512 == 0 and n % 512 == 0 for off, n in writes))
        self.assertEqual(install.main(["disk-remove", path, "--backup-dir", str(backups)]
                                      + (["--partition"] if partition else [])), 0)
        self.assertEqual(install.disk_status(path, partition), ("stock", 0))
        self.assertEqual(install.main(["disk-restore", path, str(backup)] + (["--partition"] if partition else [])), 0)
        self.assertEqual(img.read_bytes(), image)

    def test_mbr_disk(self):
        self.round_trip(bytes(mbr_disk(self.part)))
        self.assertEqual(self.locks, [])

    def test_apm_disk(self):
        self.round_trip(bytes(apm_disk(self.part)))

    def test_partition_device(self):
        self.round_trip(self.part, partition=True)

    def test_windows_physical_drive(self):
        self.round_trip(bytes(mbr_disk(self.part)), path=r"\\.\PhysicalDrive3")
        # each write (install, remove, restore) locks the volumes on disk 3 and gives them back
        self.assertEqual(self.locks, [("lock", 3), ("unlock", [("Z", 3)])] * 3)

    def test_windows_refuses_what_isnt_an_ipod(self):
        img = self.dir / "other.img"
        img.write_bytes(bytes(mbr_disk(bytes(len(self.part)))))      # an MBR, but no firmware in it
        self.images[r"\\.\PhysicalDrive0"] = img
        before = img.read_bytes()
        (self.dir / "l.bin").write_bytes(LOADER)
        self.assertEqual(install.main(["disk-install", r"\\.\PhysicalDrive0", str(self.dir / "l.bin"),
                                       "--backup-dir", str(self.dir / "b")]), 1)
        self.assertEqual(img.read_bytes(), before)
        self.assertEqual(self.locks, [])


@pytest.mark.firmware("firmware/iPod_2.2.3.ipsw")
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
    sys.exit(pytest.main([__file__]))


try:
    import unicorn  # noqa: F401
except ImportError:
    unicorn = None

LOADER_BIN = ROOT / "build/loader/frogger-loader.bin"


@pytest.mark.firmware("firmware/iPod_2.2.3.ipsw")
@pytest.mark.skipif(unicorn is None, reason="needs unicorn (nix develop)")
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
        self.assertEqual(struct.unpack_from("<3I", ram, entry), (0x278d, menu - (0x181d20 + 0x313c), 4 + 23 * 40))
        self.assertEqual(struct.unpack_from("<I", ram, menu)[0], 23)
        # after Clicker (row 8): Show Hidden, Jump by Letter, Resume Mixes, then the five feature switches and Flash Storage
        for row, item in enumerate(range(0x2900, 0x2909), 9):
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

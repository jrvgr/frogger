#!/usr/bin/env python3
r"""Install Frogger's loader into an iPod 3G's firmware partition, or take it out.

Frogger never touches the iPod's flash. The flash boot code loads the osos
image from the hard drive's firmware partition and jumps to its entry
point, so installing means: append the loader to osos, point the
directory's entryOffset at it and fix the checksum. When the images after
osos (aupd) are in the way, they move up the partition first.

Partition images (files, no root needed):

    install.py patch PARTITION LOADER -o OUT     # also replaces an older loader
    install.py strip PARTITION -o OUT
    install.py status PARTITION

A whole disk (or a disk image file): /dev/rdiskN on macOS (`diskutil list`),
/dev/sdX on Linux (`lsblk`), \\.\PhysicalDriveN on Windows (`Get-Disk`). Or with
--partition the firmware partition's own device (/dev/rdisk6s2, /dev/sdX1; not
on Windows). Raw devices need root (sudo) or, on Windows, an Administrator
terminal. Unmount the iPod's volume first (diskutil unmountDisk, umount); on
Windows install.py locks and dismounts it while it writes:

    install.py disk-status /dev/rdiskN
    install.py disk-install /dev/rdiskN LOADER --backup-dir DIR [--owner UID]
    install.py disk-remove /dev/rdiskN --backup-dir DIR [--owner UID]
    install.py disk-restore /dev/rdiskN BACKUP
    install.py disk-install --partition /dev/rdiskNsM LOADER --backup-dir DIR

disk-install and disk-remove always save the whole firmware partition to --backup-dir
before writing, reads it back after writing, and refuses anything that
isn't Apple's 2.3 osos (or 2.3 with a Frogger loader on it).
"""

import argparse
import errno
import os
import re
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fwtool  # noqa: E402

SECTOR = 512
OSOS_2_3_LEN = 0x346368          # Apple's osos 2.3, before any loader
ENTRY = {"devOffset": 12, "len": 16, "entryOffset": 24, "chksum": 28}


class InstallError(Exception):
    pass


# --- partition images ------------------------------------------------------

def _set(part, fw, img, field, value):
    k = fw["images"].index(img)
    struct.pack_into("<I", part, fw["dirOffset"] + 40 * k + ENTRY[field], value)


def _osos(fw):
    return next(i for i in fw["images"] if i["id"] == "osos")


def status(part):
    """'stock', 'frogger' (with the loader's size) or raises if it's not a 3G 2.3 osos."""
    fw = fwtool.parse(bytes(part))
    osos = _osos(fw)
    blob = fwtool.image_bytes(part, osos)
    if blob[0x20:0x2c] != b"portalplayer":
        raise InstallError("osos doesn't start like Apple's firmware")
    if fwtool.byte_sum(blob) != osos["chksum"]:
        raise InstallError("osos checksum doesn't match; refusing to touch it")
    base = osos["entryOffset"] or osos["len"]
    if base != OSOS_2_3_LEN:
        raise InstallError(f"osos is {base:#x} bytes, not firmware 2.3 ({OSOS_2_3_LEN:#x})")
    if osos["entryOffset"] == 0:
        return "stock", 0
    return "frogger", osos["len"] - osos["entryOffset"]


def strip(part):
    """Returns a copy of the partition with Apple's osos as it was."""
    part = bytearray(part)
    state, _ = status(part)
    if state == "stock":
        return part
    fw = fwtool.parse(bytes(part))
    osos = _osos(fw)
    base = osos["entryOffset"]
    start = osos["fileOffset"]
    part[start + base:start + osos["len"]] = bytes(osos["len"] - base)
    _set(part, fw, osos, "len", base)
    _set(part, fw, osos, "entryOffset", 0)
    _set(part, fw, osos, "chksum", fwtool.byte_sum(part[start:start + base]))
    return part


def patch(part, loader):
    """Returns a copy of the partition with `loader` appended to osos. An
    older loader is replaced. Images after osos move up when needed."""
    if not loader or len(loader) % 4:
        raise InstallError("the loader must be a non-empty multiple of 4 bytes")
    part = strip(part)
    fw = fwtool.parse(bytes(part))
    osos = _osos(fw)
    new_len = osos["len"] + len(loader)
    end = osos["fileOffset"] + new_len

    # Move the images after osos (last first, so none overwrites another).
    later = sorted((i for i in fw["images"] if i["fileOffset"] > osos["fileOffset"]), key=lambda i: i["fileOffset"])
    if later and later[0]["fileOffset"] < end:
        shift = -(-(end - later[0]["fileOffset"]) // SECTOR) * SECTOR
        last_end = max(i["fileOffset"] + i["len"] for i in later)
        if last_end + shift > len(part):
            raise InstallError(f"no room in the firmware partition: needs {last_end + shift:#x}, has {len(part):#x}")
        for img in reversed(later):
            blob = fwtool.image_bytes(part, img)
            part[img["fileOffset"]:img["fileOffset"] + img["len"]] = bytes(img["len"])
            part[img["fileOffset"] + shift:img["fileOffset"] + shift + img["len"]] = blob
            _set(part, fw, img, "devOffset", img["devOffset"] + shift)
        fw = fwtool.parse(bytes(part))
        osos = _osos(fw)
    elif end > len(part):
        raise InstallError("no room in the firmware partition")

    start = osos["fileOffset"]
    part[start + osos["len"]:end] = loader
    _set(part, fw, osos, "len", new_len)
    _set(part, fw, osos, "entryOffset", osos["len"])
    _set(part, fw, osos, "chksum", fwtool.byte_sum(part[start:end]))
    if status(part) != ("frogger", len(loader)):
        raise InstallError("patched partition doesn't check out")
    return part


# --- disks -----------------------------------------------------------------

def find_firmware_partition(read):
    """(offset, size) in bytes of the firmware partition on a whole disk.
    `read(offset, n)` reads sector-aligned bytes. Handles the MBR layout of
    Windows-formatted iPods and the Apple Partition Map of Mac-formatted ones."""
    s0 = read(0, SECTOR)
    if s0[0:2] == b"ER":                                      # Apple Partition Map
        n = struct.unpack_from(">I", read(SECTOR, SECTOR), 4)[0]
        for k in range(1, n + 1):
            e = read(k * SECTOR, SECTOR)
            if e[0:2] != b"PM":
                break
            start, count = struct.unpack_from(">II", e, 8)
            ptype = e[48:80].split(b"\0")[0]
            if ptype == b"Apple_MDFW":
                return start * SECTOR, count * SECTOR
        raise InstallError("no Apple_MDFW partition in the Apple Partition Map")
    if s0[510:512] == b"\x55\xaa":                            # MBR: the first entry, type 0
        ptype = s0[0x1be + 4]
        start, count = struct.unpack_from("<II", s0, 0x1be + 8)
        if ptype == 0 and count:
            return start * SECTOR, count * SECTOR
        raise InstallError(f"first MBR partition is type {ptype:#x}, not an iPod firmware partition")
    raise InstallError("no partition table (neither MBR nor Apple Partition Map)")


CHUNK = 1 << 20                  # whole sectors: Windows raw disks take nothing else
WINDOWS = os.name == "nt"


def check_device(path, partition=False):
    r"""'windows' for \\.\PhysicalDriveN, else None (a Unix device or an image file). Refuses
    the Windows paths that aren't a whole physical disk: drive letters and volumes."""
    p = str(path).replace("/", "\\")
    if re.fullmatch(r"[A-Za-z]:\\?", p) or re.fullmatch(r"\\\\[.?]\\[A-Za-z]:\\?", p):
        raise InstallError(f"{path} is a drive letter: give the iPod's whole disk, \\\\.\\PhysicalDriveN "
                           "(the Number column of Get-Disk)")
    if p.startswith(("\\\\.\\", "\\\\?\\")):
        if not re.fullmatch(r"(?i)PhysicalDrive\d+", p[4:]):
            raise InstallError(f"{path}: on Windows only a whole disk, \\\\.\\PhysicalDriveN, will do")
        if partition:
            raise InstallError("--partition doesn't work on Windows: give the whole disk, \\\\.\\PhysicalDriveN")
        return "windows"
    return None


def _hint():
    if WINDOWS:
        return "run it from an Administrator terminal"
    if sys.platform == "darwin":
        return "run it with sudo, after diskutil unmountDisk /dev/diskN"
    return "run it with sudo, after umount-ing the iPod's partitions (lsblk shows them)"


_open = open                     # tests swap in a fake device


class Disk:
    """A raw disk, a partition device or an image file. Every read and write is whole
    512-byte sectors at sector-aligned offsets, which Windows' raw disks insist on."""

    def __init__(self, path, write=False, partition=False):
        self.kind = check_device(path, partition)
        self.number = int(re.search(r"\d+$", str(path)).group()) if self.kind == "windows" else None
        self.partition = partition
        try:
            self.f = _open(path, "r+b" if write else "rb", buffering=0)
        except PermissionError as e:
            raise InstallError(f"{path}: permission denied; {_hint()}") from e
        except OSError as e:
            if e.errno == errno.EBUSY:
                raise InstallError(f"{path} is busy (mounted?); {_hint()}") from e
            raise
        size = self.sector_size()
        if size not in (None, SECTOR):
            self.f.close()
            raise InstallError(f"{path} has {size}-byte sectors; an iPod 3G's disk has {SECTOR}")

    def sector_size(self):
        """The device's logical sector size, or None for an image file (or when it can't say)."""
        try:
            fd = self.f.fileno()
            if WINDOWS:
                import ctypes
                import msvcrt
                from ctypes import wintypes
                k32 = ctypes.WinDLL("kernel32", use_last_error=True)
                k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                                wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                wintypes.LPVOID]
                geometry, got = ctypes.create_string_buffer(24), wintypes.DWORD()
                if not k32.DeviceIoControl(msvcrt.get_osfhandle(fd), 0x70000, None, 0,   # IOCTL_DISK_GET_DRIVE_GEOMETRY
                                           geometry, 24, ctypes.byref(got), None):
                    return None
                return struct.unpack_from("<I", geometry.raw, 20)[0]           # BytesPerSector
            import fcntl
            req = 0x1268 if sys.platform.startswith("linux") else 0x40046418   # BLKSSZGET, DKIOCGETBLOCKSIZE
            return struct.unpack("<I", fcntl.ioctl(fd, req, bytes(4)))[0]
        except (OSError, ValueError, AttributeError, ImportError):
            return None

    def firmware_partition(self):
        """(offset, size) of the firmware partition: the whole device with
        --partition, else found in the partition table."""
        if not self.partition:
            return find_firmware_partition(self.read)
        try:
            size = self.f.seek(0, os.SEEK_END)        # files and Linux block devices
        except OSError:
            size = 0
        if size:
            return 0, size
        self.f.seek(0)
        while True:                       # macOS raw devices don't report a size through seek
            chunk = self.f.read(CHUNK)
            if not chunk:
                return 0, size
            size += len(chunk)

    def read(self, offset, n):
        lo = offset - offset % SECTOR
        hi = -(-(offset + n) // SECTOR) * SECTOR
        self.f.seek(lo)
        out = bytearray()
        while len(out) < hi - lo:
            chunk = self.f.read(min(hi - lo - len(out), CHUNK))
            if not chunk:
                raise InstallError(f"short read at {lo + len(out):#x}")
            out += chunk
        return bytes(out[offset - lo:offset - lo + n])

    def write(self, offset, data):
        assert offset % SECTOR == 0 and len(data) % SECTOR == 0
        self.f.seek(offset)
        view = memoryview(data)
        for k in range(0, len(data), CHUNK):
            part = view[k:k + CHUNK]
            if self.f.write(part) != len(part):
                raise InstallError(f"short write at {offset + k:#x}; restore the backup")
        os.fsync(self.f.fileno())
        if hasattr(os, "posix_fadvise"):    # Linux: drop the cached copy, so the read-back reads the disk
            os.posix_fadvise(self.f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)

    def close(self):
        self.f.close()


def _lock_volumes(number):
    r"""Locks and dismounts the volumes (drive letters) on \\.\PhysicalDrive<number>, so Windows
    lets raw writes through. Returns their handles: closing them gives the volumes back."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    invalid = wintypes.HANDLE(-1).value

    def ioctl(h, code, out=None):
        got = wintypes.DWORD()
        return k32.DeviceIoControl(h, code, None, 0, out, len(out) if out is not None else 0, ctypes.byref(got), None)

    handles = []
    mask = k32.GetLogicalDrives()
    for letter in (chr(65 + i) for i in range(26) if mask >> i & 1):
        h = k32.CreateFileW(f"\\\\.\\{letter}:", 0xC0000000, 3, None, 3, 0, None)  # read|write, share r|w, open existing
        if h in (None, invalid):
            continue
        extents = ctypes.create_string_buffer(8 + 24 * 16)
        if not ioctl(h, 0x560000, extents):                                      # IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS
            k32.CloseHandle(h)
            continue
        count = struct.unpack_from("<I", extents.raw)[0]
        disks = {struct.unpack_from("<I", extents.raw, 8 + 24 * k)[0] for k in range(min(count, 16))}
        if number not in disks:
            k32.CloseHandle(h)
            continue
        for _ in range(10):                                                      # Explorer lets go after a moment
            if ioctl(h, 0x90018):                                                # FSCTL_LOCK_VOLUME
                break
            time.sleep(0.5)
        else:
            print(f"warning: {letter}: is in use; dismounting it anyway", file=sys.stderr)
        if not ioctl(h, 0x90020):                                                # FSCTL_DISMOUNT_VOLUME
            err = ctypes.get_last_error()
            k32.CloseHandle(h)
            for _, other in handles:
                k32.CloseHandle(other)
            raise InstallError(f"couldn't dismount {letter}: (error {err}); close what uses it and try again")
        handles.append((letter, h))
    return handles


def _unlock_volumes(handles):
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    for _, h in handles:
        k32.CloseHandle(ctypes.c_void_p(h))


def _changed_range(old, new):
    """The smallest sector-aligned range where old and new differ."""
    old, new = bytes(old), bytes(new)
    sectors = [k for k in range(0, len(old), SECTOR) if old[k:k + SECTOR] != new[k:k + SECTOR]]
    return (sectors[0], sectors[-1] + SECTOR) if sectors else None


def _write_partition(disk, offset, old, new):
    r = _changed_range(old, new)
    if r:
        lo, hi = r
        locked = _lock_volumes(disk.number) if disk.kind == "windows" else []
        try:
            disk.write(offset + lo, bytes(new[lo:hi]))
        finally:
            if locked:
                _unlock_volumes(locked)
    if disk.read(offset, len(new)) != bytes(new):
        raise InstallError("read-back after writing doesn't match; restore the backup")


def disk_status(path, partition=False):
    disk = Disk(path, partition=partition)
    try:
        off, size = disk.firmware_partition()
        return status(disk.read(off, size))
    finally:
        disk.close()


def disk_install(path, loader, backup_dir, owner=None, partition=False):
    """Installs (or updates) the loader; None as loader takes Frogger out."""
    disk = Disk(path, write=True, partition=partition)
    try:
        off, size = disk.firmware_partition()
        old = disk.read(off, size)
        state, _ = status(old)
        new = patch(old, loader) if loader else strip(old)
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"firmware-partition-{stamp}-{state}.bin"
        n = 2
        while backup.exists():
            backup = backup_dir / f"firmware-partition-{stamp}-{state}-{n}.bin"
            n += 1
        backup.write_bytes(old)
        if owner is not None:
            os.chown(backup, owner, -1)
            os.chown(backup_dir, owner, -1)
        if backup.read_bytes() != old:
            raise InstallError("backup didn't save correctly; nothing written")
        _write_partition(disk, off, old, new)
        return backup
    finally:
        disk.close()


def disk_restore(path, backup, partition=False):
    data = Path(backup).read_bytes()
    disk = Disk(path, write=True, partition=partition)
    try:
        off, size = disk.firmware_partition()
        if len(data) != size:
            raise InstallError(f"backup is {len(data)} bytes, the firmware partition {size}")
        status(data)                                          # it must be a sane 2.3 partition
        old = disk.read(off, size)
        _write_partition(disk, off, old, data)
    finally:
        disk.close()


# --- command line ----------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("patch"); s.add_argument("partition"); s.add_argument("loader"); s.add_argument("-o", "--output", required=True)
    s = sub.add_parser("strip"); s.add_argument("partition"); s.add_argument("-o", "--output", required=True)
    s = sub.add_parser("status"); s.add_argument("partition")
    s = sub.add_parser("disk-status"); s.add_argument("disk")
    s = sub.add_parser("disk-install"); s.add_argument("disk"); s.add_argument("loader")
    s.add_argument("--backup-dir", required=True); s.add_argument("--owner", type=int)
    s = sub.add_parser("disk-remove"); s.add_argument("disk")
    s.add_argument("--backup-dir", required=True); s.add_argument("--owner", type=int)
    s = sub.add_parser("disk-restore"); s.add_argument("disk"); s.add_argument("backup")
    for name in ("disk-status", "disk-install", "disk-remove", "disk-restore"):
        sub.choices[name].add_argument("--partition", action="store_true",
                                       help="the device is the firmware partition itself, not a whole disk")
    args = p.parse_args(argv)
    try:
        if args.cmd == "patch":
            _, part = fwtool.load_partition(args.partition)
            Path(args.output).write_bytes(patch(part, Path(args.loader).read_bytes()))
        elif args.cmd == "strip":
            _, part = fwtool.load_partition(args.partition)
            Path(args.output).write_bytes(strip(part))
        elif args.cmd == "status":
            _, part = fwtool.load_partition(args.partition)
            state, n = status(part)
            print(state if state == "stock" else f"frogger ({n} byte loader)")
        elif args.cmd == "disk-status":
            state, n = disk_status(args.disk, args.partition)
            print(state if state == "stock" else f"frogger ({n} byte loader)")
        elif args.cmd == "disk-install":
            backup = disk_install(args.disk, Path(args.loader).read_bytes(), args.backup_dir, args.owner, args.partition)
            print(f"installed; backup at {backup}")
        elif args.cmd == "disk-remove":
            backup = disk_install(args.disk, None, args.backup_dir, args.owner, args.partition)
            print(f"removed; backup at {backup}")
        elif args.cmd == "disk-restore":
            disk_restore(args.disk, args.backup, args.partition)
            print("restored")
    except (InstallError, fwtool.FirmwareError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

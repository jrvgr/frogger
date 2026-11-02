#!/usr/bin/env python3
"""Install Frogger's loader into an iPod 3G's firmware partition, or take it out.

Frogger never touches the iPod's flash. The flash boot code loads the osos
image from the hard drive's firmware partition and jumps to its entry
point, so installing means: append the loader to osos, point the
directory's entryOffset at it and fix the checksum. When the images after
osos (aupd) are in the way, they move up the partition first.

Partition images (files, no root needed):

    install.py patch PARTITION LOADER -o OUT     # also replaces an older loader
    install.py strip PARTITION -o OUT
    install.py status PARTITION

A whole disk (or a disk image file), or with --partition the firmware
partition's own device (/dev/rdisk6s2, from `diskutil list`). Reading raw
devices needs root, and Crate unmounts the iPod's volume while writing:

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
import os
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


class Disk:
    def __init__(self, path, write=False, partition=False):
        self.f = open(path, "r+b" if write else "rb", buffering=0)
        self.partition = partition

    def firmware_partition(self):
        """(offset, size) of the firmware partition: the whole device with
        --partition, else found in the partition table."""
        if not self.partition:
            return find_firmware_partition(self.read)
        size = 0
        self.f.seek(0)
        while True:                       # raw devices don't report a size through seek
            chunk = self.f.read(1 << 20)
            if not chunk:
                return 0, size
            size += len(chunk)

    def read(self, offset, n):
        self.f.seek(offset)
        out = bytearray()
        while len(out) < n:
            chunk = self.f.read(min(n - len(out), 1 << 20))
            if not chunk:
                raise InstallError(f"short read at {offset + len(out):#x}")
            out += chunk
        return bytes(out)

    def write(self, offset, data):
        assert offset % SECTOR == 0 and len(data) % SECTOR == 0
        self.f.seek(offset)
        view = memoryview(data)
        for k in range(0, len(data), 1 << 20):
            self.f.write(view[k:k + (1 << 20)])
        os.fsync(self.f.fileno())

    def close(self):
        self.f.close()


def _changed_range(old, new):
    """The smallest sector-aligned range where old and new differ."""
    old, new = bytes(old), bytes(new)
    sectors = [k for k in range(0, len(old), SECTOR) if old[k:k + SECTOR] != new[k:k + SECTOR]]
    return (sectors[0], sectors[-1] + SECTOR) if sectors else None


def _write_partition(disk, offset, old, new):
    r = _changed_range(old, new)
    if r:
        lo, hi = r
        disk.write(offset + lo, bytes(new[lo:hi]))
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

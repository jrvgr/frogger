#!/usr/bin/env python3
"""Inspect and unpack Apple iPod 1G-5G firmware partition images.

Accepts an Apple .ipsw (a zip holding a firmware partition dump) or a raw
partition dump made with `ipodpatcher -r`. The format follows Rockbox's
utils/ipodpatcher: a "STOP sign" copyright banner at 0x0, a "]ih[" header at
0x100 with the directory offset at 0x104 and the format version at 0x10a, and
a directory of 40-byte entries describing each image (osos, rsrc, aupd, ...).

Each entry is: device ("!ATA"), type ("soso" = osos, byte-reversed), image
index, devOffset, len, addr (load address), entryOffset, chksum, vers, loadAddr.
On 1G-3G images loadAddr is not a load address (2.3 stores 0x048d0040 there);
addr is where Apple's boot code copies the image.

    fwtool.py info iPod_2.2.3.ipsw
    fwtool.py extract iPod_2.2.3.ipsw -o build/fw
"""

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

STOP_SIGN = b"{{~~  /-----\\   {{~~ /       \\  "
HEADER_MAGIC = b"]ih["
DIR_ENTRY = struct.Struct("<4s4sIIIIIIII")
SECTOR = 512
MAX_IMAGES = 10

# Directory ids are stored byte-reversed on disk ("soso" is osos).
KNOWN_IDS = {"osos", "rsrc", "aupd", "osbk", "hibe"}


class FirmwareError(Exception):
    pass


def load_partition(path):
    """Return (name, bytes) of the firmware partition inside path."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for member in zf.infolist():
                data = zf.read(member)
                if data.startswith(STOP_SIGN):
                    return member.filename, data
        raise FirmwareError(f"{path}: no firmware partition image inside the zip")
    data = path.read_bytes()
    if not data.startswith(STOP_SIGN):
        raise FirmwareError(f"{path}: not an iPod firmware partition (no Apple STOP banner)")
    return path.name, data


def parse(data):
    """Parse the header and directory. Returns a dict describing the partition."""
    if data[0x100:0x104] != HEADER_MAGIC:
        raise FirmwareError("bad firmware header (no ]ih[ at 0x100)")
    version = struct.unpack_from("<H", data, 0x10A)[0]
    diroffset = struct.unpack_from("<I", data, 0x104)[0] + 0x200

    # Same 2nd-gen Nano quirk ipodpatcher handles: directory starts a sector later.
    if data[diroffset] == 0:
        diroffset += SECTOR - (diroffset % SECTOR)

    images = []
    pos = diroffset
    while len(images) < MAX_IMAGES and pos + DIR_ENTRY.size <= len(data):
        dev, ident, index, dev_offset, length, addr, entry, chksum, vers, load_addr = DIR_ENTRY.unpack_from(data, pos)
        if dev not in (b"!ATA", b"DNAN"):
            break
        images.append({
            "id": ident[::-1].decode("ascii", "replace"),
            "dev": dev.decode("ascii"),
            "index": index,
            "devOffset": dev_offset,
            "len": length,
            "addr": addr,
            "entryOffset": entry,
            "chksum": chksum,
            "vers": vers,
            "loadAddr": load_addr,
        })
        pos += DIR_ENTRY.size

    if not any(img["id"] == "osos" for img in images):
        raise FirmwareError("no osos image in the directory")

    # Version 2 (1G-3G) images are addressed from the partition start,
    # version 3 (4G and later) from one sector in.
    fwoffset = 0 if (version == 2 and len(images) > 1) else SECTOR
    for img in images:
        img["fileOffset"] = fwoffset + img["devOffset"]

    return {"version": version, "dirOffset": diroffset, "images": images}


def image_bytes(data, img):
    start = img["fileOffset"]
    end = start + img["len"]
    if end > len(data):
        raise FirmwareError(f"{img['id']}: runs past the end of the partition ({end:#x} > {len(data):#x})")
    return data[start:end]


def byte_sum(blob):
    return sum(blob) & 0xFFFFFFFF


def describe(img, blob):
    return {
        **img,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "byteSum": byte_sum(blob),
        "chksumMatches": byte_sum(blob) == img["chksum"],
        "portalplayerTag": blob[0x20:0x2C] == b"portalplayer",
    }


def cmd_info(args):
    name, data = load_partition(args.firmware)
    fw = parse(data)
    print(f"{name}: {len(data)} bytes, format version {fw['version']}, directory at {fw['dirOffset']:#x}")
    print(f"{'id':5} {'offset':>10} {'len':>10} {'addr':>10} {'entry':>8} {'vers':>10}  checksum")
    for img in fw["images"]:
        d = describe(img, image_bytes(data, img))
        state = "ok" if d["chksumMatches"] else f"stored {img['chksum']:#010x}, sum {d['byteSum']:#010x}"
        print(f"{img['id']:5} {img['fileOffset']:#10x} {img['len']:#10x} {img['addr']:#10x} "
              f"{img['entryOffset']:#8x} {img['vers']:#10x}  {state}")
    return 0


def cmd_extract(args):
    name, data = load_partition(args.firmware)
    fw = parse(data)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"source": name, "version": fw["version"], "images": []}
    for img in fw["images"]:
        blob = image_bytes(data, img)
        (out / f"{img['id']}.img").write_bytes(blob)
        manifest["images"].append(describe(img, blob))
        print(f"wrote {out / (img['id'] + '.img')} ({len(blob)} bytes)")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out / 'manifest.json'}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="list the images in a firmware partition")
    p.add_argument("firmware")
    p.set_defaults(func=cmd_info)
    p = sub.add_parser("extract", help="write each image plus manifest.json to a directory")
    p.add_argument("firmware")
    p.add_argument("-o", "--output", default="build/fw")
    p.set_defaults(func=cmd_extract)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FirmwareError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

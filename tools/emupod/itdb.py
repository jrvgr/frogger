"""iTunesDB records for test cards (mhbd v9), as Apple's 2.3 reads them: hmcard.py and the scripts that
write their own database use these; mhit(..., hidden=True) sets Frogger's hide flag, dbid= the
persistent id (default 0x1000 + track id), mhyp(..., pid=) a playlist's."""
import struct
MHOD_TYPES = {"title": 1, "location": 2, "album": 3, "artist": 4, "genre": 5}

def mhod(kind, text):  # as tools/emu/itunesdb.py builds it
    s = text.encode("utf-16-le")
    body = struct.pack("<IIII", 1, len(s), 0, 0) + s
    return struct.pack("<4sIII8x", b"mhod", 0x18, 0x18 + len(body), MHOD_TYPES[kind]) + body

def mhit(tid, fields, size, ms, bitrate, rate=44100, hidden=False, dbid=None):
    mh = b"".join(mhod(k, v) for k, v in fields.items())
    h = bytearray(0x9c)
    struct.pack_into("<4sIIIII", h, 0, b"mhit", 0x9c, 0x9c + len(mh), len(fields), tid, 1)
    struct.pack_into("<I", h, 0x18, 0x4d503320)          # 'MP3 '
    h[0x1c] = 1; h[0x1d] = 1                              # type1/type2: CBR MP3
    struct.pack_into("<IIIIIII", h, 0x24, size, ms, 1, 1, 2026, bitrate, rate << 16)
    struct.pack_into("<Q", h, 0x70, 0x1000 + tid if dbid is None else dbid)   # the dbid (Frogger's files go by it)
    if hidden:
        h[0x98:0x9c] = b"HIDE"                            # Frogger's hide flag
    return bytes(h) + mh

def mhod100(pos):
    return struct.pack("<4sIIIII", b"mhod", 0x18, 0x2c, 100, 0, 0) + struct.pack("<I16x", pos)

def mhip(tid, pos):
    body = mhod100(pos)
    h = bytearray(0x4c)
    struct.pack_into("<4sIIIIII", h, 0, b"mhip", 0x4c, 0x4c + len(body), 1, 0, 0, tid)
    return bytes(h) + body

def mhyp(name, tids, master=True, pid=None):
    t = mhod("title", name)
    items = b"".join(mhip(tid, i + 1) for i, tid in enumerate(tids))
    h = bytearray(0x6c)
    struct.pack_into("<4sIIIII", h, 0, b"mhyp", 0x6c, 0x6c + len(t) + len(items), 1, len(tids), int(master))
    struct.pack_into("<Q", h, 0x1c, pid if pid is not None else 0xabcdef if master else 0xabcdf0)
    struct.pack_into("<H", h, 0x28, 1)
    return bytes(h) + t + items

def mhsd(kind, body):
    h = bytearray(0x60); struct.pack_into("<4sIII", h, 0, b"mhsd", 0x60, 0x60 + len(body), kind); return bytes(h) + body

def mhl(tag, items):
    h = bytearray(0x5c); struct.pack_into("<4sII", h, 0, tag, 0x5c, len(items)); return bytes(h) + b"".join(items)

def mhbd(sds):
    body = b"".join(sds)
    h = bytearray(0x68)
    struct.pack_into("<4sIIIII", h, 0, b"mhbd", 0x68, 0x68 + len(body), 1, 9, len(sds))
    struct.pack_into("<Q", h, 0x18, 0x1122334455667788)
    struct.pack_into("<H", h, 0x20, 2)
    return bytes(h) + body

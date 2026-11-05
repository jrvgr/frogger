#!/usr/bin/env python3
"""What Frogger keeps on an iPod, readable without Crate.

Crate (the Mac app that syncs Frogger's iPod) isn't released yet. Until it is, this script shows
what Frogger wrote on the iPod and sets the hide flag, so the features that need a syncing app
can be looked at and used by hand. It reads the iPod's files and names the songs from its
iTunesDB. Plain Python 3, nothing to install. The iPod must be mounted (disk mode).

    tools/podinfo.py /Volumes/IPOD                 # summary: the database, Frogger's files
    tools/podinfo.py /Volumes/IPOD hidden          # songs flagged hidden, and hidden/shown on the iPod
    tools/podinfo.py /Volumes/IPOD skips           # skip counts (FroggerSkips)
    tools/podinfo.py /Volumes/IPOD playlists       # songs added on the iPod (OTGPlaylistInfo*, FroggerPlaylist_*)
    tools/podinfo.py /Volumes/IPOD bookmarks       # where long songs were left (Play Counts, FroggerBookmarks)
    tools/podinfo.py /Volumes/IPOD hide ID...      # set the hide flag on these track ids
    tools/podinfo.py /Volumes/IPOD unhide ID...    # clear it
    tools/podinfo.py /Volumes/IPOD tracks          # every track: position, id, title, artist

Every list prints tab-separated columns with a header, so it can go into a spreadsheet or a
sync script. Positions are a track's index in the iTunesDB (from 0); ids are its mhit id.

hide/unhide write the iTunesDB in place (4 bytes per track) after copying it to
iTunesDB.frogger-backup next to it. Any other syncing app (iTunes, gtkpod, ...) writes a new
iTunesDB without the flag. Frogger's own files (FroggerHidden, FroggerSkips, FroggerBookmarks,
FroggerPlaylist_<id>, FroggerArt) name songs by their dbid (or track id, size and length), so
they still apply after such a sync, to the songs that are still there. Older versions of them
(by position) only fit the iTunesDB they were written for. Every format: docs/file-formats.md."""

import argparse
import collections
import datetime
import os
import shutil
import struct
import sys

HIDE_OFFSET, HIDE_MAGIC = 0x98, b"HIDE"
MHOD_TITLE, MHOD_LOCATION, MHOD_ALBUM, MHOD_ARTIST = 1, 2, 3, 4
FIELDS = {MHOD_TITLE: "title", MHOD_LOCATION: "location", MHOD_ALBUM: "album", MHOD_ARTIST: "artist"}
RESUME_MIN_MS = 20 * 60 * 1000          # Frogger bookmarks songs this long (payload/resume.h)
MAC_EPOCH = datetime.datetime(1904, 1, 1)


def read(path):
    with open(path, "rb") as f:
        return f.read()


class Key(collections.namedtuple("Key", "dbid id size ms")):
    """How Frogger's files name a song (payload/tracks.h): the mhit's dbid (+0x70), track id
    (+0x10), size (+0x24) and length in ms (+0x28). 20 bytes, little-endian."""
    SIZE = 20

    @classmethod
    def unpack(cls, data, off=0):
        return cls(*struct.unpack_from("<QIII", data, off))

    def pack(self):
        return struct.pack("<QIII", *self)


class Track:
    def __init__(self, pos, offset, tid, ms, bookmark, hidden, header, dbid=0, size=0):
        self.pos, self.offset, self.id, self.ms = pos, offset, tid, ms
        self.bookmark, self.hidden, self.header = bookmark, hidden, header
        self.dbid, self.size = dbid, size
        self.title = self.artist = self.album = self.location = ""     # location: ":iPod_Control:Music:F00:X.mp3"


class Database:
    """The iTunesDB's tracks (in file order) and its master playlist (the order Apple's
    On-The-Go files refer to)."""

    def __init__(self, path):
        self.path = path
        self.data = read(path)
        self.tracks, self.master, self.playlists = [], [], []
        d = self.data
        if d[:4] != b"mhbd":
            raise SystemExit(f"{path}: not an iTunesDB")
        off = struct.unpack_from("<I", d, 4)[0]
        while off + 16 <= len(d) and d[off:off + 4] == b"mhsd":
            hlen, total, kind = struct.unpack_from("<III", d, off + 4)
            if kind == 1:
                self._tracks(off + hlen)
            elif kind == 2:
                self._playlists(off + hlen)
            off += total
        self.by_id = {t.id: t for t in self.tracks}
        self.by_dbid = {}
        for t in self.tracks:
            if t.dbid:
                self.by_dbid.setdefault(t.dbid, t)

    def _tracks(self, off):
        d = self.data
        hlen, n = struct.unpack_from("<II", d, off + 4)
        off += hlen
        for pos in range(n):
            hlen, total, nmhod, tid = struct.unpack_from("<IIII", d, off + 4)
            ms = struct.unpack_from("<I", d, off + 0x28)[0] if hlen >= 0x2c else 0
            bookmark = struct.unpack_from("<I", d, off + 0x6c)[0] if hlen >= 0x70 else 0
            hidden = hlen >= HIDE_OFFSET + 4 and d[off + HIDE_OFFSET:off + HIDE_OFFSET + 4] == HIDE_MAGIC
            size = struct.unpack_from("<I", d, off + 0x24)[0] if hlen >= 0x28 else 0
            dbid = struct.unpack_from("<Q", d, off + 0x70)[0] if hlen >= 0x78 else 0
            t = Track(pos, off, tid, ms, bookmark, hidden, hlen, dbid, size)
            m = off + hlen
            for _ in range(nmhod):
                mh, mtotal, kind = struct.unpack_from("<III", d, m + 4)
                if kind in FIELDS:
                    length = struct.unpack_from("<I", d, m + mh + 4)[0]
                    s = d[m + mh + 16:m + mh + 16 + length].decode("utf-16-le", "replace")
                    setattr(t, FIELDS[kind], s)
                m += mtotal
            self.tracks.append(t)
            off += total

    def _playlists(self, off):
        d = self.data
        hlen, n = struct.unpack_from("<II", d, off + 4)
        off += hlen
        for _ in range(n):
            hlen, total, nmhod, nmhip = struct.unpack_from("<IIII", d, off + 4)
            master = d[off + 0x14]
            pid = struct.unpack_from("<Q", d, off + 0x1c)[0] if hlen >= 0x24 else 0
            self.playlists.append((pid, self._name(off + hlen, off + total)))
            if master:
                m = off + hlen
                end = off + total
                while m < end:
                    mtotal = struct.unpack_from("<I", d, m + 8)[0]     # an mhip's takes in its mhods
                    if d[m:m + 4] == b"mhip":
                        self.master.append(struct.unpack_from("<I", d, m + 0x18)[0])
                    m += mtotal
            off += total

    def _name(self, m, end):
        d = self.data
        while m + 16 <= end and d[m:m + 4] == b"mhod":
            mh, mtotal, kind = struct.unpack_from("<III", d, m + 4)
            if kind == MHOD_TITLE:
                length = struct.unpack_from("<I", d, m + mh + 4)[0]
                return d[m + mh + 16:m + mh + 16 + length].decode("utf-16-le", "replace")
            m += mtotal
        return ""

    def key(self, t):
        return Key(t.dbid, t.id, t.size, t.ms)

    def find(self, key):
        """The track a key names, by the payload's rule (tracks.c): the same dbid, else the
        same track id, size and length when one of the two has no dbid; None if it's gone."""
        t = self.by_dbid.get(key.dbid) if key.dbid else None
        if t:
            return t
        t = self.by_id.get(key.id)
        if t and t.size == key.size and t.ms == key.ms and not (key.dbid and t.dbid):
            return t
        return None

    def name(self, t):
        return "\t".join((t.title, t.artist, t.album))


def itunes(root, name):
    return os.path.join(root, "iPod_Control", "iTunes", name)


HIDDEN, SKIPS, BOOKMARKS, PLAYLIST, ART = b"FRGH", b"FRGS", b"FRGB", b"FRGP", b"FRGA"
# Each format's versions: entry size, and whether entries name songs by key (else by position, id).
VERSIONS = {HIDDEN: {1: (8, False), 2: (12, False), 3: (24, True)}, SKIPS: {1: (16, False), 2: (28, True)},
            BOOKMARKS: {1: (24, True)}, PLAYLIST: {1: (20, True)}}


class FroggerFile:
    """A FroggerHidden/FroggerSkips/FroggerBookmarks/FroggerPlaylist_<id> file. entries: one
    tuple each, the song first: a Key for the keyed versions, else (position, track id); then
    the entry's other u32s (hidden: flags; skips: count, last; bookmarks: ms)."""

    def __init__(self, data, magic):
        self.magic = magic
        if len(data) < 20 or data[:4] != magic:
            raise ValueError("not a Frogger %s file" % magic.decode())
        _, self.version, self.entry_size, self.stamp, count, self.reserved = struct.unpack_from("<IHHIII", data, 0)
        self.id = None
        head = 20
        if magic == PLAYLIST:
            self.id = struct.unpack_from("<Q", data, 16)[0]
            head = 24
        size, keyed = VERSIONS[magic].get(self.version, (None, None))
        if size != self.entry_size:
            raise ValueError("%s version %d with %d-byte entries: not one this reads" % (magic.decode(), self.version, self.entry_size))
        self.keyed = keyed
        self.entries = []
        for i in range(count):
            off = head + i * size
            if off + size > len(data):
                break
            if keyed:
                rest = struct.unpack_from("<%dI" % ((size - Key.SIZE) // 4), data, off + Key.SIZE)
                self.entries.append((Key.unpack(data, off), *rest))
            else:
                w = struct.unpack_from("<%dI" % (size // 4), data, off)
                self.entries.append(((w[0], w[1]), *w[2:]))

    def track(self, db, song):
        """The track an entry's song is in db, or None: by key, or for the old versions by
        position and id (the iPod reads those only with their own iTunesDB)."""
        if self.keyed:
            return db.find(song)
        return track(db, *song)


def frogger_file(path, magic):
    """A FroggerFile, None if there's no such file, or what's wrong with it (a str)."""
    if not os.path.exists(path):
        return None
    try:
        return FroggerFile(read(path), magic)
    except ValueError as e:
        return str(e)


def fresh(path, db):
    """Whether a file Frogger wrote is newer than the iTunesDB (the iPod reads it only then)."""
    return os.path.getmtime(path) >= os.path.getmtime(db.path)


def track(db, pos, tid):
    """The track a Frogger file names by position and id, if the database still has it there."""
    t = db.tracks[pos] if pos < len(db.tracks) else None
    return t if t and t.id == tid else db.by_id.get(tid)


class FroggerArt:
    """FroggerArt (payload/nowplaying.h): version 2's table of (Key, image), version 1's image
    per track position. images: the pictures' bytes (72 rows of 20 bytes, 2 bits a pixel)."""
    SIZE, NONE = 72, 0xffff
    ROW = (SIZE // 4 + 3) & ~3
    BYTES = ROW * SIZE

    def __init__(self, data):
        if len(data) < 24 or data[:4] != ART:
            raise ValueError("not a FroggerArt file")
        _, self.version, size, n, images, image_bytes, _ = struct.unpack_from("<IHHIIII", data, 0)
        if size != self.SIZE or image_bytes != self.BYTES or self.version not in (1, 2):
            raise ValueError("FroggerArt version %d, %d px: not one this reads" % (self.version, size))
        if self.version == 1:
            self.table = list(struct.unpack_from("<%dH" % n, data, 24))
            off = (24 + 2 * n + 3) & ~3
        else:
            self.table = [(Key.unpack(data, 24 + 24 * i), struct.unpack_from("<H", data, 24 + 24 * i + 20)[0])
                          for i in range(n)]
            off = 24 + 24 * n
        if len(data) < off + images * self.BYTES:
            raise ValueError("FroggerArt: %d bytes, %d images need %d" % (len(data), images, off + images * self.BYTES))
        self.images = [data[off + i * self.BYTES:off + (i + 1) * self.BYTES] for i in range(images)]

    def covers(self, db):
        """{track position: image index} for db, as the iPod reads it (version 1 only if it
        has db's track count; entries whose song is gone are dropped)."""
        if self.version == 1:
            if len(self.table) != len(db.tracks):
                return {}
            return {pos: i for pos, i in enumerate(self.table) if i != self.NONE and i < len(self.images)}
        out = {}
        for key, i in self.table:
            t = db.find(key)
            if t and i != self.NONE and i < len(self.images):
                out.setdefault(t.pos, i)
        return out


def show_summary(root, db):
    print("iTunesDB\t%d tracks, %d in the master playlist, written %s" % (
        len(db.tracks), len(db.master), datetime.datetime.fromtimestamp(os.path.getmtime(db.path)).strftime("%Y-%m-%d %H:%M")))
    print("hide flags\t%d tracks" % sum(t.hidden for t in db.tracks))
    for name, magic in (("FroggerHidden", HIDDEN), ("FroggerSkips", SKIPS), ("FroggerBookmarks", BOOKMARKS)):
        path = itunes(root, name)
        f = frogger_file(path, magic)
        if f is None:
            print(f"{name}\tnone")
        elif isinstance(f, str):
            print(f"{name}\t{f}")
        else:
            here = sum(f.track(db, e[0]) is not None for e in f.entries)
            stale = not f.keyed and not fresh(path, db)
            print("%s\tversion %d, %d entries, %d of them songs in this database%s" % (
                name, f.version, len(f.entries), here, " (older than the iTunesDB: the iPod ignores it)" if stale else ""))
    lists = sorted(n for n in os.listdir(itunes(root, "")) if n.startswith(("OTGPlaylistInfo", "FroggerPlaylist_")))
    print("playlist files\t%s" % (", ".join(lists) or "none"))
    art = itunes(root, "FroggerArt")
    if os.path.exists(art):
        try:
            a = FroggerArt(read(art))
            n = len(a.covers(db))
            print("FroggerArt\tversion %d, %d covers, %d of %d songs have one%s" % (
                a.version, len(a.images), n, len(db.tracks), "" if n or not a.table else
                " (not for this database: Now Playing shows the frame)"))
        except ValueError as e:
            print("FroggerArt\t%s" % e)
    else:
        print("FroggerArt\tnone (Now Playing shows the frame; Crate or tools/coverart.py writes it)")


def show_tracks(db):
    print("pos\tid\thidden\ttitle\tartist\talbum")
    for t in db.tracks:
        print("%d\t%d\t%s\t%s" % (t.pos, t.id, "yes" if t.hidden else "", db.name(t)))


def show_hidden(root, db):
    print("id\tstate\twhere\ttitle\tartist\talbum")
    for t in db.tracks:
        if t.hidden:
            print("%d\thidden\tiTunesDB flag\t%s" % (t.id, db.name(t)))
    path = itunes(root, "FroggerHidden")
    f = frogger_file(path, HIDDEN)
    if not isinstance(f, FroggerFile):
        return
    note = "on the iPod" if f.keyed or fresh(path, db) else "on the iPod, stale"
    for e in f.entries:
        t = f.track(db, e[0])
        shown = len(e) > 1 and e[1] & 1
        print("%s\t%s\t%s\t%s" % (t.id if t else e[0][1], "shown" if shown else "hidden", note,
                                    db.name(t) if t else "(not in this database)"))


def show_skips(root, db):
    path = itunes(root, "FroggerSkips")
    f = frogger_file(path, SKIPS)
    print("id\tskips\tlast skipped\ttitle\tartist\talbum")
    if not isinstance(f, FroggerFile):
        return
    for song, count, last in f.entries:
        t = f.track(db, song)
        when = (MAC_EPOCH + datetime.timedelta(seconds=last)).strftime("%Y-%m-%d %H:%M") if last else ""
        print("%d\t%d\t%s\t%s" % (t.id if t else song[1], count, when, db.name(t) if t else "(not in this database)"))
    if not f.keyed and not fresh(path, db):
        print("# older than the iTunesDB: these counts are from before the last sync", file=sys.stderr)


def show_playlists(root, db):
    """Apple's On-The-Go files and Frogger's old FroggerPlaylist_I: an mhpo header and a u32 per
    song, the index of the song in the master playlist's order. Frogger's FroggerPlaylist_<id>:
    the songs by key."""
    print("file\tid\ttitle\tartist\talbum")
    names = dict(db.playlists)              # persistent id: name
    for name in sorted(os.listdir(itunes(root, ""))):
        if not name.startswith(("OTGPlaylistInfo", "FroggerPlaylist_")):
            continue
        d = read(itunes(root, name))
        if d[:4] == PLAYLIST:
            try:
                f = FroggerFile(d, PLAYLIST)
            except ValueError:
                continue
            label = "%s (%s)" % (name, names.get(f.id, "no such playlist now"))
            for (song,) in f.entries:
                t = db.find(song)
                print("%s\t%s\t%s" % (label, t.id if t else "", db.name(t) if t else "(not in this database)"))
            continue
        if d[:4] != b"mhpo":
            continue
        hlen, size, count = struct.unpack_from("<III", d, 4)
        for i in range(count):
            ref = struct.unpack_from("<I", d, hlen + i * size)[0]
            tid = db.master[ref] if ref < len(db.master) else None
            t = db.by_id.get(tid)
            print("%s\t%s\t%s" % (name, tid if tid is not None else "", db.name(t) if t else "(not in this database)"))


def show_bookmarks(root, db):
    """Play Counts (mhdp): 16 bytes per track in the track list's order, +8 the bookmark (ms);
    FroggerBookmarks for the songs without one."""
    path = itunes(root, "Play Counts")
    print("id\tleft at\tlength\ttitle\tartist\talbum")
    marks = {}
    if os.path.exists(path):
        d = read(path)
        if d[:4] == b"mhdp":
            hlen, size, count = struct.unpack_from("<III", d, 4)
            if count == len(db.tracks):
                for i in range(count):
                    marks[i] = struct.unpack_from("<I", d, hlen + i * size + 8)[0]
    f = frogger_file(itunes(root, "FroggerBookmarks"), BOOKMARKS)
    if isinstance(f, FroggerFile):          # the iPod uses these after another app's sync
        for song, ms in f.entries:
            t = db.find(song)
            if t and not marks.get(t.pos, t.bookmark):
                marks[t.pos] = ms
    for t in db.tracks:
        ms = marks.get(t.pos, t.bookmark)
        if t.ms >= RESUME_MIN_MS and ms:
            print("%d\t%s\t%s\t%s" % (t.id, clock(ms), clock(t.ms), db.name(t)))


def clock(ms):
    s = ms // 1000
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def set_hidden(db, ids, on):
    missing = [i for i in ids if i not in db.by_id]
    if missing:
        raise SystemExit("no such track id: %s" % ", ".join(map(str, missing)))
    short = [i for i in ids if db.by_id[i].header < HIDE_OFFSET + 4]
    if short:
        raise SystemExit("these tracks' mhit headers are too short for the flag: %s" % ", ".join(map(str, short)))
    backup = db.path + ".frogger-backup"
    shutil.copyfile(db.path, backup)
    with open(db.path, "r+b") as f:
        for i in ids:
            if db.by_id[i].hidden != on:          # unhide clears only Frogger's own word
                f.seek(db.by_id[i].offset + HIDE_OFFSET)
                f.write(HIDE_MAGIC if on else b"\0\0\0\0")
    print("%s %d tracks; the old iTunesDB is %s. Eject the iPod to see it." % (
        "hid" if on else "unhid", len(ids), backup))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ipod", help="the mounted iPod, e.g. /Volumes/IPOD")
    ap.add_argument("what", nargs="?", default="summary",
                    choices=["summary", "tracks", "hidden", "skips", "playlists", "bookmarks", "hide", "unhide"])
    ap.add_argument("ids", nargs="*", type=int, help="track ids, for hide and unhide")
    a = ap.parse_args(argv)
    path = itunes(a.ipod, "iTunesDB")
    if not os.path.exists(path):
        raise SystemExit(f"no iTunesDB at {path}: is the iPod mounted?")
    db = Database(path)
    if a.what in ("hide", "unhide"):
        if not a.ids:
            raise SystemExit("which track ids? (podinfo.py IPOD tracks lists them)")
        set_hidden(db, a.ids, a.what == "hide")
    elif a.what == "summary":
        show_summary(a.ipod, db)
    else:
        {"tracks": lambda: show_tracks(db), "hidden": lambda: show_hidden(a.ipod, db),
         "skips": lambda: show_skips(a.ipod, db), "playlists": lambda: show_playlists(a.ipod, db),
         "bookmarks": lambda: show_bookmarks(a.ipod, db)}[a.what]()


if __name__ == "__main__":
    main()

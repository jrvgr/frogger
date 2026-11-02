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
    tools/podinfo.py /Volumes/IPOD bookmarks       # where long songs were left (Play Counts)
    tools/podinfo.py /Volumes/IPOD hide ID...      # set the hide flag on these track ids
    tools/podinfo.py /Volumes/IPOD unhide ID...    # clear it
    tools/podinfo.py /Volumes/IPOD tracks          # every track: position, id, title, artist

Every list prints tab-separated columns with a header, so it can go into a spreadsheet or a
sync script. Positions are a track's index in the iTunesDB (from 0); ids are its mhit id.

hide/unhide write the iTunesDB in place (4 bytes per track) after copying it to
iTunesDB.frogger-backup next to it. Any other syncing app (iTunes, gtkpod, ...) writes a new
iTunesDB without the flag. Frogger's own files (FroggerHidden, FroggerSkips, FroggerPlaylist_*)
carry the iTunesDB's time stamp, so the iPod ignores them once the database is newer: read them
before syncing (or before hide/unhide), and carry what you want to keep into your library.
Formats: payload/hide.h, payload/skips.h, docs/re-notes.md ("Playlists made on the iPod",
"Bookmarks"), docs/nowplaying.md (FroggerArt)."""

import argparse
import datetime
import os
import shutil
import struct
import sys

HIDE_OFFSET, HIDE_MAGIC = 0x98, b"HIDE"
MHOD_TITLE, MHOD_ALBUM, MHOD_ARTIST = 1, 3, 4
RESUME_MIN_MS = 20 * 60 * 1000          # Frogger bookmarks songs this long (payload/resume.h)
MAC_EPOCH = datetime.datetime(1904, 1, 1)


def read(path):
    with open(path, "rb") as f:
        return f.read()


class Track:
    def __init__(self, pos, offset, tid, ms, bookmark, hidden, header):
        self.pos, self.offset, self.id, self.ms = pos, offset, tid, ms
        self.bookmark, self.hidden, self.header = bookmark, hidden, header
        self.title = self.artist = self.album = ""


class Database:
    """The iTunesDB's tracks (in file order) and its master playlist (the order Apple's
    On-The-Go files refer to)."""

    def __init__(self, path):
        self.path = path
        self.data = read(path)
        self.tracks, self.master = [], []
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

    def _tracks(self, off):
        d = self.data
        hlen, n = struct.unpack_from("<II", d, off + 4)
        off += hlen
        for pos in range(n):
            hlen, total, nmhod, tid = struct.unpack_from("<IIII", d, off + 4)
            ms = struct.unpack_from("<I", d, off + 0x28)[0] if hlen >= 0x2c else 0
            bookmark = struct.unpack_from("<I", d, off + 0x6c)[0] if hlen >= 0x70 else 0
            hidden = hlen >= HIDE_OFFSET + 4 and d[off + HIDE_OFFSET:off + HIDE_OFFSET + 4] == HIDE_MAGIC
            t = Track(pos, off, tid, ms, bookmark, hidden, hlen)
            m = off + hlen
            for _ in range(nmhod):
                mh, mtotal, kind = struct.unpack_from("<III", d, m + 4)
                if kind in (MHOD_TITLE, MHOD_ALBUM, MHOD_ARTIST):
                    length = struct.unpack_from("<I", d, m + mh + 4)[0]
                    s = d[m + mh + 16:m + mh + 16 + length].decode("utf-16-le", "replace")
                    setattr(t, {MHOD_TITLE: "title", MHOD_ALBUM: "album", MHOD_ARTIST: "artist"}[kind], s)
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
            if master:
                m = off + hlen
                end = off + total
                while m < end:
                    mtotal = struct.unpack_from("<I", d, m + 8)[0]     # an mhip's takes in its mhods
                    if d[m:m + 4] == b"mhip":
                        self.master.append(struct.unpack_from("<I", d, m + 0x18)[0])
                    m += mtotal
                return
            off += total

    def name(self, t):
        return "\t".join((t.title, t.artist, t.album))


def itunes(root, name):
    return os.path.join(root, "iPod_Control", "iTunes", name)


def frogger_file(path, magic):
    """A FroggerHidden/FroggerSkips file: (version, stamp, entries as tuples of u32), or None."""
    if not os.path.exists(path):
        return None
    d = read(path)
    if len(d) < 20 or d[:4] != magic:
        return "not a Frogger file"
    _, version, size, stamp, count, _ = struct.unpack_from("<IHHIII", d, 0)
    words = size // 4
    entries = [struct.unpack_from("<%dI" % words, d, 20 + i * size) for i in range(count)
               if 20 + (i + 1) * size <= len(d)]
    return version, stamp, entries


def fresh(path, db):
    """Whether a file Frogger wrote is newer than the iTunesDB (the iPod reads it only then)."""
    return os.path.getmtime(path) >= os.path.getmtime(db.path)


def track(db, pos, tid):
    """The track a Frogger file names by position and id, if the database still has it there."""
    t = db.tracks[pos] if pos < len(db.tracks) else None
    return t if t and t.id == tid else db.by_id.get(tid)


def show_summary(root, db):
    print("iTunesDB\t%d tracks, %d in the master playlist, written %s" % (
        len(db.tracks), len(db.master), datetime.datetime.fromtimestamp(os.path.getmtime(db.path)).strftime("%Y-%m-%d %H:%M")))
    print("hide flags\t%d tracks" % sum(t.hidden for t in db.tracks))
    for name, magic in (("FroggerHidden", b"FRGH"), ("FroggerSkips", b"FRGS")):
        path = itunes(root, name)
        f = frogger_file(path, magic)
        if f is None:
            print(f"{name}\tnone")
        elif isinstance(f, str):
            print(f"{name}\t{f}")
        else:
            print("%s\tversion %d, %d entries%s" % (name, f[0], len(f[2]), "" if fresh(path, db) else
                                                    " (older than the iTunesDB: the iPod ignores it)"))
    lists = sorted(n for n in os.listdir(itunes(root, "")) if n.startswith(("OTGPlaylistInfo", "FroggerPlaylist_")))
    print("playlist files\t%s" % (", ".join(lists) or "none"))
    art = itunes(root, "FroggerArt")
    if os.path.exists(art):
        d = read(art)[:24]
        magic, version, size, positions, images, _ = struct.unpack_from("<4sHHIII", d, 0) if len(d) == 24 else (b"", 0, 0, 0, 0, 0)
        ok = magic == b"FRGA" and positions == len(db.tracks)
        print("FroggerArt\t%d covers for %d tracks%s" % (images, positions, "" if ok else
                                                       " (not for this database: Now Playing shows the frame)"))
    else:
        print("FroggerArt\tnone (Now Playing shows the frame; Crate writes it, tools/emupod/mkart.py makes test pictures)")


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
    f = frogger_file(path, b"FRGH")
    if not isinstance(f, tuple):
        return
    note = "on the iPod" if fresh(path, db) else "on the iPod, stale"
    for e in f[2]:
        t = track(db, e[0], e[1])
        shown = f[0] >= 2 and len(e) > 2 and e[2] & 1
        print("%d\t%s\t%s\t%s" % (e[1], "shown" if shown else "hidden", note, db.name(t) if t else "(not in this database)"))


def show_skips(root, db):
    path = itunes(root, "FroggerSkips")
    f = frogger_file(path, b"FRGS")
    print("id\tskips\tlast skipped\ttitle\tartist\talbum")
    if not isinstance(f, tuple):
        return
    for pos, tid, count, last in f[2]:
        t = track(db, pos, tid)
        when = (MAC_EPOCH + datetime.timedelta(seconds=last)).strftime("%Y-%m-%d %H:%M") if last else ""
        print("%d\t%d\t%s\t%s" % (tid, count, when, db.name(t) if t else "(not in this database)"))
    if not fresh(path, db):
        print("# older than the iTunesDB: these counts are from before the last sync", file=sys.stderr)


def show_playlists(root, db):
    """Apple's On-The-Go files and Frogger's FroggerPlaylist_I: an mhpo header and a u32 per
    song, the index of the song in the master playlist's order."""
    print("file\tid\ttitle\tartist\talbum")
    for name in sorted(os.listdir(itunes(root, ""))):
        if not name.startswith(("OTGPlaylistInfo", "FroggerPlaylist_")):
            continue
        d = read(itunes(root, name))
        if d[:4] != b"mhpo":
            continue
        hlen, size, count = struct.unpack_from("<III", d, 4)
        for i in range(count):
            ref = struct.unpack_from("<I", d, hlen + i * size)[0]
            tid = db.master[ref] if ref < len(db.master) else None
            t = db.by_id.get(tid)
            print("%s\t%s\t%s" % (name, tid if tid is not None else "", db.name(t) if t else "(not in this database)"))


def show_bookmarks(root, db):
    """Play Counts (mhdp): 16 bytes per track in the track list's order, +8 the bookmark (ms)."""
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

# Frogger's files on the iPod

Every file Frogger reads or writes on the iPod, and the iTunesDB fields it relies on. A syncing
app (Crate, or your own script) needs this to read what the iPod recorded and to write what
Frogger shows. `tools/podinfo.py` reads all of them, `tools/coverart.py` writes FroggerArt, and
`tests/fixtures/` has a sample of each format and version (`tests/fixtures/mkfixtures.py` writes
them, `tests/test_fixtures.py` reads them back).

All files are in `iPod_Control/iTunes/` on the iPod's FAT32 volume. Numbers are little-endian.
Frogger's own files share a 20-byte header (FroggerPlaylist's is 24 bytes, FroggerArt's 24 bytes of
its own).

## How a file names a song

Frogger's files name songs by a **track key** (`payload/tracks.h`), 20 bytes, taken from the song's
`mhit` in the iTunesDB:

| Offset | Size | Field | From |
| --- | --- | --- | --- |
| 0 | 8 | dbid, the persistent id | `mhit+0x70` |
| 8 | 4 | track id | `mhit+0x10` |
| 12 | 4 | file size, bytes | `mhit+0x24` |
| 16 | 4 | length, ms | `mhit+0x28` |

A key matches the track in the loaded iTunesDB:

1. with the same dbid, if the key's dbid isn't 0;
2. else (no dbid in the key, or no track has it) the track with the same track id, size **and**
   length, as long as the key or the track has no dbid (two different dbids never match).

An entry whose key matches no track is **dropped**: its song isn't on the iPod any more. Frogger
never falls back to the song at the same position. iTunes and most syncing apps (libgpod's among
them) keep a song's dbid from sync to sync, so Frogger's data stays with its songs whichever app
synced last. An app that writes new dbids and new track ids for every song breaks the link, and the
data is lost rather than put on the wrong songs.

The firmware's track record keeps neither the dbid nor the position (the track loader never reads
`mhit+0x70`), so `track_hook` (`0xc4b30`) hands `tracks.c` each record with its `mhit` header as the
database loads, and `tracks.c` keeps the keys in a table by position (up to 16384 tracks; songs
beyond that can't be named by Frogger's files) with hash tables by dbid and by track id.

**Older versions** named a song by its **position** in the iTunesDB (the `mhit`'s index in the `mhlt`,
from 0) and its track id. Those only fit the iTunesDB they were written for, so Frogger reads them
only when their `stamp` is the loaded iTunesDB's (see below), checks the track id at that position,
and writes the new version the next time it saves. No migration is needed on the host side:
podinfo.py reads both.

**stamp** is what `0x77600()` returns: the iTunesDB's file time (`0xa0380`, word `+8`), which Apple
puts in its On-The-Go files too. Every sync writes a new iTunesDB, so a new stamp. The keyed versions
carry the stamp they were written with for information; only FroggerBookmarks uses it (below).

## The common header (20 bytes)

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | magic: `"FRGH"`, `"FRGS"`, `"FRGB"` (`"FRGP"`: 24-byte header, below) |
| 4 | 2 | version |
| 6 | 2 | entry size, bytes |
| 8 | 4 | stamp: the iTunesDB's when written |
| 12 | 4 | count: entries after the header |
| 16 | 4 | reserved, 0 |

A reader takes `count` entries of `entry size` bytes. Frogger refuses a version or entry size it
doesn't know and goes on as if there were no file.

## FroggerHidden: songs hidden or shown on the iPod

Written by the iPod (`payload/hide.c`) when the hold menu's **Hide** or **Show** changes a song (at
once if the disk is free, else at the next quiet tick or as Play Counts is written). Read by the iPod
after every database load, and by the syncing app, which writes the hide flag (below) into the next
iTunesDB and can then delete the file.

The file holds only the differences from the iTunesDB's flag: a song hidden that the iTunesDB doesn't
flag, or shown (Show) that it does. A Hide that the flag already says, or a Show of a song only the
file hid, takes the song out of the file.

| Version | Entry size | Entry | Read |
| --- | --- | --- | --- |
| 3 (written) | 24 | track key (20), flags (4) | always |
| 2 | 12 | position, track id, flags | only with the loaded iTunesDB's stamp |
| 1 | 8 | position, track id (all hidden) | only with the loaded iTunesDB's stamp |

flags bit 0: **shown** (Show on a song the iTunesDB flags; the syncing app shouldn't flag it again);
else **hidden**. Up to 4096 entries. On a mismatch (no track for the key, or the old versions' track
id isn't at that position) the entry is dropped.

## FroggerSkips: skip counts

Written by the iPod (`payload/skips.c`) only as Apple writes Play Counts (`counts_hook`: a second or
two after a song change, at sleep, before the database unloads), never in the middle of a song change.
A song counts as skipped when it's left with Next or for another song between 2 and 20 s in (iTunes'
rule). Read back after every database load, so the counts add up until the syncing app takes them
into its library and deletes the file.

| Version | Entry size | Entry | Read |
| --- | --- | --- | --- |
| 2 (written) | 28 | track key (20), skips (4), last skipped (4) | always |
| 1 | 16 | position, track id, skips, last skipped | only with the loaded iTunesDB's stamp |

last skipped: seconds since 1904-01-01, local time (the clock of Play Counts' "last played",
`0xa065c`). Up to 2048 songs. Entries for songs that are gone are dropped; two old entries for one
song add up.

## FroggerBookmarks: where long songs were left

Written by the iPod (`payload/resume.c`) as Apple writes Play Counts, right after Frogger puts the
playing song's position in its bookmark, and only when a bookmark changed. One entry per track of 20
minutes or more (Resume Mixes) with a bookmark that isn't 0.

| Version | Entry size | Entry |
| --- | --- | --- |
| 1 | 24 | track key (20), bookmark in ms (4) |

Apple keeps bookmarks in the track record (`track+0x60`, `mhit+0x6c`) and in Play Counts, which is
by position and which Apple ignores once the iTunesDB's track count changes; most syncing apps delete
it after reading it. So after a database load the iPod uses FroggerBookmarks only if its stamp is
**not** the loaded iTunesDB's (a sync happened since), and only for the long tracks that came without
a bookmark of their own (`mhit+0x6c` and Play Counts both 0). It then marks Play Counts to be written,
so the position is Apple's again. A syncing app that carries bookmarks over should write them into
`mhit+0x6c` and can delete the file.

## FroggerPlaylist: songs added to a synced playlist

The hold menu's **Add to Playlist** adds songs to a playlist on the iPod. Apple saves On-The-Go and
the playlists made on the iPod in its own files (below); a synced playlist has no file of Apple's, so
`payload/playlist.c` writes one of Frogger's, holding the playlist's whole song list after the add.
It's read the first time Playlists opens after boot (`playlist_load_saved`), and if it names any song
still on the iPod, its songs replace the synced ones. The syncing app should take the list into its
library (and delete the file), or the file's list keeps winning over what it syncs.

**`FroggerPlaylist_<id>`** (written): `<id>` is the playlist's persistent id (`mhyp+0x1c`, which the
firmware keeps in the playlist object at `+0x14`, `0xc4370`) as 16 hex digits, upper case, e.g.
`FroggerPlaylist_0000000000ABCDF0`. So the file follows the playlist through syncs that keep its id,
whatever its position.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | `"FRGP"` |
| 4 | 2 | version: 1 |
| 6 | 2 | entry size: 20 |
| 8 | 4 | stamp |
| 12 | 4 | count |
| 16 | 8 | the playlist's persistent id, as in the name |
| 24 | 20 × count | the songs in order, a track key each |

Songs whose key matches nothing are left out; a file whose id isn't the playlist's is ignored.

**`FroggerPlaylist_I`** (old, still read, and still written for a playlist whose persistent id is 0):
`I` is the playlist's index in the library's playlist list (`lib+0x870`; 0 is the library, synced
playlists follow in the iTunesDB's order). Apple's On-The-Go format, read by Apple's own reader
`0xc5a90`, which turns it down unless the stamp matches:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | `"mhpo"` |
| 4 | 4 | header size: `0x14` |
| 8 | 4 | entry size: 4 |
| 12 | 4 | count |
| 16 | 4 | stamp |
| 20 | 4 × count | each song's index in the **master playlist's order** (its `mhip`s), from 0 |

`FroggerPlaylist_<id>` is tried first; `FroggerPlaylist_I` only for a playlist that has none.

## FroggerArt: the covers

Written by the syncing app or `tools/coverart.py` (Crate writes it at the end of every sync). Read by
the iPod's cover task (`payload/art.c`) when a song starts. Version 2's table is read once per
database (and again if the file's entry or image count changes) into a cover per track position.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | `"FRGA"` |
| 4 | 2 | version: 2 (1 is still read) |
| 6 | 2 | cover size: 72 |
| 8 | 4 | count: table entries (version 1: the iTunesDB's track count) |
| 12 | 4 | images |
| 16 | 4 | bytes per image: 1440 |
| 20 | 4 | reserved, 0 |

**Version 2**: `count` entries of 24 bytes: a track key (20), the image index (2, `0xffff` for none),
2 bytes padding. List the songs that have a cover; songs not in the table get none. The images start
right after the table, at `24 + 24 × count`. Entries for songs that are gone are ignored, so the file
stays right for the songs that remain after any sync; new songs have no cover until it's written
again.

**Version 1**: a u16 image index (or `0xffff`) per track position, padded to 4 bytes; the images
start at `(24 + 2 × count + 3) & ~3`. Used only if `count` is the loaded iTunesDB's track count, else
the cover page shows the frame with a refresh arrow (`WHY_TRACK_COUNT`).

**Images**: 72 rows of 20 bytes (18 used), 2 bits a pixel, the left pixel in the top bits, 0 =
background, 3 = black (the LCD's four greys). Songs of an album share one image. On a read failure or
a song without a cover, the cover page shows a frog in a frame; the frog frowns and a small icon says
what went wrong (`docs/nowplaying.md`, "Covers").

## FroggerDebug: the crash record (debug builds)

Written by `frogger-loader-debug.bin` only (`payload/debug.c`), on the first UI tick after a boot, from
the record the previous boot left in RAM. Plain text, one item a line:

    Frogger debug, boot 3
    crash: data abort (kind 4)            (or: no crash recorded)
    spsr 600000d3  sp 0040fe2c  lr 000b9178
    r0  ...   r1  ...   r2  ...   r3  ...
    ...
    stack:
     ...
    vm trail, oldest first; ... (N in all): pc [-> pc it went on with]
    00195630 -> 001956c1

Nothing reads it back. Attach it to a bug report.

## Apple's files Frogger relies on

- **`iTunesDB`**: the database. Frogger never writes it on the iPod (`tools/podinfo.py hide` does,
  on the host). The fields Frogger reads are below.
- **`Play Counts`** (`mhdp`, header `0x60`, 16 bytes per track in the track list's order: plays since
  the sync, last played, **bookmark ms**, rating): Apple writes it (`0xf4d6c`) and reads it back at
  boot if its count matches the iTunesDB's. Resume Mixes puts the playing song's position in it
  (`counts_hook`); FroggerSkips and FroggerBookmarks are written at the same moments.
- **`OTGPlaylistInfo`**, **`OTGPlaylistInfo_N`**: On-The-Go and the playlists made on the iPod ("New
  Playlist N"), Apple's format (the `mhpo` table above), stamped. Add to Playlist into them goes
  through Apple's writer. They don't survive a sync by design; the syncing app reads them.
- **`iPod_Control/Device/Preferences`**: Apple's settings. Frogger's switches live in Apple's prefs
  flags word (`prefs+0xb04`, bits 16-26, `payload/settings.h`; at offset `0xafc` in the file), so
  Apple saves them.

## The iTunesDB fields Frogger relies on

| Field | Where | What Frogger does with it |
| --- | --- | --- |
| hide flag | `mhit+0x98`, the 4 bytes `"HIDE"` | Hidden song: out of Artists, Albums, Genres, Composers (`hide.h`). The firmware reads that word but never uses it. Any other value: not hidden |
| track id | `mhit+0x10` | Part of the track key. The track list must be in ascending track id (the firmware finds playlist items by id) |
| size | `mhit+0x24` | Part of the track key |
| length, ms | `mhit+0x28` | Part of the track key; 20 minutes or more: Resume Mixes bookmarks the song |
| bookmark, ms | `mhit+0x6c` | Where a long song starts (Apple's audiobook bookmark, `track+0x60`) |
| dbid | `mhit+0x70`, 8 bytes | The track key's main part. 0 if the app writes none: then id, size and length must all match |
| visible | `mhit+0x14` | Must be 1, or the firmware doesn't load the track at all |
| album artist | mhod type 22 | Read in place of the artist, for Album Artists (`artist.c`) |
| playlist persistent id | `mhyp+0x1c`, 8 bytes | Names `FroggerPlaylist_<id>` |
| master playlist order | the master `mhyp`'s `mhip`s | What Apple's On-The-Go entries (and `FroggerPlaylist_I`) count in |

The `mhit` header must be at least `0x9c` bytes, as 2.3 reads it.

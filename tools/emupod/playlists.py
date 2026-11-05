"""Frogger image: the hold menu's "Add to Playlist" (payload/playlist.c), and whether it lasts.

    playlists.py add     # card copy pl-card.img (written back). Songs: hold Tone A > Add to
                         # Playlist > pick On-The-Go; On-The-Go > Save Playlist ("New Playlist 1");
                         # Songs: hold Tone B > Add to Playlist > pick New Playlist 1; sleep;
                         # list iPod_Control/iTunes
    playlists.py check   # boot pl-card.img again: open New Playlist 1 (Tone A and Tone B?)
    playlists.py album   # Albums > the first album > hold its first song > Add to Playlist >
                         # On-The-Go: back in that album (pl_album_*.png)
    playlists.py synced  # a card with a synced playlist "Mix" holding Tone A only: Songs: hold
                         # Tone B > Add to Playlist > Mix; sleep; list the files
    playlists.py check   # (after synced: is the song still in that playlist after a restart?)
    playlists.py lists   # (after synced) Artists: hold the artist > Add to Playlist > On-The-Go
                         # (both songs); Playlists: hold Mix > Add to Queue (it plays)
    playlists.py order   # a synced Mix of three songs whose title, artist, album and database
                         # orders all differ (C/A/B, A/C/A, B/B/C), plus D/D/D added through
                         # the hold menu: which order the file's song references count in
    playlists.py order2  # the same, but the iTunesDB lists 102, 103, 101 (master too): only two
                         # songs load, so the track list must be in track-id order
    playlists.py order3  # tracks in id order, master playlist 103, 101, 102, 104: refs [1, 2, 0, 3]
                         # (order 0x26 is the master playlist's order)
    playlists.py resync  # (after synced) write the iTunesDB again, as a sync would: the file
                         # is now stale, so Mix must stay as synced (Tone A only)

Screenshots pl_*.png; prints each playlist's song count after each step."""
import shutil, struct, subprocess, sys
from pathlib import Path
from ipod3g import Pod, W

card = W + "/pl-card.img"
step = sys.argv[1]
if step in ("add", "album"):
    shutil.copy(W + "/music-card.img", card)
if step == "resync":
    mbr = Path(card).read_bytes()[:512]
    start = struct.unpack_from("<I", mbr, 0x1be + 24)[0]
    db = Path(card).with_suffix(".iTunesDB")
    subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{card}@@{start * 512}",
                    "::/iPod_Control/iTunes/iTunesDB", str(db)], check=True)
    import os; os.utime(db, None)                               # a new file time, as a sync's iTunesDB has
    subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{card}@@{start * 512}",
                    str(db), "::/iPod_Control/iTunes/iTunesDB"], check=True)
    db.unlink()
if step in ("synced", "order", "order2", "order3"):                       # Mix: Tone A only
    import itdb as mkdb
    shutil.copy(W + "/music-card.img", card)
    loc = lambda name: ":iPod_Control:Music:F00:%s.mp3" % name
    tracks = [(101, {"title": "Tone A", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
                     "location": loc("TONEA")}, 2881119, 180000, 128),
              (102, {"title": "Tone B long", "artist": "Test Artist", "album": "Test Album", "genre": "Test",
                     "location": loc("TONEB")}, 28802739, 720000, 320)]
    mix = [101]
    master = [101, 102]
    if step.startswith("order"):                                # title/artist/album; D/D/D last in every order
        tracks = [(i, {"title": t, "artist": a, "album": b, "genre": "Test", "location": loc("TONEA")},
                   2881119, 180000, 128)
                  for i, t, a, b in [(101, "C", "A", "B"), (102, "A", "C", "A"), (103, "B", "B", "C"),
                                     (104, "D", "D", "D")]]
        mix, master = [101, 102, 103], [101, 102, 103, 104]
        if step == "order2":
            tracks = [tracks[1], tracks[2], tracks[0], tracks[3]]
            master = [102, 103, 101, 104]
        if step == "order3":
            master = [103, 101, 102, 104]
    db = mkdb.mhbd([mkdb.mhsd(1, mkdb.mhl(b"mhlt", [mkdb.mhit(*t) for t in tracks])),
                    mkdb.mhsd(2, mkdb.mhl(b"mhlp", [mkdb.mhyp("iPod", master),
                                                    mkdb.mhyp("Mix", mix, master=False)]))])
    mbr = Path(card).read_bytes()[:512]
    start = struct.unpack_from("<I", mbr, 0x1be + 24)[0]
    tmp = Path(card).with_suffix(".iTunesDB"); tmp.write_bytes(db)
    subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-o", "-i", f"{card}@@{start * 512}",
                    str(tmp), "::/iPod_Control/iTunes/iTunesDB"], check=True)
    tmp.unlink()
p = Pod(osos=W + "/osos-frogger.img", disk=card, persist=True)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]


def lists(tag):
    lib = rd(rd(0x43580c) + 0x1c)
    arr, n = rd(lib + 0x870), rd(lib + 0x874)
    counts = ["%d:%d(N=%d)" % (i, rd(rd(rd(arr + 4 * i) + 0x24) + 0x2c), rd(rd(arr + 4 * i) + 0x124)) for i in range(n)]
    otg = rd(lib + 0x48)
    print("%-36s lists %s  otg=%d" % (tag, " ".join(counts), rd(rd(otg + 0x24) + 0x2c)))


def sel(after=1_500_000):
    p.press("select", after_us=after); p.settle()


def wheel(n):
    p.scroll(n); p.settle(); p.run(500_000)


def menu(times=1):
    for _ in range(times):
        p.press("menu", after_us=1_500_000); p.settle()


def shot(name):
    print(p.shot("pl_%s.png" % name, 1))


def add_to_playlist(pick_row, tag, row=2):
    """Hold, then the popup's Add to Playlist: row 2 on a song (Add to Queue, Play Album Next,
    Add to Playlist, ...), row 1 on an album, artist or playlist (no Play Album Next)."""
    p.press("select", hold_us=2_000_000); p.settle()
    wheel(row); sel(); shot(tag + "_picker")
    wheel(-6); wheel(pick_row); sel(2_000_000); shot(tag + "_back")


if step == "add":
    sel()                                                       # first run: Language -> English
    sel(); wheel(3); sel()                                      # Music > Songs
    lists("start")
    add_to_playlist(1, "a")                                     # rows: Mix, On-The-Go
    lists("Tone A > On-The-Go")
    menu(); wheel(-6); sel(); sel(); shot("otg")                # Music > Playlists > On-The-Go
    wheel(2); sel(); wheel(1); sel(2_000_000)                   # Save Playlist > confirm
    lists("saved New Playlist 1")
    shot("saved")                                               # (Save lands in Playlists)
    menu(); wheel(-6); wheel(3); sel(); wheel(1)                # Music > Songs, Tone B
    add_to_playlist(1, "b")                                     # rows: Mix, New Playlist 1, On-The-Go
    lists("Tone B > New Playlist 1")
    menu(3)
    p.press("play", hold_us=3_000_000, after_us=10_000_000)     # sleep
    del p
    mbr = Path(card).read_bytes()[:512]
    start = struct.unpack_from("<I", mbr, 0x1be + 24)[0]
    print(subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mdir", "-a", "-i", f"{card}@@{start * 512}",
                          "::/iPod_Control/iTunes"], capture_output=True, text=True).stdout)
elif step == "album":
    sel(); sel(); wheel(2); sel(); wheel(1); sel(); shot("album_before")   # Music > Albums > first album
    add_to_playlist(1, "album")                                 # rows: Mix, On-The-Go
    lists("album song > On-The-Go")
elif step in ("synced", "order", "order2", "order3"):
    sel(); sel(); wheel(3); sel(); wheel(1 if step == "synced" else 3)   # (Language), Music > Songs, Tone B (D)
    lists("start")
    add_to_playlist(0, "synced")                                # rows: Mix, On-The-Go
    lists("Tone B > Mix")
    menu(3)
    p.press("play", hold_us=3_000_000, after_us=10_000_000)     # sleep
    del p
    mbr = Path(card).read_bytes()[:512]
    start = struct.unpack_from("<I", mbr, 0x1be + 24)[0]
    print(subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mdir", "-a", "-i", f"{card}@@{start * 512}",
                          "::/iPod_Control/iTunes"], capture_output=True, text=True).stdout)
    out = Path(card).with_suffix(".fp")
    subprocess.run(["nix", "shell", "nixpkgs#mtools", "-c", "mcopy", "-n", "-i", f"{card}@@{start * 512}",
                    "::/iPod_Control/iTunes/FroggerPlaylist_1", str(out)], check=True)
    f = out.read_bytes(); out.unlink()
    n = struct.unpack_from("<I", f, 0xc)[0]
    print("FroggerPlaylist_1: stamp %#x, refs %s" % (struct.unpack_from("<I", f, 0x10)[0],
                                                     list(struct.unpack_from("<%dI" % n, f, 0x14))))
elif step == "lists":
    def playing():
        lib = rd(rd(0x43580c) + 0x1c); it = rd(rd(rd(lib) + 4) + 0x2a8)
        return "nothing" if not it else "list %x" % rd(it)
    wheel(-6); sel(); wheel(1); sel(); shot("artists")           # Music > Artists
    lists("Artists")
    add_to_playlist(5, "artist", 1)                            # picker rows: Mix, On-The-Go
    lists("artist > On-The-Go")
    menu(); wheel(-6); sel(); shot("playlists")                 # Music > Playlists
    p.press("select", hold_us=2_000_000); p.settle(); shot("mix_popup")
    sel(2_000_000); lists("Mix > Add to Queue"); print("playing:", playing()); shot("mix_queued")
else:
    lists("after a restart")
    wheel(-6); sel(); sel(); lists("Playlists opened"); sel(); shot("check")   # Music > Playlists > first

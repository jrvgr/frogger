#!/usr/bin/env python3
"""The README's screenshots: boots the Frogger image in emupod on a demo card and saves one PNG per
feature in docs/screenshots/, each in the same plain frame. Re-running gives the same files.

The demo card (build/emupod-work/demo-card.img) is music-card.img with a database of made-up
artists, albums and songs (the test tones as audio), one compilation under its album artist, and
a FroggerArt of drawn covers (simple shapes, made for 2-bit grey). Every boot fakes a battery
reading (battery.py's stub), so the title bar shows a percentage.

    tools/emupod/screenshots.py [-j 4] [--no-image] [SCENE...]    # default: every scene
    tools/emupod/screenshots.py --raw SCENE                        # also the plain 2x shots, in build/emupod-work

Needs mkcards.py's cards and a loader build (it runs mkimage.py first, unless --no-image).
"""
import argparse, math, struct, subprocess, sys, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "docs/screenshots"
WORK = ROOT / "build/emupod-work"
CARD = WORK / "demo-card.img"

# ---------------------------------------------------------------------------------------------
# The demo card: (album artist or None, artist(s), album, cover, songs). Songs are (title, m:ss).

ALBUMS = [
    (None, "Amber Coast", "Salt Lines", "sun", ["Afterglow", "Breakwater", "Coastal", "Driftwood", "Estuary", "Foghorn"]),
    (None, "Brightwater", "Paper Moons", "rings", ["Gardenia", "Hollow Hills", "Indigo", "Juniper", "Kestrel", "Lanterns"]),
    (None, "Delta Moth", "Low Light", "peaks", ["Mercury", "Nocturne", "Opal", "Paper Planes", "Quiet Hours", "Riverbed"]),
    (None, "Field Lines", "Signal Path", "bands", ["Satellite", "Tidewater", "Undertow", "Vapour", "Wavelength", "Xylem"]),
    (None, "Glass Harbour", "North Window", "tiles", ["Yellow Room", "Zephyr", "Arcade", "Blue Hour", "Cassette", "Daylight"]),
    (None, "Kite Season", "Weather Report", "waves", ["Ember", "Fieldnotes", "Glow", "Harbour Lights", "Icebreaker", "Jetstream"]),
    ("Selector Fen", ["Pale Orchard", "Quiet Engines", "Tin Lantern", "Copper Fox", "Lumen Drive", "Moss Avenue"],
     "Night Bus Tapes", "dots", ["Kaleidoscope", "Last Light", "Moonlit", "Neon Rain", "Overpass", "Pulse"]),
    (None, "Low Orbit", "Satellites", "chevrons", ["Quartz", "Rooftops", "Sunday", "Telescope", "Umbra", "Violet"]),
]
LENGTHS = [152, 167, 179, 141, 173, 160, 178, 149]        # seconds, cycled (Tone A is 3:00 long)
TONEA = (":iPod_Control:Music:F00:TONEA.mp3", 2881119, 128)
PLAYLISTS = {"Road Trip": ["Coastal", "Jetstream", "Neon Rain", "Satellite", "Blue Hour"]}


def songs():
    """[(track id, fields, track number, ms, cover)] in database order."""
    out, n = [], 0
    for aa, artist, album, cover, titles in ALBUMS:
        for i, t in enumerate(titles):
            f = {"title": t, "artist": artist[i] if isinstance(artist, list) else artist, "album": album, "genre": "Demo",
                 "location": TONEA[0]}
            if aa:
                f["albumartist"] = aa
            out.append((300 + n, f, i + 1, LENGTHS[n % len(LENGTHS)] * 1000, cover))
            n += 1
    return out


SIZE = 72
CX = (SIZE - 1) / 2


def cover_level(kind, x, y):
    """0 (light) .. 3 (black) at (x, y) of a 72 x 72 cover."""
    dx, dy = x - CX, y - CX
    r = math.hypot(dx, dy)
    if kind == "sun":                                       # a sun setting into striped water
        if y >= 42:
            return 2 if ((y - 42) // 5) % 2 == 0 else 0
        return 3 if math.hypot(dx, y - 42) < 22 else 1
    if kind == "rings":                                     # bold rings
        return 2 if r > 34 else (3, 0, 3, 1)[int(r // 6) % 4]
    if kind == "peaks":                                     # two mountains and a moon
        if y > 30 + abs(x - 24) * 1.1:
            return 3
        if y > 40 + abs(x - 52) * 0.9:
            return 2
        return 0 if math.hypot(x - 54, y - 16) < 8 else 1
    if kind == "bands":                                     # diagonal bands
        return (3, 2, 1, 0)[((x + y) // 12) % 4]
    if kind == "tiles":                                     # quarter circles on a 2 x 2 grid
        tx, ty = x // 36, y // 36
        lx, ly = x % 36, y % 36
        corner = ((0, 0), (35, 0), (35, 35), (0, 35))[tx + 2 * ty if ty == 0 else 3 - tx]
        fg, bg = ((3, 0), (1, 3), (0, 2), (2, 1))[tx + 2 * ty]
        return fg if math.hypot(lx - corner[0], ly - corner[1]) < 34 else bg
    if kind == "waves":                                     # wavy lines
        return 3 if (y + 6 * math.sin(x / 7)) % 12 < 5 else 1
    if kind == "dots":                                      # a dot grid with one big dot
        if math.hypot(x - 46, y - 26) < 16:
            return 3
        return 0 if math.hypot((x % 12) - 5.5, (y % 12) - 5.5) < 3.5 else 2
    if kind == "chevrons":                                  # stacked chevrons
        return 3 if ((y + abs(dx)) // 9) % 2 else 1
    raise ValueError(kind)


def cover(kind):
    row = (SIZE // 4 + 3) & ~3
    px = bytearray(row * SIZE)
    for y in range(SIZE):
        for x in range(SIZE):
            px[y * row + x // 4] |= cover_level(kind, x, y) << (6 - 2 * (x & 3))
    return bytes(px)


def make_card():
    sys.path.insert(0, str(HERE))
    import itdb, hmcard, mkart
    import shutil
    itdb.MHOD_TYPES["albumartist"] = 22
    shutil.copyfile(WORK / "music-card.img", CARD)
    tracks = songs()
    mhits = []
    for tid, f, num, ms, _ in tracks:
        h = bytearray(itdb.mhit(tid, f, TONEA[1], ms, TONEA[2]))
        struct.pack_into("<II", h, 0x2c, num, 6)                # track number, of
        mhits.append(bytes(h))
    ids = [t[0] for t in tracks]
    tid = {t[1]["title"]: t[0] for t in tracks}
    lists = [itdb.mhyp("iPod", ids)] + [itdb.mhyp(n, [tid[s] for s in ss], master=False) for n, ss in PLAYLISTS.items()]
    db = itdb.mhbd([itdb.mhsd(1, itdb.mhl(b"mhlt", mhits)), itdb.mhsd(2, itdb.mhl(b"mhlp", lists))])
    kinds = list(dict.fromkeys(t[4] for t in tracks))
    art = mkart.froggerart([kinds.index(t[4]) for t in tracks], [cover(k) for k in kinds])
    for name, data in (("iTunesDB", db), ("FroggerArt", art)):
        tmp = WORK / f"demo-{name}"
        tmp.write_bytes(data)
        hmcard.mtools(str(CARD), "mcopy", "-o", str(tmp), f"::/iPod_Control/iTunes/{name}")
        tmp.unlink()


# ---------------------------------------------------------------------------------------------
# The frame: the LCD 3x, nearest neighbour, in a soft LCD palette, in a plain rounded bezel.

SCALE, PAD, R_OUT, R_IN, RIM = 3, 18, 26, 6, 2
LCD = [(0xc8, 0xd1, 0xb6), (0x9b, 0xa5, 0x8c), (0x5e, 0x67, 0x56), (0x24, 0x29, 0x21)]   # levels 0..3
BEZEL, EDGE, SHADOW = (0x33, 0x37, 0x3c), (0x5b, 0x61, 0x69), (0x1c, 0x1f, 0x22)
SW, SH = 160 * SCALE, 128 * SCALE
FW, FH = SW + 2 * PAD, SH + 2 * PAD


def inside(x, y, x0, y0, x1, y1, r):
    """Is the point in the rounded rectangle [x0, x1) x [y0, y1) with corner radius r?"""
    if not (x0 <= x < x1 and y0 <= y < y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def coverage(px, py, *rect):
    """The share of the pixel inside the rounded rectangle, in 16ths (4 x 4 samples)."""
    return sum(inside(px + (i + 0.5) / 4, py + (j + 0.5) / 4, *rect) for i in range(4) for j in range(4))


def mix(a, b, k):
    return tuple((a[i] * k + b[i] * (16 - k) + 8) // 16 for i in range(3))


def frame_template():
    """Per frame pixel: an RGBA, or None for the LCD's own pixel."""
    outer = (0, 0, FW, FH, R_OUT)
    body = (RIM, RIM, FW - RIM, FH - RIM, R_OUT - RIM)
    screen = (PAD, PAD, PAD + SW, PAD + SH, R_IN)
    lip = (PAD - 1, PAD - 1, PAD + SW + 1, PAD + SH + 1, R_IN + 1)
    t = []
    for y in range(FH):
        row = []
        for x in range(FW):
            near_in = PAD - 3 <= x < PAD + SW + 3 and PAD - 3 <= y < PAD + SH + 3
            in_scr = PAD <= x < PAD + SW and PAD <= y < PAD + SH
            if in_scr and (PAD + R_IN <= x < PAD + SW - R_IN or PAD + R_IN <= y < PAD + SH - R_IN):
                row.append(None)
                continue
            k_scr = coverage(x, y, *screen) if near_in else 0
            if k_scr == 16:
                row.append(None)
                continue
            k_out = coverage(x, y, *outer)
            if k_out == 0:
                row.append((0, 0, 0, 0))
                continue
            k_body = coverage(x, y, *body)
            c = mix(BEZEL, EDGE, k_body)
            if near_in:
                c = mix(SHADOW, c, coverage(x, y, *lip))
            if k_scr:
                row.append(("mix", k_scr, c))                   # the LCD's background over the bezel
                continue
            a = (255 * k_out + 8) // 16
            row.append(c + (a,))
        t.append(row)
    return t


_TEMPLATE = []


def render(levels):
    """The framed shot of 160 x 128 levels, as palette PNG bytes."""
    if not _TEMPLATE:
        _TEMPLATE.append(frame_template())
    t = _TEMPLATE[0]
    pixels = []
    for y in range(FH):
        row = []
        for x in range(FW):
            c = t[y][x]
            if c is None:
                row.append(LCD[levels[((y - PAD) // SCALE) * 160 + (x - PAD) // SCALE]] + (255,))
            elif c[0] == "mix":
                row.append(mix(LCD[0], c[2], c[1]) + (255,))
            else:
                row.append(c)
        pixels.append(row)
    return png_palette(pixels)


def png_palette(pixels):
    colours = sorted({c for row in pixels for c in row}, key=lambda c: (c[3], c))
    if len(colours) > 256:
        raise ValueError("%d colours" % len(colours))
    index = {c: i for i, c in enumerate(colours)}
    raw = b"".join(b"\0" + bytes(index[c] for c in row) for row in pixels)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    plte = b"".join(bytes(c[:3]) for c in colours)
    alpha = bytes(c[3] for c in colours)
    alpha = alpha[:max((i + 1 for i, a in enumerate(alpha) if a < 255), default=0)]
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", len(pixels[0]), len(pixels), 8, 3, 0, 0, 0))
    out += chunk(b"PLTE", plte) + (chunk(b"tRNS", alpha) if alpha else b"")
    return out + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


# ---------------------------------------------------------------------------------------------
# The scenes: each boots once (emupod opens once per process) and returns {name: levels}.

T = (0x10e, 0x11e, 0x129, 0x133, 0x139, 0x13f, 0x147, 0x151, 0x15d, 0x16e, 0x17c, 0x190, 0x1a3, 0x1b8, 0x1ce)
BATTERY_RAW = (T[11] + T[12]) // 2                         # 82%, battery.py's percent_of
FAKE_RAW = 0x118e40


class Demo:
    def __init__(self):
        sys.path.insert(0, str(HERE))
        from ipod3g import Pod, W
        self.p = Pod(osos=W + "/osos-frogger.img", disk=str(CARD), boot_us=0)
        self.p.m.mem_write(FAKE_RAW, list(struct.pack("<5I", 0xe59f1008, 0xe5801000, 0xe3a00000, 0xe1a0f00e,
                                                       BATTERY_RAW)))
        self.p.run(9_000_000)
        self.press("select")                                # Language: English, the main menu
        self.shots = {}
        self.anims = {}

    def press(self, key, hold_us=150_000):
        self.p.press(key, hold_us=hold_us, after_us=1_500_000)
        self.p.settle()

    def hold(self, key="select"):
        self.press(key, hold_us=2_000_000)

    def scroll(self, n):
        if n:
            self.p.scroll(n)
            self.p.settle()
            self.p.run(300_000)

    def open(self, *rows):
        """Select the row n below the highlight, for each n (lists open on their first row)."""
        for n in rows:
            self.scroll(n)
            self.press("select")

    def film(self, name, back=False):
        """Press Select and keep every distinct screen of the slide (10 ms steps) as `name`'s frames."""
        frames = self.anims.setdefault(name, [])
        if not back:
            frames.append((self.p.settle(), 1500))
        self.p.press("select", after_us=0)
        last = frames[-1][0]
        for _ in range(60):
            self.p.e.run_for(10_000)
            sc = self.p.screen()
            if sc != last:
                frames.append((sc, 40))
                last = sc
        self.p.run(500_000)
        frames.append((self.p.settle(), 1500))

    def key(self, name, ms=1500):
        """The settled screen as the next frame of `name`'s GIF, shown for ms."""
        self.p.run(500_000)
        self.anims.setdefault(name, []).append((self.p.settle(), ms))

    def shot(self, name):
        self.p.run(500_000)
        self.shots[name] = self.p.settle()

    def song(self, title):
        """Its row in Songs (sorted by title)."""
        return sorted(t[1]["title"] for t in songs()).index(title)


def scene_menu(d):
    d.shot("battery")                                       # the main menu, the percentage


def scene_nowplaying(d):
    d.open(0, 3, d.song("Coastal"))                         # Music > Songs > Coastal: the cover page
    d.press("select")                                       # Apple's page
    d.press("select")                                       # scrubbing
    d.p.wheel(-160, after_us=300_000)
    d.press("select")                                       # done: back on the cover page
    d.p.run(2_000_000)
    d.shot("cover-page")
    d.film("page-slide")                                    # Select: the slide to Apple's page
    d.film("page-slide", back=True)                         # and back to the cover page


def _gif(frames):
    """Rendered PNGs → a looping GIF: each end page held, the slide frames quick."""
    import io
    from PIL import Image
    ims = [Image.open(io.BytesIO(render(f))).convert("RGB").quantize(8, dither=Image.Dither.NONE) for f, _ in frames]
    out = io.BytesIO()
    ims[0].save(out, "GIF", save_all=True, append_images=ims[1:], duration=[ms for _, ms in frames],
                loop=0, optimize=False)
    return out.getvalue()


def scene_holdmenu(d):
    d.open(0, 3)                                            # Music > Songs
    d.scroll(d.song("Juniper"))
    d.key("hold-song", 1200)                                # the song highlighted
    d.hold()
    d.key("hold-song", 2500)                                # held: the menu for it


def queue(d, titles):
    """In Songs, from the top: play the first, then Add to Queue each title."""
    at = 0
    for t in titles:
        d.scroll(d.song(t) - at)
        at = d.song(t)
        d.hold()
        d.press("select")                                   # Add to Queue


def scene_queue(d):
    d.open(0, 3)                                            # Music > Songs
    d.scroll(d.song("Lanterns"))
    d.press("select")                                       # play Lanterns
    d.press("menu")
    d.scroll(-60)
    queue(d, ["Glow", "Moonlit", "Overpass", "Telescope"])
    d.press("menu"); d.press("menu")                        # the main menu
    d.shot("main-queue")
    d.open(10)                                              # Now Playing, the last row
    d.key("up-next", 1200)
    d.hold()
    d.key("up-next", 1500)                                  # held: Queue, as songs wait
    d.press("select")                                       # the songs waiting
    d.key("up-next", 2500)


def scene_quick(d):
    d.open(0, 3, d.song("Neon Rain"))                       # play Neon Rain: the cover page
    d.hold("menu")
    d.scroll(1)
    d.press("select")                                       # Shuffle: Songs
    d.scroll(-1)
    d.shot("quick-settings")


def scene_letters(d):
    d.open(0, 3)                                            # Music > Songs
    d.scroll(2)
    d.p.wheel(-60, gap_us=1_500, after_us=200_000)
    d.shots["jump-letter"] = d.p.screen()


def scene_albumartist(d):
    d.open(0, 1)                                            # Music > Artists
    d.scroll(8)
    d.shot("album-artists")


def scene_hidden(d):
    d.open(0, 2)                                            # Music > Albums
    d.scroll(4)
    d.key("hide", 1200)                                     # an album
    d.hold()
    d.scroll(5)
    d.key("hide", 1200)                                     # Hide
    d.press("select")
    d.key("hide", 2500)                                     # gone from Albums


def scene_settings(d):
    d.open(2)                                               # Frogger! (Settings)
    d.scroll(16)
    d.shot("settings")


SCENES = {n[6:]: f for n, f in globals().items() if n.startswith("scene_")}


def run_scene(name, raw=False):
    d = Demo()
    SCENES[name](d)
    from emupod.recording import png
    for anim, frames in d.anims.items():
        (OUT / f"{anim}.gif").write_bytes(_gif(frames))
        print("wrote", OUT / f"{anim}.gif")
    for shot, levels in d.shots.items():
        (OUT / f"{shot}.png").write_bytes(render(levels))
        if raw:
            (WORK / f"ss_{shot}.png").write_bytes(png(levels, 2))
        print("wrote", OUT / f"{shot}.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--no-image", action="store_true")
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--scene", help=argparse.SUPPRESS)          # one scene, in this process
    ap.add_argument("scenes", nargs="*", default=list(SCENES))
    a = ap.parse_args()
    if a.scene:
        return run_scene(a.scene, a.raw)
    OUT.mkdir(parents=True, exist_ok=True)
    if not a.no_image:
        subprocess.run([sys.executable, str(HERE / "mkimage.py")], check=True)
    make_card()

    def one(name):
        cmd = [sys.executable, __file__, "--scene", name] + (["--raw"] if a.raw else [])
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
        return name, r
    bad = []
    with ThreadPoolExecutor(a.j) as pool:
        for name, r in pool.map(one, a.scenes):
            print(r.stdout, end="")
            if r.returncode:
                bad.append(name)
                print(f"{name}: exited {r.returncode}\n{r.stderr[-2000:]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""Frogger image + a card with one silent song (ck-card.img), with emupod's 2.3 sound:
the clicker in the headphones (payload/clicker.c, settings.c). One run, checking as it goes (exits 1 on
the first wrong step; screenshots ck_*.png):

1. Settings > Clicker: Select steps Speaker (the start) > Headphones > Both > Off > Speaker; the prefs
   flags hold bit 0 (Apple's On, clear only for Off) and bits 30-31 (0, 1, 2); Off is Apple's own
   (the settings object's +0x33 byte 0). Click Volume steps Quiet > Medium > Loud > Quiet (bits 14-15).
2. The song plays; a wheel step in the Music menu is one click:
   Speaker: the piezo clicks, nothing is mixed into the music.
   Headphones: no piezo click (no divisor set, and the task never on to
   its pump of 0xaa bytes into the UART, 0x13c710-0x13c7c4: that's the sound on a device); the click is added to the decoded music ahead of the read pointer (the
   ring 0x4449f80-0x4461980, before the codec) and comes out of the I2S FIFO: the song is silence, so
   what the sound FIQ sends then is the click. Its peak per Click Volume: about 4125, 8231, 16423
   (-18, -12, -6 dBFS).
   Both: the piezo and the music.
0. Before any song since boot, Headphones: the piezo (the codec isn't up: Apple's copy of its
   registers, 0x44be49c, has R9 inactive).
3. Paused, Headphones: the click on its own through I2S (click_paused), no piezo; then I2S is in
   Apple's paused state again (0xc0002500 = 0, the sound FIQ masked). Also checked: the codec
   copy says active, DAC and output on. (emupod's FIFO always has room and doesn't play without
   the FIQ, so the click's sound isn't checked here.)
4. Nothing in Apple's image changed (read-only on a device)."""
import struct, sys
from pathlib import Path
from ipod3g import Pod, W, ROOT
import hmcard, itdb, shutil, subprocess

SYM = {l.split()[2]: int(l.split()[0], 16) for l in open(ROOT / "build/payload/payload.sym") if len(l.split()) == 3}
RING, RING_END = 0x4449f80, 0x4461980
READ, WRITE = 0x40017704, 0x4001770c
PEAK = {0: 4125, 1: 8231, 2: 16423}
PUMP = 0x13c710                         # the piezo task, on to its 0xaa pump (0x13c724): emupod's UART never asks for bytes, so the way there


def silent_card():
    """music-card.img with one song, a minute of digital silence (sox, lame: nix develop .#emu)."""
    card, mp3 = W + "/ck-card.img", Path(W) / "SILENT.mp3"
    shutil.copy(W + "/music-card.img", card)
    subprocess.run("sox -q -n -r 44100 -c 2 -b 16 -t wav - trim 0 60 | lame --quiet -b 128 - %s" % mp3, shell=True, check=True)
    hmcard.mtools(card, "mcopy", "-o", str(mp3), "::/iPod_Control/Music/F00/SILENT.mp3")
    h = itdb.mhit(100, {"title": "Silence", "artist": "Nobody", "album": "Quiet", "genre": "Test",
                        "location": ":iPod_Control:Music:F00:SILENT.mp3"}, mp3.stat().st_size, 60000, 128)
    db = itdb.mhbd([itdb.mhsd(1, itdb.mhl(b"mhlt", [h])), itdb.mhsd(2, itdb.mhl(b"mhlp", [itdb.mhyp("iPod", [100])]))])
    tmp = Path(card).with_suffix(".iTunesDB")
    tmp.write_bytes(db)
    hmcard.mtools(card, "mcopy", "-o", str(tmp), "::/iPod_Control/iTunes/iTunesDB")
    tmp.unlink(); mp3.unlink()
    return card


card = silent_card()
p = Pod(osos=W + "/osos-frogger.img", disk=card)
rd = lambda a: struct.unpack("<I", bytes(p.m.mem_read(a, 4)))[0]
END = 0x346368
snap = bytes(p.m.mem_read(0, END))
p.press("select"); p.settle()                                          # English
lib = rd(rd(0x43580c) + 0x1c)


def check(tag, ok, msg=""):
    print("%-56s %s" % (tag, "ok" if ok else "WRONG " + msg))
    if not ok:
        p.shot("ck_wrong.png"); sys.exit(1)


def flags():
    return rd(rd(lib) + 0xb04)


def set_flags(f):
    p.m.mem_write(rd(lib) + 0xb04, list(struct.pack("<I", f)))


def place_bits(f):
    return (f & 1, f >> 30 & 3)


def go(n):
    if n:
        p.scroll(n); p.settle(); p.run(300_000)


# 1. Settings
go(2); p.press("select"); p.settle(); p.scroll(-30); p.settle()         # Frogger! (Apple's Settings), its top
go(8)                                                                  # Clicker
check("1. Clicker starts On: Speaker", place_bits(flags()) == (1, 0), hex(flags()))
for want, tag in (((1, 1), "Headphones"), ((1, 2), "Both"), ((0, 0), "Off"), ((1, 0), "Speaker")):
    p.press("select"); p.settle(); p.shot("ck_1_%s.png" % tag.lower(), 1)
    check("   Select: %s" % tag, place_bits(flags()) == want, hex(flags()))
go(19 - 8)                                                             # Click Volume
for v, tag in ((1, "Medium"), (2, "Loud"), (0, "Quiet")):
    p.press("select"); p.settle()
    check("   Click Volume: %s" % tag, flags() >> 14 & 3 == v, hex(flags()))
p.press("menu"); p.settle(); go(-20)                                   # the main menu

# 0. Nothing played yet
WM = 0x44be49c
wm = lambda r: struct.unpack("<H", bytes(p.m.mem_read(WM + 2 * r, 2)))[0] & 0x1ff
set_flags(flags() & ~(3 << 30) | 1 | 1 << 30)
fb, pa = rd(SYM["clicker_fallback"]), rd(SYM["clicker_paused"])
p.m.hook_start([PUMP], None, 0)
for _ in range(12):
    p.wheel(-1, gap_us=0, after_us=12_000)                             # down: the main menu is at its top
    if rd(SYM["clicker_fallback"]) != fb:
        break
p.run(150_000)
pumped = len(p.m.hook_log()); p.m.hook_start([], None, 0)
dfb, dpa = rd(SYM["clicker_fallback"]) - fb, rd(SYM["clicker_paused"]) - pa
go(-20)
check("0. Before a song, Headphones: the piezo (R9 %d)" % wm(9), pumped and dfb == 1 and dpa == 0 and not wm(9) & 1,
      "pumped %d fallback +%d paused +%d" % (pumped, dfb, dpa))
set_flags(flags() & ~(3 << 30))

# 2. A song plays
go(0); p.press("select"); p.settle()                                   # Music
go(3); p.press("select"); p.settle()                                   # Songs
p.press("select", after_us=200_000)                                    # Silence plays
while not p.m.audio_on():
    p.run(20_000)
p.run(300_000)
p.press("menu", after_us=400_000); p.settle(); p.press("menu", after_us=400_000); p.settle()   # Music, still playing


def click(place, volume=0):
    """click_once, again (up to 8 tries: more under load) when the mixer fell back to the piezo while a song plays: emupod's
    sound FIQ stalls now and then (audio_late), and the mixer then takes the song for paused."""
    for _ in range(8):
        fb = rd(SYM["clicker_fallback"])
        r = click_once(place, volume)
        if place == 0 or not p.m.audio_on() or rd(SYM["clicker_fallback"]) == fb:
            return r
        print("   (emupod's FIQ stalled: the click fell back to the piezo; again)")
    return r


def click_once(place, volume=0):
    """One click from the wheel with the Clicker at `place` (0 Speaker, 1 Headphones, 2 Both): (piezo
    clicks, clicks mixed, the loudest sample the sound FIQ sent meanwhile: the song is silence)."""
    set_flags(flags() & ~(3 << 30 | 3 << 14) | 1 | place << 30 | volume << 14)
    p.run(50_000)
    if p.m.audio_on():                  # emupod's FIQ stalls now and then (late): wait till it runs
        for _ in range(500):
            f = p.m.fiqs(); p.run(2_000)
            if p.m.fiqs() - f >= 4:
                break
    piezo, mixed, alone = p.m.click_count(), rd(SYM["clicker_mixed"]), rd(SYM["clicker_paused"])
    p.m.hook_start([PUMP], None, 0)     # the piezo's sound: the pump, 0xaa bytes into the UART
    p.m.audio_take()
    for _ in range(12):                 # 2.3 moves the highlight once per 4-6 steps
        p.wheel(click_once.d, gap_us=0, after_us=12_000)
        if p.m.click_count() != piezo or rd(SYM["clicker_mixed"]) != mixed or rd(SYM["clicker_paused"]) != alone:
            break
    click_once.d = -click_once.d
    p.run(150_000)                      # the 10 ms click, played out (emupod's FIQ runs slow)
    out = p.m.audio_take()
    pumped = len(p.m.hook_log()); p.m.hook_start([], None, 0)
    peak = max((abs(x) for x in struct.unpack("<%dh" % (len(out) // 2), out)), default=0)
    pz = max(p.m.click_count() - piezo, 1) if pumped else 0    # the pump is the sound, divisor set or not
    return pz, rd(SYM["clicker_mixed"]) - mixed, peak
click_once.d = 1                        # up and down the Music menu

pz, mx, peak = click(0)
check("2. Speaker: the piezo, nothing mixed", pz == 1 and mx == 0 and peak < 64, "piezo %d mixed %d peak %d" % (pz, mx, peak))
for v, tag in ((0, "Quiet"), (1, "Medium"), (2, "Loud")):
    pz, mx, peak = click(1, v)
    ok = pz == 0 and mx == 1 and abs(peak - PEAK[v]) <= PEAK[v] // 10
    check("   Headphones, %s: no piezo, peak %d (want ~%d)" % (tag, peak, PEAK[v]), ok, "piezo %d mixed %d" % (pz, mx))
pz, mx, peak = click(2, 1)
check("   Both: the piezo and the music", pz == 1 and mx == 1 and abs(peak - PEAK[1]) <= PEAK[1] // 10,
      "piezo %d mixed %d peak %d" % (pz, mx, peak))

# 3. Paused
p.press("play", after_us=600_000); p.settle()
fb, pa = rd(SYM["clicker_fallback"]), rd(SYM["clicker_paused"])
check("3. Paused: the codec still up (R9 %d, R6 %#x)" % (wm(9), wm(6)), wm(9) & 1 and not wm(6) & 0x98)
pz, mx, peak = click(1)
i2s, fiq = rd(0xc0002500), rd(0xcf001030) >> 5 & 1
check("   Headphones: on its own, no piezo", pz == 0 and mx == 0 and rd(SYM["clicker_paused"]) == pa + 1
      and rd(SYM["clicker_fallback"]) == fb, "piezo %d mixed %d paused %d" % (pz, mx, rd(SYM["clicker_paused"]) - pa))
check("   then Apple's paused state (I2S %#x, FIQ %d)" % (i2s, fiq), i2s == 0 and fiq == 0)

now = bytes(p.m.mem_read(0, END))
diff = [i for i in range(END) if snap[i] != now[i]]
check("4. Apple's image unchanged", not diff, "%d bytes, first %#x" % (len(diff), diff[0] if diff else 0))

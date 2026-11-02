# Emulation options for the iPod 3G

Can we debug Frogger without flashing a real iPod? Mostly, yes: with a patch, emupod
boots 2.3 on an emulated 3G, menus and all (see "What's built"). These are the options,
as of October 2026.

## What exists

- **[clicky](https://github.com/daniel5151/clicky)**: an open-source (Rust) iPod
  emulator. It targets the 4G grayscale iPod, which has a **PP5020**. It boots
  Apple's own firmware and Rockbox, and iPodLinux too according to
  [Hackaday](https://hackaday.com/2026/08/26/emulating-the-ipod/). The author calls
  it early-stage.
- **Rockbox's simulator** builds Rockbox for a desktop. It does not run Apple's
  firmware, so it is no use here.
- **[emupod](https://github.com/davidbarnhart/emupod.com)** emulates the PP5002 (both
  ARM7TDMI cores, IDE, LCD, timers, GPIO, audio) for the 1st and 2nd generation. With
  `tools/emupod/emupod-gen3.patch` (a reset entry option, the IDE interrupt, the clock
  registers, GPIO edges while idle) it boots stock 2.3 to the UI. Keys and the wheel
  drive it, and its Python API hooks exact pcs and reads RAM.

The 3G has a **PP5002**. Its memory map, LCD controller, interrupt controller and
CPU/COP control registers all differ from the PP5020's (see `loader/pp5002.h` and
`docs/re-notes.md`), so osos 2.3 will not boot in clicky as it is.

## Options

1. **Run only the code we patch, in Unicorn (recommended to start).** Load
   `build/fw/osos.img` at address 0 into the [Unicorn](https://www.unicorn-engine.org/)
   CPU emulator and call single functions with MMIO hooks:
   - Dark mode (M1): run `lcd_update_rect` (`0xd2db4`) with a known framebuffer at
     `0x3835a0`. Hook writes to `0xc0001008`/`0xc0001010` and check that the stream of
     bytes sent to the LCD is the inverted image. Make reads of `0xc0001000` return
     "not busy" (bit `0x8000` clear) and give `0xcf001110` (µs timer) any value.
   - Spotify-hide (M2): run the iTunesDB parser (`0xc54bc`) over a test iTunesDB,
     with the file reads (`0x57504`, `0x376a4`) stubbed to read from a buffer.
   - It's cheap: one Python script, plus `python3Packages.unicorn` from Nix.
2. **Add a PP5002 target to clicky.** This gives full-system debugging (Apple boot,
   menus, gdb stub), but it's a big job: memory map, IDE, LCD, timers, the
   interrupt controller, and the CPU/COP sleep/wake used at boot (`0x1306a4`,
   `0x1f310`). The addresses in `docs/re-notes.md` cover a lot of what it needs.
   Worth it only if on-device testing gets painful.
3. **Test on the iPod.** Frogger never writes to flash, so a bad patch costs one
   restore (`docs/recovery.md`). The loader's Menu/hold bypass boots stock even
   with a broken patch installed, except in `FROGGER_IGNORE_BUTTONS` test builds. Which
   level of the hold line the loader should treat as "on" is still open (README,
   "Tested on a device").

## What's built

`tools/emu/` runs single osos functions in Unicorn (`nix develop` has it):

- `osos.py` maps the image at 0, recreates what the scatter loader sets up
  (IRAM code, `.data`), logs MMIO writes and lets you stub functions.
- `itunesdb.py` runs the track loader (`0xc4a68`) on a generated iTunesDB, with
  the file reads, track allocator and string interning stubbed. It confirms that
  tracks with `mhit` visible = 0 never get a track record. (`hide.py` drives the
  browse loop at `0xf1ce8` the same way. That loop turned out not to build Music's
  lists, see below.)
- `lcd.py` runs `lcd_update_rect` (`0xd2db4`) and decodes the LCD stream
  (`--expect-invert` for a dark-mode build).

`tests/test_emu.py` runs both when the image and unicorn are available.

Unicorn only runs what you call, with whatever arguments you build, so it can't tell you
which code a menu actually uses. That's how the first hidden-songs hook passed
`hide.py` but did nothing on the iPod.

`tools/emupod/` (setup in its README) runs the whole firmware in emupod: stock 2.3, or the
RAM image Frogger's loader leaves. emupod can't boot the loader itself, because it
requires the COP to sleep at reset and the loader parks it in a wait loop instead. The
scripts press keys and turn the wheel, take screenshots, and count which functions run
while a list opens. That's how the hook point Music's lists really use, `0x58440`, was
found (`docs/re-notes.md`).

## Plan

Use Unicorn for quick checks of single functions, emupod to see what the firmware
really does with a patch in place, and the iPod for the final check (playback still
hangs emupod, so playing songs needs the device). Option 2 isn't needed now that
emupod runs the 3G.

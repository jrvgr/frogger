# Emulator tests

These scripts boot Apple's firmware 2.3, with or without Frogger, in the
[emupod](https://github.com/davidbarnhart/emupod.com) emulator, press the buttons and check what
happens. Each script's docstring says what it does.

## Setup

emupod is a submodule (`third_party/emupod`, pinned). `emupod-gen3.patch` is what we change in
it: 3G/2.3 support and some hooks for counting and tracing. With `firmware/iPod_2.2.3.ipsw` in
place:

    nix develop .#emu
    tools/emupod/setup.sh                    # submodule, patch, build emupod's Rust core
    python3 tools/fwtool.py extract firmware/iPod_2.2.3.ipsw -o build/fw
    make -C loader
    python3 tools/emupod/mkcards.py          # test cards, in build/emupod-work
    pytest -n auto -m emupod                 # all the checks below (tests/test_emupod.py); CI runs this
    python3 tools/emupod/runtests.py -j 4    # the same without pytest

To run one script, run `mkimage.py` after building the loader, then `python3 SCRIPT.py` from
this folder.

## What's checked

| Feature | Check |
| --- | --- |
| Hold menu: Go to Album/Artist, Play Album Next, Hide | `holdmenu2.py` |
| Hold menu on Now Playing as the first hold | `npfirst.py` |
| Add to Queue on any row, hidden songs above it | `holdrow.py` |
| Show (un-hide), Settings › Show Hidden, FroggerHidden | `unhide.py` |
| Up Next: open, remove, play from, clear | `upnext.py` |
| Play After Album: the queue waits for the album playing | `afteralbum.py` |
| Clicker: Speaker, Headphones, Both; Click Volume; the piezo while paused | `clicker.py` |
| The main menu's Queue row | `queuerow.py` |
| Quick settings (hold Menu), its Sleep | `quicksettings.py` |
| Settings' feature switches, each off | `switches.py` |
| Now Playing: back to the cover page after a scrub | `npscrub.py` |
| Now Playing: the page slide | `npslide.py` |
| Lock Cover: Hold on, Hold off, the switch off | `lockcover.py` |
| Resume Mixes | `resume.py` |
| Skip counts, FroggerSkips | `skips.py` |
| Battery percentage | `battery.py` |
| Nothing writes Apple's image (read-only on a device) | `readonly.py` |
| The payload's memory stays free of Apple's heap | `heaptop.py` |
| The disk coming back after it stops answering (SRST, re-init, retry) | `diskhang.py` |
| Settings › Flash Storage: the shorter disk hold, a hard drive left alone in Auto | `flash.py` |
| Covers changing on Next and Previous | `artplay.py` |
| The Now Playing cycle: the cover page, Apple's, scrubbing, rating and back | `npcycle.py` |
| Jump by Letter, the letter in the title; Settings › Jump by Letter off | `letters.py` |
| Album artists: a compilation's songs under its album artist | `albumartist.py` |
| Add to Playlist into a playlist of your own, saved and read back | `ownplaylist.py` |
| DEBUG=1: the debug record comes out whole in FroggerDebug on the next boot (skipped on a plain build) | `debugrecord.py` |

Device realism (`tests/test_device.py`, CONTRIBUTING.md): on a big library card (`library.py`),

| Guard | Check |
| --- | --- |
| The speed budget: instructions per UI action, against stock | `perf.py` (`perf-baseline.json`) |
| No disk I/O on the UI thread, per scenario | `uidisk.py` |
| The UI answering while the disk is hung | `stall.py` |

Shown in screenshots only, not checked: the hold menu and queue step by step (`holdmenu.py`).
`playlists.py` traces the other ways into Add to Playlist (synced playlists, albums, artists, song
orders; docs/re-notes.md).

## Other scripts

- `ipod3g.py`: `Pod()`, the driver: boot, `press()`, `scroll()`, `wheel()`, `settle()`, `shot()`.
  `itdb.py`: iTunesDB records, for scripts that write their own database.
- Cards: `mkcards.py`, `hmcard.py`, `mkart.py`, `mkresume.py`, `library.py` (the big library:
  generated, or yours with `FROGGER_LIBRARY=DIR`); `mkimage.py` makes the Frogger
  RAM image emupod boots; `checkart.py` reads a FroggerArt and draws it.
- `libperf.py DIR`: browsing and the hold menu's actions on a real library (a copy of an iPod's
  `iPod_Control/iTunes`, kept out of the repo), Hold Menu on and off: instructions, VM steps,
  `0x58440` calls and disk reads on the UI's thread per step.
- `screenshots.py`: the README's screenshots (`docs/screenshots/`), on a demo card it makes.
- `probes/`: one-off reverse-engineering traces, kept for how things were found
  (`docs/re-notes.md`, `docs/tcmd.md`). They check nothing. Run them from this folder too, e.g.
  `python3 probes/settrace.py 8`.

`probes/lists.py`, `probes/hot.py` and the other `*trace.py` probes need the function prologues:

    grep -E "^ *[0-9a-f]+:	[0-9a-f]{8} 	push	\{[^}]*lr\}" build/osos.dis | awk -F: '{print $1}' \
        | tr -d ' ' > build/emupod-work/prologues.txt

## Gotchas

- GPIOA bit 5 high means Hold is on, and 2.3 drops every key.
- emupod's own `make_screen()` comes back blank after an idle stretch; use `Pod.screen()`.
- Songs really play (emupod-gen3.patch models 2.3's I2S FIFO `0xc0002540`, its free slots at
  `0xc000251c`, and the FIQ dispatcher's source bit at `0xcf00100c`/`0xcf001030`): the clock and the
  progress bar move, and a song plays on into the next. A script that compares Now Playing's pixels
  pauses first; one that checks a start position reads it where the player sets it
  (`resume.py`'s `started`). The emulated FIQ still falls behind now and then (`audio_late`).
- More on the emulator: `docs/power-and-emupod.md`.

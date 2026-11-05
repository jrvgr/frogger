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

Shown in screenshots only, not checked yet: covers changing on Next (`artplay.py`), Jump by Letter
(`letters.py`), album artists (`albumartist.py`), Add to Playlist (`playlists.py`), the Now Playing
cycle (`npcycle.py`), the hold menu and queue step by step (`holdmenu.py`).

## Other scripts

- `ipod3g.py`: `Pod()`, the driver: boot, `press()`, `scroll()`, `wheel()`, `settle()`, `shot()`.
  `itdb.py`: iTunesDB records, for scripts that write their own database.
- Cards: `mkcards.py`, `hmcard.py`, `mkart.py`, `mkresume.py`; `mkimage.py` makes the Frogger
  RAM image emupod boots; `checkart.py` reads a FroggerArt and draws it.
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
- The emulated audio stops after about 2000 sample FIQs, so the clock stays at 0:00. Scripts
  scrub to stand in for listening.
- More on the emulator: `docs/power-and-emupod.md`.

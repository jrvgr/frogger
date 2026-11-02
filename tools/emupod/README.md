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
    python3 tools/emupod/runtests.py         # all the checks below; CI runs this

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
| Resume Mixes | `resume.py` |
| Skip counts, FroggerSkips | `skips.py` |
| Battery percentage | `battery.py` |
| Nothing writes Apple's image (read-only on a device) | `readonly.py` |
| The payload's memory stays free of Apple's heap | `heaptop.py` |

Shown in screenshots only, not checked yet: covers changing on Next (`artplay.py`), Jump by Letter
(`letters.py`), album artists (`albumartist.py`), Add to Playlist (`playlists.py`), the Now Playing
cycle (`npcycle.py`).

## Other scripts

- `ipod3g.py`: `Pod()`, the driver: boot, `press()`, `scroll()`, `wheel()`, `settle()`, `shot()`.
- Cards: `mkcards.py`, `hmcard.py`, `mkart.py`, `mkresume.py`; `mkimage.py` makes the Frogger
  RAM image emupod boots; `checkart.py` reads a FroggerArt and draws it.
- Reverse engineering, kept for how things were found (`docs/re-notes.md`, `docs/tcmd.md`):
  `settrace.py`, `vmtrace.py`, `optable.py`, `lists.py`, `ramdiff.py`, `whowrites.py`,
  `whoreads.py`, `sethandler.py`, `whenfn.py`, `strlookup.py`, `nplookups.py`, `npbmaps.py`,
  `npselect.py`, `hm2trace.py`, `hot.py`, `playhang.py`, `maskedwhen.py`, `maskedpath.py`,
  `idleloop.py`, `nobar.py`, `otgqueue.py`, `frogset.py`, `frogshow.py`, `persist.py`,
  `artdemo.py`, `playshot.py`.

`lists.py` and `hot.py` need the function prologues:

    grep -E "^ *[0-9a-f]+:	[0-9a-f]{8} 	push	\{[^}]*lr\}" build/osos.dis | awk -F: '{print $1}' \
        | tr -d ' ' > build/emupod-work/prologues.txt

## Gotchas

- GPIOA bit 5 high means Hold is on, and 2.3 drops every key.
- emupod's own `make_screen()` comes back blank after an idle stretch; use `Pod.screen()`.
- The emulated audio stops after about 2000 sample FIQs, so the clock stays at 0:00. Scripts
  scrub to stand in for listening.
- More on the emulator: `docs/power-and-emupod.md`.

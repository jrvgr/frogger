# Contributing

Bugs, ideas and fixes are welcome. Frogger patches Apple's firmware on someone's iPod, so a
change has to be tested before it goes in, and a wrong address can mean a crash at boot.

## Building

[Nix](https://nixos.org/download) gives the toolchain (arm-none-eabi-gcc, Python with Unicorn,
Pillow and pytest):

    nix develop
    make -C loader                         # build/loader/frogger-loader.bin
    make -C loader DEBUG=1                 # with the crash recorder (payload/debug.c)
    pytest                                 # tests/; the ones that need Apple's firmware skip without it
    pytest --cov --cov-report=term         # the same, with the coverage of tools/

Install your build the same way as a release's (README, Install), with
`build/loader/frogger-loader.bin`. `tools/backup.sh` and `tools/restore.sh` save and write back
the firmware partition with Rockbox's `ipodpatcher` (docs/recovery.md).

## Emulator tests

These boot Apple's firmware 2.3 with Frogger in emupod and press the buttons. They need
Apple's `iPod_2.2.3.ipsw` in `firmware/` (from Apple, never in the repo; CI fetches it):

    nix develop .#emu
    tools/emupod/setup.sh                                  # emupod, patched and built
    python3 tools/fwtool.py extract firmware/iPod_2.2.3.ipsw -o build/fw
    make -C loader
    python3 tools/emupod/mkcards.py                        # test cards
    pytest -n auto                                         # every test, the emupod checks too
    pytest -n auto -m emupod -k upnext                     # one check (-m 'not emupod': none)

A failing check shows the end of its script's output (all of it in `build/emupod-work/logs/`).
`tools/emupod/runtests.py -j 4` still runs the checks on their own, without pytest. Tests that
need Apple's firmware carry `@pytest.mark.firmware` (a path argument for a file other than
`build/fw/osos.img`) and skip, with what to run, when it's missing; `--require-firmware` makes
that a failure, as in CI.

More, and what each check covers: [tools/emupod/README.md](tools/emupod/README.md).

The README's screenshots come from the emulator too. After a change that shows on screen, make
them again and commit `docs/screenshots/` with it (same setup as above; the files only change
when the screen does):

    python3 tools/emupod/screenshots.py                    # every shot, on a demo card of made-up music
    python3 tools/emupod/screenshots.py --raw quick        # one scene, plus plain shots in build/emupod-work

## Device realism

emupod runs on a fast host, with no cache misses, on two-song test cards and a disk that never
sleeps or stalls. A real 3G has thousands of songs, a slow CPU and a disk (or an SD adapter) that
takes seconds to wake and sometimes stops answering. So a change can pass every check and still
make the menus sluggish or freeze on Menu. Three guards in `tests/test_device.py` look for that.
They run on a big library card, and they're part of `pytest -n auto -m emupod`, CI included:

| Guard | Marker | What it catches |
| --- | --- | --- |
| `tools/emupod/perf.py` | `perf` | Frogger costing more CPU than stock 2.3 for everyday actions: Menu back, Select into a list, scrolling, hold Select or Menu, a song change. It counts the ARM instructions run from the key until the CPU is idle again, stock against Frogger. The budget is stock × 1.25 + 0.65 M (50 ms), or a cap for popups stock doesn't have |
| `tools/emupod/uidisk.py` | `uidisk` | Disk I/O on the UI thread. That's a frozen wheel while the disk wakes, and a ~10 s freeze when an adapter stalls. Every ATA command issued on the UI's stack while a key is handled fails the guard, with its call site (lr), unless stock 2.3 issues it from the same place |
| `tools/emupod/stall.py` | `stall` | A UI that waits on a stalled disk. The drive is hung at a random moment as a song loads. While it's hung, Menu, the wheel and the hold menu (with its rows that save) must answer within 500 ms of emulated time, and the drive must come back afterwards |

The card is `build/emupod-work/lib-generated-card.img` (`tools/emupod/library.py`, made by
`mkcards.py` or on first use). It's a made-up library: 5,000 songs, 400 albums, 800 artists,
compilations, long titles, 20 playlists and covers. To run the guards on your own library, copy
`iPod_Control/iTunes/iTunesDB` from your iPod (with `FroggerArt`, `FroggerHidden` and
`FroggerSkips`) into a folder under `build/`. It never goes in the repo, and CI never uses it:

    pytest -n auto -m "perf or uidisk or stall" --library=build/device-library
    FROGGER_LIBRARY=build/device-library python3 tools/emupod/perf.py     # one guard on its own

`pytest -m emupod --ata-hang 1` runs every emupod check with the disk hanging once at a random
read (seed 1). `--stall-seed N` picks the stall guard's random moments.

The speed numbers are deterministic. `tools/emupod/perf-baseline.json` keeps the last accepted
ones and each action's budget, so a change in cost shows up as a diff. After a change that costs
or saves instructions on purpose, run `python3 tools/emupod/perf.py --update` and commit the
JSON. Your own library's baseline stays in `build/emupod-work/`. CI's job summary shows the table
and any UI-thread disk I/O. A known failure is marked `xfail` (not strict) with the reason. When a
fix lands, the test turns XPASS: then drop the mark.

The emulator still can't show everything (its sound FIQ falls behind now and then, the disk is fast
when it does answer). Before a release, go through [docs/device-checklist.md](docs/device-checklist.md) on a
real iPod.

## Layout

| Path | What |
| --- | --- |
| `loader/` | Runs first at boot, patches Apple's OS in RAM |
| `payload/` | The features, resident next to Apple's OS |
| `tests/` | Unit tests (Python): the installer, the hooks, Frogger's files |
| `tools/install.py` | Puts the loader in the firmware partition and takes it out |
| `tools/podinfo.py`, `tools/coverart.py` | Frogger's data on a mounted iPod; the covers |
| `tools/fwtool.py` | Lists and extracts the images in an `.ipsw` |
| `tools/emu/` | Unicorn harness: runs single firmware functions |
| `tools/emupod/` | Emulator tests; `probes/` has the one-off reverse-engineering traces |
| `tools/re/` | Reverse-engineering helpers (the bytecode disassembler, resources) |
| `docs/` | Notes on firmware 2.3 |

`docs/addresses.md` maps every firmware address Frogger uses: start there for a new feature.

## Issues

Open one from a form (Bug, Feature or Docs). Blank issues are off. The form sets the `type:`
label, and its Area answer sets the `area:` label. For a bug, say whether it also happens on
stock firmware (hold Menu while the iPod starts). For a crash or freeze, attach a debug record
(the Bug form says how).

## Pull requests

1. One change per PR, with an issue for anything bigger than a small fix.
2. Label it: exactly one `type:` and at least one `area:`. The **Labels** check fails until it
   has them. All labels are in `.github/labels.json`. Add new ones there, not on GitHub.
3. Fill in the template's checklist.

What has to pass:

- `make -C loader`, `pytest` and the lint (`ruff check .`,
  `shellcheck tools/*.sh tools/emupod/*.sh`): the **CI** checks.
- The emulator checks (`pytest -n auto -m emupod`; CI runs them with the firmware from Apple).
  A new or changed feature needs a check of its own in `tools/emupod/` that exits 1 when
  something's wrong, listed in `runtests.py`'s `FEATURES` with the payload files it goes through.
  Screenshots alone don't count.

A pull request's CI run adds a **Test results** check (every test, failures at their line), a
summary per job and one comment with the coverage of `tools/` and which features have an
emupod check. It's a report: no coverage number fails a job.
- Tried on a real 3G, or labelled `needs device test`. The emulator doesn't model everything:
  the sound's timing is rough, the screen never goes dark, Apple's image isn't read-only.

## Code

- Match the code around it: C99 for `arm7tdmi`, no libc, comments that say why.
- Every firmware address goes in `docs/addresses.md`, with what it is, where Frogger uses it and
  how sure we are (**confirmed** in emupod, on a device, **likely**, **guess**). How you found
  it goes in `docs/re-notes.md` or `docs/tcmd.md`.
- Hooks: an original instruction in `tools/mkpayload.py`'s `HOOKS` table (checked against the
  firmware by the tests), the glue in `payload/hooks.S`. If a hook replaces a function's first
  instruction, enter it with `B`, not `BL` (`BRANCH_HOOKS`).
- Apple's image is read-only on a device once it runs. Write only to the payload's memory.
- A feature someone might not want gets a switch in Settings (`FEATURE_*` in
  `payload/settings.h`, docs in `docs/tcmd.md`, "The feature switches").

## Releases

Actions › Release › Run workflow, with a version like `v0.3` (`v0.3-rc1` for a pre-release). It
tags main's head, runs every CI check and publishes `frogger-loader.bin`, the debug build and
`SHA256SUMS`. Pushing a `v*` tag does the same. The notes list the merged pull requests by their
`type:` label (`.github/release.yml`).

Dependabot keeps the Actions up to date, and `flake-update.yml` opens a pull request for a newer
nixpkgs once a month.

## Things that never go in the repo

Apple's firmware, `.ipsw` files, firmware or disk images, iPod backups, other people's music
or covers. `.gitignore` keeps out the usual places (`firmware/`, `backups/`, `build/`).

## AI

Much of Frogger was written with AI (Claude). That's fine for contributions too, as long as you
read the change, the tests pass and you've tried it. Say so in the PR if a device test wasn't
possible.

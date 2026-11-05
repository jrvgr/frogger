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
  something's wrong, listed in `runtests.py`. Screenshots alone don't count.
- Tried on a real 3G, or labelled `needs device test`. The emulator doesn't model everything:
  audio stops early, the screen never goes dark, Apple's image isn't read-only.

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

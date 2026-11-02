# Contributing

Bugs, ideas and fixes are welcome. Frogger patches Apple's firmware on someone's iPod, so a
change has to be tested before it goes in, and a wrong address can mean a crash at boot.

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

- `make -C loader` and `python3 -m unittest discover -s tests` (the **CI** check).
- The emulator checks (`tools/emupod/runtests.py`; CI runs them with the firmware from Apple).
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

## Things that never go in the repo

Apple's firmware, `.ipsw` files, firmware or disk images, iPod backups, other people's music
or covers. `.gitignore` keeps out the usual places (`firmware/`, `backups/`, `build/`).

## AI

Much of Frogger was written with AI (Claude). That's fine for contributions too, as long as you
read the change, the tests pass and you've tried it. Say so in the PR if a device test wasn't
possible.

## What

<!-- What changes on the iPod (or in the tools), in a sentence or two. -->

## Tested

- [ ] `make -C loader` builds
- [ ] `pytest`
- [ ] `pytest -n auto -m emupod` (needs the firmware; CI runs it too)
- [ ] New or changed feature: an emulator check for it (`tools/emupod/`, listed in `runtests.py`)
- [ ] On a real 3G (say which storage), or labelled `needs device test`

## Docs

- [ ] New firmware addresses in `docs/addresses.md`, findings in `docs/re-notes.md` / `docs/tcmd.md`
- [ ] README's feature list, if a feature changed

Labels: one `type:` and at least one `area:`. The label check fails until they're there.

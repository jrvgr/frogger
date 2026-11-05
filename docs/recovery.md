# Backup and recovery (iPod 3G)

Frogger never writes to the iPod's flash ROM. Everything it changes lives in
the hard drive's firmware partition, so disk mode always comes back and a
backup restores the iPod to exactly how it was.

## Ways back, from quickest to most thorough

| Situation | Do this |
| --- | --- |
| A patch misbehaves, just this once | Hold **Menu** while the iPod boots: the loader skips every patch and boots stock Apple OS |
| One patch is bad | Rebuild without it, `make -C loader DISABLE="darkmode"`, and reinstall |
| Frogger should go | `tools/restore.sh --remove-loader` drops the loader and keeps Apple's firmware |
| Anything else | `tools/restore.sh` writes your backup back, byte for byte |
| Can't even get to disk mode | Apple's iPod Updater or iTunes restore (this wipes the music) |

The loader also refuses to patch if Apple's code isn't byte-for-byte what a patch
expects, so a wrong firmware version boots stock instead of crashing.

## Before the first install: back up

`tools/install.py` saves the firmware partition every time it writes, so this is an extra.
It needs `ipodpatcher` from Rockbox (`utils/ipodpatcher` in Rockbox's source; `nix develop`
doesn't have it). Connect the iPod in disk mode (below), then:

    tools/backup.sh

It dumps the whole firmware partition with `ipodpatcher -r` to
`backups/firmware-<date>.bin`, refuses to call it a backup unless
`tools/fwtool.py` reads it as Apple's firmware, writes a `.sha256` next to it
and points `backups/latest.bin` at it. Copy it somewhere outside the repo as
well; `backups/` is gitignored.

## Restore

    tools/restore.sh                     # writes backups/latest.bin back
    tools/restore.sh backups/firmware-20261028-090000.bin

It checks the file with `fwtool.py` and against its `.sha256`, asks you to type
`restore`, and only then runs `ipodpatcher -w`.

## Button combinations

These are for the 1G to 3G iPods. Check them on your iPod before you rely on them.

| What | How |
| --- | --- |
| Reset | Toggle hold on and off, then hold Menu + Play until the Apple logo appears |
| Disk mode | Reset, then as soon as the Apple logo shows hold Previous + Next |
| Stock Apple OS, Frogger installed | Hold Menu while it boots (the hold switch on does the same) |

## Installing

Crate's iPod page has **Install Frogger** and **Remove Frogger**. They run
`tools/install.py` as root (macOS asks for your password), with the iPod's volume
unmounted for the few seconds it takes. Each run first saves the whole firmware
partition to `~/Library/Application Support/Crate/Frogger/`, then writes, then
reads it back to check. By hand:

    sudo python3 tools/install.py disk-install /dev/rdiskN build/loader/frogger-loader.bin --backup-dir backups

## Undo an install

Any of these gets you back to stock:

- Crate's **Remove Frogger**, or `sudo python3 tools/install.py disk-remove /dev/rdiskN --backup-dir backups`
- `sudo python3 tools/install.py disk-restore /dev/rdiskN BACKUP` writes a saved partition back

- Write the backup back: `ipodpatcher -w backups/ipod3g-firmware-partition.bin`
- Remove the appended loader: `ipodpatcher -d`
- Restore with Apple's iPod Updater or iTunes (this also wipes the music).

## What can still go wrong

A dead hard drive or a flat battery look like a brick but aren't caused by the
firmware. If the drive was replaced with a CF or SD adapter, all of the above
works the same way.

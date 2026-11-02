<p align="center"><img src="docs/frog.svg" width="120" alt=""></p>

# Frogger

New features for the 3rd generation iPod, patched into Apple's firmware 2.3 at boot. Apple's
OS still does the UI, the database and playback. Hold Menu while the iPod starts to get the
stock firmware.

> **Heads-up:** this code was written with AI (Claude). It runs on a real iPod 3G, and every
> change goes through emulator tests that drive Apple's firmware with Frogger loaded
> (`tools/emupod/`). Keep a backup anyway: see [Getting back to stock](#getting-back-to-stock).

Work in progress. Some features need a syncing app that knows about them: that's
[Crate](#without-crate), a Mac app that isn't released yet.

## Features

- **Cover page.** Now Playing opens on a page with the title, a 72×72 cover and the progress
  bar. Select slides to Apple's page (scrubbing, rating), and it slides back.
- **Hold menu.** Hold Select on a song, album, artist or playlist, or on Now Playing:
  Add to Queue, Play Album Next, Add to Playlist, Go to Album, Go to Artist, Hide.
- **Queue.** Queued songs play next, then playback goes back to where it was. The queue
  shows in Now Playing's hold menu and on the main menu, where you can play from it, remove
  songs or clear it.
- **Hidden songs.** Hidden songs stay out of Artists, Albums, Genres and Composers but still
  play from Songs and playlists. Hide and Show on the iPod, or Settings › Show Hidden.
- **Quick settings.** Hold Menu anywhere: Backlight, Shuffle, Repeat, Sleep.
- **Jump by letter.** Spin the wheel fast in a long list and it moves a letter at a time.
- **Resume mixes.** Songs of 20 minutes or longer start where you left them.
- **Skip counts.** Songs left within 2–20 s count as skipped, as in iTunes.
- **Album artists.** Compilations list under their album artist.
- **Battery percentage** in the title bar.

Settings has a switch for the ones you might not want: Cover Page, Hold Menu, Quick Settings,
Battery Percent, Page Slide, Jump by Letter, Resume Mixes (all on), and Show Hidden (off). Off is
Apple's behaviour again, from the next time the feature runs. How each feature works:
`docs/re-notes.md`, `docs/nowplaying.md`, `docs/tcmd.md`.

## Install

You need a 3G iPod on firmware 2.3 and Apple's `iPod_2.2.3.ipsw` (Apple's firmware isn't in
this repo and never will be).

Frogger takes the top 1 MiB of the iPod's 32 MiB of RAM for itself. That comes out of the
song cache, so a hard drive spins up a little more often and the battery runs down a little
sooner. A flash mod (a CF or SD card in place of the drive) is recommended for that reason.

    nix develop
    make -C loader                         # build/loader/frogger-loader.bin
    tools/backup.sh                        # save the firmware partition first
    sudo tools/install.py disk-install /dev/rdiskN build/loader/frogger-loader.bin --backup-dir backups

`diskutil list` shows which disk is the iPod. Restart it afterwards (hold Menu + Play). The main
menu says "Frogger!" instead of "Settings" when Frogger is running.

## Getting back to stock

- Hold **Menu** while the iPod starts: stock firmware, nothing patched.
- `sudo tools/install.py disk-remove /dev/rdiskN --backup-dir backups`: take Frogger out.
- `tools/restore.sh`: put the backup from `tools/backup.sh` back, byte for byte.
- [docs/recovery.md](docs/recovery.md) has disk mode and the rest.

## Without Crate

Crate writes the covers, sets the hide flag and reads back what the iPod recorded (hides,
skips, songs added to playlists, mix positions) when it syncs. Until it's out,
`tools/podinfo.py` shows that data and sets the flag (plain Python 3, iPod mounted):

    tools/podinfo.py /Volumes/IPOD                # summary
    tools/podinfo.py /Volumes/IPOD hidden         # also: skips, playlists, bookmarks, tracks
    tools/podinfo.py /Volumes/IPOD hide 1234      # hide track id 1234 (unhide to undo)

Without FroggerArt the cover page shows a frog instead of covers. Any other syncing app
writes a new database, and the iPod then ignores Frogger's files from before it.

## Development

    nix develop                                     # toolchain, Python with Unicorn
    make -C loader
    python3 -m unittest discover -s tests

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Emulator tests:
[tools/emupod/README.md](tools/emupod/README.md). CI runs both, fetching the firmware from
Apple. `docs/addresses.md` maps every firmware address Frogger uses: start there for a new
feature. A debug build (`make -C loader DEBUG=1`) writes a crash record to
`iPod_Control/iTunes/FroggerDebug` on the next boot (`payload/debug.c`).

| Path | What |
| --- | --- |
| `loader/` | Runs first at boot, patches Apple's OS in RAM |
| `payload/` | The features, resident next to Apple's OS |
| `tools/install.py` | Puts the loader in the firmware partition and takes it out |
| `tools/podinfo.py` | Frogger's data on a mounted iPod |
| `tools/fwtool.py` | Lists and extracts the images in an `.ipsw` |
| `tools/emu/`, `tools/emupod/` | Unicorn harness, emulator tests |
| `tools/re/` | Reverse-engineering helpers |
| `docs/` | Notes on firmware 2.3 |

## License

MIT, see [LICENSE](LICENSE). It covers Frogger's own code, and every earlier version of it,
including commits from before the LICENSE file was added. Apple's firmware isn't part of it and
isn't in the repo. emupod (`third_party/emupod`) is MIT too.

# Device checklist

The emulator checks and the device-realism guards (CONTRIBUTING.md, "Device realism") catch a
lot, but not everything a 3G does. Before a release (and for a pull request labelled
`needs device test`), install the build on a real iPod and go through this list. Use one with a
full library, ideally one with an SD or CF adapter and one with the hard drive. Note the
firmware, the storage and the library size in the release's pull request or issue.

## Before you start

- [ ] `pytest -n auto -m emupod` passes on the release commit, with no new xfail
- [ ] `pytest -n auto -m "perf or uidisk or stall" --library=build/device-library` on your own
      library: nothing over budget, no UI-thread disk I/O besides the known xfails
- [ ] A backup of the firmware partition (`tools/backup.sh`), and the debug build at hand
      (docs/recovery.md)

## Boot and basics

- [ ] It boots with the library, and holding Menu at boot gives stock 2.3
- [ ] Settings › Frogger: every switch is there and On (Flash Storage as you left it)
- [ ] The battery percentage looks right and moves over a play session

## Speed (with the disk asleep: wait 30 s first, for each)

- [ ] Menu back out of Songs, Albums and Artists: as quick as stock (try stock too)
- [ ] Select into Songs, Albums and Artists: as quick as stock
- [ ] Scrolling a long list fast: no stutter, Jump by Letter shows the letter
- [ ] Hold Select on a song: the hold menu opens at once; Menu closes it at once
- [ ] Hold Menu: quick settings open at once; Menu closes them
- [ ] Next and Previous while playing: the cover changes, the wheel never stops answering

## The disk (most freezes are here)

- [ ] Hold menu › Hide, Show, Add to Queue, Add to Playlist, each with the disk asleep: the wheel
      keeps answering while the disk spins up, and no freeze on the next Menu
- [ ] The same right after a song change, while the disk is refilling the music cache
- [ ] Settings › Show Hidden, then Hide again: still hidden after a restart
- [ ] A playlist made with Add to Playlist is still there after a restart, and after a sync
- [ ] Play an album through: every song loads, no gap longer than stock's

## Now Playing and Hold

- [ ] The cover page, the slide, a scrub and back to the cover page
- [ ] Hold on: Lock Cover shows the cover large; Hold off: back where you were
- [ ] Resume Mixes: a long mix resumes where it stopped

## Afterwards

- [ ] No crash record (the debug build's file, docs/recovery.md) and no freeze longer than a
      second you can't explain
- [ ] Anything new goes in an issue, with whether stock 2.3 does it too

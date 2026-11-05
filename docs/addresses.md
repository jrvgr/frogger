# Address map: firmware 2.3

Every address in Apple's `osos` 2.3 that Frogger relies on, in one place. Start a new feature
here, then follow the **Details** link for how it was found. This is a map, not the notes:
explanations stay in [`re-notes.md`](re-notes.md), [`tcmd.md`](tcmd.md) and
[`nowplaying.md`](nowplaying.md), and in the comments of the file named in **Used by**.

Addresses are runtime addresses (DRAM at 0, as Ghidra and `build/osos.dis` show them). The
loader writes before the remap, so it adds `DRAM_START` (`0x28000000`): `0x28000000 + A`.

**Status** follows `re-notes.md`: **confirmed**, **likely**, **guess**. Where it matters, it says
what confirmed it: the code, emupod, or a device.

Two things to know before writing anything:

- **Apple's image `[0, 0x346368)` is read-only once Apple's OS runs** on a device (a store there
  is a data abort). emupod doesn't enforce it, so such a feature works in emupod and crashes the
  iPod. Change the image from the loader (`loader/`), which runs before the remap. The payload,
  `.data`, `.bss` and the heap are writable. ([Address spaces][as])
- **`[vm+0x24]` is the end of the running bytecode function**, not of all bytecode. The VM
  returns when the pc reaches it (`0x9d288`). Jumping into another function means moving it to
  that function's end. ([Running our own bytecode][hm])

## Memory regions

| Range | What | Used by | Status | Details |
| --- | --- | --- | --- | --- |
| `0x000000–0x346368` | Apple's `osos` image: code, the UI bundle, `.data` copy sources. **Read-only at runtime on a device.** | everything | confirmed (device) | [Address spaces][as] |
| `0x28000000` | `DRAM_START`: where Apple's boot puts the image, and where the loader sees it before the remap | `loader/pp5002.h`, `tools/mkpayload.py` | confirmed | [Address spaces][as] |
| `0x346368–0x35f800` | The loader's appended copy (loaded by Apple's boot right after the image). `loader/Makefile` checks that it ends below the debug record | `loader/Makefile` | confirmed | [Free RAM][ram] |
| `0x35f800–0x360000` | Frogger's debug record (`DEBUG_ADDR`, `DEBUG_END`), DEBUG=1 builds. Survives a reset while RAM keeps power | `payload/debug.h`, `debug.c` | confirmed (device) | `payload/debug.c` |
| `0x360000–0x36fc00` | Referenced by Apple (`0x24664`, `0x33500`); unknown. Stay below `0x360000` | `payload/debug.h` | likely | [Free RAM][ram] |
| `0x36fc00–0x37b048` | Apple's `.data` (copied from `0x313da0`) | | confirmed | [Free RAM][ram] |
| `0x37b048–0x449dc8` | Apple's `.bss`. The globals below live here | | confirmed | [Free RAM][ram] |
| `0x449e00–0x53c304` | Apple's uncached `.bss` (reached through `0x0444xxxx`) | | confirmed | [Free RAM][ram] |
| `0x53c304–0x1f00000` | Heap and music cache, handed out by `0x91e90` up to the end of DRAM; the loader patches its mask at `0x91eac` into `sub ip, ip, #0x100000` so it stops 1 MiB short. Not free | `loader/patches.c` | confirmed | [Free RAM][ram] |
| `0x1f00000–0x2000000` | Frogger's resident payload: code, data, `.bss` (`payload/payload.lds`), taken from the heap's end | `payload/payload.lds` | confirmed (emupod) | [Free RAM][ram] |
| `0x2000000` | End of DRAM (32 MiB); `debug.c`'s `readable()` bound | `payload/debug.c` | confirmed | [Free RAM][ram] |
| `0x29e00000` (`+0x100000`) | The loader's link address, the MiB below the payload's, so installing the payload doesn't overwrite it. Only safe before Apple's OS runs: the heap takes it after | `loader/loader.lds` | confirmed | [Free RAM][ram] |
| `0x40000000–0x40018000` | IRAM (96 KiB). Full: vectors, IRAM code, stacks. `debug.c`'s `readable()` bound | `payload/debug.c` | confirmed | [Free RAM][ram] |
| `0xc4000000` | `PROCESSOR_ID` (`0x55` CPU, `0xaa` COP) | `loader/crt0.S`, `pp5002.h` | confirmed | [Boot flow][boot] |
| `0xcf000000`, `0xcf000010`, `0xcf000030` | GPIO A enable, output enable, input (the buttons; Menu at boot) | `loader/main.c`, `pp5002.h` | confirmed | [Key input][keys] |

## Hooks

Each replaces one instruction with a `BL` (or a plain `B`) into `payload/hooks.S`, which redoes
the instruction (a BL hook on a `bl` can be a C function that makes the call itself, as
`battery.c`'s do). The table is `HOOKS` in `tools/mkpayload.py`; `--image` checks every original
word against an `osos` image. **B** hooks (`BRANCH_HOOKS`) sit where `lr` is still live, usually a
function's first instruction, and jump back to **Back at** themselves; a `BL` there overwrites
the return address. **BL** hooks return with `bx lr` to the next instruction.

| Address | Original | Hook | Entry | Back at | What it does | Used by | Status | Details |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `0xc4b30` | `0xe59d0430` `ldr r0, [sp, #1072]` | `track_hook` | BL | | Track loader `0xc4a68`, each new track record (`r4`; mhit at `sp+0x420`, index `[sp+0x4bc]`): note where it is (covers); flag hidden tracks | `art.c`, `hide.c` | confirmed (emupod) | [Hidden-songs hooks][itdb], [Playlist loader][plload] |
| `0xc4e64` | `0xe59d0414` `ldr r0, [sp, #1044]` | `mhod_hook` | BL | | Before the mhod type switch (`[sp+0x414]`): album artist (22) read as artist | `artist.c` | confirmed (emupod) | [Album artists][aa] |
| `0xc431c` | `0xe3a07001` `mov r7, #1` | `mhyp_hook` | BL | | Playlist loader `0xc4244`, each mhyp: is it the master (`[sp+0xc0]`)? | `hide.c` | confirmed (emupod) | [Playlist loader][plload] |
| `0xc4768` | `0xe5dd1030` `ldrb r1, [sp, #48]` | `mhip_hook` | BL | | After an mhip joined: remember the master playlist (`[sp+0xa8]`) | `hide.c` | confirmed (emupod) | [Playlist loader][plload] |
| `0xf205c` | `0xe59d0058` `ldr r0, [sp, #88]` | `filter_hook` | BL | `0xf2060` / `0xf211c` (drop) | Browse loop `0xf1ce8`: drop hidden items. No Music list uses this loop | `hide.c` | confirmed (code); never runs in Music lists | [On a device: nothing hidden][hidden] |
| `0x58444` | `0xe1a05000` `mov r5, r0` | `browse_hook` | BL | (returns from `0x58440`) | `0x58440(lib, item)`, the keep-this-item predicate of every library list: 0 drops hidden songs; Songs (`0x7c4fc`) and Shuffle Songs (`0x512e8`) skipped by return address | `hide.c`, `settings.c` | confirmed (emupod) | [On a device: nothing hidden][hidden] |
| `0xdafc8` | `0xe1a04000` `mov r4, r0` | `setting_set_hook` | BL | (returns from `0xdafc4` like `0xdbce0`) | Settings setter `0xdafc4(obj, 'prID', item, msg*)`: our items | `settings.c` | confirmed (emupod) | [Native side of a setting][native] |
| `0x7db6c` | `0xe1a05000` `mov r5, r0` | `setting_get_hook` | BL | (returns from `0x7db68` like `0x7ea64`) | Settings getter `0x7db68`: our items' values, like Clicker's case `0x7e480` | `settings.c` | confirmed (emupod) | [Native side of a setting][native] |
| `0x875c8` | `0xe590e00c` `ldr lr, [r0, #12]` | `string_hook` | BL | (returns from `0x875c4`) | Bundle lookup `0x875c4(bundle, fourcc, id, size*)`: Frogger's strings and bitmaps | `art.c` (`frogger_resource`) | confirmed (device) | [Frogger's settings][fset] |
| `0xb916c` | `0xeb000e35` `bl 0xbca48` | `play_hook` | BL | `0xbca48` | Loads a track as the song now playing (not the preload from `0x94a5c`): note it for the cover | `art.c` | confirmed (device) | [How the pages work][nppages] |
| `0xb4578` | `0xe5903020` `ldr r3, [r0, #32]` | `vis_hook` | B | `0xb457c` | First instruction of every element's SetVisible (`vtable+0x94`): Now Playing opens or closes; skip showing what the cover page hides | `nowplaying.c` | confirmed (device) | [How the pages work][nppages] |
| `0x9bab0` | `0xe5940020` `ldr r0, [r4, #32]` | `vm_hook` | B | `0x9bab4` | Bytecode interpreter, before each opcode fetch (`r4` the VM): the pcs in [UI bytecode](#ui-bytecode) go to `frogger_vm`, which may return another pc | `holdmenu.c`, `queue.c`, `nowplaying.c`, `debug.c` | confirmed (device) | [The VM][vm], [How the pages work][nppages] |
| `0xe3aac` | `0xe59d6054` `ldr r6, [sp, #84]` | `trans_hook` | B | `0xe3ab0` | `0xe3a9c(stack, from, to, kind, ms)`, a screen stack's slide: 1 ms for the bar area on the cover page | `nowplaying.c` | confirmed (device) | [How the pages work][nppages] |
| `0xd2db4` | `0xe92d47f0` `push {r4-r10, lr}` | `lcd_hook` | B | `0xd2db8` | First instruction of `lcd_update_rect(display, rect)` (top, left, bottom, right), the only code that writes the LCD, from the framebuffer `0x3835a0`: held (skipped, noted) while a page switch's new page draws; `lcd_flush` goes past it for the slide's frames | `nowplaying.c` | confirmed (emupod) | [How the pages work][nppages] |
| `0x68e60` | `0xe5940020` `ldr r0, [r4, #32]` | `drawn_hook` | B | `0x68e64` | In the end-update `0x68dfc`, after its drain of dirty rectangles (each drawn, then copied to the LCD; it also comes here when it isn't the last end-update): the new page is in the framebuffer, so the slide runs | `nowplaying.c` | confirmed (emupod) | [How the pages work][nppages] |
| `0xc0c68` | `0xe5940000` `ldr r0, [r4]` | `queue_add_hook` | BL | | `0xc0b30(lib, row)`, the add to On-The-Go, on its way out (`r9` = count before) | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xb7b00` | `0xe92d4ff0` `push {r4-r11, lr}` | `queue_next_hook` | B | `0xb7b04` | First instruction of `0xb7b00(player, list, key, flags)`, the item after `key`: answer with the queue (past songs removed in Up Next; `QUEUE_NO_NEXT` makes it return 0). `queue_next_orig` runs Apple's | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0x5e8cc` | `0xe92d4010` `push {r4, lr}` | `keep_hook` | B | `0x5e8d0` | First instruction of `0x5e8cc(lib)`, which deletes `lib+0x44` as something else starts: spare the queue; note the song playing for `skip_pick_hook` | `queue.c`, `skips.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0x9106c` | `0xe3540000` `cmp r4, #0` | `letter_hook` | BL | | Wheel handler `0x90fe4`, where it looks at the step (`r4`; `r5` the list widget) | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x7998c` | `0xe92d43f0` `push {r4-r9, lr}` | `label_hook` | B | `0x79990` | First instruction of the UI getter `0x7998c(ui, fourcc, prop, row, out*)`: note the `'Str '` property rows ask for | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x1fabc` | `0xe92d4008` `push {r3, lr}` | `title_hook` | B | `0x1fac0` | First instruction of `0x1fabc(obj, element, string, flags)` (`0x08de.60`): note the title's string (element `0x25e7`) | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0xe9664` | `0xe92d4030` `push {r4, r5, lr}` | `tick_hook` | B | `0xe9668` | Called by the UI dispatcher `0x88ee4` about every 0.25 s on the UI thread | `letters.c`, `debug.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x41e5c` | `0xe3a024c4` `mov r2, #0xc4000000` | `crash_hook` | B | `0x41e60` | Apple's abort handler `0x41e5c(frame, kind)`, from the vectors `0x140`, `0x158`, `0x170`. DEBUG=1 only (`OPTIONAL_HOOKS`) | `debug.c` | confirmed (device) | [Address spaces][as], `payload/debug.c` |
| `0xb9354` | `0xe59d0230` `ldr r0, [sp, #560]` | `resume_flags_hook` | BL | | `0xb8ed8`, the track load: the flags from `0xb7efc`, about to be `[player+0x2380]` (`r6` the track record): `0x40` (bookmark) for long tracks | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| `0xb9550` | `0xe5840164` `str r0, [r4, #356]` | `resume_start_hook` | BL | | `0xb8ed8`: a bookmarked track's start (`r0`, from `track+0x60`) into `[player+0x2164]`: 5 s back | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| `0xb903c` | `0xe5860060` `str r0, [r6, #96]` | `resume_save_hook` | BL | | `0xb8ed8`: the track being left (`r6`) gets its position as its bookmark: 0 in its last 15 s | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| `0xf4d6c` | `0xe92d4ff0` `push {r4-r11, lr}` | `counts_hook` | B | `0xf4d70` | First instruction of `0xf4d6c(lib)`, which writes Play Counts: the playing track's position into its bookmark first | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| `0xb81d4` | `0xe92d47f0` `push {r4-r10, lr}` | `skip_next_hook` | B | `0xb81d8` | First instruction of Next, `0xb81d4(player, flags)`: the song left counts as skipped (2-20 s in) unless `flags & 0x10` (it ended) | `skips.c` | confirmed (emupod) | [Skips][skips] |
| `0xb8eb4` | `0xe92d4038` `push {r3, r4, r5, lr}` | `skip_pick_hook` | B | `0xb8eb8` | First instruction of `0xb8eb4(player, item)`, a pick's load: the song before it (playing, or noted by `keep_hook`) counts as skipped; `lr` passed, `0xd9268`'s ignored | `skips.c` | confirmed (emupod) | [Skips][skips] |
| `0x118df0` | `0xeb000012` `bl 0x118e40` | `battery_read` (C) | BL | | `0x118de0`, a battery reading: calls `0x118e40(&raw)` itself and notes raw | `battery.c` | confirmed (emupod, read stubbed) | [The battery icon][bat] |
| `0x8e788` | `0xebfed0d9` `bl 0x42af4` | `battery_state` (C) | BL | | `0x8e760`, the bar's update: calls `0x42af4(bar)` itself; a level state becomes child 4 or 5 (the percentage) | `battery.c` | confirmed (emupod) | [The battery icon][bat] |
| `0xc347c` | `0xe92d407c` `push {r2-r6, lr}` | `disk_reinit_hook` | B | `0xc3480` | First instruction of the drive re-init `0xc347c(ata, unit)`, run before the next command while `ata+0x1e0` is set: a drive still BSY/DRQ gets a soft reset (SRST) and up to 5 s to come back first | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0xc788c` | `0xe92d47fc` `push {r2-r10, lr}` | `disk_read_hook` | B | (calls `0xc7890`) | First instruction of the ATA read `0xc788c(ata, unit, lba, buf, count)`: runs it again, up to 3 tries in all, while it fails with `ata+0x1e0` set | `hooks.S` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x9dbac` | `0xe5940190` `ldr r0, [r4, #400]` | `flash_id_hook` | BL | | ATA dispatcher `0x9da1c`, op `0xEC`, as the IDENTIFY ends (`r4` the ATA object, error at `+0x190`, the 512 bytes at `[+0x17c]`): keep words 0 and 217 and the model for Auto | `flash.c` | confirmed (emupod) | [Flash Storage][flash] |
| `0x57820` | `0xe92d4010` `push {r4, lr}` | `flash_hold_hook` | B | `0x57824` | First instruction of the disk arbiter's `hold(client, ms)`: with Flash Storage on, `ms` is cut to 1000 | `flash.c` | confirmed (emupod) | [Flash Storage][flash] |

Other patches, in `loader/patches.c` (bytes, not hooks):

| Address | Original → new | What | Status | Details |
| --- | --- | --- | --- | --- |
| `0x191914`, `0x191c80` (written at `0x28191914`, `0x28191c80`) | `"Settings"` → `"Frogger!"` | Main menu and Settings title: shows the patched OS runs. `0x1917ce` (tail of "Reset All Settings") is left alone. `-DFROGGER_NO_MARK` turns it off | confirmed (device) | [On a device: nothing hidden][hidden] |

The loader also rewrites three bundle entries and the hold menu's bytecode: see
[UI bundle](#ui-bundle) and [UI bytecode](#ui-bytecode).

## Native functions Frogger calls

Called from C through a cast `#define` (or from `hooks.S`). Signatures are as Frogger uses them.

| Address | As used | What it does | Used by | Status | Details |
| --- | --- | --- | --- | --- | --- |
| **Files** | | | | | |
| `0xb1d50` | `fw_volume()` | The volume word for a path | `art.c` | confirmed (device) | `payload/art.c` |
| `0x403fc` | `fw_open(path, file, 0x20000, 'data')` | Opens a file to read (`path`: volume word, then a DOS-style name; `file`: 0x80 bytes) | `art.c` | confirmed (device) | `payload/art.c` |
| `0x404ec` | `fw_read(file, &len, buf)` | Reads; `len` in/out | `art.c` | confirmed (device) | `payload/art.c` |
| `0x4069c` | `fw_seek(file, offset, 0)` | Seeks from the start | `art.c` | confirmed (device) | `payload/art.c` |
| `0x40110` | `fw_close(file)` | Closes | `art.c`, `debug.c` | confirmed (device) | `payload/art.c` |
| `0x40474` | `fw_create(path, file, 0, 'data')` | Opens a file to write (as `0xf4ad4` does) | `debug.c` | confirmed (device) | `payload/debug.c` |
| `0x407e8` | `fw_write(file, &len, data)` | Writes | `debug.c` | confirmed (device) | `payload/debug.c` |
| `0x53a24` | `make_path(out, 'itun', "iPod_Control\\iTunes\\", name)` | Path to write (`out` 0x108 bytes); **creates or empties the file** | `playlist.c`, `debug.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x7b3bc` | `find_path(out, name)` | Path to read; `-0x2b` if no such file | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0xf4ad4` | `write_otg_file(lib, path)` | Writes the playlist at `lib+0x48` as an On-The-Go file | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0xc5a90` | `read_otg_file(dest, tracks, stamp, path)` | Appends an On-The-Go file's songs to `dest` if it carries `stamp`; 0 = done | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x6fcfc` | `lib_tracks([lib])` | The library's track list, for `0xc5a90` | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x77600` | `db_stamp()` | The iTunesDB's file time, the files' stamp | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| **Playlists and playback** | | | | | |
| `0xac2ec` | `new_temp_list(lib, &list)` | New temporary playlist (flag `0x40`, never listed); 0 = made | `queue.c`, `playlist.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xa97bc` | `list_stop(list)` | Stops the list if it's playing (first step of `0x465b0`) | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x5aea8` | `list_pldm(list)` | Sends `'pldm'`; 0 = go on | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0xba31c` | `list_remove_all(list)` | Removes the items | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x51250` | `copy_list(lib, src, key, 0, dest)` | Appends `src`'s songs to `dest` | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x849a4` | `list_key(lib)` | The key `0xc0b30` passes to `0x51250` | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x9f6e8` | `row_is_otg(ui, row)` | `0x08eb.ee`: is Playlists' row On-The-Go | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0x78d60` | `list_item(list, order, 0, i)` | Item `i` (order 1: the playlist's own; `0x26`: the master's) | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xb8eb4` | `player_load(player, item)` | Loads an item to play (step of `0xb6c38`) | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xda9a4` | `list_playing(list, shuffle)` | Marks the list as playing | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xce9b0` | `list_touch(list)` | Step of `0xb6c38` after `0xda9a4` | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xb8548` | `player_start(player, item, 1)` | Starts playing | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xb81d4` | `player_next(player, 0)` | Next (the button's `0xaca28`): asks `0xb7b00`, then plays its answer. Up Next's pick goes through it | `queue.c` | confirmed (emupod) | [Up Next][upnext] |
| `0x465fc` | `ui_clear_otg(ui)` | Clear Playlist's Confirm (`0x08eb.f2`): stop, empty On-The-Go, save, refresh | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0x506ec` | `append_item(item, list, 0, 0)` | Appends one item (from `0x78d60(src, 0x849a4(lib), 0, i)`), as `0x4fb50` does; one per `queue_added` | `queue.c` | confirmed (emupod) | [How songs start playing][play] |
| `0xa5054`, `0xef76c` | `db_begin(db)`, `db_end(db)` | Bracket item fetches and appends on `[lib+0x868]` (as `0x4fb50`) | `queue.c`, `browse.c` | confirmed (emupod) | [How songs start playing][play] |
| **Browsing** | | | | | |
| `0xd6760` | `browse_list(lib, i)` | Browse playlist `i` (0 the library); frees the level arrays, clears the filters | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0xd6138` | `browse_reset(ui)` | `0x08eb.dd`: `0xd6760(lib, 0)`, rows and mode reset | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0xdce44` | `set_level(lib, level)` | `0x08eb.f4`: `lib+0x86c` | `browse.c` | confirmed (code) | [Browsing the Music lists][browse] |
| `0xd539c` | `set_artist(lib, i)` | Artist filter (`-1` All), name for the title | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0x7c3a0`, `0x7c1a8`, `0x7c368`, `0x7c178`, `0x7c460` | `build(lib)` → count | Build the genres, artists, composers, albums, songs array from the query | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0xf0fe8`, `0xefdec`, `0xf0670`, `0xefd9c`, `0xf2518` | `build_list(ui)` | `0x08eb.f8/.f5/.f6/.f7/.f9`: build a level and refresh its widget unless the count is cached (`ui+0x12f8…`) | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0xd6478` | `songs_reset(ui)` | `0x08eb.de`, Songs' reset: caches -1, `ui+0x1618` -1, browse the library | `browse.c` | confirmed (emupod) | [Up Next][upnext] |
| `0xaa10c`, `0xa9f70` | `mem_alloc(size)`, `mem_free(p)` | Heap, as `0x7c460` allocates the songs array and `0x9d7c4` frees it | `browse.c` | confirmed (emupod) | [Up Next][upnext] |
| widget `vtable+0x15c`, `+0x158` | `move(w, n)` | Moves the list's cursor down / up (`-n`), as the wheel does | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0xbca48` | (`play_hook` goes on into it) | Loads a track as the song now playing | `hooks.S` | confirmed (device) | [How the pages work][nppages] |
| **Settings** | | | | | |
| `0xd85cc` | `prefs_set_flags(lib, flags)` | Stores the prefs flags word (`[lib]+0xb04`), mirrors it at `0x420a34`, marks prefs dirty (`0xacfac`) | `settings.c` | confirmed (emupod) | [Frogger's settings][fset] |
| `0x7722c`, `0x80890` | `0x80890(0x7722c(), 'Str ', id)` | The string resource for an id, as the getter's `'Str '` case does | `hooks.S` (`setting_get_hook`) | confirmed (emupod) | [Native side of a setting][native] |
| **UI** | | | | | |
| `0x7998c` | `label_get(ui, 'Str ', prop, row, &text)` | A list row's label, UTF-8, in the UI object's buffer | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0xa065c` | `mac_time(&t)` | Now, in seconds since 1904 (local): what `0xb79ac` stores as a track's last played (`track+0x90`) | `skips.c` | confirmed (emupod) | [Skips][skips] |
| `0x87de0` | `clock_us(&now)` | Microsecond clock | `letters.c`, `skips.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x1fabc` | `set_text(obj, element, string, 0x80)` | Sets an element's text (`0x08de.60`); `obj` is `[0x41e938]`. Also the popup's rows (Up Next's labels) | `letters.c`, `holdmenu.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0xdafc4` | `apple_setter(settings, 'prID', item, msg*)` | Settings' setter: quick settings' Backlight row turns the toggle message for Backlight Timer (`0x279f`) into the next of Off, the timer remembered and Always On | `settings.c` | confirmed (emupod) | [The hold menu][hm] |
| `0xd8710` | `backlight_seconds(ui, seconds)` | The backlight's own timer (UI object `+0x164c`; 0 Off, `0xffff` Always On), which the prefs value doesn't change until a boot: `0x08eb.111`, as Settings' Backlight list runs it | `settings.c` | confirmed (emupod) | [The hold menu][hm] |
| `0xefec4` | `backlight_apply(app)` | Takes that timer: lights the screen and arms the off timer, or turns it off (`0x08ea.c7`); `app` is `[lib]+0xbc4` | `settings.c` | confirmed (emupod) | [The hold menu][hm] |
| `0x42768` | `layout(view, 1)` | Lays a View out again and repaints | `nowplaying.c` | confirmed (device) | [How the pages work][nppages] |
| `0xda3cc` | `invalidate(obj)` | Repaints an element (what SetVisible ends in) | `nowplaying.c` | confirmed (device) | `payload/nowplaying.c` |
| `vtable+0x94` (= `0xb4578`) | `SetVisible(obj, on)` | Shows or hides an element, repaints | `nowplaying.c` | confirmed (device) | [How the pages work][nppages] |
| `0x42af4` | `battery_state(bar)` | The battery's state: 0-2 charging, 3 charged, 4 + level, 20 low, 21 none | `battery.c` | confirmed (emupod) | [The battery icon][bat] |
| `0x118e40` | `battery_raw(&raw)` | One raw battery reading (0 when it read one; by hardware revision) | `battery.c` | confirmed (emupod: fails there) | [The battery icon][bat] |
| widget `[+0x90]` `vtable+0x11c` | `current_row(cursor)` | The list's current row | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x14b0b8` | `udelay(us)` | Busy-waits on the µs timer `0xcf001110` | `disk.c` | confirmed | [The disk that stops answering][disk] |
| `0x13fa14` | `wait_ready(ata, us)` | Waits for BSY clear, sleeping 1 ms a step; 0 clear, 1 timed out | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0xac6fc` | `thread(name, entry, args, prio, stack, 0, 0)` | Starts a task (`args` a command line, 0 for none); Frogger's cover task FroggerArt is started the way `0x54da8` starts TrackCacheReadTask (`prio` `0x40`, stack `0x2000`). The entry never returns | `art.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x3460` | `sleep(0, ticks)` | Sleeps the calling task (kernel call 20 through `0x2eda8`); a tick is 10 ms in emupod (`sleep(0, 20)`: 24 calls in 5 s), so `0x13fa14`'s step is likely 10 ms, not 1 | `art.c` | confirmed (emupod) | [The disk that stops answering][disk] |

Vtables are relative: a slot holds an offset from the vtable, so the function is `vt + [vt + slot]`.

### Other firmware code named in Frogger's comments

Not called, but where the hooks sit or what they stand in for.

| Address | What | Named in | Status | Details |
| --- | --- | --- | --- | --- |
| `0x140`, `0x158`, `0x170` | Undefined, prefetch-abort, data-abort vectors | `debug.c` | confirmed | [Boot flow][boot] |
| `0xc4a68`, `0xc4244` | Track loader, playlist loader | `hide.c`, `hooks.S` | confirmed | [iTunesDB][itdb] |
| `0xf1ce8` | Browse loop (not what builds the Music lists) | `hide.c` | confirmed | [On a device: nothing hidden][hidden] |
| `0x58440` | Keep-this-item predicate of every library list | `hide.c`, `hooks.S` | confirmed (emupod) | [On a device: nothing hidden][hidden] |
| `0x7c4fc`, `0x512e8` | Return addresses into Songs and Shuffle Songs (`browse_hook` lets them keep hidden songs) | `hooks.S` | confirmed (emupod) | [On a device: nothing hidden][hidden] |
| `0xdafc4`, `0xdbce0` | Settings setter, and its "handled" return | `hooks.S`, `settings.h` | confirmed (emupod) | [Native side of a setting][native] |
| `0xdc530`, `0xdc1dc`, `0xd8670` | What the setter calls to apply Shuffle (`[lib]+0x20` on, `+0x92` Albums), Repeat (`+0x1c`: 0 Off, 1 All, 2 One) and the backlight timer (`+0xaf8`: 0 Off, 1–5 for 1, 2, 5, 10, 20 s, 6 Always On; the prefs only, see `0xd8710`); quick settings' labels read those | `holdmenu.c` | confirmed (emupod) | [Key input][keys] |
| `0xbe8a8`, `0xbe828`, `0x8abe0` | Hold Menu's native (`0x08ea.cb(event)`, run by fn 243) and the main menu's Backlight item: `(app+0x11c, app, event)`, a state machine that flips the light (`0xd86b4` → `0x139a80`). Quick settings replaces the hold | `holdmenu.h` | confirmed (emupod) | [Key input][keys] |
| `0x7db68`, `0x7e480`, `0x7ea64` | Settings getter, its Clicker case, its "handled" return | `hooks.S`, `settings.h` | confirmed (emupod) | [Native side of a setting][native] |
| `0x875c4` | Bundle lookup | `art.c`, `hooks.S` | confirmed | [Frogger's settings][fset] |
| `0x94a5c` | Preloads the next song through `0xbca48` (not through `play_hook`) | `hooks.S` | confirmed (emupod) | `payload/hooks.S` |
| `0xe3a9c` | Starts a screen stack's slide | `hooks.S`, `nowplaying.c` | confirmed (emupod) | [How the pages work][nppages] |
| `0xe0bc0` | SetVisible's own invalidate (only for flag `0x10`) | `nowplaying.c` | confirmed (emupod) | `payload/nowplaying.c` |
| `0x9bab4`, `0x9d288` | Interpreter: after the opcode fetch; the "pc reached `[vm+0x24]`" return | `hooks.S`, `holdmenu.h` | confirmed (emupod) | [Running our own bytecode][hm] |
| `0xc0b30`, `0xc0ce8` | Add a row to On-The-Go; its native method `0x08eb.e9` | `queue.c`, `playlist.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0x465b0` | Empties On-The-Go and resets the list on screen (`0x9d7c4`), which `list_empty` avoids | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0xd6760` | `0x08eb.e2(row)`: Playlists' row → playlist, and points the browse list at it | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `0xb6c38` | Plays a list from a row (the steps `play_from` copies) | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xb8ed8`, `0xb7efc` | Loads a track (every song that plays); its flags (`0x40` for a `.m4b` path) | `resume.c`, `hooks.S` | confirmed (emupod) | [Bookmarks][bm] |
| `0xe4338`, `0x8db2c`, `0xe4abc` | Play Counts read at boot; written on sleep and on the database's unload | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| `0x6a15c` | Apple reaching the library as `[[0x43580c]+0x1c]` | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `0xacfac` | Marks prefs dirty | `settings.c` | confirmed (emupod) | [Frogger's settings][fset] |
| `0x90fe4`, `0x90d50` → `0x4295c` | Wheel handler; its step accelerator | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x88ee4` | UI dispatcher (calls `0xe9664`) | `hooks.S`, `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x913d0` | ATA error reset: pulses `0xcf005034` bit 2 (the PP5002's IDE controller, not the drive), redoes the timings (`0xdda40`), sets `ata+0x1e0` | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x1302a0` | ATA state handler for event 5 (timeout/error): `+0x18c = 0xff`, error `0x400` into `+0x190`, `0x913d0`, then event 0 (done) | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x11ac00` | `post(table, ata, event)`: the ATA state machine's next step, `ata+0x174 = table + 4 + 8 * event` | | confirmed | [The disk that stops answering][disk] |
| `0x12ff68`, `0x1300bc`, `0x1301fc` | ATA state handlers that check the timeout (`0xe7290`) and post event 5 | | confirmed | [The disk that stops answering][disk] |
| `0xc7720` | Block-device read (ATA vtable `+0xc`), calls `0xc788c` | `hooks.S` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0xe9c4c` | TrackCacheReadTask: on a read error it goes back to waiting (`0xe9c6c`) and the refill is lost | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x13bc94` | The disk arbiter task (mailbox 19): 19 clients, each busy (`0x5790c`), released with a hold (`0x57820`) or idle; it waits for the next message or the shortest hold left (in 10 ms ticks), and when no client holds the disk it posts sub-op 2 (STANDBY) to the disk-power task, sub-op 4 otherwise (`0x13bf58..0x13bfb0`) | `flash.c` | confirmed (emupod) | [Flash Storage][flash] |
| `0x57820` | `hold(client, ms)` | Arbiter message kind 2: the client is done, keep the disk up `ms / 10 + 1` ticks more. Callers: client 1 (database load `0xe4454`) 15000, 6 (TrackCacheReadTask `0xe9cac`) 10000, 4 (`0xbc18c`) 3000, 2 (playback `0x94b34`, `0x46d38`), 3 (`0xe4c1c`) and 10 2000, 8, 11, 13, 15 1000, 12 952, 7 100, 3 (`0xe1ed0`) and 9 0 | `flash.c` | confirmed (code, emupod) | [Flash Storage][flash] |
| `0x5790c`, `0x57970` | `busy(client)` | Arbiter kind 0: the client uses the disk, no hold (`0x57970` with `[msg+0x24] = 1`) | | confirmed (code) | [Flash Storage][flash] |
| `0x576ec`, `0x57758`, `0x577bc`, `0x578a8` | | Arbiter kinds 1, 5, 3, 4 (not followed) | | likely | [Flash Storage][flash] |
| `0x54da8` | Where TrackCacheReadTask is started (`0xac6fc`, name at `0x1c0a68`): the pattern FroggerArt follows | `art.c` | confirmed | [The disk that stops answering][disk] |

## RAM objects and globals

| Address / offset | What | Used by | Status | Details |
| --- | --- | --- | --- | --- |
| `0x43580c` | The UI object (bytecode `0x08eb`; methods at `0x1bd808 + 4 * selector`, `.e9` at `0x1bdbac`). `re-notes.md` calls it `0x08df` | `queue.c`, `playlist.c`, `letters.c` | confirmed (emupod) | [On-The-Go and the queue][otg], [The hold menu][hm] |
| `lib+0x58`, `+0x5c`, `+0x60`, `+0x64`; `+0x68…0x868` | Browse filters (genre, artist, composer, album; `-1` All) and their names | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `lib+0x86c`; `lib+0x878…0x89c` | Browse level; the level arrays and counts (genres, artists, composers, albums, songs) | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `ui+0x12f8…0x1308`, `+0x1618…0x1624`, `+0x168c` | Builders' cached counts; rows picked; mode | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| track record `+0x30`, `+0x7c` | Album (pool key); track number (halfword) | `browse.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `[lib+0x3c]` = `0x93c20` | The "started playing" callback (posts `0x3300001d`) | `queue.c` | confirmed (emupod) | [How songs start playing][play] |
| `0x41e938` | The bytecode's `0x08de` object (screens, element text) | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| `0x420a34` | Copy of the prefs flags word | `settings.c` | confirmed (emupod) | [Native side of a setting][native] |
| `Device/Preferences` file offset `0xafc` | The saved prefs flags word: the file is the prefs struct from `prefs+8` (offset = struct offset − 8) | Crate | confirmed (device) | [Frogger's settings on the disk][fdisk] |
| ui `+0x1c` | The library object (`lib`) | `queue.c`, `playlist.c`, `letters.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `[lib]` | Root object = prefs: `+4` the player, `+0x20` shuffle byte, `+0xb04` prefs flags word (Apple: bits 0, 1; Frogger: 16 Show Hidden, 17 Jump by Letter off, 18 Resume Mixes off, 19–23 a feature switch off (`FEATURE_*`), 24–26 the backlight timer's last value other than Off and Always On), `+0xbc4` the app object (`0x08ea`), `+0xb41` Play Counts needs writing, `+0xb42` On-The-Go needs saving | `queue.c`, `playlist.c`, `settings.c`, `letters.c`, `resume.c` | confirmed (emupod) | [Frogger's settings][fset], [Playlists made on the iPod][otgfiles] |
| `lib+0x3c` | Callback run when a list starts playing | `queue.c` | likely | `payload/queue.c` |
| `lib+0x44` | The list Now Playing plays from | `queue.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `lib+0x48` | On-The-Go. Stock's add, clear and save all read it, so Frogger swaps its own list in while they run | `queue.c`, `playlist.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| `lib+0x870`, `+0x874` | The playlists (`[0]` the library; Playlists' row `r` is `[r + 1]`), count | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| `player+0x2164`, `+0x2380` | Position in the track (ms); the loaded track's flags (`0x40` bookmark) | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| `player+0x2a4`, `+0x2a8` | The list playing, its current item (0 when stopped) | `queue.c`, `playlist.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| list `+0x24` → `+0x2c` | Song count | `queue.c`, `playlist.c` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| list `+0x124` | N of "New Playlist N" (0: synced) | `playlist.c` | confirmed (emupod) | [Playlists made on the iPod][otgfiles] |
| item `+0`, `+0x10`, `+0x20` | Its list, its key, its track record | `queue.c`, `hooks.S` | confirmed (emupod) | [On-The-Go and the queue][otg] |
| settings obj `+0x48`, `+0x54` | Last value string id; the library | `hooks.S`, `settings.c` | confirmed (emupod) | [Frogger's settings][fset] |
| widget `+0x90`, `+0x9c` | Its cursor; row count | `letters.c` | confirmed (emupod) | [The wheel and the lists][wheel] |
| element `+0x10`, `+0x18`, `+0x1c`, `+0x20`, `+0x28..+0x54`, `+0x58`, `+0x6c`/`+0x70`, `+0x78` | Parent, type, id, flags (`0x800` shown, `0x1000` hidden), layout coordinates, rectangle, children (count/array), clip | `nowplaying.c` | confirmed (emupod) | `payload/nowplaying.c`, [How the screen is put together][npscreen] |
| track record `+0x54`, `+0x60` | Length (ms, mhit `+0x28`); bookmark (ms, mhit `+0x6c`, Play Counts `+8`) | `resume.c` | confirmed (emupod) | [Bookmarks][bm] |
| track record `+0x28`, mhit `+0x98` | Artist (album artist when there is one); Frogger's `"HIDE"` flag | `artist.c`, `hide.h` | confirmed (emupod) | [iTunesDB][itdb], [Album artists][aa] |
| `0x36ffc0` | Apple's 15 battery thresholds (u16, rising, raw units): level = how many are ≤ raw | `battery.c` | confirmed (emupod) | [The battery icon][bat] |
| `0x370d64` | The battery level 0..15 (16 none yet), moved a step per reading | | confirmed (emupod) | [The battery icon][bat] |
| `0x1fd44dc` (heap, stock; differs with Frogger) `ata+0x10c`, `+0x114`/`+0x118`, `+0x1a4`, `+0x1e0` | The ATA object: pointers to the status, device-control and alt-status registers; the running command's timeout; re-init pending (set by `0x913d0`, cleared at `0xc3560`) | `disk.c`, `hooks.S` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x420a5c` (19 bytes), `0x420a70` (19 words), `0x420a54` | The disk arbiter's state: a client holds the disk, its ticks left (−1 busy), and `+4` "some client holds it" | | confirmed (code) | [Flash Storage][flash] |
| `ata+0x17c`, `ata+0x190` | the transfer pointer: `0xdec68` stores the IDENTIFY buffer there, and at `0x9dbac` it points just past its 512 bytes (the buffer is reused later); the command's error | `flash.c` | confirmed (emupod) | [Flash Storage][flash] |
| prefs flags (`prefs+0xb04`) bits 27-28 | Flash Storage: 0 Off, 1 Auto, 2 On | `settings.c` | confirmed (emupod) | [Flash Storage][flash] |
| `0xc00033f8` | ATA device control (write: bit 1 nIEN, bit 2 SRST) / alternate status (read) | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |
| `0x1ed44dc` (heap, with Frogger in emupod) | The ATA object as `disk_read_hook` sees it (r0 of `0xc788c`); `disk.c` keeps the pointer from the first read rather than a fixed address | `disk.c` | confirmed (emupod) | [The disk that stops answering][disk] |

## UI bytecode

TCmd resource at `0x191dcc`; **code base `0x192948`** (`TCMD_CODE`). `tools/re/tcmd.py` prints
offsets from the code base; function id = index + `0x69c`. Details: [The resource][tcres],
[The VM][vm], [The hold menu][hm].

VM object fields Frogger reads or writes:

| Field | What | Used by | Status |
| --- | --- | --- | --- |
| `[vm+0x10]` → `+0x24` | The frame; its locals (local0 = `[[[vm+0x10]+0x24]]`) | `holdmenu.c`, `queue.c` | confirmed (emupod) |
| `[vm+0x18]` | Stack pointer | | confirmed |
| `[vm+0x20]` | pc (`vm_hook` reads it and writes back `frogger_vm`'s answer) | `hooks.S` | confirmed (device) |
| `[vm+0x24]` | **The running function's end**: the VM returns when the pc reaches it (`0x9d288`). Move it when jumping into another function | `holdmenu.c` (`VM_CODE_END`) | confirmed (device) |

Bytecode pcs `vm_hook` acts on (absolute = `0x192948` + offset):

| pc | Offset | Fn | What | Used by | Status |
| --- | --- | --- | --- | --- | --- |
| `0x195b86–0x196cce` | `0x323e–0x4386` | 188–239 | `HM_LO`–`HM_HI`: every pc in here goes to C | `holdmenu.h` | confirmed (device) |
| `0x195b86` | `0x323e` | 188 (`0x758`) | Opening Playlists (`HM_PLAYLISTS`) | `holdmenu.c` | confirmed (emupod) |
| `0x195c58` | `0x3310` | 190 (`0x75a`) | Playlists' Select, after the row read (`HM_PICKED`) | `holdmenu.c` | confirmed (emupod) |
| `0x196332` | `0x39ea` | 210 (`0x76e`) | A songs list's Select, after the row read: Up Next plays the queue's song (`HM_SONG_PICK`) | `holdmenu.h` | confirmed (emupod) |
| `0x195d44` | `0x33fc` | 192 (`0x75c`) | Playlists' Menu (`HM_PICK_MENU`) | `holdmenu.c` | confirmed (emupod) |
| `0x195ced` | `0x33a5` | 191 | Playlists hold: guard that skips row 0, On-The-Go (`QUEUE_FN_HOLD`) | `queue.h` | confirmed (emupod) |
| `0x193580`, `0x19358a`, `0x19358b` | `0xc38`, `0xc42`, `0xc43` | 50 (`0x6ce`) | A menu item's Select: the `0x08df.9b()` send, after it, its return nil | `holdmenu.h` | confirmed (emupod) |
| `0x192d82` | `0x43a` | 14 (`0x6aa`) | Go back (`HM_FN_BACK`) | `holdmenu.h` | confirmed (emupod) |
| `0x1930e8`, `0x1930f0` | `0x7a0`, `0x7a8` | 28 (`0x6b8`) | Popup's first row (Cancel); its tail, fn 14 + return (`HM_GO_BACK`) | `holdmenu.h` | confirmed (emupod) |
| `0x1930e8` | `0x7a0` | 28 (`0x6b8`) | Also the main menu's Queue row's function (`hm_main`): run off a popup (`hm.up` 0, inside fn 50), it opens the Queue list (`main_queue`) | `holdmenu.c` | confirmed (emupod) |
| `0x1932bc`, `0x1932bd` | `0x974`, `0x975` | 33 (`0x6bd`) | The main menu's rows shown or hidden by their Main Menu setting (fn 36, its opener, runs it): its last drop, only reached with the main menu up, and its return. The Queue row is shown or hidden there (`HM_MM_SHOW`, `HM_MM_SHOWN`) | `holdmenu.h` | confirmed (emupod) |
| `0x196f32`–`0x196fdc` | `0x45ea`–`0x4694` | 249 (`0x795`) | Apple's sleep, what holding Play runs after a second (fn 250 `0x796` arms it): quick settings' Sleep runs this body (`HM_SLEEP_BODY`, `HM_SLEEP_END`) | `holdmenu.h` | confirmed (emupod) |
| `0x192f3d`, `0x192efd` | `0x5f5`, `0x5b5` | 20 (`0x6b0`) | A screen slides in forward, back (`HM_SCREEN_FWD`, `HM_SCREEN_BACK`): browse.c's restore point | `holdmenu.h` | confirmed (emupod) |
| `0x1930bc` | `0x774` | 26 (`0x6b6`) | The popup is up (fn 26's return): rows shown or hidden here (`HM_POPUP_UP`) | `holdmenu.h` | confirmed (emupod) |
| `0x1947c0` | `0x1e78` | 110 (`0x70a`) | Entry; Frogger calls fn 110 for its frame and sends it to `HM_VIS` / `HM_NP_HOLD` (`HM_FN_VIS_FRAME`) | `holdmenu.h` | confirmed (emupod) |
| `0x196e5a` | `0x4512` | 243 (`0x78f`) | Entry: hold Menu (fns 77 and 148 bind it); Frogger opens quick settings there instead, unless a popup is up (`HM_QS_HOLD`) | `holdmenu.h` | confirmed (emupod) |
| `0x19a918` | `0x7fd0` | 480 (`0x87c`) | Entry; no arguments, two locals, stack 5: quick settings' `HM_OPEN` runs in its frame (`HM_QS_FRAME`, called from `HM_QS_RUN`) | `holdmenu.h` | confirmed (emupod) |
| `0x19517c` | `0x2834` | 151 (`0x733`) | Now Playing binds Select (fn 169); replaced by `HM_NP_BIND` (`HM_FN_NP_SELECT`) | `holdmenu.h` | confirmed (emupod) |
| `0x1930ca` | `0x782` | 27 (`0x6b7`) | Popup's second row (Confirm): calls global `0x8e8` | `holdmenu.h` | confirmed (emupod) |
| `0x195630`, `0x1956c1` | `0x2ce8`, `0x2d79` | 169 (`0x745`) | Now Playing's Select; its "nothing to do" return | `nowplaying.h` | confirmed (device) |
| `0x1959c0` | `0x3078` | 183 (`0x753`) | Select while rating: back to normal | `nowplaying.h` | confirmed (device) |
| `0x1957de` | `0x2e96` | 173 (`0x749`) | The 5 s timeout back to normal | `nowplaying.h` | confirmed (device) |
| `0x1953f4` | `0x2aac` | 160 (`0x73c`) | Now Playing's Menu | `nowplaying.h` | confirmed (device) |

The eight hold handlers (`handlers[]` in `holdmenu.c`; offsets there, absolute here). Each reads
the row into local0, adds it, then flashes the row (`0x08df.ae`).

| Fn | Id | Entry | Row read | Flash | End (no add) | `[vm+0x24]` (entry + len) | List |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 191 | `0x75b` | `0x195cc4` (`0x337c`) | `0x195ce6` (`0x339e`) | `0x195d28` (`0x33e0`) | `0x195d36` (`0x33ee`) | `0x195d38` (len `0x74`) | Playlists |
| 199 | `0x763` | `0x196006` (`0x36be`) | `0x196028` (`0x36e0`) | `0x196042` (`0x36fa`) | `0x196050` (`0x3708`) | `0x196052` (len `0x4c`) |  |
| 211 | `0x76f` | `0x196364` (`0x3a1c`) | `0x196393` (`0x3a4b`) | `0x1963ad` (`0x3a65`) | `0x1963bb` (`0x3a73`) | `0x1963be` (len `0x5a`) | Songs |
| 212 | `0x770` | `0x1963ca` (`0x3a82`) | `0x1963ec` (`0x3aa4`) | `0x196406` (`0x3abe`) | `0x196414` (`0x3acc`) | `0x196416` (len `0x4c`) |  |
| 219 | `0x777` | `0x1965aa` (`0x3c62`) | `0x1965d9` (`0x3c91`) | `0x19660a` (`0x3cc2`) | `0x196618` (`0x3cd0`) | `0x19661a` (len `0x70`) |  |
| 226 | `0x77e` | `0x1967f0` (`0x3ea8`) | `0x19681f` (`0x3ed7`) | `0x196850` (`0x3f08`) | `0x19685e` (`0x3f16`) | `0x196860` (len `0x70`) |  |
| 233 | `0x785` | `0x196a32` (`0x40ea`) | `0x196a61` (`0x4119`) | `0x196a92` (`0x414a`) | `0x196aa0` (`0x4158`) | `0x196aa2` (len `0x70`) |  |
| 239 | `0x78b` | `0x196c60` (`0x4318`) | `0x196c8f` (`0x4347`) | `0x196cc0` (`0x4378`) | `0x196cce` (`0x4386`) | `0x196cd0` (len `0x70`) |  |

Frogger's own bytecode and the bytecode names it uses:

| Address / id | What | Used by | Status | Details |
| --- | --- | --- | --- | --- |
| `0x18e48c–0x18e714` | `HM_SNIPPET`: Menu `0x25ba`'s stock data (`0x54` bytes) and Apple's stock Settings Menu (`0x234` bytes at `0x18e4e0`), both free once their entries point at the payload's copies. **The loader copies `hm_code` here** (popup, row visibility, Add to Playlist's pick, Go to Album/Artist, Now Playing's hold, Up Next, going back twice and quick settings' call into fn 480; layout in `holdmenu.h`), at boot: read-only later. Below the code base, so it runs; `vm_hook` hands every pc in it to `holdmenu_vm` | `holdmenu.h`, `loader/patches.c` | confirmed (device) | [Running our own bytecode][hm] |
| `0x08de` | Object: element text `.60`, defer `.76`, go back `.7a` | `holdmenu.c` | confirmed (emupod) | [The hold menu][hm] |
| `0x08df` | Object: run item `.9b`, highlight `.9f`, read row `.a9`, flash row `.ae` | `holdmenu.c` | confirmed (emupod) | [The hold menu][hm] |
| `0x08eb` | The UI object `[0x43580c]`: `.e2` row → playlist, `.e9` add, `.ee` is On-The-Go, `.f2` clear, `.f3` save | `playlist.c`, `queue.c` | confirmed (emupod) | [The hold menu][hm] |
| global `0x8e8` | The function the popup's second row runs | `holdmenu.c` | confirmed (emupod) | [The hold menu][hm] |
| fn 24, 26, 53 (`0x6b4`, `0x6b6`, `0x6d1`) | Open the popup; its deferred opener; set the title (`hm_open` repeats fn 24's steps) | `holdmenu.c` | confirmed (emupod) | [The hold menu][hm] |

## UI bundle

The resource bundle at **`0x181d20`**, data offset `0x313c`: an index entry's offset counts from
`0x181d20 + 0x313c`. Details: [UI resources][uires], [The resource][tcres].

Entries the loader repoints at a bigger copy in the payload (it checks them first; any mismatch
and nothing is patched):

| Index entry | Resource | Stock data | Copy | Used by | Status | Details |
| --- | --- | --- | --- | --- | --- | --- |
| `0x18224c` | Menu `0x25ba`, the popup's list: offset `0x9630`, `0x54` bytes, 2 items (Cancel, Confirm); the stock bytes then hold the start of `HM_SNIPPET` | `0x18e48c` | `hm_popup`, 6 items | `loader/patches.c` | confirmed (emupod) | [Browsing the Music lists][browse] |
| `0x182210` | Menu `0x2512`, the main menu: offset `0x8f14`, `0x374` bytes, 22 items (row 0 Music, row 17 Settings) | `0x18dd70` | `hm_main`, 23 items: Queue (Settings' item, fn 28, label `0x3f1b`) after Music | `loader/patches.c` | confirmed (emupod) | [The main menu's Queue row][mmq] |
| `0x182258` | Menu `0x278d`, Settings: offset `0x9684`, `0x234` bytes, 14 items, row 8 Clicker (item `0x282d`) | `0x18e4e0` | `settings_menu`, + 2 items | `loader/settings.c` | confirmed (emupod) | [Frogger's settings][fset] |
| `0x184184` | View `0x25ee`, Now Playing: offset `0x1ac94`, `0x300` bytes, 9 elements | `0x19faf0` | `np_view`, + art element | `loader/nowplaying.c` | confirmed (device) | [How the pages work][nppages] |

Ids Frogger adds (served by `string_hook` → `frogger_resource`; `tests/test_settings.py` checks
they're free):

| Id | Kind | What | Defined in |
| --- | --- | --- | --- |
| `0x2900`, `0x2901`, `0x2902` | Settings item id (word 6) | Show Hidden, Jump by Letter, Resume Mixes | `settings.h` |
| `0x3f00`, `0x3f16`, `0x3f1e` | `Str ` | "Show Hidden", "Jump by Letter", "Resume Mixes" | `settings.h` |
| `0x2903`–`0x2907` | Settings item id (word 6) | The feature switches: Cover Page, Hold Menu, Quick Settings, Battery Percent, Page Slide | `settings.h` |
| `0x3f20`–`0x3f24` | `Str ` | Their labels | `settings.h` |
| `0x3f2c` | `Str ` | Quick settings' "Sleep" | `holdmenu.h` |
| `0x3f01` | `BMap` | The cover (`FROGGER_BMAP_ART`) | `settings.h` |
| `0x3f10`, `0x3f11`, `0x3f12`, `0x3f13` | `Str ` | Hold menu: "Frogger", "Add to Queue", "Add to Playlist", "Add to" | `holdmenu.h` |
| `0x3f14`, `0x3f15` | `Str ` | The letter in the title (two ids, taken in turn) | `letters.h` |
| `0x3f17`–`0x3f1a` | `Str `, and the new popup rows' element ids | Hold menu: "Play Album Next", "Go to Album", "Go to Artist", "Hide" (`0x3f12` is Add to Playlist's row element too) | `holdmenu.h` |
| `0x3f1b`, `0x3f1c`, `0x3f1d` | `Str ` | "Up Next" (Now Playing's row 0, and the list's title), "Remove from Queue", "Clear Queue" (the Up Next popup's rows 0, 1, relabelled) | `holdmenu.h` |
| `iPod_Control/iTunes/FroggerHidden` | file | Songs hidden on the iPod: header (`"FRGH"`, version 2, entry size 12, the iTunesDB's stamp, count, reserved; 20 bytes), then per song its iTunesDB position, track id and flags (bit 0 shown: Show on a song the iTunesDB flags; else hidden). Version 1 (entry size 8, no flags, all hidden) is still read | `hide.h` |

Apple's ids Frogger uses:

| Id | What | Used by | Details |
| --- | --- | --- | --- |
| `0x279d`, `0x279e`, `0x282f` | "On", "Off", the toggle message | `settings.h` | [Native side of a setting][native] |
| `0x282d` | Clicker's item id | `loader/settings.c` | [Native side of a setting][native] |
| `0x2503` | The title bar (View) | `nowplaying.c` | [How the pages work][nppages] |
| `0x25e7` | The screen title element | `letters.c`, `hooks.S` | [The wheel and the lists][wheel] |
| `0x3319`, `0x331a`, `0x331b` | Now Playing's title, artist, album | `nowplaying.c`, `loader/nowplaying.c` | [The screen: View 0x25ee][npview] |
| `0x331f`, `0x25ed`, `0x335e`, `0x25ec`, `0x25eb` | Now Playing's "1 of 2" row (`0x25ed` is also the art element's template) | `nowplaying.c`, `loader/nowplaying.c` | [The screen: View 0x25ee][npview] |
| `0xff33` | Now Playing's bar area (`None`, a screen stack) | `nowplaying.c`, `loader/nowplaying.c` | [The screen: View 0x25ee][npview] |
| `0x25ba`, `0x25d4`, `0x25d5`, `0x25e2` | The popup's list, its two row elements, its screen | `holdmenu.c` | [The hold menu][hm] |
| `0x3315`, `0x3317` | Titles: the artist's, the album's (from the filter's name) | `holdmenu.c` | [Browsing the Music lists][browse] |
| `0xfff2` | Playlists' title (pool constant `0x85`), renamed "Add to" while picking | `playlist.h` | [Playlists made on the iPod][otgfiles] |
| `0x335f`, `0x3364` | Row label properties: Songs, Artists | `letters.c` | [The wheel and the lists][wheel] |
| `0x2579` | The ">" arrow (a 1-bit BMap) | `art.c` | [Covers][covers] |
| `0x3342`; `0x2594`, `0x2595` | The bar's battery (`None`, a child per state); its level 0 and 1 bitmaps, which Frogger serves (the percentage) | `battery.c` | [The battery icon][bat] |

## Not addresses

The other hex constants in `payload/`, `loader/` and `tools/mkpayload.py`: instruction words
(`0xe…`, `0xeb000000`/`0xea000000` for BL/B); fourccs (`'Str '` `0x53747220`, `'BMap'`
`0x424d6170`, `'None'` `0x4e6f6e65`, `'prID'` `0x70724944`, `'data'` `0x64617461`, `'itun'`
`0x6974756e`); magic words (`"HIDE"` `0x45444948`, `"FRGA"` `0x41475246`, `"FRDB"` `0x46524442`,
`0xc0de0000`); View coordinate anchors (`0x80000002`, `0x80000004`, `0x80000008`, `0x80000018`); Menu word 5
(`0x03100000`, `0x03110000`, plus the label id); element flags (`0x800`, `0x1000`, mask `0x1800`); file mode
`0x20000`; `ART_FRAME` `0xff00`, `NP_ART_NONE` `0xffff`; masks (`0xffffff`, `0xffffffff`); the
`0x2800abcd` example in `loader/patches.c`; and the digit bitmaps in `art.c` (`0x2c97`, `0x73e7`, …) and `battery.c`.

[as]: re-notes.md#address-spaces
[bm]: re-notes.md#bookmarks-resume-confirmed-in-emupod
[bat]: re-notes.md#the-battery-icon-confirmed-in-emupod
[skips]: re-notes.md#skips-confirmed-in-emupod
[boot]: re-notes.md#entry-point-and-boot-flow
[ram]: re-notes.md#free-ram-for-any-resident-patch-code
[itdb]: re-notes.md#itunesdb-where-artistsalbumssongs-come-from-for-m2
[plload]: re-notes.md#playlist-loader-0xc4244-confirmed
[hidden]: re-notes.md#on-a-device-nothing-gets-hidden
[aa]: re-notes.md#album-artists-confirmed-in-emupod
[keys]: re-notes.md#key-input-gpio-events-confirmed-from-the-code-and-emupod
[uires]: re-notes.md#ui-resources-menus-strings-bytecode-for-m2s-all-artists
[otg]: re-notes.md#on-the-go-and-the-play-queue-confirmed-in-emupod
[otgfiles]: re-notes.md#playlists-made-on-the-ipod-confirmed-in-emupod
[browse]: re-notes.md#browsing-the-music-lists-confirmed-in-emupod
[play]: re-notes.md#how-songs-start-playing-for-anything-that-hooks-playback
[upnext]: re-notes.md#up-next-seeing-and-changing-the-queue-confirmed-in-emupod
[mmq]: re-notes.md#the-main-menus-queue-row-confirmed-in-emupod
[wheel]: re-notes.md#the-wheel-and-the-lists-confirmed-in-emupod
[tcres]: tcmd.md#the-resource-confirmed
[vm]: tcmd.md#the-vm-confirmed-unless-marked
[native]: tcmd.md#the-native-side-of-a-setting-confirmed-in-emupod-clicker
[fset]: tcmd.md#froggers-settings-working-in-emupod-not-yet-on-a-device
[fdisk]: tcmd.md#on-the-disk-ipod_controldevicepreferences-confirmed-on-a-device
[hm]: tcmd.md#the-hold-menu-working-in-emupod-payloadholdmenuc
[npview]: nowplaying.md#the-screen-view-0x25ee-confirmed-from-the-resource-roles-likely
[nppages]: nowplaying.md#how-the-pages-work-confirmed-in-emupod-payloadnowplayingc
[npscreen]: nowplaying.md#how-the-screen-is-put-together-runtime
[covers]: nowplaying.md#covers-confirmed-in-emupod-and-on-crates-output
[disk]: power-and-emupod.md#part-c-the-disk-that-stops-answering-confirmed-in-emupod
[flash]: power-and-emupod.md#part-d-flash-storage-working-in-emupod

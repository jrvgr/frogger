# Reverse-engineering notes: iPod 3G firmware 2.3

Notes on Apple's `osos` image from `iPod_2.2.3.ipsw` (`Firmware-2.2.3`,
BuildID `0x02308000`, i.e. 2.3 final). They are what M1 (dark mode) and M2
(Spotify-hide) build on.

Each finding is marked:

- **confirmed**: read straight from the code, with the instructions to back it.
- **likely**: the code strongly suggests it, but nobody has checked it on a device yet.
- **guess**: a starting point, not a fact.

For a map of every address Frogger uses (hooks, native calls, RAM objects, bytecode pcs, bundle
entries), with links back to the sections here, see [`addresses.md`](addresses.md).

## Reproduce

    nix develop .#re
    python3 tools/fwtool.py extract firmware/iPod_2.2.3.ipsw -o build/fw
    tools/ghidra-import.sh                      # build/ghidra/frogger.gpr, base 0x0
    arm-none-eabi-objdump -D -b binary -m arm build/fw/osos.img > build/osos.dis
    tools/re/xref.py callers 0x1335d8           # quick xrefs without Ghidra

`fwtool info` on the ipsw:

    id        offset        len       addr    entry       vers  checksum
    osos      0x4400   0x346368 0x28000000      0x0      0x210  ok
    aupd    0x34a800   0x10fbf8 0x28000000      0x0      0x210  ok

There is no `rsrc` partition image on the 3G: fonts and strings live inside osos.
osos is plain, uncompressed ARM (ARM7TDMI, ARM mode) and starts with the
`portalplayer` tag at 0x20.

Two tooling fixes came out of this:

- fwtool read the 40-byte directory entries as 36 bytes (it missed the image-index
  word after the type), so every field after the type was shifted. Fixed, with tests.
- The directory's `loadAddr` field is junk on the 3G (`0x048d0040`). `addr` is the
  real load address, and fwtool now prints that.

## Address spaces

**confirmed**: Apple's boot ROM copies osos to DRAM at `0x28000000` and jumps to
its first word. The reset code is position independent. It copies a stub to IRAM
(`0x40010000`), and the stub writes the PP5002 memory-map registers
(`0xf000f008 = 0x3b00`, `0xf000f00c = 0x3f84`) so DRAM appears at address 0. It
then jumps to `0x23c`. Everything from there on is linked at 0: about 31,000 literal
words point into `[0, 0x346368)` against about 500 that point into `0x28xxxxxx`. So:

- **Ghidra and objdump use base 0.** `tools/ghidra-import.sh` now does that (set
  `BASE=0x28000000` to override).
- **The loader patches before the remap**, so a patch at runtime address `A` is
  written to `0x28000000 + A`. The `0x2800abcd` example in `loader/patches.c` is
  already in that form.

**confirmed** on a device: once Apple's OS runs, its image is **read-only**. A store
from the payload to `0x18e4e0` (bytecode in the UI bundle) was a data abort, through Apple's
handler `0x41e5c`. emupod doesn't enforce this, so a Frogger feature that writes into
`[0, 0x346368)` at runtime works there and crashes the iPod. Patch it from the loader instead
(it writes before the remap). The payload, Apple's `.data`/`.bss` and the heap are writable.

**likely**: `0x04000000 + A` is an uncached alias of the same DRAM. The scatter
loader copies from `0x0431f260` while the image holds that data at `0x31f260`,
and the heap setup ORs `0x04000000` into pointers for DMA-ish buffers.

## Entry point and boot flow

| Address | What | Status |
| --- | --- | --- |
| `0x000` | Vectors: reset `0x188`, undef `0x140`, SWI is a plain return, pabort `0x158`, dabort `0x170`, IRQ `0x118`, FIQ `0xec` | confirmed |
| `0x188` | Reset: remap DRAM to 0 through the IRAM stub, then jump to `0x23c` | confirmed |
| `0x23c` | Reads `PROCESSOR_ID` (`0xc4000000`), stores it at `0x40000000`. `0x55` (CPU) continues at `0x264`; anything else (the COP) goes to `0x258` | confirmed |
| `0x264` | CPU: stack `0x40003ffc`, about 30 init calls, wakes the COP at `0x364`, then `b 0xc3170` (the OS main loop or scheduler) | confirmed |
| `0x258` | COP: stack `0x40005ffc`, puts itself to sleep (`0x1306a4`), and after wake-up runs `0x1f2c0` | confirmed |
| `0x24320` | Scatter loader: copies `.data` and IRAM code, then zeroes `.bss` (table below) | confirmed |
| `0x126edc` | Early hardware init, and calls the RAM-size probe `0x33500` | likely |

IRQ (`0x118`) dispatches on `PROCESSOR_ID` bit 0: the CPU goes to `0x141dc0`, the
COP to `0x11bc44`. FIQ (`0xec`) handles the CPU at `0x266a0` and sends the COP to
IRAM `0x40000000`.

## LCD and contrast (for M1)

The 3G panel is a 160×128, 2 bpp grayscale controller behind `LCD1` at
`0xc0001000` (Rockbox treats it as an HD66753). There is no direct pointer to
`0xc0001000` in the literal pool: the code builds it as `0xc0000000 + 0x1000`,
so search for `#192, 8` followed by `#64, 26`.

| Address | Function | Status |
| --- | --- | --- |
| `0xa2b94` | `lcd_cmd(hi, lo)`: waits for busy bit `0x8000` on `0xc0001000` (1 ms timeout on the µs timer `0xcf001110`), then writes two bytes to `0xc0001008` | confirmed |
| `0xa2c1c` | `lcd_data(hi, lo)`: the same, writing to `0xc0001010` | confirmed |
| `0xa2ca4` | `lcd_wait_ready()` | confirmed |
| `0x1335d8` | `lcd_write_reg(reg, hi, lo)`: index, then two data bytes | confirmed |
| `0xd2db4` | `lcd_update_rect(rect*)`: sets R11 (RAM address) and writes R12 (RAM data) from the framebuffer | confirmed |
| `0x3835a0` | Framebuffer in `.bss`, 2 bpp, 40 bytes per row | confirmed |
| `0x1397d4` | LCD power-on and init: R00=1, R03 power, R01 driver output, R02, R04 contrast, then R04–R11 mostly 0 (R08=`0x0004`, R0D=`0xff00`), contrast again, and finally R07=`0x0009` (display on) | confirmed |
| `0x139b28` | `lcd_set_contrast(level)`: stores the level in the LCD state at `0x420a3c+0x14`, then writes R04 = panel base + level × panel scale / 127 | confirmed |
| `0x139a80` | Sets a mode flag (state `+0x10`), calls `0x1193dc`, and rewrites R04 with a different panel base (`+8` or `+9`) | confirmed (what it is for: guess, probably backlight compensation) |
| `0x1193dc` → `0x139aec` | Toggles bit 1 of `LCD1_CONTROL` and writes R07 = `0x9` or `0xB` | confirmed |
| `0xd90c4` | Only caller of `lcd_set_contrast`, probably the Contrast settings screen | likely |

Panel descriptors are a table of 11-byte entries at the literal near `0x139a78`,
picked by a panel ID at boot (`0x1397d4`). Byte `+6` is the R03 power value,
`+8` and `+9` are the contrast bases, and `+10` is the contrast scale.

Two ways in for dark mode:

1. **Panel-side invert (try first).** If the controller has a reverse bit in R07,
   one write after init does it. The OS only ever writes 9 or 0xB there, so the
   other bits are untested. Try them on a device before relying on this.
2. **Invert on the way out.** `0xd2db4` reads framebuffer bytes at `0xd2e48` and
   `0xd2e4c` and hands them to `lcd_data`. Flipping them (`eor rX, rX, #0xff`) inverts
   everything drawn. The loop has no spare instruction slot, so this needs a
   trampoline to resident patch code (see free RAM below). The other option is to
   patch `lcd_data` (`0xa2c1c`) itself, which only `0xd2db4` calls.

Inverted contrast may also need a new R04 base.

## Free RAM (for any resident patch code)

PP5002 memory: 32 MiB DRAM (runtime address 0) and 96 KiB IRAM at `0x40000000`.

Scatter-load table (`0x24320`, **confirmed**):

| Region | Range | Size | Source |
| --- | --- | --- | --- |
| IRAM vectors | `0x40000000–0x40000058` | 0x58 | copied from `0x31f260` |
| IRAM code | `0x40000058–0x400013c4` | 0x136c | copied from `0x31f2b8` |
| IRAM zero | `0x400013c4–0x40001aa0` | 0x6dc | zeroed |
| IRAM data | `0x4001764c–0x40017700`, `0x400179e0–0x40017b08` | small | copied |
| IRAM zero | `0x40017700–0x40017798` | 0x98 | zeroed |
| DRAM `.data` | `0x36fc00–0x37b048` | 0xb448 | copied from `0x313da0` |
| DRAM `.bss` | `0x37b048–0x449dc8` | 0xced80 | zeroed |
| DRAM uncached `.bss` | `0x449e00–0x53c304` (through `0x0444xxxx`) | 0xf2504 | zeroed |
| Small pools | `0x53c310–0x53e010` | 0x1d00 | `0xde7b4`, 12 sizes from `0x14d50c` |
| Heap / music cache | `0x53e010` to the end of DRAM (`0x2000000`) | about 26.7 MiB | `0x91e90` |
| **Frogger** (patched) | `0x1f00000–0x2000000`, taken from the heap | 1 MiB | `loader/patches.c` |

How the end of DRAM reaches the heap (**confirmed** in emupod and from the code):

- It isn't probed. Boot (`0x2a4–0x2bc`) passes the memory config `0x7000` to `0x126edc`, which
  builds a memory object in IRAM at `0x40006000`. `0x59024` turns the config's four nibbles
  into bank sizes (table `0x14d53c`: 0, 512K, 1M, … 128M): only bank 3 is set, index 7, 32 MiB.
  `[mem+0x20]` is their sum, `0x2000000`. On wake (`0x1f2f4`) it reads the same config back
  from `0xc8004020`, where boot stored it.
- `0x33500` is not a DRAM probe, despite the earlier note: `0x18bf8` is unsigned divide, and
  the loop halves 64 MiB while `size / 0x346364 > 1`, so `[mem+0x14]` is always `0x400000`, a
  cache region size. It sets `[mem+0x24]`, the end of what's used, to `0x360000 + 0x1dc304 =
  0x53c304`, rounded up to `0x53c310`; `0xde7b4` then takes the small pools and moves it to
  `0x53e010`.
- `[mem+0x20]` also programs the memory controller and cache regions (`0xa92d8`, `0xa7a24`,
  `0xf000f000`), so it has to stay 32 MiB.
- `0x133618` copies the object to `0x449ec4` (uncached `.bss`). `0x91e90` hands out the heap
  from that copy: start `[+0x28]`, length `([+0x20] - [+0x24]) & 0x3ffffff`, end start + length.
  Its one caller `0xde338` stores them at `0x37b388` (start, length, end, 0) and builds the
  heap (`0x97df4`). Stock: `0x53e010 + 0x1ac1ff0 = 0x2000000`.

**Frogger's patch**: the mask at `0x91eac` (`bic ip, ip, #0xfc000000`, a no-op for these
values) becomes `sub ip, ip, #0x100000`, so the heap ends at `0x1f00000` and the top 1 MiB
is Frogger's: the payload's code and `.bss` (`payload/payload.lds`). The loader checks the
`0x7000` config words at `0x2a8`/`0x2ac` before patching. The music cache, the heap's main
user, gives up 1 MiB of about 26.7 (`tools/emupod/heaptop.py` plays songs and checks the heap
end and that the top 1 MiB is left alone). The payload is reachable from every hook (a BL
reaches ±32 MiB). The loader itself now links at `0x29e00000` (DRAM `0x1e00000`, inside the
heap, only used before osos starts) so it doesn't overwrite itself while installing the
payload.

What this means:

- **The top of DRAM is not free after boot**, except the 1 MiB Frogger takes from the heap.
  The loader's link address (`0x29e00000`) is only safe while the loader runs.
- **IRAM is full.** `0x40001aa0–0x4001764c` has no static owner, but over 400
  literals point into it (CPU stack `0x40003ffc`, COP stack `0x40005ffc`, and
  likely decoder buffers). Treat it as used.
- **`0x346368–0x360000`, about 103 KiB**, between the end of the image and the next static
  region, is where the payload used to live (`0x34c000–0x360000`, 80 KiB, until it ran out).
  Apple's boot loads the loader's appended copy (which carries the payload's code) at its
  start, and the debug record sits at its top, `0x358000–0x360000` (`payload/debug.h`; `0x35f800`, 2 KiB, until it held a whole session;
  `0x34b800` until the payload moved): nothing loads or clears it across a reset. So the
  loader can grow to 72 KiB. `0x33500` only uses `0x346364` as a divisor and
  `0x360000` as a base constant; `0x24664`'s table copies 0 bytes to `0x360000`.
- After boot, the copy sources (`0x313da0–0x346368`) are dead too, unless sleep or
  resume runs the scatter loader again. Not checked yet.

## Second core (COP)

**confirmed**:

- `is_cpu()` is at `0x12d75c` (`PROCESSOR_ID == 0x55555555`) and `is_cop()` at
  `0x12d73c` (`0xaaaaaaaa`).
- `0x1306a4` puts the calling core to sleep by writing `0xca` to its own control
  register (`CPU_CTL` at `0xcf004054`, `COP_CTL` at `0xcf004058`).
- The CPU wakes the COP once, at `0x364`, by calling `0x1f310` (`COP_CTL = 0xce`).
  `0x1f328` writes `0xca` (sleep), but nothing calls it directly.
- The COP then runs `0x1f2c0`. That sets its interrupt masks (`0xc8004004/8`), does
  common init (`0x126edc`, `0x1248d4`), and jumps through `0x13e48c` to `0x46f18`
  with `r0 = 0x44a7280`.

**likely**: `0x46f18` is the COP's long-running loop over a large state object at
`0x44a7280` (fields up to `+0xcab0`, dispatched through a vtable). It is probably
audio decode or output. The code at `0x31f2b8–0x344328` only calls itself and
touches IRAM and `0xc000xxxx` audio-looking registers. That fits DSP or decoder code,
but only its first `0x136c` bytes are placed by the scatter loader (at
`0x40000058`). Where the rest runs from is **unknown**, so map that region in
Ghidra only after finding its loader.

For patches: the COP owns that loop, so keep UI patches on the CPU side. Nothing
here needs the COP.

## iTunesDB: where Artists/Albums/Songs come from (for M2)

Load path (**confirmed**):

| Address | What |
| --- | --- |
| `0xe4064` | Database load: builds the `iPod_Control/iTunes/iTunesDB` path, calls the parser, then post-processes. Called from `0x99530` and `0xe44a0` |
| `0xc54bc` | Top-level parser: checks `mhbd`, then each `mhsd` |
| `0xc4a68` | Track list: `mhlt`, then one `mhit` per track with its `mhod` children |
| `0xc4244` | Playlists: `mhlp`, `mhyp`, `mhip`, `mhod` |
| `0x57504` | Reads the next N bytes of the file into a buffer |
| `0x376a4` | Skips N bytes |

Inside `0xc4a68`, for each `mhit` (**confirmed**):

- **`mhit+0x14` must be 1, otherwise the track is skipped entirely** (`0xc4b04`).
  That is the "visible" flag of the iTunesDB format. Checked in Unicorn too
  (`tools/emu/itunesdb.py`): a visible = 0 track gets no track record. A track with `visible = 0` never
  reaches any menu, so a host-side tool can hide tracks from Artists/Albums/Songs
  with no firmware patch at all. Try this first for M2.
- Track records are allocated by `0xac908`. The `mhod` type switch at `0xc4e64` saves each
  string to a field of the track record and interns it in a per-field string pool on
  the database object (`r7`):

  | `mhod` type | Field | Track offset | Pool | Post hook |
  | --- | --- | --- | --- | --- |
  | 1 | title | `+0x24` | `db+0xb0` | `0x4408c` |
  | 2 | location (path) | `+0x1b8` | n/a | none |
  | 3 | album | `+0x30` | `db+0x134` | `0x43dd8` |
  | 4 | artist | `+0x28` | `db+0xdc` | `0x43e30` |
  | 5 | genre | `+0x38` | `db+0x160` | `0x44038` |
  | 6 | file type | `+0x3c` | `db+0x18c` | none |
  | 7 | EQ setting | `+0x40` | `db+0x1b8` | lookup |
  | 8 | comment | `+0x44` | `db+0x1e4` | none |
  | 9 | category | `+0x48` | `db+0x210` | none |
  | 12 | composer | `+0x34` | `db+0xdc` (shares the artist pool) | none |

  The post hooks set sort flags in the track's byte `+0x11`.

Building the browse lists:

- `0xeb1e8` returns a track's string for a browse field ID (2 = title, 3 = album,
  4 = artist, 8 = genre, 18 = composer, 19 = the `+0x2c` field from pool `db+0x108`
  falling back to artist, probably album artist). It is the
  accessor the browse code uses to sort and group.
- `0xba390` is the per-track match callback that uses it. It is passed by address
  (literal at `0xa9894`) to `0xa982c`, which tests one track against a query.
- `0xf1ce8` walks every loaded track, calls `0xa982c` (`0xf2050`) and collects the
  matches. This is where an Artists, Albums or Songs list is filled. It is called from
  `0xb9e7c`. A firmware-side filter (for example "skip tracks whose genre or comment
  is X") fits best right after the `0xa982c` check at `0xf2054`, or at load time at
  `0xc4b04`.
- The menu titles ("Artists", "Albums", ...) are `Str ` resources in the UI
  resource bundle (next section).

### Playlist loader (`0xc4244`, **confirmed**)

Track loader (`0xc4a68`, **confirmed**): each mhit header (`0x9c` bytes) is read to
`sp+0x420`, `[sp+0x4bc]` is the track's index, and `0xac908` returns the new record in
`r4`, whose `+0x1c` gets `mhit+0x10` (the track id).

Per `mhyp` (header read to `sp+0xac`, `0x6c` bytes): `[sp+0xc0]` is `mhyp+0x14`,
the master-playlist flag, and `[sp+0x320]` the playlist's index in the `mhlp`.
`0x530d0` creates the playlist object at `[sp+0xa8]` (type 5 for the master, 4
otherwise). Then:

- `mhod`s first (header at `sp+0x6c`, type at `[sp+0x78]`). Type 1, the name, goes
  through `0xc62f8(reader, buf, 1, type, pl+0xac, pl+0xd8)`, which reads the raw
  string (UTF-16LE or UTF-8) into the loader's own buffer (`r6`) before converting
  it. So after it returns, `r6[0]` is the name's first byte.
- `mhip`s next (`0x4c` bytes at `sp+0x20`). `0x70138(db, mhip+0x18)` finds the track
  record (`r7`), the same record the browse loop sees at `item+0x20`. `0x363cc` adds
  the item.
- Track records start with a pointer to the library object (`0xac908` stores it).

### Browse list builder (`0xf1ce8`, **confirmed** from the code, **not** what builds Music › Songs/Artists)

The item loop at `0xf2018` walks `r7`, a list of playlist items (`[r7]` count,
`[r7+0xc+4i]` items) of the source playlist. An item's word 0 is its playlist
(the `0xba390` predicate reads the playlist name at `item[0]+0xac`) and `+0x20` its
track (`r8`). The loop writes 1 to `track+0x1c` for an item it keeps and 0 for one
it drops (`0xf2120`); `0xf211c` is the drop path. It also already knows how to drop
unchecked tracks (`track+0x10` bit 2, from `mhit+0x78`, when the query's byte `+3`
is set), but the playback code reads that bit too (`0xba53c`), so Frogger doesn't
reuse it.

Hidden-songs hooks (`payload/`, `tools/mkpayload.py`). The flag is `"HIDE"` at
`mhit+0x98`: the track loader reads the whole `0x9c`-byte header but never uses the
words at `0x70`–`0x77`, `0x7c`–`0x87`, `0x8c`–`0x8f` or `0x94`–`0x9b`, and a 4-byte
magic can't be set by accident.

| Site | Replaced | Does |
| --- | --- | --- |
| `0xc4b30` | `ldr r0, [sp, #1072]` | Each new track record (`r4`): remember it if its mhit has the flag; the first track clears the set |
| `0xc431c` | `mov r7, #1` | New playlist: note whether it's the master |
| `0xc4768` | `ldrb r1, [sp, #48]` | Master playlist: remember its object (`[sp+0xa8]`) |
| `0xc4e64` | `ldr r0, [sp, #1044]` | Each mhod's type: album artist (22) read as the artist, and the artist mhod after it skipped (`artist.c`) |
| `0xf205c` | `ldr r0, [sp, #88]` | Browse: drop a flagged track when the item's playlist is the master or the library |

#### On a device: nothing gets hidden

Tested on a 3G with 15 flagged tracks: they all still show in Music › Artists and
Music › Songs. The hooks that run while the database loads work. The browse loop
is the problem: it doesn't build those lists.

- **The loader runs and its patches stick** (**confirmed** on the device). A test
  build that also patches the three ASCII "Settings" strings (`0x1917ce`,
  `0x191914`, `0x191c80`) to "Frogger!" shows "Frogger!" in the menus (and "Reset
  All Frogger!": `0x1917ce` is the tail of that string, so the mark patch now
  skips it), so writes
  through `0x28000000 + A` before the remap reach the running OS. So the cache isn't
  losing them, and the button check isn't the problem either: a build that skips the
  Menu/Hold check (`FROGGER_IGNORE_BUTTONS` in `loader/main.c`) hid nothing as well.
- **The load-time hooks are right** (**confirmed** in emupod, real 2.3 boot, next
  section). With track 101 of 2 flagged, `0xc4a68` runs at 3.22 s, `track_hook` fires
  for both records (`0x1d4d468`, `0x1d4d638`) and `hide_mark` gets `0x1d4d468`.
  `mhyp_hook`/`mhip_hook` record the master playlist (`0x1d4b32c`). The playlist
  loader then calls `0x70138(db, 0x65/0x66)` and `0x363cc(master, record, …)` with
  those same two records, so `item+0x20` is the record `hide_mark` saw.
- **Every item the loop walks passes `0xf205c`** (**confirmed** from the code): with
  a query (`[sp+0x54]` ≠ 0) `0xa982c` either drops the item or falls through to
  `0xf205c`; without one, `0xf2044` branches straight there. No path skips the hook.
- **Removing the owner check changes nothing** (**confirmed** on the device). A
  build whose `hide_entry` hides in every list (`FROGGER_HIDE_EVERYWHERE` in
  `payload/hide.c`) still shows the flagged tracks in Songs and Artists. If those
  lists came from this loop, they would have vanished.

So Music › Songs and Artists are built by other code. **Found in emupod** (counting
every function entry while each Music list opens, `tools/emupod/probes/lists.py`):

- The library object keeps one lazily built index per list: `+0x884` Artists
  (`0x7c1a8`), `+0x894` Albums (`0x7c178`), `+0x898`/`+0x89c` Songs and its count
  (`0x7c460`); Genres `0x7c3a0`, Composers `0x7c368`. Artists and Albums go through the
  shared category builder `0x53278`.
- Every one of them walks the **master playlist** (`0x78d60(master, …, i)`) and keeps an
  item only when **`0x58440(library, item)`** returns non-zero. That predicate caches
  its verdict in `item+0x1c` (0 unchecked, 1 keep, 2 drop). `item[0]` is the playlist
  (the master), and `item+0x20` the track record `hide_mark` saw. Its callers:
  `0x7c460` Songs, `0x53278` categories, `0x7c1d8`, `0x51250` (Shuffle Songs),
  `0x4fb50`, `0xc0b30`. Playlists never call it.
- **`browse_hook` at `0x58444`** (right after its `push {r4-r9, lr}`) returns 0 for an
  item that `hide_entry(item[0], item[0x20])` says to hide. **Confirmed in emupod** with
  Tone A flagged and alone on "Hidden Artist"/"Hidden Album": Artists, Albums and
  Genres › Test drop it, and an artist or album with only hidden songs vanishes too.
  Songs (`0x7c460`, returns to `0x7c4fc`) and Shuffle Songs (`0x512e8`) keep it on purpose:
  the hook checks `0x58440`'s return address. So does the add from a row (`0xc0b30(lib, row)`
  → `0x4fb50`, returns to `0x4fbb0`): it walks the current browse list (`[lib+0x870][lib+0x40]`,
  order `0x849a4(lib)`) and takes the row-th item `0x58440` keeps, the same walk `0x7c460`
  makes to cache the rows a list shows (`lib+0x898`, count `lib+0x89c`). Filtered there, every
  hidden song above the held row moved it one row down (hold menu, Songs; stock's hold-to-add
  had the same shift). `tools/emupod/holdrow.py` checks it. "All" (row −1) counts with
  `0xc0c14` and adds through `0x51250`, so it still adds hidden songs.
  The "Mix" playlist still lists it. Stock 2.3 on the same card shows everything.
- Not checked: playback. Starting a song hangs emupod (interrupts stop once audio
  starts), so playing a hidden song from a playlist still needs a device test. No
  playback path goes through `0x58440` when playing from a playlist, though.

`0xf1ce8` (and so `filter_hook`) didn't run in any of these lists; what it builds is still open.

The test builds behind those switches live outside the normal build, for example
`build/test-everywhere/` (payload with `-DFROGGER_HIDE_EVERYWHERE`, `mkpayload.py
--build build/test-everywhere`, loader with `-DFROGGER_IGNORE_BUTTONS
-DFROGGER_MARK`, which is now always on: `FROGGER_NO_MARK` turns it off). None of them has a Menu-at-boot fallback. Restore a saved
partition from disk mode if one misbehaves.

### Album artists (**confirmed** in emupod)

- 2.3 has no album artist. The mhod switch at `0xc4e64` (type in `[sp+0x414]`, record in
  `r4`) handles types 0–12; anything else, album artist (22) among them, goes to the default
  at `0xc50f4`, which skips the mhod.
- `+0x2c` (pool `db+0x108`) is the **sort artist**, not an album artist: the artist post hook
  `0x43e30` derives it from `+0x28` through `0x449d0` (the settings object). The Artists key
  function `0x83e6c` (the category builder `0x53278`, category 4, from `0x7c1a8`) sorts by it
  when it's set and `[[db]+8]+0xb13` is non-zero (set to 1 at `0xc3b98`, on in emupod), and by
  `+0x28` otherwise. The browse accessor `0xeb1e8`'s field 19 is the same slot.
- **Frogger's `mhod_hook`** (`payload/artist.c`) rewrites the type before the switch: 22 becomes 4,
  so the album artist is read as the artist (with its sort name), and a later type 4 for the
  same record becomes 0 (skipped). Order in the mhit doesn't matter: the artist case keeps the
  string it reads last. Every list that groups by artist follows (Artists, an artist's albums,
  Genres). On a card with Tone A (artist Peshay) and Tone B (Doc Scott), both with album artist
  LTJ Bukem, stock 2.3 lists Doc Scott and Peshay; Frogger lists LTJ Bukem › Blue Notes › both.
- **Open:** Now Playing shows the album artist too (it reads the same `+0x28`). Keeping the
  track's own artist there needs it stored elsewhere and a hook where Now Playing reads it.

### Key input (GPIO events, **confirmed** from the code and emupod)

- `0x80944(n)` returns the event object for GPIO port n (A–D at `0x420af8`,
  `0x420b44`, `0x420b90`, `0x420bdc`, `0x4c` bytes each). On first use it calls
  `0xfdbf0(obj, n)` for all four, sets `[0x420adc] = 1` and enables the GPIO
  interrupt (`0xcf001024 = 0x4000`). An object holds an event code per pin for each
  level (`+0x00` and `+0x20`), then pointers to the port's level (`0xcf000060`),
  interrupt status (`0xcf000040`) and acknowledge (`0xcf000070`) registers.
- `0xe1450(pin, code)` registers a pin's code (`pin` is a byte pair: port, mask);
  `0xe1494` clears it. After boot port A holds `0x76, 0x77, 0x74, 0x75, 0x73,
  0x78, 0x71, 0x71` for bits 0–7 at both levels, port C `0x6d, 0x6c` (bits 3, 4) and
  `0x70` (bit 7), plus `0x80` for bit 5 at the other level.
- The GPIO ISR `0x124cd8` (from the dispatcher `0x1282ac`) calls `0x8a1f0` on all
  four objects. For each pin with its status bit set, `0x8a1f0` takes the code for
  the current level, posts it with `0x2fec`, flips the level bit and acknowledges.
  `0x2fec` appends the code to the scheduler's pending list (base in the literal
  at `0x285c`, end pointer at `+0x18`) unless it's there already.
- `0x2fec(n)` signals scheduler event `n`; it is not a key queue. The scheduler (`0x84c`)
  looks up `[0x41e4b8 + 4n]`: -1 or 0 means nobody waits, otherwise it's the index of
  the thread to wake (thread table `0x37f3c4`, 56 bytes each, entry function at `+0xc`).
  `0x39d0(n)` waits for event `n`, and `0x41bc(n, timeout)` waits with a timeout (returns 5 on timeout).
- Each button has its own thread that calls `0x58e38(button, keycode, event)`:

  | GPIOA bit | Button | Event | Thread entry | Button id | Code passed to `0xbbab8` |
  | --- | --- | --- | --- | --- | --- |
  | 0 | Right / next | `0x76` | `0x13c454` | 1 | `0x5a` |
  | 1 | Select | `0x77` | `0x13b93c` | 3 | `0x6f` |
  | 2 | Play/pause | `0x74` | `0x13c7d8` | 4 | `0x10` |
  | 3 | Left / previous | `0x75` | `0x13cd88` | 2 | `0x59` |
  | 4 | Menu | `0x73` | `0x13c434` | 0 | `0x6e` |

  The buttons are active low, the same bits as `loader/pp5002.h`. The thread waits for its
  event, reads the pin (`0x9eec0`, raw `GPIOx_INPUT_VAL & mask`), debounces 20 ms and calls
  the object's vtable `+8` (`0x8d4c8`), which calls `0xbe110(button id, pressed)`. That maps
  the id to a code through the RAM table `0x36fc55` and passes it to `0xbbab8`.
- **Hold** (**confirmed** in emupod): `0xbe110` first calls `0x7a9b8` → `0x91e54`, which
  compares the Hold pin object (`[0x420c30]`, GPIOA bit 5, event `0x78`) with its fixed
  level `+0x10 = 1`. **When bit 5 reads high, stock 2.3 counts Hold as on and drops every
  key.** `loader/main.c` assumes the opposite (bit 5 low = Hold on); see the open question below.
- **Wheel** (**confirmed** in emupod): GPIOA bits 7 (high) and 6 (low) are a quadrature pair,
  and both post event `0x71` to thread 10 (`0x13c480` → loop `0xbd198`). Each edge runs
  `0x90c94`, which adds `table[prev<<2 | cur]` (`0x37000c`: +1/-1) to a counter at
  `obj+0x14` (wheel object `0x385a58`), logs the edge time from `0xcf001110` and wakes the UI
  through `0xc04d8`. Walking the states 0→1→3→2 counts down and scrolls **up**; the reverse
  scrolls down. One menu item takes 4 to 6 steps, and the first item a few more.
- **Hold Menu** (**confirmed** in emupod): a held key posts `'kHld'` (key handler `0xa2a64`,
  from the table at `0x14f7e0`: `'kDwn'`, `'kAut'` repeat, `'kP&H'`, `'kUp '`) for the keys fn 2
  registers with `0x08de.68` (Menu, Next, Previous, Play). Fns 77 and 148 bind holding Menu
  (`0x08de.6a(2, 0x6e, fn 243)`); fn 243 is `0x08ea.cb(event)`, the native `0xbe8a8(app+0x11c,
  app, event)` (`app` = `[lib]+0xbc4` in emupod). Its state machine `0x8abe0` maps
  `'kHld'` + Menu to event 4, flips `app+0x11c+3` and calls `0xd86b4(app, on)` → `0x139a80`, the
  backlight. The main menu's Backlight item reaches the same toggle through `0xbe828(…, 7)`.
  Frogger opens quick settings at fn 243 instead (`docs/tcmd.md`, "The hold menu"). Letting go
  of the hold clicks Menu, which a popup takes as back.
- So in emupod, with bit 5 **low**, Select, Menu, Play and the wheel all drive the 2.3 UI:
  Language → main menu → Music → Songs → play a track. The driver is
  `tools/emupod/ipod3g.py`.

## UI resources: menus, strings, bytecode (for M2's "All Artists")

**confirmed**: the UI lives in a resource bundle at `0x181d20` (`tools/re/resources.py`).
Header: version 3, data offset `0x313c`, 7 types, each with a fourcc (stored
byte-reversed), a count and an index of `{id, offset, size}`:

| Type | Count | What |
| --- | --- | --- |
| `BMap` | 94 | Bitmaps |
| `LDTm` | 1 | Date and time formats |
| `Menu` | 24 | Menus: a count, then 40-byte items |
| `Str ` | 529 | Strings, for example `0x25bc` "Artists", `0x3311` "All Artists" |
| `TCmd` | 1 | 43 KB of UI bytecode at `0x191dcc` |
| `Type` | 88 | Small 16-byte records |
| `View` | 303 | Screens |

`Menu 0x2512` (`0x18dd70`) is the main menu with every item it can show (Music,
Playlists, Artists, ..., Clock, Now Playing). A menu item is ten words; word 3 is
an offset into the `TCmd` bytecode that runs when the item is picked (Artists:
`0x1e02`), and word 8 the label's string id. So a new "All Artists" entry means a
new item whose bytecode builds the Artists list with the hidden-songs filter off.
The bytecode, the VM and how a Settings item is wired are in **`docs/tcmd.md`**
(disassembler: `tools/re/tcmd.py`). Word 3 of an item is *not* a code offset; word 6 is
`0x2000 |` the id of the item's bytecode function.


## On-The-Go and the play queue (**confirmed** in emupod)

Found with function-entry counts and VM traces while holding Select, playing, pressing Next and
clearing (`tools/emupod/probes/otgqueue.py` runs Frogger's version of each). Objects, as `lib` = the
library (`[[0x43580c]+0x1c]`, the way `0x6a15c` reaches it; `0x43580c` holds the menu object
the bytecode calls `0x08df`):

| Where | What |
| --- | --- |
| `[lib]` | root object; `+4` the player, `+0x20` a byte the shuffle setup reads |
| `lib+0x44` | the list Now Playing plays from |
| `lib+0x48` | the On-The-Go playlist (a normal playlist object, 1000 songs at most) |
| `lib+0x40`, `lib+0x870` | the browse list on screen: `[lib+0x870][lib+0x40]` |
| `player+0x2a4`, `+0x2a8` | the list playing and its current item (0 when stopped) |
| list `+0x24` → `+0x2c` | the song count |
| item | `+0` its list, `+4`/`+8` previous/next item, `+0x10` its key, `+0x20` the track record |

- **Add** (hold Select): bytecode fn 211 (Songs) or fn 191 (Playlists) sends `0x08eb.e9(row)`,
  the native method `0xc0ce8`, which calls **`0xc0b30(lib, row)`** (`0x08df.ae(row)` after it is
  the row flash; `docs/tcmd.md`, "The hold menu"). That appends the row's songs
  to On-The-Go (`0x4fb50` for one, `0x51250` for all) and leaves through `0xc0c68` with `r9` =
  the count before. Then `0xf0800` refreshes the menus.
- **Play from a list**: `0xb6c38(lib, row)` copies a library list into a new playlist
  (`0x51250`) but plays On-The-Go itself, then `0xb8eb4(player, item)` (load) and
  **`0xb8548(player, item, 1)`** (start). `0x78d60(list, 1, 0, i)` is item `i`.
- **Next item**: **`0xb7b00(player, list, key, flags)`** returns the playable item after the one
  with `key` (`0xb7cb8` is the previous). Every caller asks about the current item: the Next
  button (`0xaca28` → `0xb81d4`), the end of a song (player loop `0x94918` → `0xb7840` →
  `0xb81d4`), the next-song preload (`0x949bc`) and the UI (`0xf18c8`).
- **Clear** (Clear Playlist › Confirm): the menu object's method **`0x465fc(ui)`**, next to
  `0xc0ce8` in the method table at `0x1bdbac`. It stops playback if On-The-Go is playing
  (the playlist can't drop an item the player holds), then `0x465b0(lib)` sends the
  playlist `'pldm'` (`[pl+0xe8](pl, 'pldm', 0, [pl+0xec])`, `0xb9e7c`), removes the items
  (`0xba31c`), marks the prefs for saving and refreshes.
- **Hold on a Playlists row**: fn 191 reads the row into local0 (`0x08df.a9()`; ints are tagged
  `n << 1 | 1`, locals at `[[vm+0x10]+0x24]`) and skips row 0, On-The-Go, so stock does nothing
  there. Frogger's `queue_vm` acts at that guard (bytecode pc `0x195ced`).

- **Temporary playlists**: `0xac2ec(lib, &list)` makes one (class `'file'`, flag `0x40` at
  `+0xe4`: never listed under Playlists); `0xb6c38` copies the list it plays into one
  (`0x51250(lib, source, …, dest)`) and keeps it at `lib+0x44`. `0x5e8cc(lib)` deletes that one
  (unless it's On-The-Go) whenever something else starts playing (`0xb6af8`, `0xb6c38`,
  `0xb7174`, `0xb7310`, `0xb7468`, `0x462cc`). The add (`0xc0b30`) and the clear (`0x465b0`)
  read `lib+0x48` as they go, so they work on whatever playlist is there.

Frogger's queue is such a temporary playlist of its own: "Add to Queue" (`payload/holdmenu.c`)
puts it at `lib+0x48` while stock's add runs, and `keep_hook` at `0x5e8cc` keeps it from being
deleted. Frogger's hooks (`payload/queue.c`): `queue_add_hook` at `0xc0c68` (start the queue at the new
songs, or arm the queue), `queue_next_hook` at `0xb7b00`'s first instruction (answer with the
queued item while armed, and with the item after the one it cut in after when the queue runs
out), and `vm_hook` for the Playlists hold. `lib+0x44` must name the list the player plays
from: Now Playing's open handler (fn 185) otherwise goes back, so Select on the playing song in
Songs, while the queue played after cutting in, landed on the main menu. `queue_next` moves
`lib+0x44` to the queue once Apple asks about the queue's item, and back to the list it left
when playback returns there; if something else starts first, `queue_keep` gives `0x5e8cc` that
list to delete instead (`tools/emupod/holdrow.py`, its last step). Not checked: the end of a song in emupod (its audio
stops early, so songs never end; Next takes the same `0xb81d4` path), shuffle and Repeat with
a queue, and a device test.

### Up Next: seeing and changing the queue (**confirmed** in emupod)

`tools/emupod/upnext.py` (hmcard.py's card; every step also checks Apple's image).

- **A list of our own items.** The songs array's builder `0x7c460(lib)` returns at once when
  `lib+0x898` is already set (it only builds from `[lib+0x870][lib+0x40]` when there's no array),
  and `.f9` (`0xf2518`) shows whatever it returns once the cached count `ui+0x12f8` differs. So an
  array allocated as `0x7c460` does (`0xaa10c(size)`; `0x9d7c4` / `0xd6760` free it with
  `0xa9f70` when the browse state goes back) holding items of any playlist (`0x78d60(list, 1, 0,
  i)`, between `0xa5054`/`0xef76c`) is a songs list: rows show those songs' titles. Songs' own
  reset `.de` (`0xd6478`: caches -1, `ui+0x1618` -1 so `.ee` doesn't call it On-The-Go, browse the
  library) and `.f4(4)` first, then fn 208, which opens the songs screen (fn 209: Select fn 210, hold
  fn 211). `.f9` again with the cache invalidated redoes the list in place, but puts its cursor on
  row 0.
- **Select** there is fn 210: `.a9()` into local0 (offset `0x39e6`, read at `0x39ea`), then `.e7(row)`
  (`0xd6ab8` → `0xb6c38`, which would play `[lib+0x870][lib+0x40]`, the library), then fn 153 (Now
  Playing). Frogger answers at `0x39ea` and goes back instead.
- **Starting a queued song while another list plays**: `queue.c`'s `play_from` steps (`0xb8eb4`,
  `0xda9a4`, `0xce9b0`, `0xb8548`) over a playing list wrote `2` into Apple's image at `0xc4`
  (emupod; a data abort on a device). Apple's Next, **`0xb81d4(player, 0)`** (the button's
  `0xaca28` with `[[ui+0x1c]]+4`), asks `0xb7b00` first, so Frogger calls that and has
  `queue_next` answer with the song picked; nothing is written then.
- **`0xb7b00` finds the item by key** (`0x6ff40(list, key)`, item `+0x10`), not by the player's
  state, so asking it again with the key of its own answer walks on through a list: that's how
  `queue_next` skips songs taken out.
- **No single-song remove in 2.3**: On-The-Go only clears (`0xba31c` removes everything). Frogger
  keeps the queue's songs and marks the removed ones (`q.removed`), which Up Next leaves out and
  `queue_next` skips; `queue_next_hook` returns 0 from `0xb7b00` for `QUEUE_NO_NEXT`.
- **Popup row labels** can be changed from C after fn 24's labels: `0x1fabc([0x41e938], element,
  string, 0x80)` on the row's element (`0x25d4`, `0x25d5`); the next open's `.60` sets the stock
  id again, so the text is fetched each time (it's only refetched when the id changes).
- **More room for bytecode**: Menu `0x25ba`'s stock data (`0x54` bytes at `0x18e48c`) is unused
  once the loader repoints its entry, and it ends where the Settings Menu (`0x18e4e0`) starts, so
  `HM_SNIPPET` now starts there (`0x288` bytes in all).

Not checked: Up Next while shuffle or Repeat is on, a song ending by itself into a removed one
(emupod's audio stops early; Next takes the same `0xb7b00` path), and a device test. Prev
(`0xb7cb8`, not hooked) can still step back onto a removed song.

### The main menu's Queue row (**confirmed** in emupod)

`tools/emupod/queuerow.py` (every step also checks Apple's image).

- **The main menu** is `Menu 0x2512` (index entry `0x182210`), every row it can show. fn 36 opens
  it (also on Menu back to it) and calls **fn 33**, which, only while the main menu is the screen
  up (**likely** what `0x08de.77() == fn 36` asks), runs fn 32 on each row's element: `0x08f8.141(element)` (its Main
  Menu setting) into fn 31 → fn 30, `0x08df.a0(0x2512, element, 3, nil|true)`. An element is the
  row's label id (word 8).
- **A row of our own**: the loader points the entry at `hm_main`, Apple's 22 items with a clone of
  Settings' (word 1 `0x22`, a plain row with the `>` arrow) after Music, word 3 `0x1ae2` (fn 28)
  and label/element `0x3f1b` ("Queue"). Frogger shows or hides it at fn 33's last drop (`0x974`,
  past the guard), with `.a0` in fn 110's frame (fn 33's stack is 3), as the popup does. It is
  hidden before the screen is drawn: no flash at boot or on Menu back (`queuerow.py`'s pixel checks).
- **Its function** has to be one that runs our bytecode and nothing else in that spot: fn 28 only
  runs as the popup's Cancel (row 0 of Menu `0x25ba`; fn 541 calls it, **likely** only with a popup up), so inside
  fn 50 with no popup up it is ours. It opens the Queue list as Now Playing's popup does, minus the
  back: the screen slide that follows is depth 1, so `upnext_up()`, Select on a song (back to the
  main menu, playing it) and the hold (Remove, Clear; Clear goes back twice) all work the same.
- Leaving the main menu for Music doesn't keep the songs array (the save from the main menu holds
  none); Music > Songs builds it again.

Not checked: the row showing or going while the main menu is up (fn 185 also runs fn 33, **likely**
on a change of what plays), and a device test.

## Playlists made on the iPod (**confirmed** in emupod)

`tools/emupod/probes/savetrace.py` and `playlists.py` (both write back into a card copy and then boot it
again).

- **Save Playlist** (`0x08eb.f3` → `0xd292c`) takes the highest N of the playlists (`+0x124`,
  `0x81128(lib, i)`), names On-The-Go's copy "New Playlist N+1" and writes it with
  `0xd2444(lib, …, N)`: `iPod_Control\iTunes\OTGPlaylistInfo_N` through `0xf4ad4(lib, path)`,
  which writes **the playlist at `lib+0x48`** (no path: plain `OTGPlaylistInfo`). The file is
  an `mhpo` header (`0x14` bytes; entry size 4; count) and a 4-byte track reference per song.
  On-The-Go itself goes to `OTGPlaylistInfo` when its flag `[lib]+0xb42` is set. At boot
  `0xc5a90` reads them all back. Synced playlists have `+0x124` = 0 and no file.
- **Paths** (out: `0x108` bytes): `0x53a24(out, 'itun', "iPod_Control\iTunes\", name)` to
  write, and it **creates the file** (an existing one is emptied); `0x7b3bc(out, name)` to read
  (`-0x2b`: no such file). Reading through the first one wipes the file.
- **Reading back**: `0xc5a90(dest, tracks, stamp, path)` appends a file's songs to `dest` if its
  header's `+0x10` is `stamp`; Apple passes `0x6fcfc([lib])` and `0x77600()`, the iTunesDB's
  file time (`0xa0380`, word `+8`), so a sync makes old files stale. `0xc35a0` is the boot
  loader of `OTGPlaylistInfo_N` (a new `'file'` playlist, `+0x124` = N, then `0xc5a90`).
- **References**: each 4-byte entry is a song's **index in the library in sort order `0x26`**:
  `0x78d60(list, order, 0, i)` is item `i` of a list in an order (1 is the playlist's own), and
  the loader passes the library's tracks and `0x26`. Order `0x26` is **the master playlist's
  order** (its `mhip`s), not title, artist, album, track id or the track list's order
  (`playlists.py order`/`order3`: songs whose title, artist, album and database orders all
  differ come out in the order the master playlist lists them; with the master playlist
  103, 101, 102, Mix [101, 102, 103] is written [1, 2, 0]). So a reader maps entry `i` to the
  `i`th track of the current iTunesDB's master playlist. The track list itself has to be in
  ascending track id: listing 102, 103, 101 loads only two songs (`order2`).
- **The playlists**: `[lib+0x870]`, count `+0x874`, `[0]` the library; Playlists' row `r` is
  `[r + 1]` (`0x08eb.e2(r)` → `0xd6760(lib, r + 1)`, which also points the browse list,
  `lib+0x40`, at it), and `0x08eb.ee(r)` (`0x9f6e8`) says whether it's On-The-Go.
- **Copying**: `0x51250(lib, source, 0x849a4(lib), 0, dest)` appends a list's songs to a
  playlist (what `0xc0b30` and `0xb6c38` use).
- **Emptying**: `0x465b0(lib)` is `0xa97bc`, `0x5aea8` ('pldm', 0 = go on) and `0xba31c` on
  `lib+0x48`, then `0x9d7c4`/`0x9d7ec`, which reset **the list on screen** (`lib+0x898`,
  `+0x89c`): a list gone back to afterwards is empty. Frogger calls the first three itself.
- **Frogger's files for synced playlists**: `FroggerPlaylist_I` (I: the index in
  `lib+0x870`), written like Apple's and read back the first time Playlists opens
  (`playlist_load_saved`), into a list of its own first, so a missing or stale file changes
  nothing. Playlists' title is pool constant `0x85`, string `0xfff2`, asked for as `0xfffffff2`.
- **Playlists screen**: fn 188 (`0x758`) opens it (deferred fn 189: keys, screen `0x25d7`);
  Select is fn 190 (row, `.e2`, then fn 193 for On-The-Go or `0x76c` for a playlist), Menu
  fn 192, hold fn 191.

## The wheel and the lists (**confirmed** in emupod)

`tools/emupod/probes/wheeltrace.py` (60-song `letters-card.img`; a trace of three clicks) and
`letters.py`.

- **Scrolling is native.** The UI thread hands each wheel event to the list widget's
  `vtable+0x164`, `0x90fe4`: the step comes from `0x90d50` → `0x4295c`, an accelerator (it
  doubles a factor at `+0xc`, up to `+0x1c`, while events keep coming within its window, timed
  with `0x87de0`, a microsecond clock), and the list moves through `vtable+0x15c(n)` (down) or
  `+0x158(-n)` (up). Frogger's `letter_hook` sits at `0x9106c` (`cmp r4, #0`; `r4` the step,
  `r5` the widget). In emupod the step hardly grows, so Frogger times the moves itself.
- **The list widget**: `+0x90` its cursor (`vtable+0x11c` the current row, `+0x120` whether
  there is one), `+0x9c` the row count, `vtable+0x120(w, row)` selects a row; `0x816a8`
  (`0x08df.a9`) reads the row the same way.
- **Row text**: rows ask the UI object's getter `0x7998c(ui, fourcc, property, row, &out)`:
  `'Str '` gives the label in UTF-8 (in the UI object's buffer at `+0x1314`, converted from
  the database's UTF-16 by `0xdabe4`), `'BMap'` the icon. The property depends on the list:
  `0x335f` Songs, `0x3364` Artists. `label_hook` (`0x7998c`'s first instruction) notes it.
  Songs is also the library's browse list (`lib+0x898`, rows `+0x89c`); Artists isn't (0).
- **The title**: element `0x25e7`, whose text fn 52 sets through `0x08de.60` → `0x1fabc(obj,
  element, string, 0x80)` (`obj` is `0x08de`, `[0x41e938]`). It fetches the string again only
  when the id changes, so Frogger's letter alternates between two ids (`LETTER_STR`,
  `LETTER_STR2`); `title_hook` (`0x1fabc`'s first instruction) notes the screen's own title to
  put it back.
- **A tick on the UI thread**: the UI's dispatcher (`0x88ee4`) calls `0xe9664` about every
  quarter second, idle or not (on the UI thread's stack, `0x1ff4f..`; found by counting idle
  function entries on Songs). `tick_hook` there puts the title back 0.8 s after the last move.

## Browsing the Music lists (**confirmed** in emupod)

`tools/emupod/probes/hm2trace.py` (one run: Albums › an album, Artists › an artist › an album, back out,
Songs, Now Playing; bytecode, native methods and the browse state per step) and `holdmenu2.py`.

- **One query on the library.** `lib+0x40` the playlist browsed (0 the library; `0xd6760(lib, i)`
  sets it, frees every array below and clears the filters), filters `lib+0x58` genre, `+0x5c`
  artist, `+0x60` composer, `+0x64` album (`-1` = All; `0xd539c(lib, i)` and `0xd5150(lib, i)` set
  artist and album and copy the name for the title into `+0x268`, `+0x668`), `lib+0x86c` the
  level (`0xdce44`; 3 albums, 4 songs, 1 artists, 0 genres, 2 composers). Each level's rows are
  an array built from the query by `0x7c3a0` genres (`lib+0x878`), `0x7c1a8` artists (`+0x880`),
  `0x7c368` composers (`+0x888`), `0x7c178` albums (`+0x890`), `0x7c460` songs (`+0x898`, items),
  count in the next word, all through `0x58440` (so hidden songs drop out). Artists/albums hold
  string-pool keys, the same keys as the track record's `+0x28` artist (album artist,
  `artist.c`) and `+0x30` album. Row 0 of Artists and Albums is "All", so row = index + 1.
- **The UI object's side** (`ui` = `[0x43580c]`): `.dd` (`0xd6138`) resets the query, `.e3(row)`
  (`0xd5434`) artist, `.e5(row)` (`0xd51e8`) album, `.f4(level)`; `.f5/.f7/.f8/.f6/.f9` (`0xefdec`,
  `0xefd9c`, `0xf0fe8`, `0xf0670`, `0xf2518`) build a level and refresh its list widget, unless the
  count is the one cached at `ui+0x12f8…0x1308` (songs, albums, composers, artists, genres).
  `ui+0x1618…0x1624` are the rows picked, `ui+0x168c` a mode word. The method table is at
  `0x1bd808 + 4 * selector` (`.e9` = `0xc0ce8` at `0x1bdbac`).
- **Select** on Albums (fn 225): `.e5(row)`, title `0x3317`, fn 208 (`.f9`, defers fn 209, which
  opens the songs screen `0x25d8`); on Artists (fn 232): `.e3(row)`, title `0x3315`, fn 222
  (`.f7`, defers fn 224: albums screen `0x25d9`, `.f4(3)`). An album's songs sort by track at
  level 3 and by title at level 4 (Songs), so Go to Album sets `.f4(3)` first.
- **Menu** (fn 14 → `0x08de.7a` → `0xbaa48`) only reruns the previous screen's deferred opener
  (fn 224, fn 209, …), which builds nothing: the list shows whatever its array holds. And a
  View is one object, so an album's songs and Songs are the same widget. Going somewhere and
  back therefore needs the state put back (`browse.c`: save; on return `0xd6760`, the filters
  and names copied back, every array built again, each builder refreshing its widget with its
  cache invalidated, and the held list's cursor moved back with the wheel's own `vtable+0x15c`
  / `+0x158`).
- **Screens**: fn 20 opens one; its pc `0x5f5` (abs `0x192f3d`) is the slide forward, `0x5b5`
  (`0x192efd`) the slide back (both seen for every push and pop above), so Frogger counts screens
  there.
- **Track record**: `+0x24` title, `+0x28` artist, `+0x2c` album artist (falls back to artist),
  `+0x30` album, `+0x38` genre (pool keys); `+0x7c` track number (halfword, mhit `+0x2c`), `+0x7e`
  of how many; `+0x14` the database position + 2. **Not** the track id: `+0x1c` is 0 (the browse
  loop writes it), so `track_hook` hands `hide.c` the mhit's id (`mhit+0x10`) as it loads.
- **The popup's rows**: Menu `0x25ba` repointed (loader) to six items; `0x08df.a0(0x25ba, element,
  3, hidden)` hides one (`hidden` is `42`, the push the main menu's fn 30 uses; nil shows it), but
  it finds the list in the screen that's up, so it has to run after fn 26 has opened the popup
  (`0x1930bc`, fn 26's return), and the popup then sizes itself to the rows shown.
- **The VM's stack is per function** (TCmd header halfword 3, `tcmd.md`): a send with more
  arguments than the running function's frame allows silently stops the VM. A hold handler's
  (5) can't do `.a0`'s four arguments, fn 151's (3) not `.6a`'s three, so Frogger runs those in
  fn 110's frame (7; Extras' setup, which uses `.a0` itself): it calls fn 110 and `holdmenu_vm`
  sends its entry (`0x1947c0`) to the bytecode wanted.
- **A held row's songs, before the popup opens** (Show, `browse_row_hidden`): a song's row is
  `[lib+0x898][row]` (`+0x20` its track); an album's or artist's is index row - 1 of
  `lib+0x890`/`+0x880` (row 0 All), matched against each master item's track `+0x30`/`+0x28`.
  At the album level after an artist, `lib+0x5c` is that artist's index into `lib+0x880` (the array
  is still there). **Confirmed in emupod** (`unhide.py`): Show offered on a hidden song, an album
  and an artist with all songs hidden, Hide on Beta with one of two hidden. Songs, and an album's
  songs, list hidden songs even with Show Hidden off (only Artists/Albums/Genres/Composers drop
  them); with Show Hidden on, Artists and Albums list them too. The artist filter at the album level
  is not checked against a card with one album name under two artists.

### How songs start playing (for anything that hooks playback)

- **From a list** (Select, fn 210 → `.e7` → `0xd6ab8` → `0xb6c38(lib, row)`): copies the list
  into a temporary playlist (`0x51250`), deletes the previous one (`0x5e8cc`), keeps it at
  `lib+0x44`, then `0xb8eb4(player, item)` load, `0xda9a4(list, shuffle)`, `0xce9b0(list)`, the
  callback `[lib+0x3c](0, 0)` (`0x93c20`, which posts message `0x3300001d`/`0x3300001e`), and
  `0xb8548(player, item, 1)` start; `0xb916c` (`play_hook`) is where the track becomes the one
  playing. `player+0x2a4` the list, `+0x2a8` the item (`+0x20` its track record).
- **From the queue** (`queue.c` `play_from`): the same steps on Frogger's queue list. Items
  appended with `0x506ec(item, list, 0, 0)` (as `0x4fb50` does for one row, bracketed by
  `0xa5054`/`0xef76c` on `[lib+0x868]`) must each be followed by `queue_added`, one at a time:
  two appended before playback started left a garbage entry in the list's index array (`0x54240`),
  which `0xe1220` then wrote through (into Apple's image at `0x150`, in emupod). Fetch items with
  `0x78d60(list, 0x849a4(lib), 0, i)` (stock's add's order) inside that bracket.
- **Now Playing** binds Select to fn 169 through fn 151 (`0x19517c`) every time it's in its
  normal state; it binds no hold. Frogger's `HM_NP_BIND` replaces fn 151's body and also binds
  holding Select (`0x08de.6a(2, 0x6f, fn 191)`).

## Bookmarks (resume) (**confirmed** in emupod)

`tools/emupod/resume.py` (card: `mkresume.py`, a 25-minute "Long Mix"). 2.3 has no Podcasts and
no iTunesDB "remember position" flag (the track loader reads the mhit only up to `+0x99`; the
`+0xa6` flag of later iTunes isn't there). It bookmarks by **file name**:

- **The flag**: `0xb8ed8(player, item, flags)` loads every track that plays (list pick, Next,
  Prev, the end of a song, Up Next, `0xb8eb4`/`0xb8548`). It asks **`0xb7efc`** for the track's
  flags (`0x18`; `| 0xc0` for Audible, `0x9eba0` on the path; **`| 0x40` when the path ends in
  `.m4b`**) and stores them at **`[player+0x2380]`** (`0xb935c`). Bit `0x40` is "bookmarkable".
- **Leaving**: at the top of `0xb8ed8`, if the old track had `0x40`, its position
  **`[player+0x2164]`** (ms) goes into its record's **bookmark, `track+0x60`** (`0xb903c`),
  then `0xdcac4` and a `0xd7738` notice. Prev within 3 s of the start (`0xb75dc` → `0xb8cf8`)
  stores the start instead (`0xb8d4c`).
- **Starting**: with `0x40` the start position is `track+0x60` (`0xb9544`–`0xb9550`), else 0;
  `0xb8548` opens the decoder there. Stop keeps the position for `0x40` tracks (`0xb9cc4`).
- **Storage**: `track+0x60` is **mhit `+0x6c`** (track loader, `0xc4bcc`). `0xf4d6c(lib)` writes
  **`iPod_Control\iTunes\Play Counts`** (`mhdp`, header `0x60`, then 16 bytes per track in the
  track list's order: play count since sync, last played, **bookmark ms**, rating), only if
  `[lib]+0xb41` is set (`0xeb4b8`); the database load (`0xe4338`) reads it back at boot, if its
  count matches, over the mhit's values. `0xf4d6c` runs on sleep (`0x8db2c`, a message handler)
  and before the database is unloaded (`0xe4abc`, which first loads item 0, so the playing
  track's bookmark is saved); the sleep path doesn't save the playing track's position.
- So an MP3 named `.m4b` would get bookmarks with no patch at all, if the decoder goes by the
  iTunesDB's file type and not the name (not tried).

Frogger (`payload/resume.c`): `resume_flags_hook` (`0xb9354`) adds `0x40` for a track of 20
minutes or more (`track+0x54`, mhit `+0x28`); `resume_start_hook` (`0xb9550`) starts it 5 s
early; `resume_save_hook` (`0xb903c`) stores 0 for one left in its last 15 s (in emupod, a scrub
to the end ends the song and the bookmark is 0); `counts_hook` (`0xf4d6c`) saves the playing
track's position and sets `[lib]+0xb41` before Play Counts is written. Since every song that
plays loads through `0xb8ed8`, Up Next's songs resume too (`resume.py queue`). A pick that's left
again at once moves the bookmark 5 s back each time. Not seen in emupod: a scrub followed by
sleep never sleeps there (the player seems stuck after a seek), so `resume.py sleep` starts from
a bookmark instead; the end of a song played out (emupod's audio stops early).

**For Crate**: on sync, read Play Counts' bookmark (entry `+8`) and write it to that track's mhit
`+0x6c` (only for tracks of 20 minutes or more, or all: 2.3 ignores it for the rest), as iTunes
does for audiobooks. Otherwise a sync loses every position (a new iTunesDB with another track
count makes the old Play Counts stale).

## Skips (**confirmed** in emupod)

`tools/emupod/skips.py` (its own card: a 10 s "Short Tone", Tone A, Tone B long). 2.3 counts plays
(`0xb7840`, a song's end: `track+0x88`/`+0x8c` up, `0xa065c(track+0x90)` the time) but no skips.
Where a song is left for another:

- **Next**: `0xb81d4(player, flags)`. The button (`0xaca28`) and Up Next's pick (`queue.c`) pass
  **0**; the end of a song (`0xb7840` → `0xb795c`) always passes **`0x10`** (`| 1`, `| 8` by
  shuffle/repeat state), and `0xb81d4` itself tests it (`0xb8200`). That's how Next is told from
  the end. Its only callers are those two.
- **Prev**: `0xb75dc` → `0xb8cf8`, which loads through `0xb8ed8` directly: neither hook sees it.
- **A pick**: the "start playing" functions (`0xb6c38` a list row, `0xb6af8`, `0xb7310`,
  `0xb7468`, `0xb7174`) first call **`0x5e8cc(lib)`** (delete the list playing; Frogger's
  `keep_hook`), which unloads the song playing (`0xb7fb8` → `0xb8ed8(player, 0)`, from `0xb807c`),
  then load the pick with **`0xb8eb4(player, item)`** (traced in emupod: `0xb6c38`, `0x5e8cc`,
  `0xb8ed8(0)`, `0xac2ec`, `0xb8eb4`). When the list picked is the one playing, `0x5e8cc` is
  skipped and the song is still loaded at `0xb8eb4`. `0xb70c4` loads with `0xb8eb4` without
  `0x5e8cc`; `0xd9268(lib, i)` (callers `0x8fa80`, `0x95b20`, `0xd6590`, not looked into) too;
  `0x462cc` and the database unload (`0xe4abc`) load item 0.
- **The position**: `[player+0x2164]` (ms) and `[player+0x2a8]` (+0x20 the track), read as
  Apple's bookmark reads them at `0xb902c`. In emupod it never moves while "playing" (Now
  Playing stays at 0:00): only scrubs change it, so the driver scrubs to stand for listening.
- **Last played's clock**: `0xa065c(&t)`, seconds since 1904 local (Play Counts' last played).

Frogger (`payload/skips.c`): `skip_next_hook` (`0xb81d4`) counts the song playing unless `0x10`;
`keep_hook` notes the song playing and its position (`skips_keep`), and `skip_pick_hook`
(`0xb8eb4`) counts the song playing, or the noted one if nothing is (within 1 s), unless it's the
song picked; `0xd9268`'s loads (by return address `0xd92bc`) don't count. A skip is 2 s to 20 s in.
The skips go in `iPod_Control/iTunes/FroggerSkips` (`payload/skips.h`), saved only from `counts_hook`,
as Apple writes Play Counts, and read back after each database load like FroggerHidden. Apple writes
Play Counts (`0xf4d6c`, from the event handler `0x58398`: events `'cprm'`, `'hcpu'`, `'plsp'`,
`'prwp'`) a little after the song change too: in emupod the `'prwp'` 0.5 to 2 s after Next,
depending on the disk work before it (**likely** the disk going idle once the next song is read).
An earlier build also saved on the next UI tick after a skip, on its own, while the player was
reading the next song into RAM; on a device, skipping then left it unable to play anything (and
Now Playing without covers) until a restart, so that save is gone (`tools/emupod/skips.py save`
checks every save comes from `counts_hook`).
Seen in emupod: Next at 0 s and at 27 s, Prev at 5 s and a song scrubbed to its end don't count;
a list pick at 10 s and Next at 6 s do; the file holds both and comes back after a reboot.
Not seen: Up Next's pick (same `0xb81d4(player, 0)` as the button), Shuffle Songs, the position
moving on a device, sleep's save (emupod doesn't sleep after a scrub). By the code, Next on a list's last song counts too (the user left it).

## The battery icon (**confirmed** in emupod)

`tools/emupod/battery.py`, and the traces behind it (lookups, GPIO and I2C traffic, function
entries over an idle minute).

- **The icon** is a container, `None 0x3342` (`(4, 134)` to `(14, 159)` in the bar), in View
  `0x25e5` and the two other bar Views that have it: six instances at runtime, listed at
  `0x442a1c` (`+4` the count). It has 21 children, one per **state**: `0`–`2` charging (BMap
  `0x2590`, `0x2591`, `0x2592`, animated, vtable `0x2b32c`), `3` charged (`0x2593`), `4`–`19` the
  levels 0..15 on battery (`0x2594`–`0x25a3`, 25 × 10, 2 bits, loaded when first shown), `20`
  a `Str 0x3341` (low battery, **likely**), `21` none at all (no reading yet).
  `0xe0c9c(container, state)` shows child `state` and hides the others; the show repaints it.
- **The update**: `0x8e760(bar)` (from a vtable), every 30 s and when a screen opens, if the bar
  is shown: `state = 0x42af4(bar)`, then `0xe0c9c` on every container in the list. `0x42af4`:
  on the charger (`0x7cf84`) `3` if charged (`0x74430`), else `0`–`2` from `0x7cf64`; off it,
  `20` if `0xefff4`, else `4 + level` for a level ≤ 15, else `21`.
- **The level**: `0x74388` keeps it at `[0x370d64]` (0..15; 16 = none yet; `+4` counts readings
  that failed or were skipped) and moves it **one step per reading** toward a new one;
  `0x78bd8` can skip up to 6 readings in a row. A reading is `0x74320` → `0x118de0(&level)`:
  `0x118e40(&raw)` (0 when it read one), bucketed as the number of the 15 rising thresholds at
  `0x36ffc0` (u16, in RAM; emupod's boot leaves `0x10e 0x11e 0x129 0x133 0x139 0x13f 0x147 0x151
  0x15d 0x16e 0x17c 0x190 0x1a3 0x1b8 0x1ce`) that are ≤ raw. The units of raw are not known
  (an ADC count).
- **The raw read** `0x118e40` depends on the hardware revision (`0x118850() >> 16`): 1 a GPIO
  bit-banged read on port B pins `0x21`–`0x24` (`0x1393c0`/`0x139358`), 2 another GPIO
  handshake, 3 `0x139d88`. The pin numbers are `port << 4 | bit` with port 1 = A (`0x1391c0`
  sets one, `0x139358` reads one). Which revision a 3G is, and so which read runs on a device,
  isn't checked (**guess**: 3).
- **In emupod** the revision reads 0, the read fails (`0x53`), the level stays 16 and stock shows
  **no battery at all** (and no I2C traffic but the codec's, `0x34`). `battery.py` makes
  `0x118e40` a stub that returns a chosen raw value; the stock icon then shows that level.
- **Frogger** (`payload/battery.c`): BL hooks on the `bl 0x118e40` in `0x118de0` (notes raw) and
  the `bl 0x42af4` in `0x8e760` (states 4–19 become the first two level children in turn,
  whose bitmaps `0x2594`/`0x2595` are Frogger's: the percentage).

## Open questions

- Which R07 bits on the 3G panel invert the display (M1). Test on a device.
- What lives at `0x360000–0x36fc00`? (`0x24664` refers to it.)
- Where does the code at `0x320624–0x344328` run from, and does the COP use it?
- The native side of a Settings toggle (menu word 3 `0x1eb6`, `0x08df.method_9b`), which is
  what a Frogger setting has to hook. See `docs/tcmd.md`, "Adding a Frogger setting".
- What `0xf1ce8` (caller `0xb9fe4`) builds; it isn't any Music list.
- Hold polarity on the device. Stock 2.3 counts GPIOA bit 5 **high** as Hold on (Key input
  above), but `loader/main.c` returns the stock OS when bit 5 is **low**. If 2.3 is right, the
  normal loader never patches with Hold off. Check whether a build *without*
  `FROGGER_IGNORE_BUTTONS` ever showed a patch on the device.
- What `0x139a80`'s flag means (backlight on or off is the guess).
- Which battery read (`0x118e40`, by hardware revision) a 3G runs, the units of its raw value,
  and how far Apple's thresholds are from the real charge. See "The battery icon".

## Testing without a device

See `docs/emulation.md` for the options (run single functions in Unicorn, add
PP5002 to clicky, or test on the iPod).

**emupod** (a whole-PP5002 emulator, the submodule `third_party/emupod` with the gen3
changes in `tools/emupod/emupod-gen3.patch`, notes in `docs/power-and-emupod.md`) boots
stock 2.3 to the UI with `EMUPOD_ENTRY=0x28000000 EMUPOD_IDE_IRQ=1` and GPIOA bit 5
held **low** (Hold off, as 2.3 reads it). Two things matter for Frogger:

- It can't boot a partition with the loader: it runs the COP alone first and
  requires it to sleep, but `loader/crt0.S` parks the COP in a wait loop until the
  CPU is done. Boot the RAM image the loader leaves instead: run `tools/emu/boot.py`'s
  `boot()` on the patched partition and pass all 32 MiB it returns (Apple's image, and the
  payload and its bss at the top) to emupod as the osos (`tools/emupod/mkimage.py`).
- Its Python API hooks exact pcs (`hook_start`/`hook_log`) and reads RAM
  (`mem_read`) during a normal run. `call_trace_set` only logs inside `call_run`.
  Key presses and the wheel drive the 2.3 UI (Key input above), so the browse code
  behind Music › Songs/Artists can be traced while you open those lists.

## Helper: tools/re/xref.py

A dependency-free xref helper for quick questions before opening Ghidra.
`callers ADDR` lists every B or BL to an address, `loads LO HI` lists pc-relative
literal loads of values in a range, `words VALUE` finds data words, and
`strings TEXT` finds a C string and the code that loads its address. Function
boundaries come from `push {..., lr}` prologues, so they are approximate.

## Lock Cover (**confirmed** in emupod)

`payload/lock.c`, checked by `tools/emupod/lockcover.py`; `probes/holdprobe.py` shows stock.

- **What stock draws** (`holdprobe.py`, Frogger with Lock Cover off): Hold on, the Hold thread
  (`0x13c2a0`, a pin object with vtable `0x29378` waiting on event `0x78`) sees the level change
  and calls its vtable `+8`, `0x8d470`, which signals the object's event `[obj+0x18]` (`0x37cc`)
  and calls `0xad0f8(id)`; the UI then draws a small lock in the title bar (one LCD flush). A
  key with Hold on draws nothing at all: `0xbe110` returns before the key reaches the UI (no
  flush, and the backlight isn't touched there). Hold off takes the lock away (one flush). On
  Now Playing's cover page, which has no title bar, nothing changes on screen.
- **The lock screen**: `lock_tick` (tick_hook, ~4 times a second on the UI thread) reads Hold
  with `0x7a9b8`, as `0xbe110` does. With Hold on, the switch on and a song playing or paused
  (`[player+0x2a8]`, 0 when stopped), it draws its own screen: the 72×72 cover from `art.c` at
  1.5× (nearest neighbour, 108×108), the title in a built-in 5×7 font (ASCII; Latin-1 letters
  lose their accents) and a bar (`[player+0x2164]` of `track+0x54`). It builds the screen in
  its own buffer, swaps it into the framebuffer `0x3835a0` for a full `lcd_flush`, and puts
  Apple's pixels back, so the firmware keeps drawing its own screen underneath. It redraws
  when the song, the cover or the bar's width changes.
- **Keeping Apple's off the LCD**: while Lock Cover could show (`lock_armed`), `lcd_hook` asks
  `lock_lcd`: with Hold on every flush is skipped (the title bar's lock too, so it never
  flickers), and the first flush after Hold off flushes the whole framebuffer instead, which is
  Apple's screen as it is now. `lock_tick` does the same if no flush comes. The cover page's
  slide (`nowplaying.c`'s `lcd_all`) leaves the lock screen alone.
- **The title**: the track record's `+0x24` is a key in the title pool on the library object
  (`[track]+0xb0`); `0xbfb44`, which `0xeb1e8` uses for field 2, locks the pool (`0xa5004`),
  looks the key up with `0x81ee8(pool, key, &text, &bytes)` and unlocks it (`0xef738`); the text
  is UTF-16 halfwords (`0xc01b4` compares them as such).
- **Not checked on a device**: the backlight with Hold on (left to stock), the LCD's look at
  1.5×, and sleep with Hold on while paused (the screen goes off as stock's does, presumably).

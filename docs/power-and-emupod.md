# Disk power, audio buffer and emupod: research notes (2.3 osos)

Image: `build/fw/osos.img` (2.3, linked at base 0). Disassembly made with
`nix develop -c arm-none-eabi-objdump -D -b binary -m arm build/fw/osos.img`.

Status labels follow re-notes.md: **confirmed** (read from the instructions),
**likely**, **guess**.

## Part A: emupod gen3

All gen3 core changes are in one diff, `tools/emupod/emupod-gen3.patch` (`rust/pp5002/src/lib.rs`,
`ata.rs`, `rust/pybind/src/lib.rs`), applied to the clone in `build/emupod/rust`. All are opt-in via
environment variables; 1G/2G are unchanged. Run with `EMUPOD_ENTRY=0x28000000 EMUPOD_IDE_IRQ=1`.

- **Reset entry** (`EMUPOD_ENTRY`, also honoured by `boot()`). The core's default 1.x reset pc
  `0x2800012c` is inside the 2.3 IRQ handler, so the COP never sleeps ("coprocessor did not put
  itself to sleep at reset: pc 0x40010004"). 2.3 needs `0x28000000`.
- **Clock block** `0xcf005000..0x3c` stored, with defaults `0x18 = 1`, `0x1c = 3`. The 2.3 clock code
  `0x12eefc` divides by the low byte of `0xcf005018` and multiplies by `0xcf00501c`; with both 0 it
  divides by zero → `__rt_raise(SIGFPE=2)` → handler 0 → jump to 0 → reset loop. (Without the model,
  patching `0x12ef24 and r0,#0xff` → `mov r0,#1` and `0x12ef30 and r2,#0xff` → `mov r2,#3` also works.)
- **IDE interrupt** (`EMUPOD_IDE_IRQ=<bit>`): the drive's INTRQ as a level on that
  interrupt-controller line, cleared by a status-register read or by the `0xc0003024` bit-4 ack;
  `0xc0003024` bit 4 reflects INTRQ for DRAM boots too. `Machine::ide_line()` also offers the IRQ
  after each `run_cpu`, which wakes an idle CPU (while the CPU idles, every slice starts inside the
  timer ISR with I set). Key edges use the same mechanism (`gpio_late`; only with `EMUPOD_IDE_IRQ`).
  Without this, 2.3 stalls at 2.407 s: the 1.x and disk-mode code poll, but the 2.3 driver sleeps
  until the interrupt after the second IDENTIFY.
- The `paths.py` gen3 guard only affects the CLI. The Rust core has no `events("fault")`.

**IDE IRQ line: bit 1** (**confirmed** by the trace). The ATA driver brackets every command with
`0xcf001028 = 0x2` / `0xcf001024 = 0x2`, and its ISR reads `0xcf001000 = 0x2`, reads `0xc0003024`
(0x5c), acks with `0xc0003024 = 0x58`, then reads status. Bit 1 is not one of the named
branches in the dispatcher `0x1282ac`; it is handled on the default path (`0x13ddc0`/`0x1349a8`).
Bit 3 (`0x13f090`) is something else.

Test cards (scratch):

- `build/emupod-work/gen3-card.img`, 256 MB, made by emupod's `tools/synth_card.py` from
  `iPod_2.2.3.ipsw` (MBR, firmware partition at sector 63, empty FAT32), with `mkfs.fat` from
  `nixpkgs#dosfstools`. Boots to the first-run **Language** menu (no settings, no iTunesDB).
- `build/emupod-work/music-card.img`: the same plus `iPod_Control/iTunes/iTunesDB`, a minimal mhbd v9
  (2 tracks + master playlist) written by `tools/emupod/mkcards.py` with the repo's mhod layout, and
  two sine-tone MP3s made with `nix shell nixpkgs#sox nixpkgs#lame`: `TONEA.mp3` (3 min, 128 kbps,
  2.9 MB) and `TONEB.mp3` (12 min, 320 kbps, 28.8 MB, bigger than the about 26.8 MiB music cache, so a
  full play shows more than one wake). Files copied in with `nix shell nixpkgs#mtools`.

Boot, as observed:

- CPU idle pc `0x2f36c` (CPU idle sleep: `CPU_CTL 0xcf004054 = 0xca`); COP asleep at `0x2f38c`
  (`COP_CTL = 0xca`). The CPU writes the IRQ enable `0xcf001024 = 0x405808` at 156 ms, then
  `0x4000`, `0x80`, `0x4`.
- ATA bring-up: **0x90** EXECUTE DIAGNOSTIC; **0xEC** IDENTIFY (polled, DRQ 0x48, 256 data reads);
  **0xEF** SET FEATURES sub 3 count 8; devctl = 0 (nIEN off) and `0xc0003024 = 0x50`/`0x40`; then
  **0xEC** IDENTIFY again, interrupt-driven, issued by `0x1416f0` on a heap ATA object `0x1fd44dc`.
- `0x9439c` (boot spin-up wait) is hit at 2.40 s with `n = 0x2c4020` (29 s = 31 s − 2 s uptime,
  matching the static reading).
- First reads: READ SECTORS `0x20` (builder `0xdf700`) at LBA 0, 0, 0, 0x3f, 0x1003f, 0x10040, 0x11bf1
  (MBR, firmware partition, FAT32 boot sector/FSInfo/FAT), SET MULTIPLE `0xC6`, then single-sector
  READ MULTIPLE `0xC4` (builder `0xdf014`).
- Empty card: UI up at 7.7 s; 172 ATA commands, 169 IDE IRQs, 119 sectors read (all single-sector
  READ MULTIPLE), plus 47 single-sector WRITE MULTIPLE `0xC5` around 3.7–3.96 s (settings/FAT
  updates on the fresh card).

**Disk idle timeout: 12.8 s (confirmed in emulation, stock 2.3, empty card).** Last disk command:
a read at 8.1025 s. **STANDBY IMMEDIATE `0xE0` reaches the drive at 20.9334 s** (`0x134c58` →
`0x9e83c` → `0x9da1c` → `0x9db0c` → builder `0xe0078`; emupod's power log marks the drive powered
down): 12.83 s after the last access. The disk-power messages (type 14, sub-op 4 → op `0xFC` per
unit) are per-access notifications; the last one is 12.81 s before the standby. No literal
constant for it (no 1280/12800/12.8e6 near the power code); it is probably computed or counted
in ticks. `0x9da1c` first runs the "re-init after wake" path `0xc347c` when `obj+0x1e0` is set;
if its BSY/DRQ check (`0x13f9c4`, 30 × 10 µs) fails, it returns `0x400` before reaching `0xe0078`.

Keys and screen:

- **Hold**: `0xbe110` (where every button ends up) returns early when `0x7a9b8` says Hold is on,
  which compares GPIOA bit 5 with a fixed level 1. Bit 5 **high** = Hold on, so keep it **low**.
  The full button, event and code map is in `docs/re-notes.md` (Key input).
- Key edges: GPIO IRQ bit 14. The GPIO ISR `0x124cd8` reads `0xcf000040 = 0x2`, flips
  `0xcf000060`, acks `0xcf000070` and reads GPIOA input (`0x3d` Select down, `0x3f` up).
- Wheel: GPIOA bits 7:6 are a quadrature pair (event `0x71`, decoder `0x90c94`). One menu item
  takes 4 to 6 steps.
- Screenshots: `e.lcd.make_screen()` starts blank and only fills in if there were LCD writes since
  the last update, so a shot taken after an idle stretch is empty. Read `m.lcd_update(); m.lcd_px()`
  instead.
- Driver: `build/emupod-work/scripts/ipod3g.py` (`Pod().press("select")`, `.scroll(n)`,
  `.shot(...)`). Run it with plain `python3` from that folder; `-I` hides the module.
- With the music card, Music › Songs lists "Tone A" and "Tone B long", and Select on a song
  starts playback (▶ in the title bar).

**Read size per disk wake: not measured yet.** Play TONEB and log READs per wake. There is no
callable "play track" entry known: `0x54de4` (allocates a 0x424-byte per-track cache object and
links it into the cache; called from `0x999ac` and `0xe4bc8`, i.e. player/database setup) and
`0x94918` (the playback tick that calls the refill check `0x45760`) need the playback controller's
state, which is not mapped (strings `Now Playing` at `0x18fde0`/`0x190818` and `NowPlayingMode`
at `0x3074b0` are the way in). The static answer from B.3 stands.

## Part B: disk power and audio buffer in 2.3 osos

### B.1 The ATA driver and the commands it issues

**ATA device object** (**confirmed**): a static C++ object at `0x418b9c`, built at boot by
`0x206f0` (calls the base constructor `0x100678`, then installs vtable `0x26d88`).
The vtables are *relative*: each slot holds an offset added to the vtable base
(`ldr r2,[vt,#k]; add r2,r2,vt; mov pc,r2`), so you cannot search for them as absolute addresses.
The constructor stores pointers to the taskfile registers in the object (taskfile base `0xc00031e0`):

| obj field | register | address |
|---|---|---|
| `+0xec` | data | `0xc00031e0` |
| `+0xf0/+0xf4` | error / features | `0xc00031e4` |
| `+0xf8` | sector count | `0xc00031e8` |
| `+0xfc/+0x100/+0x104` | LBA low/mid/high | `0xc00031ec..f4` |
| `+0x108` | device/head | `0xc00031f8` |
| `+0x10c` | status (read) | `0xc00031fc` |
| `+0x110` | command (write) | `0xc00031fc` |
| `+0x114/+0x118` | device control / alt status | `0xc00031e0+0x218 = 0xc00033f8` |

How a command is issued (**confirmed**):

- Each command builder fills a staged taskfile in the object: `+0x18` features, `+0x19` count,
  `+0x1a..0x1c` LBA, `+0x1d` device (`0x40|LBA[27:24]` for LBA mode), and **`+0x1e` the command byte**.
  It then tail-calls `0x12d180(obj, dir, timeout_us, ?)`.
- `0x12d180` stores the direction (0 = none, 1 = PIO in, 2 = PIO out, 3 = DMA) at `+0x178` and the
  timeout at `+0x1a4`. It stamps the start time from the µs timer `0xcf001110` (`0x14b134`) at `+0x1a8`
  and arms the request (`+0x194 = 1`).
- `0x141990` copies the staged bytes to the registers. `0x1416f0` writes `+0x1e` to the
  command register (`strb` at `0x141710`) and then waits for DMA-ready (`0x13fa88`).
- The default timeout is `0x989680` = 10 s. ATAPI command `0x5b` uses `0x5f5e100` = 100 s.

Command builders (**confirmed**; each one writes the byte shown into `+0x1e`):

| Address | Command | Notes |
|---|---|---|
| `0xdeb0c` | `0x08` DEVICE RESET | 10 s |
| `0xdeb50` | `0xC0` with LBA, count 1 | vendor or CFA; purpose unknown (guess) |
| `0xdebac` | **`0xE3` IDLE, count = 0** | count 0 **disables the drive's own standby timer**, so the OS manages spin-down itself (likely) |
| `0xdec68` | `0xEC` IDENTIFY DEVICE | |
| `0xdecf4` | `0xA1` IDENTIFY PACKET | |
| `0xdefac` | `0xC6` SET MULTIPLE | count = `min(req, obj+0x184)` |
| `0xdf014` | `0xC8` READ DMA / `0xC4` READ MULTIPLE | DMA if the setup vfunc (`vt+0x80`) succeeds, PIO-multiple otherwise |
| `0xdf700` | `0xC8` READ DMA / `0x20` READ SECTORS | same pattern, single-sector PIO fallback |
| `0xdf138` | `0xC5` WRITE MULTIPLE | |
| `0xe012c` | `0x30` WRITE SECTORS | |
| `0xdffd4` | `0x70` SEEK | |
| `0xe002c` | `0xEF` SET FEATURES, sub 3 (transfer mode) | also `0xddae0` writes `0xEF` straight to the registers (PIO/UDMA mode set) |
| **`0xe0078`** | **`0xE0` STANDBY IMMEDIATE** | 10 s |
| `0xdea5c`, `0xdebf0`, `0xded80`, `0xdedfc`, `0xdee78`, `0xe00bc` | `0xA0` PACKET (ATAPI CDBs `0x12`, `0x5a`, `0xbe`, ...) | for ATAPI devices; not used by the 3G HDD (likely) |
| `0x6b05c`, `0x93f88`, `0x94184` | `0x90` DIAGNOSE / `0xEC` / `0xA1` | probe path, written straight to the registers |

**Not found anywhere in the image** (scanned every `strb` to `+0x1e` and every direct
command-register store): `0xE2` STANDBY, `0xE6` SLEEP, `0xE1` IDLE IMMEDIATE, `0xE5` CHECK POWER,
`0xE7` FLUSH CACHE. The only spin-down command is **STANDBY IMMEDIATE (0xE0)** (**confirmed**
as far as constant operands go).

Command dispatcher (**confirmed**): `0x9da1c(obj, unit, op, args)` (ATA vtable slot `+0x14`) switches on
an op code that mostly equals the ATA opcode: 8, 1, 3, 0x15, 0x20, 0xC2..0xC6, 0xE0, 0xE3, 0xEF, 0xFC, 0xFD.
The public entry is **`0x9e83c(dev, unit, op, arg)`**: it takes a lock, calls `vt+0x14`, then unlocks.

**Who spins the disk down** (**confirmed**): only one caller passes op `0xE0`. **`0x134bc8`, case 2**
loops over every block device. For each unit whose state (`vt+0x40`) is `6` (spinning, likely),
it calls `0x9e83c(dev, i, 0xE0, 0)` and then `0x9e83c(dev, i, 0xFD, 0)` (`0xFD` is internal and clears the
per-unit word at `[0x370efc + i*4]`). `0x134bc8` is the handler for message type 14 ("disk power")
in the task loop `0x13bc2c` → `0x134d3c`. The sub-op sits at message `+0x18`, and the message
constructor is `0xfac38(buf, arg, op)`. Other sub-ops: 0/1 → `0xd80c4`/`0xd82bc`, 5 → `0xd7ef8`,
8/9 → `0xd8394`/`0xd81c0`. Case 4 of the same switch (`0x134ca8`) sends op `0xFC` to every unit in state 6.

**Spin-up and BSY wait loops** (**confirmed**). The delay `0x14b0b8(us)` busy-waits on `0xcf001110`:

| Address | What | Timeout |
|---|---|---|
| `0x13f984(obj, n)` | wait for BSY (`0x80`) clear, `udelay(10)` per poll | `10·n` µs |
| `0x13f9c4(obj, n)` | wait for BSY and DRQ (`0x08`) clear, reads alt status first | `10·n` µs |
| `0x13fa14(obj, us)` | wait for BSY clear, yielding 1 ms per step (`0x3460`) | `us` |
| `0x9439c` in `0x942cc` (ATA init, vt `+0x1c`) | **boot spin-up wait**: `n = (31 − seconds since boot) × 100000` → waits until **31 s after boot** (minimum 1 s) | ≤ 31 s |
| `0x94148` | BSY/DRQ wait with `n = 3000000` | 30 s |
| `0x97830` in `0x977c8` | after reset/wake: `0x13fa14(obj, 3100000)` | **3.1 s** |
| `0xddb60..0xddca8` (SET FEATURES) | `n = 1000000` | 10 s |
| `0xc34a0` | `n = 30` | 300 µs |
| `0x942cc` start | writes device control `= 0x02` (nIEN), then `udelay(5000)` | |

Note `0x94348`: the ATA init reads `0xcf000038` (GPIO C input) bit `0x20`, and if it is set calls
`0x11ad80` (likely "is a drive present / disk-mode" check; **guess**).

A second, simpler polled ATA path writes the registers directly at `0xf7210..0xf74c0`
(`0xc0003000 + 0x1e8/0x1f8/0x1e4`, polls `0xc0003024` bit `0x40`, DMA ops `0xC8`/`0xCA`).
It is likely the boot or disk-mode low-level path (**likely**). The IDE FIFO copy loop is at `0x22914`
(polls `0xc0003024`/`0xc0003028`, 64-byte bursts), and an IRAM copy of the same is at `0x31f474`.

### B.2 Disk idle timeout and drive power GPIO

- **Idle timeout: 12.8 s** (measured in emulation, Part A); found since: the disk arbiter, Part D. Known
  (**confirmed**): the drive's own standby timer is turned off (IDLE `0xE3` with count 0, `0xdebac`),
  so the timeout lives in osos. It works by posting message type 14, sub-op 2, to the disk-power
  task (`0x13bc2c`). `0xfac38` is the only type-14 message builder (every function scanned for an
  immediate 14 stored to `+0x14`: only `0xfac38` and the receiver `0x134d3c`), and its direct callers
  send sub-ops 9 (`0x9b964`), 8 (`0xb266c`) and 5, but not 2. So the sub-op 2 message is built inline
  somewhere else, probably by a timer callback. To find it: stores of `#2` to `[msg,#24]` near a
  `strb #14,[msg,#20]`, or hook `0x134c58` and backtrace. **guess**: kept in a settings word next to
  the power-state table at `0x3702a0` / `0x422080`.
- **Drive power GPIO: none found** (**likely**). No store to GPIO output registers
  (`0xcf000020..2c` / `0xcf000060..6c`) sits on the ATA or power paths. The only direct GPIO
  output write, `0x13fd30` → `0xcf000028` and onward to `0x13fe30`/`0x140614`, is the
  audio codec. Rockbox's ipod `ide_power_enable` is also a no-op, which fits a drive that
  is only ever put to sleep with STANDBY IMMEDIATE and never has its power cut. A power-off
  would have to come from the PMU or a hard power-down (not checked).

### B.3 Audio read-ahead (track cache)

- **`TrackCacheReadTask`** (**confirmed**): created by `0x54bcc` (called from the DB/boot path `0x99530`).
  `0x54bcc` allocates **64 request records of 0x150 bytes** (loop at `0x54d44..0x54d80`) and starts the
  task with entry **`0xe9c4c`**, stack `0x2000` and priority `0x40` (`0xac6fc` at `0x54da8`). The
  cache object pointer is stored at `[0x439bf0 + 0xc]`, and the chosen disk index at `cache + 0xb7c`.
- The task (`0xe9c4c`) waits on the event at `0x439c10`. It walks a list of cached tracks at
  `cache + 0xb5c` (next pointer `+0`, segments at `+0x20`), uses a per-track file handle at
  `+0x144` (`0xb2630` open, `0xa01a0`/`0xa022c`/`0xa0318` seek/read/close, **likely**), and sets
  "done" flags at `+0x148`/`+0x149`.
- **Low-water mark: 20 s of audio** (**likely**; the code is confirmed, the units are inferred).
  `0x45760(player, pos_ms)` is called from the playback path `0x94918` (at `0x94d20`). It
  finds the current track in the cache list (`cache+0xb5c`, matched on the track id at `+0x18`).
  It takes the end of the cached data (`seg+0xc + seg+0x8`), and if the file (`track+0x1c`) is
  not fully cached it converts that byte offset to time with `0x1239a4`. That function computes
  `(offset − dec+0xdd74) / (dec+0xdd64 / 8)`, i.e. bytes ÷ bytes-per-second. Decoder types 9
  and 10 subtract 20 from the result. The result is multiplied by 1000 (`0x4590c..0x45914`) and
  cached at `[0x439bf0+0x1c]`. Then **`cached_until_ms − pos_ms < 0x4e20` (20000)** at
  `0x45920..0x4592c` sets the flag byte `[0x439bf0] = 1`, signals the event `0x439c10` that
  wakes TrackCacheReadTask, and pokes `0x439bf4`. So the disk is woken when **less than about
  20 s** of audio is left in the cache. This patches as one instruction pair: the
  `subs #0x4000` / `subscs #0xe20` at `0x45924`/`0x45928`.
  Related (**confirmed**): `0x45700` compares `now_ms` against a stamp `+ 250` before acting
  (a 250 ms debounce).
- **Read-ahead size per disk wake: NOT FOUND.** **guess**: the task fills as much of the
  heap-backed cache as it can (the heap is about 26.8 MiB on a 32 MiB unit), so the amount is
  bounded by free cache space rather than by a fixed constant. That fits Apple's "20 minutes of
  skip protection" marketing. The task has no size constants of its own. They will be in the
  code that sizes cache segments from the heap (`0x33500` probes DRAM; the heap is `0x453c304`
  (uncached alias) up to `0x4346364 & ~0xfc000000`-based top, stored at `heap+0x14/+0x18`).
  To find it: xref `0x439bf0` and `cache+0xb5c` writers, and look for the free-space or
  "remaining ms" compare that signals `0x439c10`.

### Summary for the power question

- Spin-down: STANDBY IMMEDIATE `0xE0` only, from `0x134bc8` case 2 (`0x134c58..0x134c7c`). confirmed.
- The drive's own timer is disabled (IDLE `0xE3`, count 0, `0xdebac`). confirmed.
- Spin-up: implicit on the next command. The driver waits up to 3.1 s (`0x97830`) after a
  reset or wake, and up to 31 s after boot (`0x9439c`). The default command timeout is 10 s. confirmed.
- Refill trigger: less than 20 s of cached audio left ahead of the play position (`0x45924`, likely).
- Idle timeout: 12.8 s after the last disk access (emulation, confirmed); it's the disk arbiter's
  per-client holds, located in Part D.
  The spin-down path goes through the message system (type 14, sub-op 2 → `0x134bc8`).
- Read-ahead size per wake: not located or measured.

## Part C: the disk that stops answering (confirmed in emupod)

On a device with an SD adapter in place of the hard drive, a supply dip while the music cache
refills at a song change (worse with albums of big files) leaves the adapter silent: the audio
already in RAM plays out, then no song or cover loads until a restart, and Frogger's UI freezes
(`art.c`'s cover read runs on the UI loop). The emulator reproduces it.

**Fault injection** (in `emupod-gen3.patch`): `EMUPOD_ATA_HANG="skip,ms"` or
`Machine.ata_hang(skip, ms)`. After `skip` more read commands the next one hangs the drive: BSY
for good, no INTRQ, further commands ignored (logged `IGNORED`), until a soft reset (device
control `0xc00033f8` bit 2 set, then cleared) or, with `ms`, until that long has passed. A
reset after a hang also drops SET MULTIPLE, as a power-cycled drive would. `stats()` has
`ata_hangs` and `ata_resets`; `ata_log()` returns the command log.

**What stock 2.3 does** (`ata_hang(0, 0)` from Songs, then Select on Tone A):

1. The read (`0xc788c` → builder `0xdf014` → `0x12d180`, 10 s timeout) waits on the semaphore
   `ata+0xd8` (`0x93248` from the state handler `0x12fea0`). The time runs out; the handler posts
   **event 5** through `0x11ac00` (`ata+0x174 = table + 4 + 8·event`), whose handler is
   **`0x1302a0`**: `+0x18c = 0xff`, error `0x400` into `+0x190`, then **`0x913d0`**, then event 0
   (done). The other handlers that post 5 check the timeout with `0xe7290` (`0x12ff68`,
   `0x1300bc`, `0x1301fc`) or a failed wait (`0x130040`).
2. `0x913d0` writes `4`, then `0` to **`0xcf005034`**: a reset of the PP5002's IDE *controller*,
   not of the drive. It redoes the timings (`0xdda40`) and sets **`ata+0x1e0`** (re-init
   pending). Apple never sends SRST or DEVICE RESET to an ATA drive.
3. The caller retries once, 6 ms later. `0xc788c` (and the dispatcher `0x9da1c`) run the re-init
   **`0xc347c`** first while `+0x1e0` is set: a 300 µs BSY/DRQ check (`0x13f9c4`, n = 30); it
   fails, so `0x913d0` again and `0x400` at once. (When the drive answers, `0xc347c` redoes SET
   FEATURES for the transfer modes, `0xddae0`, and SET MULTIPLE, then clears `+0x1e0` at `0xc3560`.)
4. The reader is **TrackCacheReadTask** (`0xe9c4c`; stack `0x122674` → `0x6c15c` → `0x734ec` →
   `0xc7b70` → `0xc7720` → `0xc788c`). It takes the error and goes back to waiting on its event
   (`0xe9c6c`). After that **no command ever reaches the disk again** (187 commands, then
   nothing, also when another song is picked); the CPU sits idle. So it's not an endless retry
   or a thread blocked for good: the drive is never reset, the one retry fails at once, and the
   refill is dropped.

**The fix** (`payload/disk.c`, `hooks.S`): `disk_reinit_hook` at `0xc347c` soft-resets a drive
that still shows BSY or DRQ (SRST for 20 µs, 2 ms, then `0x13fa14` waits up to 3.1 s (Apple's wake value; maybe ~31 s real, as `0x3460` steps are 10 ms in emupod) for BSY
clear, sleeping 1 ms a step; then nIEN off), and Apple's re-init goes on from there.
`disk_read_hook` at `0xc788c` runs the read again, up to 3 tries in all, while it fails with
`+0x1e0` set, so the timed-out read itself comes back and the cache task never sees an error.
Worst case before giving up as before: 3 × 10 s timeouts plus 2 × 3.1 s waits, on the reading task.

In emupod (`tools/emupod/diskhang.py`): read times out at 10.2 s → `0x913d0` → retry →
SRST → `0xEF` sub 3, `0xC6` → the read is done 2 ms later; 1671 reads follow and Next still
reads Tone B. Not known without a device: whether the adapter comes back from SRST (or needs
its power cycled, which the iPod can't do: no drive power GPIO, B.2), and how long it takes.

**The UI while the disk is stuck.** Frogger's cover read used to run on the UI loop (`np_vm` →
`np_art_update` → `fw_open`/`fw_read`), so the wheel, the menus and Now Playing froze for the
whole timeout and recovery; stock 2.3 reads nothing on the UI side at a song change. Now
`art.c` starts a task of its own, **FroggerArt** (`0xac6fc`, as `0x54da8` starts
TrackCacheReadTask), on the first song: the UI hands it the record to read (and goes on), the
task reads into a buffer of its own, and the UI copies the result into the cover's BMap from
`np_vm` or the quarter-second tick and redraws it if it's up. The task polls every 3 ticks
(`0x3460(0, 3)`, 30 ms) while idle. A failed read is still retried when Now Playing next opens
(`np_art_retry`). The hold menu's Hide (`hide_save`) and a playlist save (`playlist_pick`)
write at once only when `disk_idle` says no read has run for 0.5 s (`disk_read_hook` counts
reads and notes when the last ended), no re-init is pending and the drive isn't BSY/DRQ;
otherwise from a later tick once it is (and a Hide waiting still goes out with Play Counts,
`counts_hook`). In emupod (`diskhang.py art`, `art-card.img`): song 2's cover read hangs the
drive; 2.7 s later, drive still hung, Menu and the wheel move Songs' highlight, and after the
recovery song 2's cover is up. With the read forced back onto the UI (FroggerArt marked
unavailable) the same run fails: the wheel does nothing during the hang.

## Part D: Flash Storage (working in emupod)

Settings › Flash Storage (`payload/flash.c`; Off, Auto, On; **Off by default**) lets a flash mod's
disk go to standby sooner. Measured with `tools/emupod/flash.py` (the check) and
`tools/emupod/probes/flashplay.py` (the long play).

A flash mod is still an ATA drive to the iPod: the SD or CF card sits behind an IDE bridge
(iFlash and the like), which answers IDENTIFY, takes STANDBY IMMEDIATE (or ignores it) and sets
BSY as it likes. Nothing here talks to the card itself, and disk.c's soft reset (Part C) goes
through the same bridge.

### D.1 Where the 12.8 s comes from: the disk arbiter (**confirmed**, code and emupod)

The idle timeout isn't one number. The task at **`0x13bc94`** (mailbox 19) arbitrates the disk
between 19 clients. A client says **busy** with `0x5790c(client)` (message kind 0) and **done,
hold the disk `ms` more** with **`0x57820(client, ms)`** (kind 2, stored as `ms / 10 + 1` ticks
of 10 ms). Per client the arbiter keeps a flag (`0x420a5c[19]`) and the ticks left (`0x420a70[19]`,
−1 while busy), waits for the next message or the shortest hold left (`0x40b8(19, ..., ticks)`),
and when no client holds the disk any more it builds the type-14 message **sub-op 2** inline
(`0x13bf58..0x13bfb0`) and sends it to the disk-power task with `0xbb514(msg, 5)`: STANDBY
IMMEDIATE (`0x134c58`). While some client still holds it, it sends sub-op 4 instead. That's the
inline sub-op 2 message Part B was looking for.

The holds, by caller: client 1 (database load, `0xe4454`) 15000 ms; client 6
(TrackCacheReadTask, `0xe9cac`) 10000; client 4 (`0xbc18c`) 3000; clients 2 (playback
`0x94b34`, `0x46d38`), 3 (`0xe4c1c`) and 10 2000; 8, 11, 13, 15 1000; 12 952; 7 100; 3 (`0xe1ed0`)
and 9 0. So the standby comes 2 s after a music-cache refill during playback (client 2), about
10 s after boot's database load (the 12.8 s of Part A: client 1's 15 s from 2.8 s), and up to
10-15 s after other disk use.

### D.2 What the switch does

- **Holds cut to 1 s** (`flash_hold_hook`, a B hook on `0x57820`'s first instruction): with the
  switch in effect, any `ms` over 1000 becomes 1000. The arbiter works as before; it just runs out
  sooner. A drive that needs a command after standby gets it as before: the driver's wake is
  implicit in the next command.
- **Detection for Auto** (`flash_id_hook`, BL at `0x9dbac` in the dispatcher's IDENTIFY case, as
  the command ends): at that point `ata+0x17c` points just past the 512 bytes read, `ata+0x190` is
  the error. `flash.c` keeps word 0, word 217 and the model (words 27-46) in `flash_id_w0`,
  `flash_id_rpm`, `flash_id_model`. Auto acts when word 217 is 1 (non-rotating), word 0 is
  `0x848a` (CompactFlash) or the model has FLASH, SDCF, SSD, SD CARD, SDHC, SDXC or CF CARD in it,
  or starts with TS and a digit (Transcend CF); a drive that reports a rotation rate is always left
  alone. A bridge may report none of these (it answers for the card, and old CF cards and bridges
  leave word 217 at 0), so Auto can miss a flash mod: use On. That's why the default is Off, not
  Auto. **Not known without devices:** what iFlash and other bridges put in these words.
- The switch is read through the prefs (bits 28-29, `frogger_flash_mode()`); until they're up it
  counts as Off. In emupod they're up at 2.64 s, before boot's first hold (client 1, at 2.79 s), so
  a saved On or Auto covers boot too.

### D.3 Measured in emupod

`probes/flashplay.py 760`: boot, Music › Songs, Tone B (12 min, 320 kbps) played for 760 s,
777 s in all; IDENTIFY word 217 = 1; the switch set as soon as the prefs are up (as a saved
value would be). Awake = from the first command after a STANDBY (or from 1 s) to the next STANDBY.

| | STANDBYs | last command → STANDBY | disk awake | reads |
| --- | --- | --- | --- | --- |
| Off (Apple) | 1, at 24.5 s | 2.05 s | **22.2 s** | 1741 (44973 sectors) |
| On (or Auto on flash) | 3, at 3.8, 7.7, 23.5 s | 0.86, 1.03, 1.03 s | **11.4 s** | 1741 (44973 sectors) |

Half the awake time for the same reads: Apple's holds (15 s from the database load, then the
menus' and the refill's) chain into one 22 s stretch; cut to 1 s, the disk sleeps between boot,
the menus and the refill, at the cost of two more wakes (each instant on a bridge that answers at
once). During playback alone the saving is 1 s per refill (2.05 → 1.03 s). emupod's audio
doesn't run the music cache down (Part A: "audio stops early"), so a play shows only the first
refill; on a device a refill comes about every 9-10 minutes of 320 kbps music (23 MB of cache),
each 1 s shorter, and after any browsing that touches the disk 1-14 s shorter.

`flash.py` (the check): Select steps Off, Auto, On, Off and the row shows each value; Tone A's
refill ends 1.02 s before the STANDBY with Auto on a flash IDENTIFY and with On on emupod's plain
one (no rotation rate), and 2.05 s (Apple's) with Off and with Auto on a hard drive's IDENTIFY
(word 217 = 4200, model TOSHIBA MK4004GAH). `EMUPOD_ATA_ID` (in `emupod-gen3.patch`) sets the
IDENTIFY words and model: `"w217=1,model=..."`.

What that's worth on a device depends on the bridge: only one that cuts the card's power (or puts
it in its own sleep) on STANDBY IMMEDIATE saves anything; one that ignores it saves nothing and
loses nothing. Needs a device test, ideally with a current meter.

### D.4 What was looked at and left alone

- **Boot spin-up wait** (`0x9439c`, up to 31 s after boot) and the **wait after a wake**
  (`0x97830`, 3.1 s): both are `0x13f984`/`0x13fa14`, which poll BSY and return as soon as it
  clears. They are upper bounds, not delays: a bridge that answers at once costs nothing there,
  and shortening them would only fail a slow one. In emupod the boot wait (`n = 2900000`) ends
  at once. disk.c's reset wait is unchanged.
- **Read-ahead.** A refill reads until the cache is full (Part B.3): on music-card.img, 47028
  sectors (23 MB) in 6.6 s, starting with less than 20 s of audio left. The bytes read per song
  are the same whatever the refill size, so what a smaller refill changes is the number of wakes,
  each costing a hold (now 1 s) plus the bridge's wake. Bigger refills aren't possible (the cache
  is what's left of RAM), smaller ones only add wakes: unchanged. Lowering the 20 s low-water mark
  saves nothing either (same bytes, same wakes) and risks a gap if a wake is slow.


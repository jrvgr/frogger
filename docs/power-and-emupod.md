# Disk power, audio buffer and emupod: research notes (2.3 osos)

Image: `build/fw/osos.img` (2.3, linked at base 0). Disassembly made with
`nix develop -c arm-none-eabi-objdump -D -b binary -m arm build/fw/osos.img`.
Nothing was committed or pushed, and nothing was written to the iPod.

Status labels follow re-notes.md: **confirmed** (read from the instructions),
**likely**, **guess**.

## Part A: emupod gen3 boot (run 2026-10-28, after the module was built)

Result: **2.3 boots into the OS and initialises the LCD, then stalls at 2.407 s waiting for the IDE
interrupt after the second IDENTIFY DEVICE. Blank screen, no disk reads.**

How it was run (scratch only; nothing in the repo or on the iPod changed):

- Disk: `build/emupod-work/gen3-card.img`, 256 MB, made by emupod's `tools/synth_card.py` from
  `iPod_2.2.3.ipsw` (MBR, firmware partition at sector 63, empty FAT32). The script was copied to the
  scratchpad, with `mkfs.fat` from `nixpkgs#dosfstools`.
- Driven through `emupod.emu` / `emupod_rs.Machine` directly. I did not call `boot()`, which forces the
  1G entry pc, and drove the clock with `run_for()` instead. The `paths.py` gen3 guard only affects
  the CLI, so it did not need a bypass.
- Three things had to change for gen3, all in scratch copies:
  1. **Reset entry.** The core starts both cores at the 1.x reset pc `0x2800012c`, which in 2.3 is
     inside the IRQ handler, so the COP never slept ("coprocessor did not put itself to sleep at
     reset: pc 0x40010004"). I patched `rust/pp5002/src/lib.rs` in the scratch clone to read
     `EMUPOD_ENTRY`, and set it to `0x28000000`. Note that `Machine::boot()` still resets the pc to
     the 1.x entry (`lib.rs:1939`), so do not call it for gen3.
  2. **PLL registers.** The 2.3 clock code `0x12eefc` divides by the low byte of `0xcf005018` and
     multiplies by `0xcf00501c`. emupod returns 0 for both, so it divided by zero → `__rt_raise(SIGFPE=2)`
     → handler 0 → jump to 0 → reset loop. I fixed this in a **patched osos copy**,
     `build/emupod-work/osos-emu.img`: `0x12ef24 and r0,#0xff` → `mov r0,#1`, and
     `0x12ef30 and r2,#0xff` → `mov r2,#3`. The real fix is for the core to model
     `0xcf005018`/`0xcf00501c`.
  3. With both changes it boots into the scheduler `0xc3170`.

What happens in 30 emulated seconds:

| | |
|---|---|
| LCD writes | **74** (controller init only). `build/emupod-work/lcd.png` is blank |
| Faults | none seen; the Rust core has no `events("fault")`, but the CPU stays in the OS idle loop |
| CPU pc | `0x2f36c` (the CPU idle sleep: `CPU_CTL 0xcf004054 = 0xca`), 892,851 sleeps; from about 23 s, sampled at `0x12d774` (`is_cpu()` return), still idle |
| COP | asleep at `0x2f38c` (`COP_CTL = 0xca`), woken 1,360 times |
| IRQs / ticks | 1,598 IRQs, 1,580 timer ticks: the scheduler is alive |
| IRQ enable | CPU writes `0xcf001024 = 0x405808` at 156 ms, then `0x4000`, `0x80`, `0x4` |
| ATA log | 2.4059 s **0x90** EXECUTE DIAGNOSTIC; 2.4059 s **0xEC** IDENTIFY (polled, DRQ 0x48, 256 data reads); 2.4061 s **0xEF** SET FEATURES sub 3 count 8; the driver then writes devctl = 0 (nIEN off) and `0xc0003024 = 0x50`/`0x40`; 2.4071 s **0xEC** IDENTIFY again, issued by `0x1416f0` on a heap ATA object `0x1fd44dc`. **After this, nothing.** |
| Disk reads | 0 sectors |
| Hooks | `0x9439c` (boot spin-up wait) hit at 2.40 s with `n = 0x2c4020` (29 s = 31 s − 2 s uptime: confirms the static reading); `0x1416f0` once; `0xe0078`, `0x134c58`, `0xdf014`, `0xdf700`, `0x45924` never |

**Stall:** the interrupt-driven IDENTIFY at 2.407 s waits for an IDE completion interrupt. The emupod
core models INTRQ only as a latch bit in `0xc0003024` (bit 4), only for machines booting from a
flash chip (`lib.rs:569`), and never raises an interrupt-controller line for the disk. 1.x and the
disk-mode program poll; the 2.3 driver sleeps until the interrupt. The last MMIO it touches are
`0xc0003024` (IDE config, read 0x40) and `0xc00031fc`/`0xc00033f8` (status 0x40); after that only
the timer and interrupt registers.

To get further, the core needs to: (a) return bit 4 of `0xc0003024` for DRAM-boot machines too,
(b) raise the IDE IRQ in `0xcf001000..` when `intrq` sets (the line number has to be found: one of
the bits in the 2.3 enable mask `0x405808`/`0x80`/`0x4`), and (c) model `0xcf005018`/`0xcf00501c`.
Only then can the idle-timeout and read-ahead hooks fire.

## Part A, round 2: IDE interrupt + clock model (2026-10-28)

Core changes in the scratch clone (`build/emupod/rust`, all opt-in via environment variables;
1G/2G unchanged): `EMUPOD_ENTRY` (reset pc, now also honoured by `boot()`); `EMUPOD_IDE_IRQ=<bit>`
(the drive's INTRQ as a level on that interrupt-controller line, cleared by a status-register
read or by the `0xc0003024` bit-4 ack, and `0xc0003024` bit 4 now reflects INTRQ for DRAM boots);
the clock block `0xcf005000..0x3c` stored, with defaults `0x18 = 1`, `0x1c = 3`. With these the
**stock** `build/fw/osos.img` boots, so the `osos-emu.img` patch is no longer needed.

**IDE IRQ line: bit 1** (**confirmed** by the trace). The ATA driver brackets every command with
`0xcf001028 = 0x2` / `0xcf001024 = 0x2`, and its ISR reads `0xcf001000 = 0x2`, reads `0xc0003024`
(0x5c), acks with `0xc0003024 = 0x58`, then reads status. Bit 1 is not one of the named
branches in the dispatcher `0x1282ac`; it is handled on the default path (`0x13ddc0`/`0x1349a8`).
Bit 3 (`0x13f090`) is something else. My first guess, 3, was wrong.

Result with `EMUPOD_ENTRY=0x28000000 EMUPOD_IDE_IRQ=1`, 45 emulated seconds:

- **Reaches the UI**: 8,631 LCD writes; the screen shows the first-run **Language** menu (the
  synthetic card has no settings and no iTunesDB). The first full screen appears at about 26.6 s.
  PNG: `build/emupod-work/lcd.png`.
- ATA: 13 commands, 9 IDE interrupts, **8 sectors read**, all single-sector:
  READ SECTORS `0x20` (builder `0xdf700`) at LBA 0, 0, 0, 0x3f, 0x1003f, 0x10040, 0x11bf1
  (MBR, firmware partition, FAT32 boot sector/FSInfo/FAT), SET MULTIPLE `0xC6`, then
  READ MULTIPLE `0xC4` (builder `0xdf014`) at LBA 0x11bf1, count 1, at 2.567 s.
- **That READ MULTIPLE never completes in the emulator**: its interrupt is pending (`irq_pending = 2`)
  but is never delivered, because my line model only offered the IRQ at the start of a slice, and
  while the CPU idles every slice starts inside the timer ISR (I flag set). The earlier reads
  worked only because the CPU was busy-waiting. This is a bug in my model, not a missing
  peripheral. A fix is written (`ide_line()`, also checked after `run_cpu`, and it wakes an idle
  CPU) and needs one more rebuild.
- **Spin-down path, observed:** disk-power messages (type 14) reach `0x134bc8` at 2.555 s, then
  repeatedly at 22.996–23.05 s and 26.61/26.70 s (sub-op 4 → op `0xFC` per unit). At **25.68 s and
  28.75 s** case 2 runs: `0x134c58` sees unit 0 (the ATA object `0x418b9c`) in state 6 and sends op
  `0xE0`, then `0xFD`, through `0x9e83c` → `0x9da1c` (on the per-drive object `0x1fd44dc`).
  STANDBY IMMEDIATE itself is **not** sent. `0x9da1c` first runs the "re-init after wake" path
  `0xc347c` (because `obj+0x1e0` is set), whose BSY/DRQ check (`0x13f9c4`, 30 × 10 µs) fails, since
  the stuck READ MULTIPLE leaves DRQ set. So it returns `0x400` before reaching the builder
  `0xe0078`.
- **Idle timeout: provisional, ~23 s.** The first spin-down attempt (25.68 s) comes 23.1 s after
  the last disk command (2.567 s). The next is 3.07 s later (28.75 s, probably a retry after the
  failure). Because the last read never completed and the UI only appeared at about 26.6 s, this is not
  a clean measurement yet. Rerun after the `ide_line()` fix to confirm.
- **Read size per wake:** not measurable yet (no iTunesDB or music on the synthetic card, and
  the read path stalls). Needs the fix plus a card with music.

## Part A, round 3: idle-IRQ fix, clean idle timeout, music card (2026-10-28)

Core fix (scratch clone, built by me this time): the drive's IRQ is also offered after each
`run_cpu`, which wakes an idle CPU (`Machine::ide_line()`). The same mechanism delivers a key edge
that `edge()` could not deliver at once (`gpio_late`; only with `EMUPOD_IDE_IRQ` set).

**Disk idle timeout: 12.8 s (confirmed in emulation, stock 2.3, empty card).**

- The boot reads finish and the UI is up at 7.7 s. 172 ATA commands and 169 IDE IRQs; 119 sectors read,
  all single-sector READ MULTIPLE `0xC4` (builder `0xdf014`), plus 47 single-sector WRITE MULTIPLE `0xC5`
  around 3.7–3.96 s (settings/FAT updates on the fresh card).
- Last disk command: a read at **8.1025 s**. **STANDBY IMMEDIATE `0xE0` reaches the drive at
  20.9334 s** (`0x134c58` → `0x9e83c` → `0x9da1c` → `0x9db0c` → builder `0xe0078`; emupod's power log
  marks the drive powered down). Timeout = **12.83 s** after the last access. The disk-power
  messages (sub-op 4 → op `0xFC`) at 3.03–8.12 s are per-access notifications; the last one is at
  8.1199 s, which is 12.81 s before the standby. I did not find a literal constant for it (no
  1280/12800/12.8e6 near the power code); it is probably computed or counted in ticks.
- Round 2's "~23 s" was wrong: that run had the stuck read.

**Test card with music:** `build/emupod-work/music-card.img` (scratch). The synthetic 256 MB card
plus `iPod_Control/iTunes/iTunesDB`, a minimal mhbd v9 (2 tracks + master playlist) written by
`tools/emupod/mkcards.py` with the repo's mhod layout, and two sine-tone MP3s made with
`nix shell nixpkgs#sox nixpkgs#lame`: `TONEA.mp3` (3 min, 128 kbps, 2.9 MB) and `TONEB.mp3`
(12 min, 320 kbps, 28.8 MB, bigger than the about 26.8 MiB music cache, so a full play would show
more than one wake). Files copied in with `nix shell nixpkgs#mtools`.

**Playing a song: not reached.** Two input problems:

1. Hold: ~~on the 3G, GPIOA bit 5 low = Hold on~~ **wrong, see round 4**: stock 2.3 reads bit 5
   **high** as Hold on, so setting it high is what made every key get dropped. Leave it low.
2. Key edges: like the disk IRQ, `edge()` only offered the GPIO IRQ (bit 14) while 2.3's idle
   loop had IRQs masked. Fixed (`gpio_late`). Now the GPIO ISR `0x124cd8` runs, reads
   `0xcf000040 = 0x2`, flips `0xcf000060`, acks `0xcf000070` and reads GPIOA input `0x3d`
   (Select down) and then `0x3f` (up). **But the Language menu does not react** (LCD count unchanged
   after Select). Not traced yet. The next step is to follow the handlers registered at
   `0x420ae8` (called through `0x8a1f0`) and find which task consumes the key event. The 3G's
   button handling may also want the touch wheel or a held key polled by a timer.

So the read size per disk wake is still open. The static answer from B.3 stands: refill when
less than 20 s of audio is cached, and the cache is the heap.

## Part A, round 4: keys and wheel work (2026-10-28)

No core changes. The only blocker was Hold: `0xbe110` (where every button ends up) returns early
when `0x7a9b8` says Hold is on, and that compares GPIOA bit 5 with a fixed level 1. With bit 5
**low**, Select on the Language menu goes to the main menu, and the wheel, Menu and Play work too.
The full button, event and code map is in `docs/re-notes.md` (Key input).

- Wheel: GPIOA bits 7:6 are a quadrature pair (event `0x71`, decoder `0x90c94`). One menu item
  takes 4 to 6 steps.
- Screenshots: `e.lcd.make_screen()` starts blank and only fills in if there were LCD writes since
  the last update, so a shot taken after an idle stretch is empty. Read `m.lcd_update(); m.lcd_px()`
  instead.
- Driver: `build/emupod-work/scripts/ipod3g.py` (`Pod().press("select")`, `.scroll(n)`,
  `.shot(...)`). Run it with plain `python3` from that folder; `-I` hides the module.
- With it, Music › Songs lists "Tone A" and "Tone B long" from the test card, and Select on a song
  starts playback (▶ in the title bar). The read size per disk wake can now be measured by playing
  TONEB.

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

- **Idle timeout: NOT FOUND within the timebox.** What is known (**confirmed**): the drive's own
  standby timer is turned off (IDLE `0xE3` with count 0, `0xdebac`), so the timeout lives in osos.
  It works by posting message type 14, sub-op 2, to the disk-power task (`0x13bc2c`).
  `0xfac38`'s direct callers send sub-ops 9 (`0x9b964`), 8 (`0xb266c`) and 5, but not 2. So the
  sub-op 2 message is built inline somewhere else, probably by a timer callback. Next step:
  find stores of `#2` to `[msg,#24]` near a `strb #14,[msg,#20]`, or hook `0x134c58` in Unicorn and
  backtrace. **guess**: the value is a few seconds to tens of seconds, kept in a settings word
  next to the power-state table at `0x3702a0` / `0x422080`.
- **Drive power GPIO: none found** (**likely**). No store to GPIO output registers
  (`0xcf000020..2c` / `0xcf000060..6c`) sits on the ATA or power paths. The only direct GPIO
  output write I found, `0x13fd30` → `0xcf000028` and onward to `0x13fe30`/`0x140614`, is the
  audio codec. Rockbox's ipod `ide_power_enable` is also a no-op, which fits a drive that
  is only ever put to sleep with STANDBY IMMEDIATE and never has its power cut. A power-off
  would have to come from the PMU or a hard power-down, which I did not check.

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
  skip protection" marketing. Still open from the original note: The task has no size
  constants of its own. They will be in the code that sizes cache segments from the heap
  (`0x33500` probes DRAM; the heap is `0x453c304` (uncached alias) up to
  `0x4346364 & ~0xfc000000`-based top, stored at `heap+0x14/+0x18`). Next step: xref `0x439bf0`
  and `cache+0xb5c` writers, and look for the free-space or "remaining ms" compare that signals
  `0x439c10`.

### Summary for the power question

- Spin-down: STANDBY IMMEDIATE `0xE0` only, from `0x134bc8` case 2 (`0x134c58..0x134c7c`). confirmed.
- The drive's own timer is disabled (IDLE `0xE3`, count 0, `0xdebac`). confirmed.
- Spin-up: implicit on the next command. The driver waits up to 3.1 s (`0x97830`) after a
  reset or wake, and up to 31 s after boot (`0x9439c`). The default command timeout is 10 s. confirmed.
- Refill trigger: less than 20 s of cached audio left ahead of the play position (`0x45924`, likely).
- Idle timeout value and the exact read-ahead size: not located yet. The spin-down path goes
  through the message system (type 14, sub-op 2 → `0x134bc8`). Statically, the only
  constructor of type-14 messages (`0xfac38`) is called with sub-ops 5/8/9, so sub-op 2 is set
  some other way. The fastest route is dynamic: hook `0x134c58` (or `0xe0078`) in an emulator
  and backtrace. That needs the emupod build, which this session is not allowed to run.

## Follow-up pass (2026-10-28, second request)

- I tried the emupod build again: still refused by the permission classifier.
- Found the refill low-water mark (20 s, `0x45760`, see B.3).
- Ruled out: a second type-14 message builder (scanned every function for an immediate 14
  stored to `+0x14`: only `0xfac38` and the receiver `0x134d3c`).

## Shortcut attempt: play without the UI (2026-10-28, 15 min timebox): not reached

- The goal was to call the firmware's play function on TONEB directly and log READs per wake. I did not
  find a callable "play track" entry in the timebox. What I checked: `0x54de4` (allocates a
  0x424-byte per-track cache object and links it into the cache; called from `0x999ac` and
  `0xe4bc8`, i.e. player/database setup) and `0x94918` (the playback tick that calls the refill check
  `0x45760`). Neither can be called on its own without the playback controller's state, which
  is not mapped yet.
- So **bytes per wake and time between wakes are still unmeasured.** Two ways forward: (a) fix
  the UI key path (the GPIO ISR already sees Select; trace where the event goes), then play from
  the menus; or (b) map the "Now Playing" controller (strings `Now Playing` at `0x18fde0`/`0x190818`
  and `NowPlayingMode` at `0x3074b0` are the way in) and call its start-playback method.
- All scratch emupod changes are exported as one diff: `tools/emupod/emupod-gen3.patch` (179 lines:
  `rust/pp5002/src/lib.rs`, `ata.rs`, `rust/pybind/src/lib.rs`), not committed anywhere.

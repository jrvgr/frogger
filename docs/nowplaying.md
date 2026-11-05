# Now Playing (firmware 2.3) and the cover-art page

Goal: Now Playing opens on a new page with the song title, cover art and the progress bar;
Select cycles **cover art → Apple's page → scrubbing → rating → cover art** (with
the title alone on top, no title bar). Status labels as in `re-notes.md`. Tools are in
`tools/emupod/` (see its README); the UI bytecode is in `docs/tcmd.md`.

**Status: works in emupod and on a real 3G** (covers switch cleanly on Next). The page switches slide like Apple's screens (below, "The slide"); that part is tested in emupod, not yet on a device. Now Playing opens on the cover
page (title on top, no title bar, the 72×72 cover, the progress bar and times); Select goes to
Apple's page, then Apple's scrubbing and rating; the third Select, Select after a scrub or the 5 s
timeout brings the cover page back. Transitions are drawn in the same frame as the key, except that the rating dots
stay about 25 ms before the progress bar replaces them (below, "Open").

## Seeing it in emupod (**confirmed**)

Playback used to deadlock the emulator; that's fixed in the scratch core (the `irq_unmasked`
hook, `tools/emupod/emupod-gen3.patch`; details in `tools/emupod/README.md`). `probes/playshot.py` plays Tone A
and screenshots Now Playing. The emulated audio still stops after about 2000 sample FIQs, so the
clock and the progress bar stay at 0:00 (**open**: an emupod audio-model gap, not the firmware).

## The screen: View `0x25ee` (**confirmed** from the resource, roles **likely**)

A count (9), then elements. Each element: `size` (of the rest), flags, type fourcc (stored
reversed), id, then four position triples (top, left, bottom, right: `flags/anchor`, value, 0)
and a few type-specific words (font, colours). iPodWizard's `resource_type_view_elem` is close.

| # | Offset | Type / id | Position (top, left, height, width) | Role |
| --- | --- | --- | --- | --- |
| 0 | `0x004` | `Str 0x331f` | 4, 5, 9, auto | "1 of 2" |
| 1 | `0x05c` | `BMap 0x25ed` | prev, 83, 9, 9 | the small icon beside it |
| 2–4 | `0x0a8`… | `Str 0x335e`, `BMap 0x25ec`, `0x25eb` | prev, … | the rest of that row (right side) |
| 5, 6, 7 | `0x198`, `0x200`, `0x258` | `Str 0x3319`, `0x331a`, `0x331b` | 18 / 35 / 52, 2, 15, −2 | title, artist, album |
| 8 | `0x2b0` | `None 0xff33` | below the previous element | the progress bar and times (native) |

(Earlier versions of this table had `0x25ed` as the progress bar; it's the icon, **confirmed**
by moving it.)

**Element format** (**confirmed** by moving elements in emupod): a size word (bytes after it),
flags, fourcc, id, three words (`0x3300, 0, 0x800`-like: colour/font class, **guess**), then four
coordinates of three words each, `0, anchor, value`, for top, left, height, width, then
type-specific words (a `Str` has its font, `0x255d0000`, and the title its marquee timing,
`0x1388` = 5 s). Anchors: `0x80000002` the value as is, negative counting from the far edge;
`0x80000008` a height; `0x80000004` a width; `0x80000014` fit the content; `0x100` the same as
the previous element; others (`0x200`, `0x300`, `0x400`) are relative placements not decoded yet.
The bar widget (`0x300`) sits just below the element before it, so moving the elements above it
moves the bar.

Opening Now Playing fetches `BMap 0x25eb/0x25ec/0x25ed/0x3329` and `Str 0x3321` through the
bundle lookup we already hook (`0x8100c` → `0x875c4`, `string_hook`), which is where a
cover-art bitmap can come from.

## Select on Now Playing (**confirmed** by VM trace, `tools/emupod/probes/npselect.py`)

A state machine in bytecode. Each press runs the current state's function, which calls the
next state's setup, arms a 5 s timeout back to normal (`0x08de.method_64(5000, next)`) and
changes what the bar area shows (`0x08de.method_6a(…, 0x57/0x58, …)`):

| Press | Functions (index / id) | Mode |
| --- | --- | --- |
| 1 | 169 `0x745` → 177 `0x74d`, 172 `0x748` | scrubbing (knob on the bar) |
| 2 | 172 `0x748` → 171, 182 `0x752`, 181 `0x751` | rating (five dots) |
| 3 | 183 `0x753` → 170 `0x746`, 151 | back to normal |
| 2, after scrubbing | 172 `0x748` → 171, 170 `0x746` | back to normal (the knob moved: `0x08eb.method_10c`, at `0x2e74`) |

So the cycle has three ways back to normal: Select while rating (fn 183), Select after a scrub
(fn 172's call of fn 170, `NP_FN_SCRUBBED`) and the 5 s timeout (fn 173). Each brings the cover
page back (`tools/emupod/npscrub.py` checks Select after a scrub).

## How the pages work (**confirmed** in emupod; `payload/nowplaying.c`)

The loader (`loader/nowplaying.c`) rebuilds View `0x25ee` at boot into the payload (`np_view`)
and points the bundle's index entry (`0x184184`) at it, like `loader/settings.c`. The rebuilt View
is Apple's, unchanged, plus a 10th element: a `BMap` with Frogger's id `0x3f01`
(`FROGGER_BMAP_ART`) at (19, 44), 72×72 (`payload/nowplaying.h`). So the boot layout is exactly
Apple's page, and the cover page is made at runtime by changing the live objects:

- **The two pages.** `show_cover` hides the title bar (View `0x2503`) and the seven elements the
  cover page doesn't show (the "1 of 2" row, artist, album) with the firmware's own SetVisible
  (`vtable + 0x94`, which repaints), lays the page out for the cover (`set_layout(1)`) and shows
  the art. `show_apple` does the reverse.
- **Layout through coordinates, not rectangles.** The firmware lays elements out again by itself
  (`0x42768`, when a screen opens and when Select's cycle returns to normal) from each object's
  coordinates (`+0x28..+0x54`: reference, anchor, value for top, left, height, width), so
  rectangles written directly don't last, and a `Str` draws its text from an origin that only
  its SetRect (`vtable + 0x58`, `0xd8914`) updates. `set_layout` therefore changes coordinates:
  the bar container's height becomes a fixed 0 (`+0x44` anchor `0x80000008`, `+0x48` 0; Apple's
  is `0x80000018`, fit the content, 19 px), the View's absolutely placed elements move down by
  19 to stay put, and the title's top becomes `NP_TITLE_TOP`. It then writes the rectangles and
  clips (`+0x58`, `+0x78`) the root's layout would give the bar, the screen container and the View,
  and lays out only the View again (`0x42768(view, 1)`): laying out the root would resize the
  screen container and lay out all 79 screens (about 150 ms). The firmware's later root layouts
  then find nothing to change.
- **When.** Three hooks (`payload/hooks.S`, table in `tools/mkpayload.py`):

  | Hook | Site | Does |
  | --- | --- | --- |
  | `vis_hook` | `0xb4578`, the first instruction of every SetVisible | The art being shown means Now Playing is opening (it's the View's last child): show the cover page. Hidden: closing. While the cover page is up, Now Playing showing the bar or the hidden elements again is skipped. |
  | `vm_hook` | `0x9bab0`, the bytecode interpreter's opcode fetch | Now Playing's Select handler (fn 169, `NP_FN_SELECT`) on the cover page: show Apple's page and return through `NP_FN_RETURN`, so Apple's page starts in its normal state. Back to normal (fn 183 `NP_FN_RATED`, fn 173 `NP_FN_TIMEOUT`, fn 172's call of fn 170 after a scrub `NP_FN_SCRUBBED`): show the cover page. Menu (fn 160, `NP_FN_MENU`): put Apple's layout and the bar back before the screen slides away. |
  | `trans_hook` | `0xe3aac` in `0xe3a9c`, which starts a screen stack's slide | The bar area (`None 0xff33`, a screen stack with progress, scrub and rating views) sliding back to the progress bar on the cover page: the slide lasts 1 ms, so it isn't a wipe across the new page. |
  | `lcd_hook` | `0xd2db4`, the first instruction of `lcd_update_rect` | While a page switch's new page draws, the LCD is held (the call is skipped and noted). `lcd_flush` goes past it. |
  | `drawn_hook` | `0x68e60` in the end-update `0x68dfc`, after its drain | The new page is in the framebuffer: slide (`np_drawn`). |

  `vis_hook`, `vm_hook`, `trans_hook`, `lcd_hook` and `drawn_hook` are entered with a plain `B`, not `BL`
  (`BRANCH_HOOKS`): they sit where `lr` is still live, and a `BL` there overwrote the return
  address and hung the boot.
- **Timings** (emulated): a page switch about 20 ms; Menu on the cover page: the bar replaces the
  title at 25 ms, the slide is done by 200 ms; rating → cover: the cover at 20 ms, the progress
  bar replaces the dots at 45 ms. Frame captures: `tools/emupod/npcycle.py` (each step 60 ms after
  the key and settled, plus a contact sheet `cyc_sheet.png`).
- **The slide** (**confirmed** in emupod, `tools/emupod/npslide.py`). Apple's slide is a screen
  stack's (`0xe3a9c`) between two screen slots, each with its own View, so it can't run between
  two states of one View. Frogger slides the framebuffer instead. The firmware draws into it
  (`0x3835a0`, 128 rows of 40 bytes, 2 bits a pixel) and copies each dirty rectangle to the LCD
  right after drawing it (`lcd_update_rect 0xd2db4`, the only LCD writer), in the drain of the
  last end-update of a batch (`0x68dfc`), a draw cycle (~35 ms) after the key, sometimes in
  several rectangles. So `np_vm` keeps the page that's up before switching (`slide_begin`),
  `lcd_hook` holds the LCD while the batch draws the new page, and at the drain's end
  (`drawn_hook`) `np_drawn` copies the new page and draws 8 frames, 25 ms apart (the µs clock
  `0x87de0`, on the UI thread), in whole 8-pixel columns (an LCD word, two bytes): the cover
  page out to the left and Apple's page in from the right on Select; the reverse on the way
  back. Then the new page stays up. If no drain comes within 0.5 s, `np_tick` lets the LCD go.
  On the way back the bar area still shows the rating dots or the scrub knob until its own
  slide ticks, so it slides in blank and the progress bar is drawn into it after. Timings
  (emulated): the slide starts ~20 ms after the key and takes ~200 ms.

### Open

- **The rating dots stay ~25 ms** on the way back to the cover page (since the slide: for one
  frame after it; the slide itself shows the bar area blank). While a slide runs, the
  stack draws its old view until the slide's first tick. Making the stack switch views directly
  had no effect (it manages its sub-views' visibility itself), and skipping the slide left it
  with no current view (the progress bar vanished, on Apple's page too). Removing those frames
  means redoing the slide's finishing code (`0xe1fec`), which is tied into its offscreen
  compositing.
- **Select, then a slow second Select** (about 1.5 s apart): scrubbing returns to the cover page
  about 0.5 s after it starts. The build before these changes does it too.

### How it got here (what didn't work)

- Writing rectangles directly (`+0x58`) and clip copies: the screen container keeps more copies
  of (19, 0, 128, 160) at `+0xd0`, `+0xe0`, `+0xf4` and its slide frames at `+0x1a8`, `+0x200`,
  but changing them, the title's cached text box (`+0x94..+0xa8`) or the hidden bar variants'
  rectangles changed nothing: the root layout put the screen container back below the 19 px bar,
  and its Draw (`0x65ef0`) clips to its own `+0x58`, so the title's Draw (`0x6641c`) got an area
  starting at 19 and returned. The screen buffer (`0x3835a0`, 40-byte rows, 2 bits per pixel)
  showed the title was never drawn there.
- Laying the root out again (`vtable + 0x78`) did work, but took about 150 ms and delayed Menu's
  slide by 250 ms.
- `0x37b2d8` is the display object and `+0x2c` the area of the flush in progress
  (`lcd_update_rect 0xd2db4`), not pending invalidations: writing it repaints the wrong pixels.
- A "find child" method: code at `0xad1e8` calls `vtable + 0x48` as `(obj, fourcc, id)` (**likely**
  "find the child element with this type and id"); not needed in the end, since the objects are
  found from the art element's parents.

## Covers (**confirmed** in emupod and on Crate's output)

- **`BMap` format** (**confirmed**): 8 zero bytes, `height`, `width` (words), `bytes per row`,
  **bits per pixel** (1 or 2), `0`, `0` (halfwords), data length (word), then the pixels, top bit
  first, 3 = black, rows padded to 4 bytes (iPodWizard `IPOD_PICTURE_HEADER`). The ">" arrow
  (`0x2579`) this was first read from is a 1-bit bitmap; covers had its 1 too, so the firmware
  drew them as 1-bit (the left half, twice as wide, in stripes; simple test patterns hid it)
  until it became 2 (`0x256d`, 44 px wide with 12-byte rows, is a 2-bit one).
- **Drawing a new cover** (**confirmed** in emupod with a real 535-track library, eight songs in a
  row): the art element draws live from our buffer (`+0x6c` is a bitmap object pointing at it),
  but nothing repaints it on its own. `art.c` sets `np_art_dirty` when it loads a cover, and the
  next bytecode instruction (`vm_hook`, the UI's own loop) calls the firmware's invalidate
  `0xda3cc(art)`. SetVisible's own repaint (`0xe0bc0`) only runs for objects with flag `0x10`,
  which the art doesn't have, and laying the View out again repaints only what moved.
- **The file**: `iPod_Control/iTunes/FroggerArt`, written by Crate (`FroggerArt.swift`) at the end
  of every sync, right after the iTunesDB, or by `tools/coverart.py`. Layout in
  [file-formats.md](file-formats.md#froggerart-the-covers) and `payload/nowplaying.h`: a 24-byte
  header (`"FRGA"`, version 2, size 72, entry count, image count, bytes per image), then for
  version 2 a 24-byte entry per song with a cover (its **track key**: dbid, track id, size, length;
  and the image), then 72×72 2-bit images in `BMap` rows (20 bytes per row, 1440 per image). Version
  1, still read, had a u16 per track **position in the iTunesDB** instead and fit only the database
  it was made with. An album's tracks share one image, and so do identical pictures. Crate takes the
  library album's cover, or the picture embedded in the song file on the iPod, scales it to fill the
  square and dithers it to four greys. How (levels, brightness, contrast, midtones, sharpening,
  Floyd–Steinberg/Atkinson/ordered) is set in Crate's Cover Studio (iPod page › Frogger card), which
  previews it on a mock of this page; the defaults stretch the levels and use Floyd–Steinberg.
  `Crate --froggerart OUT` writes the file for the connected iPod to OUT instead, and
  `tools/emupod/checkart.py OUT --itunesdb iTunesDB --png x.png` checks it the way the payload reads
  it and draws the covers.
- **Finding a song's cover**: the firmware's track records keep neither the mhit id (`+0x1c` stays 0
  on real 2.3; `re-notes.md` and the Unicorn harness assumed otherwise) nor the dbid. `track_hook`
  sees each record with its position (`[sp+0x4bc]`) and mhit header, and `tracks.c` keeps both. The
  records are allocated in blocks of 100, `0x1d0` bytes apart within a block, and the blocks
  anywhere on the heap (**confirmed** in emupod with a real 535-track database: six runs, at
  `0x1d4ea70`, `0x1d39eb0`, …), so `tracks.c` keeps where each run starts (up to 240 runs) and
  `tracks_position` finds a record in them (past that, a search of its table). The first version
  assumed a single run; with the 2-track test database it worked, on a real iPod every cover showed
  the "no cover" frame (a thin grey border). For version 2 the cover task reads the file's table once
  per database and keeps an image per position (`by_pos`); version 1 is used only if its track count
  is the database's.
- **The song now playing**: `0xbca48(record)` loads a track for playback. It runs from `0xb9170`
  when a song starts (play, Next, Prev) and from `0x94a5c` to preload the next one, so
  `play_hook` replaces the call at `0xb916c` (`bl 0xbca48`), notes that track, then continues into
  `0xbca48`. The cover itself is read on the UI's side, at the next bytecode instruction
  (`np_vm` → `np_art_update`): when a song ends by itself `play_hook` runs on the playback side,
  and reading the card there froze a device (on a CF-to-SD adapter) at the second
  song, with covers broken until a restart. An album's next song doesn't read its image again,
  and a failed read shows the frame and is tried again when Now Playing next opens.
- **The "no cover" frame** has a pixel frog in the middle (`art.c`, `art_none`). When the song
  just has no cover, that's all. When something went wrong the frog frowns, an icon in the bottom
  right says what, and a small digit in the bottom left which step (`WHY_*`): an SD card, a read
  failed (2 the file didn't open, 3 its header, 6 the song's index entry, 7 its image); a question
  mark (1), the track isn't one `track_hook` saw load; a refresh arrow (5), a version 1 file made
  for another database (track count differs), so sync again; a warning (4), it isn't a FroggerArt this
  payload reads. A song a version 2 file doesn't name just has no cover. The card ones are tried again when Now Playing opens.
- **The firmware's file calls** (**confirmed** from the iTunesDB parser `0xc54bc` and by use):

  | Call | Address | Arguments |
  | --- | --- | --- |
  | open | `0x403fc` | `(path, file, 0x20000, 'data')`; 0 means OK; `file` is the caller's (< 0x28 bytes) |
  | read | `0x404ec` | `(file, &len, buf)` |
  | seek | `0x4069c` | `(file, pos_lo, pos_hi)` |
  | tell | `0x40350` | `(file, &pos64)` |
  | close | `0x40110` | `(file)` |
  | volume | `0xb1d50` | `()`; a path is this word, then `iPod_Control\iTunes\Name` with backslashes |

- **Testing**: `tools/emupod/mkart.py` puts a FroggerArt with test pictures (a gradient and a
  checkerboard) on a copy of the test card (`art-card.img`); `artplay.py` plays both songs and
  screenshots Now Playing. `dbid.py` checks each song keeps its cover after a new iTunesDB with
  other track ids and order, and that a version 1 file still works.

## How the screen is put together (runtime)

- **Views are laid out once, at boot** (**confirmed**). Changing View `0x25ee` in RAM after
  boot changes nothing; changing it in the image before boot moves things.
- **The tree**: the root (`None 0x2502`, the whole screen) has two children: the bar container
  (View `0x2503`, `(0, 0, 19, 160)`, with the bar variants `0x25e5` (▶, title, battery),
  `0x25e6`, `0x2883`, `0x4482`, `0x3d01`, `0x4b80` and `None 0x2504`) and the screen container
  (`0x250d`, vtable `0x2c6ec`, `(19, 0, 128, 160)`, all 79 screens; Now Playing's View is one).
  Setting `0x25e5`'s height to 0 in the image (`0x19cf0c`) removes the bar on every screen
  (**confirmed**), which is why the cover page changes it at runtime instead.
- **Object layout** (**confirmed** in emupod). Offsets from an object's start:

  | Offset | Element | View |
  | --- | --- | --- |
  | `+0x00` | vtable (`0x27218` a `BMap`, `0x2a288` a `Str`; slots hold offsets from the vtable) | vtable (`0x28d38`) |
  | `+0x10` | parent | parent |
  | `+0x18`, `+0x1c` | type, id (low halfword) | the same (`None`) |
  | `+0x20` | flags: `0x800` shown, `0x1000` hidden | the same |
  | `+0x28`–`+0x54` | the four coordinates (reference, anchor, value) | the same |
  | `+0x58` | rectangle on the display: top, left, bottom, right | its clip (also at `+0x78`) |
  | `+0x70` | a `BMap`'s bitmap pointer (ours: `&art`, which is why Next updates it) | child array; `+0x6c` the count |

  Heap addresses change with the library size (the database loads before the UI is built), so
  the payload finds the objects from the art element rather than hard-coding them.

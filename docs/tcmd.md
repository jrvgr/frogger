# TCmd: the UI bytecode in osos 2.3

Apple's menus run on a small bytecode VM. Each menu item names a bytecode function, and that
function sends messages to native objects (preferences, the menu system and so on). These notes
cover what that VM looks like, how a Settings item is wired, and what's still missing before
Frogger can add its own Settings entries. Status labels follow `re-notes.md`: **confirmed** (seen
in the code or in an emupod trace), **likely**, **guess**.

Tools:

    tools/re/tcmd.py info | fn N | at OFFSET | all | check   # disassembler (this doc's notation)
    tools/re/resources.py menus                             # Menu resources, 10 words per item
    tools/emupod/settrace.py ROW                            # VM trace: Select on Settings row ROW
    tools/emupod/vmtrace.py ROW                             # VM trace: Select on main-menu row ROW

The emupod scripts need the scratch emulator (`third_party/emupod`, set up by `tools/emupod/setup.sh`; see "Running it" below).

## Prior art

Nobody has published a decoder. [iPodWizard](https://github.com/Stehfyn/iPodWizard-stable)
(`src/firmware.h`, `resource_type_tcmd`) parses the container (header, offsets, "command sets")
and calls TCmd the "command table", but leaves the bytecode as unknown bytes. RepriseOS
([osos-lab](https://github.com/lgreitis/osos-lab)) adds Settings entries to the Classic 6G/7G,
but that firmware's UI system (named screens/`ITEM` blocks) is different; only its approach
carries over: clone a stock Settings item and point its action at your own code.

Not the same thing: osos also contains CompuPhase's **Small/AMX** VM (asserts
`amx->flags==0`, `op>0 && op<OP_NUM_OPCODES`; switches at `0x10ec18`/`0x10f428`, 135 word
opcodes). TCmd doesn't use it.

## The resource (**confirmed**)

`TCmd` id `0x2380` at `0x191dcc` (`0x98920` loads it by fourcc, `0xa1b54` parses it; the code
runs in place). Layout, as `tools/re/tcmd.py info` prints it:

| Where | What |
| --- | --- |
| `+0` | word `0x928` |
| `+4` | halfword 0, halfword pool count (`0x96` = 150) |
| `+8` (`0x191dd4`) | constant pool, 150 words: small negatives, fourccs (`'Weel'`, `'GSlp'` …), `0x33xxxxxx` tagged values |
| then | halfword function count (`0x244` = 580), halfword n, n halfwords (`153, 335`), pad to 4 |
| `0x192034` | 581 words: function offsets from the code base (the last one is the end) |
| `0x192948` | **code base**: the functions |

Runtime globals (`0xa1cdc`…): `0x4429ac` pool, `0x4429b0` code base, `0x4429b4` function table,
`0x4429b8` pool count, `0x4429c0` word0, `0x4429d4` function count.

A function is a 10-byte header and then the code, with a `43 05` ("push nil; return") at the
end and zero padding to 4 bytes:

| Header halfword | Meaning |
| --- | --- |
| 0 | **function id** (`0x99`…`0x8dd`, unique) |
| 1 | argument count (**likely**) |
| 2 | local count (**likely**: fn 273 has 2 and uses locals 0 and 1) |
| 3 | max stack depth (**confirmed** in emupod: a send needing more stack than this silently stops the VM; `re-notes.md`, "Browsing the Music lists") |
| 4 | code length |

With the opcode lengths below, 579 of the 580 functions decode to exactly their length
(`tcmd.py check`); fn 269 (Shuffle) has a variable-length op.

## The VM (**confirmed** unless marked)

Interpreter: **`0x9ba54`**. The VM object holds the pc at `+0x20` and the stack pointer at
`+0x18`. Each step reads the opcode byte, looks it up in a 4-byte-per-opcode table at
**`0x373ab0` (RAM, filled at boot; copied into `tcmd.py` as `OPS`)**, reads a big-endian 16-bit
operand when there is one, and dispatches through the switch at `0x9bbc4` (opcodes `0`–`0x7f`).
`0xa3914` decodes tagged values (the low 2 bits are the tag; tags 1/2 index the pool).

Table entry: byte 0 = `(pops << 4) | length`, where length is 1 or 3, and `0xf` means variable
(`0x23`, `0x3a`, `0x46`, `0x47`, `0x79`). Byte 1 is a group (`c1` pushes, `a1`
loads/stores, `b1` sends). The halfword's low nibble is the operand kind (1 branch offset,
2 constant/selector, 3 raw number, 6/7 slot load/store); the nibble above it is a storage class.

Opcodes seen in traces:

| Op | Form | Meaning |
| --- | --- | --- |
| `3b k` | push constant | an object or function reference (`0x08df`, `0x0918`, `0x0827`) |
| `35 s` | lookup | selector `s` on the object on top: pushes the method |
| `39` | args | marks where the arguments start |
| `3a n` | send | call the method/function under the args with `n` arguments; bytecode callees jump, native ones run |
| `58 n` / `54 n` / `3c k` | push | int literal / argument `n` / another constant kind (**likely**) |
| `56 n` / `57 n` | local | push / store local `n` |
| `6c g` / `6d g` | global | push / store global `g` |
| `42` / `43` | push | self (**guess**) / nil |
| `06 o` / `07 o` | jump | always / if false (**likely**); `o` is signed, from the instruction's own address |
| `02` | drop | |
| `05` | return | pops the return value |
| `51` | drop-like after a store (**guess**) | |

Calling a bytecode function directly is `3b <fn id>; 39; …args…; 3a n` (fn 401 does
`3b 08 27; 39; 3a 00 00`, which calls function `0x0827`).

## Menus and a Settings item (**confirmed**)

`Menu` resources are a count and 40-byte items (`tools/re/resources.py menus`). In Settings
(`Menu 0x278d`, 14 items):

| Word | Meaning |
| --- | --- |
| 0 | `0x24` |
| 1 | item kind/flags: `0x26` with a value or arrow, `0x22` plain, `0x20`/`0x24` others |
| 2 | `0x1b2a` in Settings, `0x1b26` in the main menu (the menu's handler set? **guess**) |
| 3 | **behaviour**: `0x1eb6` for on/off and cycling settings (Shuffle, Repeat, Sound Check, Clicker); `0x1b5a` submenu; `0x1eba` Backlight Timer; `0x1f2e` Contrast; … Not a function id, not a resource id, and not a clean code offset. **Open** |
| 4 | an extra string id or 0 (`0xff96` Backlight Timer, `0xff88` Reset All) |
| 5 | `0x03NN` + label string id for items showing a value; just the label otherwise |
| 6 | **the item's function: `0x2000 \| function id`**, or a `Menu`/`BMap` id: Shuffle `0x27a9` → fn `0x7a9` (index 269), Repeat → 273, Sound Check → 402, Clicker → 401, Main Menu `0x278f` → fn 243 (also the submenu's `Menu` id), `0x2579` = the ">" arrow `BMap` |
| 7 | `0x2780` (Settings items), `0x4f81`, `0x8` |
| 8 | label string id |
| 9 | 0 |

The item functions talk to native objects, for example Clicker (fn 401):

    3b 09 18   push_const 0x0918      ; the preferences object (likely)
    35 01 66   lookup 0x166           ; set/toggle pref (guess)
    39 3c 00 01 3a 00 01               ; (1)
    3b 08 27 39 3a 00 00               ; call fn 0x827 (refresh?)
    43 05

Sound Check (fn 402) asks `0x0918.method_16b()` and branches on the answer.

What a Select does (trace of toggling Clicker): the shared fn 50 (`0xc2e`) runs
`0x08df.method_9b()`, then fn 273 (id `0x7ad`) runs `0x08df.a6(5)`, `0x08df.a7(6)` (**likely** the
focused list and the selected item) and `0x08f8.method_12e(list, item, 0x282f)`. `0x282f` is the
**toggle message**. Whether fn 273 is shared by all toggles or belongs to Repeat (whose word 6 is
`0x27ad`) isn't settled. Either way the change happens in native code.

## The native side of a setting (**confirmed** in emupod, Clicker)

Settings items are properties of one native **settings object** (`0x1fd0064` in emupod's run;
find it at run time as `r0` of the handlers below). Values travel as **string ids**:
`0x279d` "On", `0x279e` "Off".

- **Message send `0xdc45c(obj, id, target, msg*, selector)`**: when `obj->vtable[0x9c]()` is
  `target`, calls `obj->vtable[0x54](obj, selector, id, msg*)`. The vtables are relative (slot
  holds an offset from the vtable).
- **Setter `0xdafc4(obj, selector, item_id, msg*)`** (settings object `vtable[0x54]`): a switch on
  `item_id` (the item's word 6: `0x25xx`–`0x28xx`). Selector `'prID'` (`0x70724944`). For Clicker
  (`0x282d`, case at `0xdb348`): `*msg == 0x282f` flips byte `obj+0x33`; `*msg == 0x279d` sets 1;
  anything else sets 0. Then `0xd85cc(prefs, flags)` stores bit 0 of the **prefs flags word**
  (`[prefs]+0xb04`, mirrored at `0x420a34`), which is what gets saved. Sound Check (`0x282e`) is
  the same with byte `obj+0x35`, Shuffle-ish bit 1 with `obj+0x32`.
- **Getter `0x7db68(obj, type, ?, out*, item_id)`** (5th argument on the stack): a switch on
  `item_id`. `type` is a fourcc: `'prID'` → the value's string id (also kept at `obj+0x48`),
  `'Str '` → the string resource (via `0x80890('Str ', id)`), `'BMap'` → a bitmap, `'Ui32'` → a
  number. Clicker (`0x7e480`): `obj+0x33 ? 0x279d : 0x279e`. The row's "On"/"Off" comes from here.

So an on/off setting is: an item id, a byte, a case in the setter and a case in the getter.

## Frogger's settings (**working in emupod**, not yet on a device)

"Show Hidden" (On/Off, under Clicker in Settings) switches `hide_state.show_all`: On puts
hidden songs back into Artists/Albums/Genres/Composers. Those lists are rebuilt each time
they're opened, so the change shows straight away. It's **saved with Apple's preferences**:
bit 16 of the prefs flags word (`prefs+0xb04`; Apple only uses bits 0 Clicker and 1, read by
`0x7403c`'s callers `0xa4384`, `0xe63b8`…, written only through `0xd85cc`, which keeps the other
bits). `setting_set` writes it with Apple's `0xd85cc(library, flags)`, which also marks the prefs
dirty (`0xacfac`, `prefs+0xb40`); Apple writes them to disk when the iPod sleeps (hold Play) or
shuts down, not right away (**confirmed** in emupod: `tools/emupod/persist.py set`, then
`persist.py check` in a new process). The library object's word 0 is the prefs struct, and the
settings object keeps the library at `+0x54`; `browse_hook` gets the library as `r0` and calls
`settings_sync()`, so the saved value applies from boot.

How it's built:

- `payload/settings.h`: our ids (`FROGGER_ITEM_HIDDEN 0x2900`, label `FROGGER_STR_HIDDEN 0x3f00`;
  both free in the bundle, `tests/test_settings.py` checks), the On/Off/toggle ids.
- `loader/settings.c`: checks the Settings index entry (`0x182258`) and that row 8 is Clicker,
  copies the 14 items into `settings_menu` (payload bss; its address reaches the loader as
  `PAYLOAD_SYM_SETTINGS_MENU` via `tools/mkpayload.py` `EXPORTS`), inserts a clone of Clicker
  after it with our id in word 6 and our label in words 5 and 8, and repoints the entry. If a
  check fails nothing is patched (same rule as the patches).
- `payload/hooks.S`: `setting_set_hook` (`0xdafc8`), `setting_get_hook` (`0x7db6c`) and
  `string_hook` (`0x875c8`, our label text for `'Str ' 0x3f00`).
- `payload/settings.c`: the label, `setting_value(item)` (string id of the value, 0 = not
  ours) and `setting_set(item, msg*)`.

Findings this relies on (**confirmed** in emupod): toggling any on/off item runs the shared
bytecode fn 50 → fn 273, never the item's own function (`tools/emupod/whenfn.py`), so an id
with no bytecode function behind it is fine. Word 5's `0x03NN` (we use `0x10`, after Clicker's
`0x0f`) draws fine; what `NN` means exactly is still unknown.

### Adding another On/Off setting

1. `payload/settings.h`: a new `FROGGER_ITEM_*` (`0x29xx`) and `FROGGER_STR_*`; check that
   they're free (extend `test_our_ids_are_free`).
2. `payload/settings.c`: its label, a `FROGGER_PREF_*` bit, and a case in `setting_value()`,
   `setting_set()` and `settings_sync()`.
3. `payload/hooks.S`, `string_hook`: return the new label for its string id (or turn the hook
   into a lookup in C once there are several).
4. `loader/settings.c`: insert one more cloned item (and bump the `+ 1` in `settings_menu`'s size
   in `settings.h`, and the expectations in `tests/test_install.py`).
5. `make -C loader && nix develop -c python3 tools/emupod/mkimage.py && cd tools/emupod &&
   python3 frogset.py`, and look at the screenshots in `build/emupod-work/`.

A setting with more than two values (like Shuffle's Off/Songs/Albums) uses other messages
(`0x282f` only flips); trace a stock one with `sethandler.py` first. A submenu item
(word 3 `0x1b5a`, word 6 = the submenu's `Menu` id, as "Main Menu" does) is the way to a
whole "Frogger" page later.

### The feature switches (**working in emupod**, `tools/emupod/switches.py`)

Five more On/Off rows after Resume Mixes, for the features someone might not want: Cover Page,
Hold Menu, Quick Settings, Battery Percent, Page Slide (`FEATURE_*` in `payload/settings.h`).
Row `n` is item `0x2903 + n`, label `0x3f20 + n` and word 5's `NN` `0x13 + n`; its prefs bit is
`19 + n`, set meaning Off, so all are On by default. `frogger_on(FEATURE_...)` reads the bit
through the UI object (`[[0x43580c]+0x1c]` is the library), and counts everything as On until
the UI is up. Each takes effect the next time the feature runs, no restart:

| Switch | Where it's asked | Off |
| --- | --- | --- |
| Cover Page | `cover_switch()`, as Now Playing opens | Apple's page. The art element stays shown (its hiding is how Now Playing's closing is seen) but its height and width values (`+0x48`, `+0x54`) are 0, so it takes no room; Apple's back-to-normal doesn't bring the cover page |
| Hold Menu | the hold handlers' row read, and fn 151 (`HM_FN_NP_SELECT`) | Apple's add to On-The-Go; Now Playing gets no hold binding |
| Quick Settings | fn 243 (`HM_QS_HOLD`) | Apple's backlight toggle |
| Battery Percent | `battery_state`, `battery_resource` | Apple's state and level bitmaps, from the next battery reading |
| Page Slide | `slide_begin` | the page switch as it's drawn |

Settings, like every list, opens on the row it was last left on: scripts scroll to the top
first (`switches.py`). Nine Frogger rows now; a "Frogger" submenu (above) would tidy them.

### Not done yet

- A device test of the feature switches.
- Bits 27 and up of the prefs flags are still free (16-23 Frogger's switches, 24-26 the
  backlight timer's last value).

## The hold menu (**working in emupod**, `payload/holdmenu.c`)

Found with `tools/emupod/popuptrace.py` (every bytecode step and native method entry while
holding Select, opening Clear Playlist and Save Playlist, written to `popuptrace.json`) and
`popupsends.py` (the native method behind each send). Native methods all go through
`0x129808` → `0xa152c` and are entered with `lr = 0xa18a8`, which is how to pick them out.

- **Item word 3 is a function**, tagged `(id << 2) | 2`: Cancel `0x1ae2` → fn 28 (`0x6b8`),
  Confirm `0x1ade` → fn 27, submenu `0x1b5a` → fn 58, On/Off `0x1eb6` → fn 273. Picking an item
  runs fn 50, whose `0x08df.9b()` (`0x45fe0`) runs the item's function. Key bindings use the same
  form: `0x08de.6a(kind, key, fn)` binds key `0x6f` (Select) or `0x10`/`0x6e` (Menu) to a handler;
  kind 3 is a click, kind 2 a hold. Function ids are the index + `0x69c`.
- **Screens**: fn 20 (`0x6b0`) opens a View as a screen (`0x08df.98(view, dir, 30, 300)` slides,
  `.90(view)` doesn't); fn 14 (`0x6aa`) goes back (`0x08de.7a`, which reruns the previous screen's
  builder, so the list keeps its row).
- **The popup** (Clear Playlist, Save Playlist): fn 25 → fn 24 (`0x6b4`)(title, label, label,
  fn): fn 53 sets the title, `0x08de.60(element, string, 0x80)` sets the text of the rows'
  elements `0x25d4`/`0x25d5`, global `0x8e8` keeps the function, `0x08de.76(fn 26)` defers
  opening screen `0x25e2`, and `0x08df.9f(0x25ba, 0x25d4, 3)` highlights the first row.
  `.9f`'s first argument is an **element id in the screen** (`0xd64d0` finds the child through the
  screen's vtable `+0xc8`), not a Menu resource id: the list was built at boot from Menu
  `0x25ba`, so the popup always has two rows. The second row runs fn 27, which calls the
  function in `0x8e8` (`3b 08 e8 39 3a 00 00`); that function goes back itself.
- **Hold handlers**: each Music list binds its hold to one of fns 191 (Playlists), 199, 211
  (Songs), 212, 219, 226, 233, 239. They read the row (`0x08df.a9()`, `0x816a8`) into local0,
  add through the UI object `0x08eb` (= `[0x43580c]`; its methods are one table at `0x1bd9f4 +
  4 * selector`: `.e9` `0xc0ce8` add, `.ea`, `.ef`, `.e2`, `.e4`, `.f1`, `.f2` `0x465fc` clear
  On-The-Go, `.f3` `0xd292c` Save Playlist) and end with **`0x08df.ae(row)`, the row flash**
  (`0x71444`, `0xe3a3c`). (`docs/re-notes.md` had `.ae` as the add.)
- **Running our own bytecode**: the VM returns once its pc reaches **the running function's
  end** (`[vm+0x24]`, checked at `0x9d288`; fn 211 has `0x1963be` there, its entry + length) and
  checks nothing below, so code below `0x192948` runs. (Jumping into a function further up
  needs `[vm+0x24]` moved to that function's end, or it returns at once.) Frogger's runs from
  Apple's Settings Menu at `0x18e4e0`, unused once `loader/settings.c` points Settings at its
  copy. **Apple's image is read-only on a device once it runs** (a store to `0x18e4e0` from the
  payload was a data abort; emupod allows it), so the loader writes that bytecode at boot.

What Frogger does: at a hold handler's row read, `holdmenu_vm` keeps the row and runs fn 24's
steps with our title and labels and the handler as the function. Picking a row runs the handler
again (the first row's fn 28 is sent into fn 27 while the popup is ours); its `.a9()` now
answers the popup's row, which becomes the action, and the list's row goes back into local0, so
stock's own add runs with all of its checks. The flash becomes fn 28's tail (go back). Letting
go of the hold clicks Select; stock swallows that click (fn 42), but the popup's binding would
pick the first row, so the first fn 50 after the popup opens is skipped.
`tools/emupod/holdmenu.py` runs it.

**Six rows** (Play Album Next, Go to Album, Go to Artist, Hide; `tools/emupod/holdmenu2.py`): the
loader points Menu `0x25ba` at a payload copy with four more items (fn 27 behind each), and
`0x08df.a0(0x25ba, element, 3, hidden)` hides the rows that don't fit, as the main menu hides
its items (fn 30). `.a0` acts on the screen that's up, so it runs at fn 26's return (the popup
open), in fn 110's frame (a hold handler's stack is too small for four arguments); Apple's
popups get their two rows back the same way. `.a9` then counts the rows shown. Picking a new
row adds the held row into the scratch playlist (as "Add to Playlist"), and C acts on those
songs; Go to runs `HM_GOTO_ALBUM` / `HM_GOTO_ARTIST` (fn 14, then what Albums or Artists and
their Select do: `.dd`, `.f4(3)`, `.e3`, `.e5`, the title, fn 208 or fn 222) with the row in
local0. Now Playing gets a hold binding from `HM_NP_BIND`, which stands in for fn 151. All of
Frogger's bytecode lives at `HM_SNIPPET` (`payload/holdmenu.h` has the layout);
`re-notes.md`, "Browsing the Music lists", has the browse state it saves and puts back.

**Up Next** (`tools/emupod/upnext.py`): rows 0 and 1 get other labels from C (`0x1fabc` on their
elements after fn 24's labels), so Now Playing's row 0 is "Up Next" and the popup on an Up Next
row is Remove from Queue / Clear Queue, with no rows of their own. `HM_UPNEXT` goes back and runs
fn 208 on a songs array of the queue's waiting songs, `HM_GO_BACK2` goes back twice (fn 14, then
a jump into fn 28's tail), and fn 210's row read is where a pick in Up Next is caught
(`re-notes.md`, "Up Next").

**Quick settings** (`tools/emupod/quicksettings.py`; **working in emupod**): holding Menu runs fn
243 (`docs/re-notes.md`, "Key input"). Unless a popup is up, `holdmenu_vm` sends it to
`HM_QS_RUN`, which calls fn 480 (no arguments, two locals, a hold handler's stack) and runs
`HM_OPEN` in its frame, with rows 0–2 shown. The popup reads its items from `hm_popup` as it
goes, so for the time it's up rows 0–2 are made into Settings' own items: word 3 `0x1eb6`
(fn 273), word 6 the item (Shuffle `0x27a9`, Repeat `0x27ad`, Backlight Timer `0x279f`) and
**word 7 `0x2780`, which is what sends fn 273's `0x08f8.12e(list, item, 0x282f)` to the
settings object** (with the popup's `0x4f81` nothing answers). So Select runs Apple's setter
`0xdafc4` as Settings does: Shuffle (`obj+0x1c`, `0xdc530`, which reshuffles) and Repeat
(`obj+0x1d`, `0xdc1dc`) cycle on the toggle message; Backlight Timer has no toggle case
(`obj+0x28 = msg + 0x60`), so `settings.c` turns it into the next of Off, the last timer
value (prefs flags bits 24–26, kept from every Settings pick but Off and Always On; 10 s if
none) and Always On, and calls the setter with that. **The setter only stores the prefs
value** (`0xd8670`); the backlight keeps its own copy, read at boot, so on its own the new
value only took effect after a restart. Settings' Backlight list (code `0x4408`) maps the
row to seconds (0, 1, 2, 5, 10, 20, `0xffff` Always On) and then runs `0x08eb.111(seconds)`
(native `0xd8710`: UI object `+0x164c`) and `0x08ea.c7()` (native `0xefec4` on the app
object, `[lib]+0xbc4`: lights the screen and re-arms the off timer for it, or turns it off),
so `settings.c` calls those two after the setter too. The labels ("Shuffle: Songs") are our strings, built from the prefs, set with
`0x08de.60` at `HM_RELABEL` and again after each Select. The first fn 14 after it opens is
the click letting go of Menu, skipped. Over a popup (Apple's or ours) the hold stays stock's
backlight toggle. Not tried: the Contrast and Clicker screens, Clock, games.

**Sleep** (row 3; `quicksettings.py` step 7): what holding Play does. Holding Play runs fn 250
(`0x796`), which arms a 1 s timeout (`0x08de.64(1000, fn 249)`) and binds Play's release to fn
248, which cancels it. fn 249 (`0x795`, body `0x45ea`–`0x4694`) is the sleep: it binds Play to
wake (fn 247/`0x797`, or fn `0x72f` in one state, global `0x8ee`), stops playback (`0x08eb.103`,
`.fb`), sets the player's state (`.116(nil)`, `.117(true)`), runs fn `0x6e6`, unbinds Menu and
Select and ends with `0x08de.6f(9)`. Nothing in Apple's bytecode calls fn 249 directly, and our
snippet area is full (8 bytes left), so row 3 is a Confirm row (fn 27 calls fn 191), whose entry
`holdmenu_vm` sends to `HM_PICK` (fn 14, back from the popup), and at `HM_PICK`'s second call
(`HM_PICK_CALL`) on into fn 249's body with the VM's end (`[vm+0x24]`) set to its end. fn 249 has
no arguments or locals and sends at most three arguments, so a hold handler's frame does. In
emupod the screen doesn't go dark either way; the check is that fn 249 runs to `0x08de.6f(9)`,
as it does for holding Play.

## Running it

emupod (`third_party/emupod`, see `docs/power-and-emupod.md` and `tools/emupod/emupod-gen3.patch`) boots
stock 2.3 with `EMUPOD_ENTRY=0x28000000 EMUPOD_IDE_IRQ=1`. `tools/emupod/ipod3g.py` drives it
(buttons, wheel, screenshots; GPIOA bit 5 must stay low, or 2.3 thinks Hold is on). The scripts
expect it set up (`tools/emupod/setup.sh`) and the test cards made (`tools/emupod/mkcards.py`).
Useful core features added in the scratch clone: `hook_start(pcs, count=True)` counts executions
of up to hundreds of thousands of pcs (sorted, binary search); `hook_counts()` reads them.
`hook_start(pcs)` without `count` logs registers at each hit (capped at 50,000 entries).

How the pieces above were found, so you don't have to redo it:

- The interpreter: `0x98920` → `0xa1b54` (loader) → the pool global → `0xa3914` → its only caller
  `0x9ba54`. (Big `addls pc` switches elsewhere are AMX or character tables.)
- Logging `r0` at `0x9bab8` (the opcode fetch) gives the bytecode pc stream; `vmtrace.py`/
  `settrace.py` print it as disassembly with jumps marked.
- `optable.py` reads the opcode table out of RAM.
- The native setter: `ramdiff.py 8` (RAM words that flip with each Clicker toggle and come back),
  then `whowrites.py 8 ADDR…` (store instructions that wrote them: `0xd85e0`, `0xdb378`, inside
  `0xdafc4`). The getter: `whoreads.py` (loads of the settings object's byte while Settings draws:
  `0x7e4b8`, inside `0x7db68`). `sethandler.py` logs the setter's calls with their selectors.
- Dead ends: `0x9ce18` (an indirect call inside the interpreter) only reaches a `return 1` type
  check (`0xa2050`); `0x129808`, the generic invoke behind `send`, is a large object runtime that
  isn't needed for settings.

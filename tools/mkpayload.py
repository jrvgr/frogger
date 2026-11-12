#!/usr/bin/env python3
"""Turn the resident payload into C for the loader.

Reads build/payload/payload.{bin,sym} and writes build/loader/payload.h:
the payload bytes, where they go, how much .bss to clear after them, and
one patch per hook that swaps an instruction in Apple's osos for a BL into
the payload. With --image it also checks every hook's original word
against an osos image.

    python3 tools/mkpayload.py [--image build/fw/osos.img]
"""

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAM_START = 0x28000000  # the loader patches before osos remaps DRAM to 0

# (osos address, original instruction, payload symbol). See payload/hooks.S.
HOOKS = [
    (0xc4b30, 0xe59d0430, "track_hook"),   # ldr   r0, [sp, #1072]
    (0xc4e64, 0xe59d0414, "mhod_hook"),    # ldr   r0, [sp, #1044]
    (0xc431c, 0xe3a07001, "mhyp_hook"),    # mov   r7, #1
    (0xc4768, 0xe5dd1030, "mhip_hook"),    # ldrb  r1, [sp, #48]
    (0xf205c, 0xe59d0058, "filter_hook"),  # ldr   r0, [sp, #88]
    (0x58444, 0xe1a05000, "browse_hook"),  # mov   r5, r0
    (0xdafc8, 0xe1a04000, "setting_set_hook"),  # mov   r4, r0
    (0x7db6c, 0xe1a05000, "setting_get_hook"),  # mov   r5, r0
    (0x875c8, 0xe590e00c, "string_hook"),  # ldr   lr, [r0, #12]
    (0xb916c, 0xeb000e35, "play_hook"),    # bl    0xbca48
    (0xb4578, 0xe5903020, "vis_hook"),     # ldr   r3, [r0, #32]
    (0x9bab0, 0xe5940020, "vm_hook"),      # ldr   r0, [r4, #32]
    (0xe3aac, 0xe59d6054, "trans_hook"),   # ldr   r6, [sp, #84]
    (0xc0c68, 0xe5940000, "queue_add_hook"),   # ldr   r0, [r4]
    (0xb7b00, 0xe92d4ff0, "queue_next_hook"),  # push  {r4-r11, lr}
    (0x5e8cc, 0xe92d4010, "keep_hook"),    # push  {r4, lr}
    (0x9106c, 0xe3540000, "letter_hook"),  # cmp   r4, #0
    (0x7998c, 0xe92d43f0, "label_hook"),   # push  {r4-r9, lr}
    (0x1fabc, 0xe92d4008, "title_hook"),   # push  {r3, lr}
    (0xe9664, 0xe92d4030, "tick_hook"),    # push  {r4, r5, lr}
    (0x41e5c, 0xe3a024c4, "crash_hook"),   # mov   r2, #0xc4000000
    (0xb9354, 0xe59d0230, "resume_flags_hook"),  # ldr   r0, [sp, #560]
    (0xb9550, 0xe5840164, "resume_start_hook"),  # str   r0, [r4, #356]
    (0xb903c, 0xe5860060, "resume_save_hook"),   # str   r0, [r6, #96]
    (0xf4d6c, 0xe92d4ff0, "counts_hook"),        # push  {r4-r11, lr}
    (0xb81d4, 0xe92d47f0, "skip_next_hook"),     # push  {r4-r10, lr}
    (0xb8eb4, 0xe92d4038, "skip_pick_hook"),     # push  {r3, r4, r5, lr}
    (0x118df0, 0xeb000012, "battery_read"),      # bl    0x118e40
    (0x8e788, 0xebfed0d9, "battery_state"),      # bl    0x42af4
    (0xd2db4, 0xe92d47f0, "lcd_hook"),           # push  {r4-r10, lr}
    (0x68e60, 0xe5940020, "drawn_hook"),         # ldr   r0, [r4, #32]
    (0xc347c, 0xe92d407c, "disk_reinit_hook"),   # push  {r2-r6, lr}
    (0xc788c, 0xe92d47fc, "disk_read_hook"),     # push  {r2-r10, lr}
    (0x9dbac, 0xe5940190, "flash_id_hook"),      # ldr   r0, [r4, #400]
    (0x57820, 0xe92d4010, "flash_hold_hook"),    # push  {r4, lr}
    (0x13c6e8, 0xe7970104, "click_hook"),        # ldr   r0, [r7, r4, lsl #2]
    (0x94984, 0xeb002a3f, "preload_hook"),       # bl    0x9f288
    (0x816a8, 0xe92d4038, "a9_hook"),            # push  {r3, r4, r5, lr}
    (0xf1000, 0xe2800001, "hr_count_genres"),    # add   r0, r0, #1
    (0xefe04, 0xe2800001, "hr_count_artists"),   # add   r0, r0, #1
    (0xf0688, 0xe2800001, "hr_count_composers"),  # add   r0, r0, #1
    (0xefdb4, 0xe2800001, "hr_count_albums"),    # add   r0, r0, #1
]

# Hooks entered with a plain B instead of BL: they sit where lr is still live (the first
# instruction of a function), so they must not overwrite it, and they jump back to the
# next instruction themselves.
BRANCH_HOOKS = {"vis_hook", "vm_hook", "trans_hook", "queue_next_hook", "keep_hook", "label_hook", "title_hook", "tick_hook", "crash_hook", "counts_hook", "skip_next_hook", "skip_pick_hook", "lcd_hook", "drawn_hook", "disk_reinit_hook", "disk_read_hook", "flash_hold_hook", "a9_hook"}

# Hooks only some builds have (the debug record, `make -C loader DEBUG=1`): left out
# when the payload doesn't define them.
OPTIONAL_HOOKS = {"crash_hook"}

# Payload symbols the loader needs (as PAYLOAD_SYM_<NAME>, runtime addresses).
EXPORTS = ["settings_menu", "np_view", "hm_code", "hm_popup", "hm_main"]


def bl(src, dst, link=True):
    off = (dst - src - 8) >> 2
    if not -(1 << 23) <= off < (1 << 23):
        raise ValueError(f"{'BL' if link else 'B'} from {src:#x} can't reach {dst:#x}")
    return (0xEB000000 if link else 0xEA000000) | (off & 0xFFFFFF)


def symbols(path):
    syms = {}
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    return syms


def hooks(syms):
    return [(addr, orig, bl(addr, syms[name], name not in BRANCH_HOOKS), name) for addr, orig, name in HOOKS
            if name in syms or name not in OPTIONAL_HOOKS]


def check_image(image, patches):
    d = Path(image).read_bytes()
    bad = [(a, o, struct.unpack_from("<I", d, a)[0]) for a, o, _, _ in patches
           if struct.unpack_from("<I", d, a)[0] != o]
    for a, o, got in bad:
        print(f"{image}: {a:#x} is {got:#010x}, expected {o:#010x}", file=sys.stderr)
    return not bad


def words(b):
    return ", ".join(f"0x{x:02x}" for x in b)


def render(blob, syms, patches):
    base, bss_end = syms["track_hook"], syms["_bss_end"]
    lines = [
        "/* Generated by tools/mkpayload.py from build/payload. Don't edit. */",
        f"#define PAYLOAD_ADDR 0x{DRAM_START + base:08x}u",
        f"#define PAYLOAD_BSS_LEN 0x{bss_end - base - len(blob):x}u",
        *(f"#define PAYLOAD_SYM_{name.upper()} 0x{syms[name]:08x}u" for name in EXPORTS),
        f"static const uint8_t payload[{len(blob)}] = {{",
    ]
    for i in range(0, len(blob), 16):
        lines.append("    " + words(blob[i:i + 16]) + ",")
    lines.append("};")
    for addr, orig, repl, name in patches:
        lines.append(f"static const uint8_t {name}_orig[] = {{ {words(struct.pack('<I', orig))} }};")
        lines.append(f"static const uint8_t {name}_repl[] = {{ {words(struct.pack('<I', repl))} }};")
    entries = [f"    {{ 0x{DRAM_START + addr:08x}, 4, {name}_orig, {name}_repl }}," for addr, _, _, name in patches]
    lines.append(" \\\n".join(["#define PAYLOAD_PATCHES"] + entries))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--build", default=str(ROOT / "build"))
    p.add_argument("--image", help="osos image to check the original words against")
    args = p.parse_args(argv)
    build = Path(args.build)
    blob = (build / "payload/payload.bin").read_bytes()
    syms = symbols(build / "payload/payload.sym")
    patches = hooks(syms)
    if args.image and not check_image(args.image, patches):
        return 1
    out = build / "loader/payload.h"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(blob, syms, patches))
    print(f"{out}: {len(blob)} bytes at {syms['track_hook']:#x}, {len(patches)} hooks")
    return 0


if __name__ == "__main__":
    sys.exit(main())

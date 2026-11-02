#!/usr/bin/env bash
# Import Apple's osos image into a Ghidra project at the address it runs at.
#
# Apple's boot code copies osos to DRAM at 0x28000000 (the directory's addr),
# but the reset code at 0x188 remaps DRAM to 0 through the PP5002 MMAP
# registers (0xf000f008/c) and jumps to 0x23c. Everything after that is linked
# at 0, so that is the base Ghidra needs for pointers and calls to resolve.
# Set BASE to override (e.g. BASE=0x28000000 to match physical addresses).
# Run inside `nix develop .#re` after `tools/fwtool.py extract firmware/iPod_2.2.3.ipsw`.
#
#   tools/ghidra-import.sh [build/fw] [build/ghidra]
set -euo pipefail

fw=${1:-build/fw}
proj=${2:-build/ghidra}

test -f "$fw/osos.img" || { echo "$fw/osos.img missing; run tools/fwtool.py extract first" >&2; exit 1; }
load_addr=${BASE:-0x0}

headless=$(command -v ghidra-analyzeHeadless || command -v analyzeHeadless || true)
if [ -z "$headless" ]; then
    echo "analyzeHeadless not found; run this inside 'nix develop .#re'" >&2
    exit 1
fi

mkdir -p "$proj"
echo "Importing $fw/osos.img at $load_addr into $proj/frogger.gpr"
"$headless" "$proj" frogger \
    -import "$fw/osos.img" \
    -overwrite \
    -loader BinaryLoader \
    -loader-baseAddr "$load_addr" \
    -processor ARM:LE:32:v4t
echo "Open it with: ghidra $proj/frogger.gpr"

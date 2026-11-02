#!/usr/bin/env bash
# Back up the iPod's whole firmware partition before installing anything.
# The iPod must be connected in disk mode. Run inside `nix develop`.
#
#   tools/backup.sh            # -> backups/firmware-<date>.bin (+ .sha256, latest.bin)
set -euo pipefail

cd "$(dirname "$0")/.."
command -v ipodpatcher >/dev/null || { echo "ipodpatcher not found; run inside 'nix develop'" >&2; exit 1; }
sudo=""; [ "$(id -u)" -eq 0 ] || sudo="sudo"

mkdir -p backups
out="backups/firmware-$(date +%Y%m%d-%H%M%S).bin"

echo "Reading the firmware partition into $out (needs admin rights to read the raw disk)"
$sudo ipodpatcher -r "$out"
[ -n "$sudo" ] && $sudo chown "$(id -u):$(id -g)" "$out"

# Refuse to call it a backup unless it parses as Apple's firmware.
python3 tools/fwtool.py info "$out"

if command -v sha256sum >/dev/null; then sha256sum "$out" > "$out.sha256"
else shasum -a 256 "$out" > "$out.sha256"; fi
ln -sf "$(basename "$out")" backups/latest.bin

echo
echo "Backup OK: $out"
echo "Copy it somewhere outside this folder too. Undo any install with: tools/restore.sh"

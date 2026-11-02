#!/usr/bin/env bash
# Put the iPod back exactly as it was before Frogger. Run inside `nix develop`
# with the iPod connected in disk mode.
#
#   tools/restore.sh                    # write backups/latest.bin back
#   tools/restore.sh backups/firmware-20261028-090000.bin
#   tools/restore.sh --remove-loader    # keep Apple's osos, just drop Frogger's loader
set -euo pipefail

cd "$(dirname "$0")/.."
command -v ipodpatcher >/dev/null || { echo "ipodpatcher not found; run inside 'nix develop'" >&2; exit 1; }
sudo=""; [ "$(id -u)" -eq 0 ] || sudo="sudo"

confirm() {
    read -r -p "$1 Type 'restore' to continue: " answer
    [ "$answer" = "restore" ] || { echo "Cancelled, nothing written."; exit 1; }
}

if [ "${1:-}" = "--remove-loader" ]; then
    confirm "This removes Frogger's loader from the iPod's firmware partition."
    $sudo ipodpatcher -d
    echo "Loader removed. The iPod boots Apple's stock firmware."
    exit 0
fi

backup=${1:-backups/latest.bin}
[ -f "$backup" ] || { echo "No backup at $backup (make one with tools/backup.sh)" >&2; exit 1; }

# Check the backup before writing a single byte.
python3 tools/fwtool.py info "$backup"
sum_file="$backup.sha256"
[ -L "$backup" ] && sum_file="$(dirname "$backup")/$(readlink "$backup").sha256"
if [ -f "$sum_file" ]; then
    expected=$(cut -d' ' -f1 "$sum_file")
    if command -v sha256sum >/dev/null; then actual=$(sha256sum "$backup" | cut -d' ' -f1)
    else actual=$(shasum -a 256 "$backup" | cut -d' ' -f1); fi
    [ "$expected" = "$actual" ] || { echo "Checksum mismatch for $backup, not writing it." >&2; exit 1; }
    echo "Checksum OK."
else
    echo "Warning: no $sum_file to check against."
fi

confirm "This overwrites the iPod's firmware partition with $backup."
$sudo ipodpatcher -w "$backup"
echo "Restored. Eject the iPod and reset it (Menu + Play)."

#!/bin/sh
# Get emupod ready for the scripts here: the submodule (third_party/emupod, pinned), our patch
# on top (emupod-gen3.patch: 3G/2.3 support and counting hooks; applied once, the submodule then
# shows as modified) and its Rust core built into emupod/emupod_rs.abi3.so. Needs cargo and a
# Python 3 (nix develop .#emu has both).
#
#     tools/emupod/setup.sh
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EMU=$ROOT/third_party/emupod
PATCH=$ROOT/tools/emupod/emupod-gen3.patch

git -C "$ROOT" submodule update --init third_party/emupod
if git -C "$EMU" apply --reverse --check "$PATCH" 2>/dev/null; then
    echo "emupod: patch already applied"
else
    git -C "$EMU" apply "$PATCH"
    echo "emupod: patch applied"
fi

cd "$EMU/rust"
case $(uname) in
    Darwin) RUSTFLAGS="-C link-arg=-undefined -C link-arg=dynamic_lookup" cargo build --release -p emupod-rs
            cp target/release/libemupod_rs.dylib ../emupod/emupod_rs.abi3.so ;;
    *)      cargo build --release -p emupod-rs
            cp target/release/libemupod_rs.so ../emupod/emupod_rs.abi3.so ;;
esac
echo "emupod: built $EMU/emupod/emupod_rs.abi3.so"

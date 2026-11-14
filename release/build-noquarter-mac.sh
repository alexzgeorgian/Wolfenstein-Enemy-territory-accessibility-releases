#!/usr/bin/env bash
#
# Builds No Quarter's Mac libraries, on a Mac, for
# release/build-noquarter.sh --mac-libs to pack.
#
#   cgame_mac, ui_mac  No Quarter's client with the accessibility mode,
#                      which go into the pk3.
#   qagame_mac         No Quarter's server module with Omni-bot support,
#                      for a game the player hosts. NoQuarter EoTS ships
#                      no Mac build at all, so this is No Quarter's own,
#                      built for the Mac, without the accessibility
#                      layer and without Lua. The engine loads it only as
#                      a loose file, so it ships beside the pk3.
#
# Each is one file for Apple Silicon and Intel.
#
#   release/build-noquarter-mac.sh OUT VERSION
#
# Clones NoQuarter EoTS at the release in integration/noquarter/base.txt
# and applies integration/noquarter/*.patch, as build-noquarter.sh does.

set -euo pipefail

out="$1"
version="$2"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base_file="$repo_root/integration/noquarter/base.txt"
base() { sed -n "s/^$1=//p" "$base_file" | head -1; }

work="$(mktemp -d "${TMPDIR:-/tmp}/eta-nq-mac-XXXXXX")"
trap 'rm -rf "$work"' EXIT

nq="$work/noquarter"
echo "==> cloning NoQuarter EoTS $(base tag)"
git clone --depth 1 --branch "$(base tag)" "$(base repo)" "$nq" >/dev/null 2>&1
test "$(git -C "$nq" rev-parse HEAD)" = "$(base commit)" \
    || { echo "error: $(base tag) is not $(base commit)" >&2; exit 1; }

echo "==> applying the patch series"
for patch in "$repo_root"/integration/noquarter/0*.patch; do
    git -C "$nq" apply "$patch"
done

common=(
    -DCMAKE_BUILD_TYPE=Release
    -DWITH_LUA=OFF
    -DCMAKE_OSX_DEPLOYMENT_TARGET=10.14
    "-DCMAKE_OSX_ARCHITECTURES=x86_64;arm64"
    "-DCMAKE_C_FLAGS=-ffile-prefix-map=$nq=/noquarter -ffile-prefix-map=$repo_root=/accessibility-mode"
)

universal() {
    local archs
    archs="$(lipo -archs "$1")"
    echo "$(basename "$1"): $archs"
    case " $archs " in *" x86_64 "*) ;; *) echo "error: $1 has no Intel code" >&2; exit 1 ;; esac
    case " $archs " in *" arm64 "*) ;; *) echo "error: $1 has no Apple Silicon code" >&2; exit 1 ;; esac
}

mkdir -p "$out"

echo "==> qagame_mac, No Quarter's server module with Omni-bot"
cmake -S "$nq" -B "$work/build-game" "${common[@]}" \
    -DBUILD_CLIENT_MOD=OFF -DWITH_OMNIBOT=ON >/dev/null
cmake --build "$work/build-game" --target qagame -j
universal "$work/build-game/src/qagame_mac"
# Into a file first: grep -q stops reading at the first match, and with
# pipefail the cut-off nm then fails the build.
nm "$work/build-game/src/qagame_mac" > "$work/qagame.symbols"
grep -q 'Omnibot_LoadLibrary' "$work/qagame.symbols" \
    || { echo "error: qagame_mac does not carry Omni-bot's loader" >&2; exit 1; }
nm -gU "$work/build-game/src/qagame_mac" > "$work/qagame.exports"
grep -q '_vmMain' "$work/qagame.exports" \
    || { echo "error: qagame_mac does not export vmMain" >&2; exit 1; }
cp "$work/build-game/src/qagame_mac" "$out/qagame_mac"

echo "==> cgame_mac and ui_mac, with the accessibility mode"
cmake -S "$nq" -B "$work/build" "${common[@]}" \
    -DBUILD_SERVER_MOD=OFF -DFEATURE_ACCESSIBILITY=ON \
    -DETA_SOURCE_DIR="$repo_root" -DETA_RELEASE_VERSION="$version" >/dev/null
cmake --build "$work/build" --target cgame ui -j
for lib in cgame_mac ui_mac; do
    universal "$work/build/src/$lib"
    nm -gU "$work/build/src/$lib" > "$work/$lib.exports"
    grep -q '_vmMain' "$work/$lib.exports" \
        || { echo "error: $lib does not export vmMain" >&2; exit 1; }
    cp "$work/build/src/$lib" "$out/$lib"
done

echo "built $(ls "$out" | tr '\n' ' ')"

#!/usr/bin/env bash
#
# Fetch the NVDA controller client and lay its two DLLs out for packing.
#
# Usage:
#   release/fetch-nvda-client.sh <destination-dir> [--report]
#
#   <destination-dir>  Receives x64/, x86/ and the licence text.
#   --report           Print what was found and do not enforce the pins.
#                      This is how the pins are established in the first
#                      place; see release/nvda-client.pin.
#
# Everything about the remote side of this - the URL, the names inside
# the archive - is somebody else's and can move. So nothing here is
# assumed silently: the candidate URLs are tried in order and the one
# that worked is printed, the archive is listed rather than indexed
# blind, and the bytes are checked against pins recorded in the
# repository. A wrong or substituted file fails the build; it does not
# reach a player.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pin_file="$repo_root/release/nvda-client.pin"

dest=""
report=0
for arg in "$@"; do
    case "$arg" in
        --report) report=1 ;;
        -*) echo "error: unknown option $arg" >&2; exit 2 ;;
        *) dest="$arg" ;;
    esac
done
[ -n "$dest" ] || { echo "usage: fetch-nvda-client.sh <dir> [--report]" >&2; exit 2; }

read_pin() {
    local key="$1"
    local value
    value="$(sed -n "s/^$key=\(.*\)$/\1/p" "$pin_file" | head -1)"
    [ -n "$value" ] || {
        echo "error: $key is missing from release/nvda-client.pin" >&2
        exit 1
    }
    printf '%s' "$value"
}

version="$(read_pin NVDA_VERSION)"
want_zip="$(read_pin NVDA_ZIP_SHA256)"
want_x64="$(read_pin NVDA_DLL_X64_SHA256)"
want_x86="$(read_pin NVDA_DLL_X86_SHA256)"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# NV Access has published this under more than one name over the years.
# Trying a list and saying which one answered is honest about that; a
# single hard-coded URL would simply start failing one day with nothing
# to say about why.
candidates=(
    # The one NV Access actually serves, as of 2026.1.1. The others are
    # kept as fallbacks rather than deleted: this naming has changed
    # before, and a list that has to be edited to survive a rename is
    # better than a single URL that starts 404ing with nothing to say.
    "https://download.nvaccess.org/releases/$version/nvda_${version}_controllerClient.zip"
    "https://download.nvaccess.org/releases/$version/controllerClient.zip"
    "https://download.nvaccess.org/releases/stable/nvda_${version}_controllerClient.zip"
)

zip_path="$work/controllerClient.zip"
source_url=""
for url in "${candidates[@]}"; do
    echo "==> trying $url"
    if curl -fsSL --max-time 120 -o "$zip_path" "$url"; then
        source_url="$url"
        break
    fi
done

if [ -z "$source_url" ]; then
    echo "error: could not download the NVDA controller client." >&2
    echo "       Tried:" >&2
    printf '         %s\n' "${candidates[@]}" >&2
    echo "       If NV Access has moved or renamed it, add the new URL to" >&2
    echo "       the candidate list in this script - do not fetch it from" >&2
    echo "       anywhere else. A DLL from a mirror or a 'free DLL' site" >&2
    echo "       is a screen reader user's worst case." >&2
    exit 1
fi

got_zip="$(sha256sum "$zip_path" | cut -d' ' -f1)"

echo "==> archive contents"
unzip -l "$zip_path" | sed 's/^/    /'

unzip -q -o "$zip_path" -d "$work/unpacked"

# Located by searching rather than by a hard-coded path: the layout has
# changed once already (the DLLs lost their 32/64 suffix), and a build
# that guesses wrong would either fail obscurely or pack the wrong
# architecture, which loads and then does nothing.
find_dll() {
    local arch="$1"
    find "$work/unpacked" -ipath "*/$arch/*" -iname 'nvdaControllerClient*.dll' \
        | sort | head -1
}

dll_x64="$(find_dll x64 || true)"
dll_x86="$(find_dll x86 || true)"

for pair in "x64:$dll_x64" "x86:$dll_x86"; do
    arch="${pair%%:*}"
    path="${pair#*:}"
    [ -n "$path" ] || {
        echo "error: no $arch nvdaControllerClient DLL inside $source_url" >&2
        echo "       The listing above is what the archive actually holds." >&2
        exit 1
    }
done

got_x64="$(sha256sum "$dll_x64" | cut -d' ' -f1)"
got_x86="$(sha256sum "$dll_x86" | cut -d' ' -f1)"

# LGPL v2.1 asks that the licence accompany the binary. Rather than
# typing out a copy and hoping it is the right one, ship the text NV
# Access puts in their own archive - and refuse to build if there is
# none to ship, because distributing it without one is not ours to do.
licence="$(find "$work/unpacked" \
    \( -iname '*licen[cs]e*' -o -iname '*copying*' \) -type f | sort | head -1 || true)"

echo
echo "==> found"
echo "    url          $source_url"
echo "    zip sha256   $got_zip"
echo "    x64 dll      ${dll_x64#$work/unpacked/}"
echo "    x64 sha256   $got_x64"
echo "    x86 dll      ${dll_x86#$work/unpacked/}"
echo "    x86 sha256   $got_x86"
echo "    licence      ${licence:-(none found)}"
echo

if [ "$report" -eq 1 ]; then
    echo "==> pin these in release/nvda-client.pin:"
    echo "    NVDA_ZIP_SHA256=$got_zip"
    echo "    NVDA_DLL_X64_SHA256=$got_x64"
    echo "    NVDA_DLL_X86_SHA256=$got_x86"
fi

unpinned=0
for value in "$want_zip" "$want_x64" "$want_x86"; do
    [ "$value" = "UNPINNED" ] && unpinned=1
done

# Reporting mode still lays the files out, so the job that establishes
# the pins also proves the rest of the packing works. What it skips is
# only the comparison there is nothing yet to compare against.
enforce=1
if [ "$unpinned" -eq 1 ]; then
    if [ "$report" -eq 1 ]; then
        echo
        echo "note: the pins are not set yet, so no checksum was enforced."
        enforce=0
    else
        echo "error: release/nvda-client.pin is UNPINNED." >&2
        echo "       A release may not carry a binary nobody checked." >&2
        echo "       Run this with --report and record the values it prints." >&2
        exit 1
    fi
fi

mismatch=0
check() {
    local what="$1" want="$2" got="$3"
    if [ "$want" != "$got" ]; then
        echo "error: $what does not match the pin" >&2
        echo "       pinned   $want" >&2
        echo "       download $got" >&2
        mismatch=1
    fi
}
if [ "$enforce" -eq 1 ]; then
    check "the controller client zip" "$want_zip" "$got_zip"
    check "the x64 DLL"               "$want_x64" "$got_x64"
    check "the x86 DLL"               "$want_x86" "$got_x86"
fi

if [ "$mismatch" -ne 0 ]; then
    echo >&2
    echo "       Either NV Access republished this version - in which case" >&2
    echo "       read the diff and re-pin deliberately - or the download is" >&2
    echo "       not what it claims to be. Do not pin your way past it" >&2
    echo "       without knowing which." >&2
    exit 1
fi

[ -n "$licence" ] || {
    echo "error: the controller client archive carried no licence text," >&2
    echo "       and redistributing an LGPL binary without one is not" >&2
    echo "       something this project is entitled to do." >&2
    exit 1
}

mkdir -p "$dest/x64" "$dest/x86"
cp "$dll_x64" "$dest/x64/nvdaControllerClient.dll"
cp "$dll_x86" "$dest/x86/nvdaControllerClient.dll"
cp "$licence" "$dest/LICENSE.txt"

cat > "$dest/README.txt" <<EOF
nvdaControllerClient.dll - NVDA controller client $version
==========================================================

This is NV Access's file, not this mod's. It is redistributed here
unmodified, under the GNU Lesser General Public License version 2.1;
the licence text NV Access ships with it is in LICENSE.txt beside this
file. The source is at https://github.com/nvaccess/nvda, under
extras/controllerClient.

It is bundled so that NVDA speech works without you having to go and
find a DLL by name - a search that leads to sites serving tampered
copies, which for a screen reader is about the worst thing that can
happen to you.

WHAT TO DO WITH IT

Copy ONE of these next to ETLegacy.exe, in the folder where the game is
installed:

    x64\\nvdaControllerClient.dll    for 64-bit ET: Legacy (most people)
    x86\\nvdaControllerClient.dll    for 32-bit ET: Legacy

Then start NVDA and start the game. The mod speaks through NVDA when it
is running and falls back to SAPI 5 when it is not, and it decides that
per message - so starting or quitting NVDA mid-game is picked up on the
next thing spoken.

You do not need this file at all if you are happy with SAPI. Nothing
breaks without it.

Downloaded from:
    $source_url
EOF

echo "==> packed into $dest"

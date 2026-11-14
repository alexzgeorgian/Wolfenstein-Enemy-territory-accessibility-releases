#!/usr/bin/env bash
#
# Builds the No Quarter download: the accessibility mode built into No
# Quarter's client libraries for 64-bit and 32-bit Windows, in one pk3
# that goes in the game's nq folder, with its install guide.
#
#   release/build-noquarter.sh --out DIR --version NAME [--mac-libs DIR] [--no-nvda] [--keep]
#
# --mac-libs is the folder release/build-noquarter-mac.sh wrote on a Mac:
# cgame_mac and ui_mac go into the same pk3, and so does qagame_mac, as
# eta/qagame_mac, for the ui to write out into the nq folder (a file the
# game writes carries none of the Mac's quarantine). A Mac download is made
# beside the Windows one, with the Mac's own guide.
#
# Clones NoQuarter EoTS at the release named in
# integration/noquarter/base.txt, applies integration/noquarter/*.patch
# and cross-compiles with mingw-w64, as build-release.sh does for
# ET: Legacy. Only cgame and ui change; the server module and Omni-bot
# come from the NoQuarter EoTS download unchanged.
#
# Requires: cmake, git, zip, and the mingw-w64 cross compilers.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base_file="$repo_root/integration/noquarter/base.txt"

out=""
version=""
nvda=1
keep=0
mac_libs=""
while [ $# -gt 0 ]; do
    case "$1" in
        --out) out="$2"; shift 2 ;;
        --version) version="$2"; shift 2 ;;
        --no-nvda) nvda=0; shift ;;
        --mac-libs) mac_libs="$2"; shift 2 ;;
        --keep) keep=1; shift ;;
        *) echo "error: unknown argument $1" >&2; exit 2 ;;
    esac
done
[ -n "$out" ] && [ -n "$version" ] || {
    echo "usage: build-noquarter.sh --out DIR --version NAME [--no-nvda] [--keep]" >&2
    exit 2
}

base() { sed -n "s/^$1=//p" "$base_file" | head -1; }
nq_repo="$(base repo)"
nq_tag="$(base tag)"
nq_commit="$(base commit)"

for tool in cmake git zip sha256sum \
            x86_64-w64-mingw32-gcc x86_64-w64-mingw32-g++ \
            i686-w64-mingw32-gcc   i686-w64-mingw32-g++; do
    command -v "$tool" >/dev/null || { echo "error: $tool is not installed" >&2; exit 1; }
done

workdir="$(mktemp -d "${TMPDIR:-/tmp}/eta-nq-XXXXXX")"
cleanup() { [ "$keep" -eq 1 ] || rm -rf "$workdir"; }
trap cleanup EXIT

nq="$workdir/noquarter"
echo "==> cloning NoQuarter EoTS $nq_tag"
git clone --depth 1 --branch "$nq_tag" "$nq_repo" "$nq" >/dev/null 2>&1
actual="$(git -C "$nq" rev-parse HEAD)"
if [ "$actual" != "$nq_commit" ]; then
    echo "error: $nq_tag resolved to $actual, expected $nq_commit" >&2
    exit 1
fi

echo "==> applying the patch series"
for patch in "$repo_root"/integration/noquarter/0*.patch; do
    git -C "$nq" apply "$patch" || {
        echo "error: $(basename "$patch") does not apply to $nq_tag" >&2
        exit 1
    }
done

mkdir -p "$workdir/stage"

build_arch() {
    local label="$1" processor="$2" triplet="$3"
    local dir="$workdir/build-$label"

    echo "==> building $label"
    # CMAKE_SYSTEM_PROCESSOR names the libraries: left empty when cross
    # compiling, they come out with a name the engine never looks for.
    # The prefix map keeps the build folder out of the binaries, so the
    # same commit always builds the same bytes.
    cmake -B "$dir" -S "$nq" \
        -DCMAKE_C_FLAGS="-ffile-prefix-map=$nq=/noquarter -ffile-prefix-map=$repo_root=/accessibility-mode" \
        -DCMAKE_SYSTEM_NAME=Windows \
        -DCMAKE_SYSTEM_PROCESSOR="$processor" \
        -DCMAKE_C_COMPILER="$triplet-gcc" \
        -DCMAKE_CXX_COMPILER="$triplet-g++" \
        -DCMAKE_RC_COMPILER="$triplet-windres" \
        -DBUILD_SERVER_MOD=OFF -DWITH_LUA=OFF \
        -DFEATURE_ACCESSIBILITY=ON -DETA_SOURCE_DIR="$repo_root" \
        -DETA_RELEASE_VERSION="$version" \
        -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build "$dir" --target cgame ui -j"$(nproc 2>/dev/null || echo 2)" >/dev/null
    cp "$dir/src/cgame_mp_$label.dll" "$dir/src/ui_mp_$label.dll" "$workdir/stage/"
}

build_arch x64 x86_64 x86_64-w64-mingw32
build_arch x86 x86    i686-w64-mingw32

pk3_libs=(cgame_mp_x64.dll ui_mp_x64.dll cgame_mp_x86.dll ui_mp_x86.dll)
if [ -n "$mac_libs" ]; then
    for lib in cgame_mac ui_mac qagame_mac; do
        test -s "$mac_libs/$lib" || { echo "error: $mac_libs has no $lib" >&2; exit 1; }
    done
    cp "$mac_libs/cgame_mac" "$mac_libs/ui_mac" "$workdir/stage/"
    mkdir -p "$workdir/stage/eta"
    cp "$mac_libs/qagame_mac" "$workdir/stage/eta/qagame_mac"
    pk3_libs+=(cgame_mac ui_mac eta/qagame_mac)
fi

# The mod's own cue sounds - the doors, ladders, the marker - generated
# as for the ET: Legacy mode, by the same script, into the same folder.
echo "==> generating the cue sounds"
mkdir -p "$workdir/stage/sound/accessibility"
python3 "$repo_root/release/make-cue-sounds.py" "$workdir/stage/sound/accessibility" >/dev/null

# Every sound the mod registers has to be in the pk3: a missing one plays
# silence and says nothing.
missing=0
for sound in $(grep -ohE '"sound/accessibility/[a-z_]+\.wav"' "$nq/src/cgame/"*.c | tr -d '"' | sort -u); do
    if [ ! -f "$workdir/stage/$sound" ]; then
        echo "  $sound is registered by the mod but was not generated"
        missing=1
    fi
done
[ "$missing" -eq 0 ] || { echo "error: the pk3 would ship without sounds the mod asks for" >&2; exit 1; }
pk3_libs+=( $(cd "$workdir/stage" && ls sound/accessibility/*.wav) )

# The Tesla gun the mode adds: its weapon file, and a stand-in crackle so it
# never fires in silence. RTCW's own models and zap come only from the
# player's own RTCW, through release/make-rtcw-sounds.py.
echo "==> adding the Tesla gun"
mkdir -p "$workdir/stage/weapons"
cp "$repo_root/release/noquarter/weapons/tesla.weap" "$workdir/stage/weapons/"
python3 "$repo_root/release/make-noquarter-sounds.py" "$workdir/stage" >/dev/null
pk3_libs+=(weapons/tesla.weap sound/weapons/tesla/tesla_fire.wav)

# The accessibility pages in No Quarter's menus: its Options menu with an
# ACCESSIBILITY button, the pages behind it (the ui loads them after No
# Quarter's own list), and the layout macros No Quarter's menudef lacks.
echo "==> adding the accessibility menus"
mkdir -p "$workdir/stage/ui"
for menu in options.menu eta_menudef.h \
            options_accessibility.menu \
            options_accessibility_environment.menu \
            options_accessibility_speech.menu \
            options_accessibility_sound.menu \
            options_accessibility_keys.menu \
            options_accessibility_hosting.menu; do
    cp "$repo_root/release/noquarter/ui/$menu" "$workdir/stage/ui/$menu"
    pk3_libs+=("ui/$menu")
done
# Every page the ui loads must be in the pk3, or its button opens nothing.
for page in $(grep -ohE '"ui/options_accessibility[a-z_]*\.menu"' "$nq/src/ui/ui_main.c" | tr -d '"' | sort -u); do
    [ -f "$workdir/stage/$page" ] || { echo "error: the ui loads $page, which is not in the pk3" >&2; exit 1; }
done

package="zzz_accessibility_nq.pk3"
bundle="wolfenstein-enemy-territory-accessibility-noquarter-$version-windows"
mkdir -p "$out" "$workdir/$bundle"
out="$(cd "$out" && pwd)"

echo "==> packaging $package"
# Fixed dates, so the pk3's bytes depend only on what is in it.
find "$workdir/stage" -exec touch -d "2000-01-01 00:00:00" {} +
rm -f "$out/$package"
(cd "$workdir/stage" && zip -X -q "$out/$package" "${pk3_libs[@]}")

cp "$out/$package" "$workdir/$bundle/"
sed -e "s/@VERSION@/$version/g" -e "s/@PACKAGE@/$package/g" -e "s/@NQ_TAG@/$nq_tag/g" \
    "$repo_root/release/INSTALL-noquarter.md.in" > "$workdir/$bundle/INSTALL.md"
if [ "$nvda" -eq 1 ]; then
    "$repo_root/release/fetch-nvda-client.sh" "$workdir/$bundle/nvda"
fi

(cd "$workdir/$bundle" && find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort \
    | xargs sha256sum > SHA256SUMS.contents)
rm -f "$out/$bundle.zip"
(cd "$workdir" && zip -X -q -r "$out/$bundle.zip" "$bundle")
sums=("$package" "$bundle.zip")

if [ -n "$mac_libs" ]; then
    mac_bundle="wolfenstein-enemy-territory-accessibility-noquarter-$version-mac"
    mkdir -p "$workdir/$mac_bundle"
    cp "$out/$package" "$workdir/$mac_bundle/"
    sed -e "s/@VERSION@/$version/g" -e "s/@PACKAGE@/$package/g" -e "s/@NQ_TAG@/$nq_tag/g" \
        "$repo_root/release/INSTALL-noquarter-mac.md.in" > "$workdir/$mac_bundle/INSTALL.md"
    (cd "$workdir/$mac_bundle" && find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort \
        | xargs sha256sum > SHA256SUMS.contents)
    rm -f "$out/$mac_bundle.zip"
    (cd "$workdir" && zip -X -q -r "$out/$mac_bundle.zip" "$mac_bundle")
    sums+=("$mac_bundle.zip")
fi

(cd "$out" && sha256sum "${sums[@]}" > SHA256SUMS)

echo "==> done"
cat "$out/SHA256SUMS"

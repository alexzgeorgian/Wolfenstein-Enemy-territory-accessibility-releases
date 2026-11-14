#!/usr/bin/env bash
#
# Build the playable ET: Legacy accessibility mod package.
#
# Produces zzz_accessibility.pk3: an additive pk3 holding the
# accessibility-enabled cgame and ui libraries for both 32-bit and 64-bit
# Windows. A player drops it into their ET: Legacy "legacy" folder; the
# game loads whichever architecture matches their install.
#
# This script exists so the package is reproducible by anyone, rather
# than being whatever a person happened to type once. Everything it does
# was found by reading the engine, and the three findings that matter are
# recorded as comments where they apply - they are all silent failures if
# you get them wrong.
#
# Usage:
#   release/build-release.sh [--engine PATH] [--out DIR] [--version V]
#
#   --engine PATH   Existing ET: Legacy checkout to build from. Without
#                   it, the pinned tag is cloned into a temporary tree.
#   --out DIR       Where to write the package. Default: release/dist
#   --version V     Names the archive and the folder it unzips to.
#   --keep          Keep the working tree on exit (for debugging).
#   --notes-only    Re-render the release page text and nothing else.
#                   Needs SHA256SUMS already in --out and a --built-from
#                   commit, so a wording fix never re-uploads a binary
#                   and never moves a checksum a player wrote down.
#   --built-from C  The commit the published archive was built from.
#                   Only meaningful with --notes-only.
#   --mac-libs DIR  Also pack the Mac libraries, cgame_mac and ui_mac,
#                   built on a Mac with the same --version by
#                   release/build-mac-libs.sh, and make the Mac's zip,
#                   with qagame_mac, the game module with bots, beside
#                   the pk3 when DIR has it. Without it the package is
#                   Windows only, and eta-update.txt says so.
#
# Requires: cmake, git, zip, and the mingw-w64 cross compilers - both
# the C and the C++ ones, for each architecture.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow="$repo_root/.github/workflows/ci.yml"

# The engine revision is read out of the CI workflow rather than repeated
# here, so the package can never be built against a different tree than
# the one CI tests the patch series against.
read_pin() {
    local key="$1" value
    value="$(sed -n "s/^[[:space:]]*${key}:[[:space:]]*//p" "$workflow" | head -1)"
    if [ -z "$value" ]; then
        echo "error: could not read $key from $workflow" >&2
        exit 1
    fi
    printf '%s' "$value"
}

ETLEGACY_TAG="$(read_pin ETLEGACY_TAG)"
ETLEGACY_COMMIT="$(read_pin ETLEGACY_COMMIT)"

engine=""
outdir="$repo_root/release/dist"
version="dev"
keep=0
notes_only=0
built_from=""
mac_libs=""

while [ $# -gt 0 ]; do
    case "$1" in
        --engine)  engine="$2"; shift 2 ;;
        --out)     outdir="$2"; shift 2 ;;
        --version) version="$2"; shift 2 ;;
        --keep)    keep=1; shift ;;
        --notes-only) notes_only=1; shift ;;
        --built-from) built_from="$2"; shift 2 ;;
        --mac-libs) mac_libs="$2"; shift 2 ;;
        -h|--help) sed -n '2,38p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

# The names the renderer substitutes into both templates. Defined here
# because --notes-only renders without ever reaching the packaging code
# that used to set them.
package="zzz_accessibility.pk3"
# One download for each system, named for it, so a player takes the one
# for their computer and finds only what it needs inside: the Mac's has
# no NVDA folder, and each guide speaks of its own system alone. The pk3
# inside is the same file in both - it carries the Windows and the Mac
# libraries - so the in-game updater has one file to offer everyone.
bundle="wolfenstein-enemy-territory-accessibility-$version-windows"
mac_bundle="wolfenstein-enemy-territory-accessibility-$version-mac"
# Which system a template is being rendered for: a guide drops the other
# system's <!-- windows --> ... <!-- /windows --> or <!-- mac --> ...
# <!-- /mac --> blocks. Empty keeps both, for the release page.
system=""

# Both the release page and the install guide are templates in the
# repository rather than text pasted into a workflow file or a document
# edited by hand each release. Two reasons: a change to the wording
# arrives as a reviewable diff, and a locally built package carries the
# same text CI would publish, so it can be proofread before it is public
# rather than after.
commit="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || echo unknown)"

# & and \ are special on the right-hand side of a sed s///, and | is the
# delimiter used below.
# A value of several lines, such as SHA256SUMS naming both archives, has
# its line breaks written as \n, which GNU sed turns back into them.
escape_for_sed() {
    local escaped
    escaped="$(printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g')"
    printf '%s' "${escaped//$'\n'/\\n}"
}

# A placeholder nobody filled in publishes as a literal @NAME@ on a
# public page or in the guide a player follows. It reads as broken
# software and is easy to miss, so it fails the build instead.
render_template() {
    local template="$1" output="$2"

    if [ ! -f "$template" ]; then
        echo "error: $template is missing" >&2
        exit 1
    fi

    # The other system's blocks go, and the markers themselves always.
    local drop='s/^//'
    case "$system" in
        windows) drop='/^<!-- mac -->$/,/^<!-- \/mac -->$/d' ;;
        mac)     drop='/^<!-- windows -->$/,/^<!-- \/windows -->$/d' ;;
    esac

    sed -e "$drop" -e '/^<!-- \/\{0,1\}\(windows\|mac\) -->$/d' "$template" |
    sed -e "s|@VERSION@|$(escape_for_sed "$version")|g" \
        -e "s|@ARCHIVE@|$(escape_for_sed "$bundle.zip")|g" \
        -e "s|@MAC_ARCHIVE@|$(escape_for_sed "$mac_bundle.zip")|g" \
        -e "s|@PACKAGE@|$(escape_for_sed "$package")|g" \
        -e "s|@CHECKSUM_LINE@|$(escape_for_sed "$(cat "$outdir/SHA256SUMS" 2>/dev/null || echo "")")|g" \
        -e "s|@COMMIT@|$(escape_for_sed "$commit")|g" \
        -e "s|@ENGINE_TAG@|$(escape_for_sed "$ETLEGACY_TAG")|g" \
        -e "s|@ENGINE_COMMIT@|$(escape_for_sed "$ETLEGACY_COMMIT")|g" \
        -e "/@CHANGES@/{r $repo_root/release/CHANGES.md
d
}" \
        -e "/@HISTORY@/{r $repo_root/release/HISTORY.md
d
}" \
        -e "/@SUMMARY@/{r $summary_file
d
}" \
        > "$output"

    if grep -q '@[A-Z_][A-Z_]*@' "$output"; then
        echo "error: unreplaced placeholder in $(basename "$output"):" >&2
        grep -o '@[A-Z_][A-Z_]*@' "$output" | sort -u >&2
        exit 1
    fi
}

if [ ! -f "$repo_root/release/CHANGES.md" ]; then
    echo "error: release/CHANGES.md is missing; the release page would" \
         "publish without saying what changed" >&2
    exit 1
fi

# The release page says what changed in a few lines: CHANGES.md up to its
# first section heading - the one-line summary and its short list. The
# rest, the detail, is in the download's CHANGELOG.md. A CHANGES.md with
# no summary above its sections would leave the page saying nothing.
summary_file="$(mktemp)"
trap 'rm -f "$summary_file"' EXIT
sed '/^## /,$d' "$repo_root/release/CHANGES.md" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' > "$summary_file"
if ! grep -q '[^[:space:]]' "$summary_file"; then
    echo "error: release/CHANGES.md has nothing above its first ## heading;" \
         "the release page would have no summary of what changed" >&2
    exit 1
fi

# sed's `r` on a file that does not exist inserts nothing and reports
# nothing, so a missing history would ship a changelog whose second half
# is silently empty - and the placeholder check below would not see it
# either, because the placeholder line is deleted either way.
if [ ! -f "$repo_root/release/HISTORY.md" ]; then
    echo "error: release/HISTORY.md is missing; the archive's changelog" \
         "would cover only this build" >&2
    exit 1
fi

# Correcting the wording on a published page should not re-upload a
# binary. The archive's timestamps are pinned to SOURCE_DATE_EPOCH, which
# is this repository's last commit, so rebuilding moves the checksum even
# when the libraries are byte-identical - and a player who wrote the old
# one down is then told a good download is wrong.
if [ "$notes_only" -eq 1 ]; then
    outdir="$(cd "$outdir" && pwd)"

    if [ ! -f "$outdir/SHA256SUMS" ]; then
        echo "error: --notes-only needs the published SHA256SUMS in $outdir," \
             "so the page keeps quoting the checksum the download has" >&2
        exit 1
    fi

    if [ -z "$built_from" ]; then
        echo "error: --notes-only needs --built-from, or the page would claim" \
             "the archive came from a commit that never produced it" >&2
        exit 1
    fi

    commit="$built_from"
    # The page names the archive that is published, whatever this
    # version of the script would call it: older releases' archives
    # were named without the systems.
    published="$(sed -n 's/^[0-9a-f]\{64\}  \(.*\)\.zip$/\1/p' "$outdir/SHA256SUMS")"
    if [ -n "$published" ]; then
        bundle="$(printf '%s\n' "$published" | grep -- '-windows$' || printf '%s\n' "$published" | head -1)"
        mac_bundle="$(printf '%s\n' "$published" | grep -- '-mac$' || printf '%s\n' "$published" | head -1)"
        bundle="$(printf '%s\n' "$bundle" | head -1)"
        mac_bundle="$(printf '%s\n' "$mac_bundle" | head -1)"
    fi
    render_template "$repo_root/release/NOTES.md.in" "$outdir/NOTES.md"

    echo "re-rendered $outdir/NOTES.md for $version"
    echo "  built from $built_from (unchanged; no archive was produced)"
    exit 0
fi

# Every tool this script hands to CMake, not just the ones it calls
# itself. ET: Legacy's project() declares C and C++, so CMake probes for
# the C++ compiler even though the mod libraries are pure C - and if it
# is missing, the failure surfaces as a CMake error deep in a configure
# log rather than as a missing dependency.
for tool in cmake git zip \
            x86_64-w64-mingw32-gcc x86_64-w64-mingw32-g++ \
            i686-w64-mingw32-gcc   i686-w64-mingw32-g++; do
    command -v "$tool" >/dev/null || { echo "error: $tool is not installed" >&2; exit 1; }
done

workdir="$(mktemp -d "${TMPDIR:-/tmp}/eta-release-XXXXXX")"
cleanup() { rm -f "$summary_file"; [ "$keep" -eq 1 ] || rm -rf "$workdir"; }
trap cleanup EXIT

borrowed_engine=""

restore_engine() {
    if [ -n "$borrowed_engine" ]; then
        rm -f "$borrowed_engine/accessibility-mode"
        git -C "$borrowed_engine" checkout -- . 2>/dev/null || true
    fi
}

if [ -n "$engine" ]; then
    engine="$(cd "$engine" && pwd)"
    echo "==> using the ET: Legacy tree at $engine"
    if [ -n "$(git -C "$engine" status --porcelain -- src cmake CMakeLists.txt)" ]; then
        echo "error: $engine has local modifications; the patch series needs a clean tree" >&2
        exit 1
    fi
    # Someone lent us their checkout; hand it back the way we found it.
    borrowed_engine="$engine"
    trap 'restore_engine; cleanup' EXIT
else
    engine="$workdir/etlegacy"
    echo "==> cloning ET: Legacy $ETLEGACY_TAG"
    git clone --depth 1 --branch "$ETLEGACY_TAG" \
        https://github.com/etlegacy/etlegacy.git "$engine" >/dev/null 2>&1
    actual="$(git -C "$engine" rev-parse HEAD)"
    if [ "$actual" != "$ETLEGACY_COMMIT" ]; then
        echo "error: $ETLEGACY_TAG resolved to $actual, expected $ETLEGACY_COMMIT" >&2
        exit 1
    fi
    # Only 'libs' is needed for the mod libraries; it carries cJSON.
    git -C "$engine" submodule update --init --depth 1 libs >/dev/null 2>&1
fi

echo "==> applying the patch series"
for patch in "$repo_root"/integration/etlegacy/0*.patch; do
    git -C "$engine" apply "$patch" || {
        echo "error: $(basename "$patch") does not apply to $ETLEGACY_TAG" >&2
        exit 1
    }
done

# The wiring expects this repository at <engine>/accessibility-mode.
rm -rf "$engine/accessibility-mode"
ln -s "$repo_root" "$engine/accessibility-mode"

build_arch() {
    local label="$1" processor="$2" cc="$3" cxx="$4" rc="$5"
    local dir="$workdir/build-$label"

    echo "==> building $label"

    # Two flags here are load-bearing, and both fail silently:
    #
    #   CMAKE_SYSTEM_PROCESSOR - when cross compiling CMake leaves this
    #   empty, ET: Legacy's arch detection then fails, and ARCH ends up
    #   as "". The libraries build fine but come out named cgame_mp_.dll
    #   while the engine looks for cgame_mp_x64.dll, so nothing loads and
    #   nothing says why.
    #
    #   CROSS_COMPILE32 - defaults ON, and forces a 32-bit build even
    #   when the compiler is x86_64, quietly producing the wrong package.
    #
    #   ETA_RELEASE_VERSION, ETA_ENGINE_TAG - what the in-game updater
    #   compares the release page against. Left out, the build calls
    #   itself "dev" and never offers to replace itself.
    # The engine bakes absolute source paths into the binaries through
    # __FILE__ (44 of them per module, in assertions and logging), so
    # without this the checksum depends on which directory you happened
    # to build in and two correct builds never agree. Mapping the paths
    # to fixed names makes the output verifiable: anyone can rebuild and
    # compare against the published SHA256SUMS.
    local prefix_map="-ffile-prefix-map=$engine=/etlegacy -ffile-prefix-map=$repo_root=/accessibility-mode"

    cmake -B "$dir" -S "$engine" \
        -DCMAKE_C_FLAGS="$prefix_map" \
        -DCMAKE_SYSTEM_NAME=Windows \
        -DCMAKE_SYSTEM_PROCESSOR="$processor" \
        -DCMAKE_C_COMPILER="$cc" \
        -DCMAKE_CXX_COMPILER="$cxx" \
        -DCMAKE_RC_COMPILER="$rc" \
        -DCROSS_COMPILE32=OFF \
        -DBUILD_MOD=ON -DFEATURE_ACCESSIBILITY=ON \
        -DBUILD_CLIENT=OFF -DBUILD_SERVER=OFF -DINSTALL_EXTRA=OFF \
        -DETA_RELEASE_VERSION="$version" -DETA_ENGINE_TAG="$ETLEGACY_TAG" \
        -DCMAKE_BUILD_TYPE=Release >/dev/null

    cmake --build "$dir" --target cgame ui -j"$(nproc 2>/dev/null || echo 2)" >/dev/null

    cp "$dir/legacy/cgame_mp_$label.dll" "$dir/legacy/ui_mp_$label.dll" "$workdir/stage/"
}

# ET: Legacy stamps the build time into the binaries via
# string(TIMESTAMP) in cmake/ETLVersion.cmake, so two builds a minute
# apart differ. CMake honours SOURCE_DATE_EPOCH there, so pinning it to
# this repository's last commit makes the output depend on the source
# rather than on the clock. Together with the path mapping above, that
# means a given commit always produces the same libraries, and anyone
# can rebuild and check the published checksums.
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
    SOURCE_DATE_EPOCH="$(git -C "$repo_root" log -1 --format=%ct 2>/dev/null || echo 0)"
fi
export SOURCE_DATE_EPOCH
echo "==> source date epoch $SOURCE_DATE_EPOCH ($(date -u -d "@$SOURCE_DATE_EPOCH" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown))"

mkdir -p "$workdir/stage"
build_arch x64 amd64 x86_64-w64-mingw32-gcc x86_64-w64-mingw32-g++ x86_64-w64-mingw32-windres
build_arch x86 x86   i686-w64-mingw32-gcc   i686-w64-mingw32-g++   i686-w64-mingw32-windres

echo "==> verifying the libraries"
fail=0
for dll in cgame_mp_x64.dll ui_mp_x64.dll cgame_mp_x86.dll ui_mp_x86.dll; do
    path="$workdir/stage/$dll"
    [ -f "$path" ] || { echo "  MISSING $dll"; fail=1; continue; }

    # Dumped once to a file rather than piped per check: `strings | grep -q`
    # looks right and is a trap, because grep -q closes the pipe on its
    # first match, strings dies of SIGPIPE, and `set -o pipefail` then
    # reports the whole pipeline as a failure - so every check "fails"
    # precisely when it should pass.
    strings "$path" > "$workdir/strings.txt"

    # vmMain and dllEntry are what the engine calls into. Without them the
    # library loads and then does nothing.
    for symbol in vmMain dllEntry; do
        grep -qx "$symbol" "$workdir/strings.txt" || { echo "  $dll does not export $symbol"; fail=1; }
    done

    # Proof the feature is actually compiled in rather than stubbed out:
    # with FEATURE_ACCESSIBILITY off these strings do not exist.
    grep -q nvdaControllerClient "$workdir/strings.txt" || { echo "  $dll has no NVDA speech path"; fail=1; }
done
[ "$fail" -eq 0 ] || { echo "error: the built libraries are not usable" >&2; exit 1; }

# The Mac libraries, built on a Mac: one file each holding Apple Silicon
# and Intel, named as the engine looks for them (DLL_EXT "_mac" in
# q_platform.h, no architecture in the name). The engine unpacks them
# from the pk3 into the player's own folder before loading, as it does
# the Windows ones, so the one pk3 serves both.
mac_files=""
if [ -n "$mac_libs" ]; then
    echo "==> adding the Mac libraries"
    for lib in cgame_mac ui_mac; do
        if [ ! -f "$mac_libs/$lib" ]; then
            echo "error: $mac_libs/$lib is missing" >&2
            exit 1
        fi
        cp "$mac_libs/$lib" "$workdir/stage/$lib"
        strings "$workdir/stage/$lib" > "$workdir/strings.txt"
        for symbol in vmMain dllEntry; do
            grep -q "$symbol" "$workdir/strings.txt" || { echo "  $lib does not export $symbol"; fail=1; }
        done
        # The Mac speech is in: VoiceOver's announcement, and the system voice.
        grep -q AVSpeechSynthesizer "$workdir/strings.txt" || { echo "  $lib has no Mac speech path"; fail=1; }
    done
    # The menus carry the updater, which must know which version it is:
    # a Mac build named anything else would offer this release to itself
    # forever, or never offer the next one.
    strings "$workdir/stage/ui_mac" > "$workdir/strings.txt"
    grep -q ETAccessibilityUpdater "$workdir/strings.txt" || { echo "  ui_mac has no updater"; fail=1; }
    grep -qxF "$version" "$workdir/strings.txt" || { echo "  ui_mac is not built as $version"; fail=1; }
    [ "$fail" -eq 0 ] || { echo "error: the Mac libraries are not usable" >&2; exit 1; }
    mac_files="cgame_mac ui_mac"
fi

# The pk3 name has to sort after the stock legacy_*.pk3. ET: Legacy sorts
# a mod folder's pk3 files ascending and then prepends each to the search
# path, so the alphabetically last one is searched first and wins. Rename
# this earlier in the alphabet and the stock libraries load instead, with
# no error.
package="zzz_accessibility.pk3"

# A release is one file that extracts into one folder. Downloading a
# directory is not something a web browser can do, so shipping the pk3,
# the guide and the checksums as loose files means fetching each by hand
# and ending up with four unrelated things in a downloads folder. The
# name is the one set above.

# Resolved to an absolute path: the archive is written from inside the
# staging directory, so a relative --out would land somewhere surprising
# or fail outright.
mkdir -p "$outdir"
outdir="$(cd "$outdir" && pwd)"

# The mod pk3 itself, assembled inside the folder the player will unzip.
rm -rf "$workdir/$bundle"
mkdir -p "$workdir/$bundle"


# The mod's own cue sounds. Generated rather than shipped as binaries:
# they loop continuously and nothing in ET's sound set does that well, so
# they are synthesised, and the synthesis is readable source in the
# repository instead of four opaque files. The generator is
# deterministic, so this does not move the archive's checksum.
echo "==> generating the cue sounds"
mkdir -p "$workdir/stage/sound/accessibility"
python3 "$repo_root/release/make-cue-sounds.py" \
    "$workdir/stage/sound/accessibility"

# Every sound the mod registers has to actually be in the pk3. A missing
# one plays silence and says nothing about it - the quietest failure
# this project has, and the reason for this check rather than trust.
missing=0
for sound in $(grep -oE '"sound/accessibility/[a-z_]+\.wav"' \
               "$engine/src/cgame/cg_main.c" | tr -d '"' | sort -u); do
    if [ ! -f "$workdir/stage/$sound" ]; then
        echo "  $sound is registered by the mod but was not generated"
        missing=1
    fi
done
[ "$missing" -eq 0 ] || {
    echo "error: the pk3 would ship without sounds the mod asks for" >&2
    exit 1
}

# The menu files. Two of them, and they are different in kind.
#
# ui/options_accessibility*.menu are the mod's own pages - a menu of
# four buttons and the Environment, Speech, Key Binds and Hosting pages
# it opens.
# They shadow nothing: the ui module parses each by name, in addition to
# the game's own menu list, so they simply did not exist before.
# ui/accessibility_update.menu is the same kind: the popups that offer a
# newer version of the mod, parsed by name and shadowing nothing.
#
# ui/options.menu is a copy of the game's, with one button added to
# reach that page. It does shadow the original, which is a real cost: an
# upstream edit to it would stop reaching players until the copy is
# re-derived. (A copy of options_controls.menu shipped for one release,
# to reach a separate keys page; the keys are back on the accessibility
# page and CONTROLS is the game's own again.)
# tests/menu_override_test.py exists to make that loud - it fails the
# build when the engine's copy stops matching the .stock file recorded
# beside ours.
echo "==> packing the menus"
mkdir -p "$workdir/stage/ui"
for menu in options_accessibility.menu \
            options_accessibility_environment.menu \
            options_accessibility_speech.menu \
            options_accessibility_sound.menu \
            options_accessibility_keys.menu \
            options_accessibility_hosting.menu \
            accessibility_update.menu \
            options.menu; do
    if [ ! -f "$repo_root/release/ui/$menu" ]; then
        echo "error: release/ui/$menu is missing; the accessibility menu" \
             "would not be reachable" >&2
        exit 1
    fi
    cp "$repo_root/release/ui/$menu" "$workdir/stage/ui/$menu"
done

# Every setting and command the page names has to exist. A misspelled
# cvar on a menu row is a control that moves and changes nothing, and a
# misspelled command is a bind row that binds into the void - both
# silent, and neither visible to anyone who cannot see the screen.
python3 "$repo_root/tests/menu_override_test.py" "$engine" \
    --menus "$repo_root/release/ui" || {
    echo "error: the shipped menus do not match the engine" >&2
    exit 1
}

# zip records each entry's mtime, so an archive checksum moves even when
# the files inside are identical. Pin them to the same epoch.
touch -d "@$SOURCE_DATE_EPOCH" "$workdir/stage"/*.dll
for lib in $mac_files; do
    touch -d "@$SOURCE_DATE_EPOCH" "$workdir/stage/$lib"
done
touch -d "@$SOURCE_DATE_EPOCH" "$workdir/stage/sound/accessibility"/*.wav
touch -d "@$SOURCE_DATE_EPOCH" "$workdir/stage/ui"/*.menu
touch -d "@$SOURCE_DATE_EPOCH" "$workdir/stage/sound/accessibility" \
    "$workdir/stage/sound" "$workdir/stage/ui"
( cd "$workdir/stage" && zip -q -9 -X "$workdir/$bundle/$package" \
    cgame_mp_x64.dll ui_mp_x64.dll cgame_mp_x86.dll ui_mp_x86.dll $mac_files \
    sound/accessibility/*.wav ui/*.menu )

# Two documents, deliberately. The guide answers "how do I run this"
# and the changelog answers "what is different this time"; a reader
# arriving with one of those questions should not have to skim the other
# to find it. Keeping them apart is also what stopped the guide drifting
# into a release history - it had collected notes about alpha-0.1.0 and
# alpha-0.4.0 that were still being shipped, and read as current, long
# after they stopped being true.
system=windows
render_template "$repo_root/release/INSTALL.md.in" "$workdir/$bundle/INSTALL.md"
render_template "$repo_root/release/CHANGELOG.md.in" "$workdir/$bundle/CHANGELOG.md"
system=""


# The same sounds, loose and looped for a few seconds, so they can be
# listened to before the game is even installed - in File Explorer, with
# whatever plays a .wav. One loop of the crosshair tick is a fifth of a
# second, too short to judge, hence the longer copies. These are for
# listening only: the game plays the ones inside the pk3.
echo "==> writing the sound previews"
python3 "$repo_root/release/make-cue-sounds.py" --preview "$workdir/$bundle/sounds" >/dev/null

# The ready-made config. It ships beside the pk3 rather than inside it
# so the player can read it, edit it, and delete it - a copy inside the
# pk3 would sit in the search path shadowing their own.
if [ -f "$repo_root/release/autoexec.cfg" ]; then
    cp "$repo_root/release/autoexec.cfg" "$workdir/$bundle/autoexec.cfg"
else
    echo "error: release/autoexec.cfg is missing; the archive would ship" \
         "without the only configuration the mod needs" >&2
    exit 1
fi

# The NVDA controller client. The mod has spoken through NVDA since its
# first release, but the DLL that carries the speech across is NV
# Access's and ships separately from NVDA itself, so every player had to
# go and find it - and the ones who search for a DLL by name land on
# sites serving tampered copies. For somebody who cannot see the screen
# that is the worst case there is, so the real file comes in the
# archive, pinned by checksum and with NV Access's own licence text.
echo "==> fetching the NVDA controller client"
"$repo_root/release/fetch-nvda-client.sh" "$workdir/$bundle/nvda"

# Checksums of the libraries inside the pk3, for anyone who wants to look
# that far in. Kept separate from the archive's own checksum because
# `sha256sum -c` fails on any line naming a file it cannot find.
{
    echo "# Checksums of everything inside $package."
    echo "# Unzip $package first, then: sha256sum -c SHA256SUMS.contents"
    ( cd "$workdir/stage" && sha256sum ./*.dll $mac_files sound/accessibility/*.wav \
        ui/*.menu | sed 's#\./##' )
} > "$workdir/$bundle/SHA256SUMS.contents"

# The Mac's download: the same folder without the NVDA client, which is
# Windows software, and with the guide written for the Mac.
bundles="$bundle"
if [ -n "$mac_files" ]; then
    echo "==> making the Mac download"
    rm -rf "$workdir/$mac_bundle"
    cp -a "$workdir/$bundle" "$workdir/$mac_bundle"
    rm -rf "$workdir/$mac_bundle/nvda"
    # The game module with bots, when the Mac build made one. It goes
    # beside the pk3, not in it: the engine loads the game module only as
    # a loose file. The guide says where it goes.
    if [ -f "$mac_libs/qagame_mac" ]; then
        strings "$mac_libs/qagame_mac" > "$workdir/strings.txt"
        grep -q 'omnibot_et' "$workdir/strings.txt" \
            || { echo "error: $mac_libs/qagame_mac has no Omni-bot support" >&2; exit 1; }
        cp "$mac_libs/qagame_mac" "$workdir/$mac_bundle/qagame_mac"
        touch -d "@$SOURCE_DATE_EPOCH" "$workdir/$mac_bundle/qagame_mac"
    fi
    system=mac
    render_template "$repo_root/release/INSTALL.md.in" "$workdir/$mac_bundle/INSTALL.md"
    system=""
    bundles="$bundle $mac_bundle"
fi

# SHA256SUMS lists only what sits beside it - the archives - so
# `sha256sum -c SHA256SUMS` succeeds cleanly on a good download.
: > "$outdir/SHA256SUMS"
for folder in $bundles; do
    rm -f "$outdir/$folder.zip"
    # -depth so a directory is stamped after the files inside it; writing
    # a file into a directory moves that directory's own mtime, and an
    # archive whose checksum drifts is one a player is told their good
    # download is bad. The nvda/ subtree is why this is a walk rather
    # than one glob.
    find "$workdir/$folder" -depth -exec touch -d "@$SOURCE_DATE_EPOCH" {} +
    ( cd "$workdir" && zip -q -9 -X -r "$outdir/$folder.zip" "$folder" )
    ( cd "$outdir" && sha256sum "$folder.zip" >> SHA256SUMS )
done

# What the in-game updater reads. The release workflow publishes the pk3
# on its own beside the archive, and this file names it: which version
# it is, which ET: Legacy it is built for, and the checksum and size the
# download has to match before the game will put it in place. The keys
# are the ones ETA_Update_ParseManifest reads (src/accessibility/update).
cp "$workdir/$bundle/$package" "$outdir/$package"
# The Mac's game module with bots goes up beside the pk3 too: on a Mac set
# up for bots, the menus fetch it from the release and put it in place,
# checked against the checksum built into ui_mac.
rm -f "$outdir/qagame_mac"
if [ -n "$mac_files" ] && [ -f "$mac_libs/qagame_mac" ]; then
    cp "$mac_libs/qagame_mac" "$outdir/qagame_mac"
fi
# Which systems the pk3 has game code for. A Mac takes only a release
# that names macos; one without the key is taken as Windows alone.
platforms="windows"
[ -z "$mac_files" ] || platforms="windows,macos"
{
    echo "# Read by accessibility mode's in-game updater."
    echo "version=$version"
    echo "engine=$ETLEGACY_TAG"
    echo "sha256=$(sha256sum "$outdir/$package" | cut -d' ' -f1)"
    echo "size=$(wc -c < "$outdir/$package" | tr -d ' ')"
    echo "platforms=$platforms"
} > "$outdir/eta-update.txt"

render_template "$repo_root/release/NOTES.md.in" "$outdir/NOTES.md"

echo
for folder in $bundles; do
    echo "built $outdir/$folder.zip"
    echo "  unzips to $folder/"
    echo "  holding   $(cd "$workdir/$folder" && echo * | tr ' ' '\n' | tr '\n' ' ')"
    echo "  size      $(du -h "$outdir/$folder.zip" | cut -f1)"
done
echo "  engine    $ETLEGACY_TAG ($ETLEGACY_COMMIT)"
echo "  libraries $(cd "$workdir/stage" && echo ./*.dll | tr ' ' '\n' | sed 's#\./##' | tr '\n' ' ')$mac_files"
echo "  notes     $outdir/NOTES.md ($(wc -l < "$outdir/NOTES.md") lines)"
echo "  updater   $outdir/eta-update.txt and $outdir/$package"

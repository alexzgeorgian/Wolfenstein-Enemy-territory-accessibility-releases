#!/usr/bin/env bash
#
# Builds the Mac libraries, on a Mac, for release/build-release.sh
# --mac-libs to pack. One script for CI, the release and the Mac test
# build, so the three cannot drift apart.
#
#   cgame_mac, ui_mac  the mod, which go into the pk3; Apple Silicon and
#                      Intel in one file each.
#   qagame_mac         the game module, which runs a match the player
#                      hosts. ET: Legacy builds its Mac one without
#                      Omni-bot ("No Omnibot Support for OSX" in its
#                      easybuild.sh), so a Mac host gets no bots. This is
#                      ET: Legacy's own, unchanged, built with Omni-bot
#                      support turned on, and without the accessibility
#                      layer, which it has no use for. The engine loads
#                      it only as a loose file, so it ships beside the
#                      pk3, and its SHA-256 is built into the menus so
#                      they can tell when the copy installed is not this
#                      one.
#
#   release/build-mac-libs.sh ENGINE OUT VERSION ENGINE_TAG
#
# ENGINE is an ET: Legacy tree with the patch series applied and
# accessibility-mode linked in. Writes OUT/cgame_mac, OUT/ui_mac,
# OUT/qagame_mac.

set -euo pipefail

engine="$1"
out="$2"
version="$3"
engine_tag="$4"

common=(
    -DCMAKE_BUILD_TYPE=Release
    -DBUILD_CLIENT=OFF -DBUILD_SERVER=OFF -DBUILD_MOD=ON -DBUILD_MOD_PK3=OFF
    -DFEATURE_RENDERER2=OFF -DFEATURE_RENDERER_GLES=OFF -DRENDERER_DYNAMIC=OFF
    -DFEATURE_CURL=OFF -DFEATURE_OGG_VORBIS=OFF -DFEATURE_THEORA=OFF
    -DFEATURE_OPENAL=OFF -DFEATURE_FREETYPE=OFF -DFEATURE_PNG=OFF
    -DBUNDLED_SDL=OFF -DBUNDLED_ZLIB=OFF -DBUNDLED_MINIZIP=OFF -DBUNDLED_JPEG=OFF
    -DBUNDLED_OGG_VORBIS=OFF -DBUNDLED_THEORA=OFF -DBUNDLED_GLEW=OFF
    -DBUNDLED_FREETYPE=OFF -DBUNDLED_PNG=OFF -DBUNDLED_CURL=OFF -DBUNDLED_OPENAL=OFF
    -DINSTALL_EXTRA=OFF -DINSTALL_OMNIBOT=OFF
    -DCMAKE_OSX_DEPLOYMENT_TARGET=10.14
    "-DCMAKE_OSX_ARCHITECTURES=x86_64;arm64"
)

universal() {
    local archs
    archs="$(lipo -archs "$1")"
    echo "$(basename "$1"): $archs"
    case " $archs " in *" x86_64 "*) ;; *) echo "error: $1 has no Intel code" >&2; exit 1 ;; esac
    case " $archs " in *" arm64 "*) ;; *) echo "error: $1 has no Apple Silicon code" >&2; exit 1 ;; esac
}

mkdir -p "$out"

echo "==> qagame_mac, ET: Legacy's game module with Omni-bot"
cmake -S "$engine" -B build-game "${common[@]}" \
    -DFEATURE_ACCESSIBILITY=OFF -DFORCE_OMNIBOT=ON -DFEATURE_OMNIBOT=ON >/dev/null
grep -q '^FEATURE_OMNIBOT:BOOL=ON' build-game/CMakeCache.txt \
    || { echo "error: Omni-bot support did not turn on for the Mac game module" >&2; exit 1; }
cmake --build build-game --target qagame -j
universal build-game/legacy/qagame_mac
nm build-game/legacy/qagame_mac > build-game/qagame.symbols
grep -q 'Omnibot_LoadLibrary' build-game/qagame.symbols \
    || { echo "error: qagame_mac does not carry Omni-bot's loader" >&2; exit 1; }
cp build-game/legacy/qagame_mac "$out/qagame_mac"
game_sha="$(shasum -a 256 "$out/qagame_mac" | cut -d' ' -f1)"
echo "qagame_mac sha256 $game_sha"

echo "==> cgame_mac and ui_mac, the mod"
cmake -S "$engine" -B build "${common[@]}" \
    -DFEATURE_ACCESSIBILITY=ON \
    -DETA_RELEASE_VERSION="$version" -DETA_ENGINE_TAG="$engine_tag" \
    -DETA_MAC_GAME_SHA256="$game_sha" >/dev/null
cmake --build build --target cgame ui -j
for lib in cgame_mac ui_mac; do
    universal "build/legacy/$lib"
    cp "build/legacy/$lib" "$out/$lib"
done

# The menus check the bots file against this one.
strings "$out/ui_mac" > build/ui.strings
grep -qx "$game_sha" build/ui.strings \
    || { echo "error: ui_mac does not know qagame_mac's checksum" >&2; exit 1; }

echo "built $(ls "$out" | tr '\n' ' ')"

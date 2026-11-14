#!/usr/bin/env python3
"""Check that the look-ahead probe reports what the engine actually sees.

Why this exists
---------------
The binoculars and the scope answer "what is in front of me" with a trace
along the view. Two things about that have to stay true, and neither
shows up as a compile error.

**It has to be a trace.** The only honest answer to "what is in front of
me" is what the engine's own collision says is there. A description
assembled from anything else - nearby entities, the command map, a guess
from the player's position - would be confidently wrong exactly when it
matters, which for a player lining up a shot is worse than silence.

**The materials have to be the engine's own.** `SURF_METAL`, `SURF_WOOD`
and the rest are the flags the engine already uses to choose footstep
and impact sounds, so they are the game's idea of what a surface is made
of. A table of our own would drift from what the player hears underfoot.

So this reads both out of the patched engine, along with the orientation
test that separates a wall from the ground - getting that backwards
would report every floor as a wall and never say "ground" at all.

Usage
-----
    ./look_ahead_test.py <engine-root>

Run it against an engine checkout with the patch series applied. Works on
both supported trees.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
SURFACEFLAGS = os.path.join("src", "game", "surfaceflags.h")

PROBE = "ETA_DescribeLookAhead"

# The naming half of the look-ahead was split into its own function so
# the obstacle narration could describe a different trace with the same
# words. The trace still lives in PROBE; the plane test moved here. A
# refactor is not a regression, but a test that keeps looking in the old
# place quietly stops checking anything - so it follows the code.
NAMER = "ETA_DescribeTraceHit"
SURFACE = "ETA_DescribeSurface"
MATERIALS = "ETA_SurfaceMaterial"
NARRATOR = "ETA_NarrateZoom"


def strip_comments(text):
    out, i, n = [], 0, len(text)
    while i < n:
        two = text[i:i + 2]
        if two == "/*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif two == "//":
            end = text.find("\n", i)
            i = n if end < 0 else end
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def function_body(text, name):
    match = re.search(r'\b%s\s*\([^;{}]*\)\s*\{' % re.escape(name), text)
    if not match:
        return None
    depth, i = 0, match.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    draw_path = os.path.join(root, DRAW)
    flags_path = os.path.join(root, SURFACEFLAGS)

    for path in (draw_path, flags_path):
        if not os.path.isfile(path):
            sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                     % (os.path.relpath(path, root), root))

    with open(draw_path, "r", errors="replace") as handle:
        draw = strip_comments(handle.read())
    with open(flags_path, "r", errors="replace") as handle:
        engine_flags = set(re.findall(r'#define\s+(SURF_[A-Z0-9_]+)',
                                      strip_comments(handle.read())))

    failures = []

    probe = function_body(draw, PROBE)
    if probe is None:
        sys.exit("could not find %s in %s - the look-ahead this test exists "
                 "to guard is gone" % (PROBE, DRAW))

    # 1. It asks the engine's collision, not something else.
    if "CG_Trace(" not in probe.replace(" ", ""):
        failures.append(
            "%s does not call CG_Trace. Anything other than the engine's own "
            "collision is a guess about what the player is looking at, and "
            "would be confidently wrong exactly when it matters" % PROBE)
    else:
        print("[look] %s answers with a CG_Trace along the view" % PROBE)

    # 2. A wall is told from the ground by the impact plane. Whichever of
    #    the functions holds that logic - the probe, the namer, or the
    #    surface wording the namer hands a hit to - one of them must.
    namer = function_body(draw, NAMER)
    surface = function_body(draw, SURFACE) if "ETA_DescribeSurface(" in (namer or "") else ""
    naming = (probe + (namer or "") + (surface or "")).replace(" ", "")

    if "plane.normal" not in naming:
        failures.append(
            "neither %s nor %s reads the impact plane, so nothing can tell "
            "a wall from the ground or a ceiling" % (PROBE, NAMER))
    else:
        print("[look] wall, ground and ceiling are separated by the plane")

    # And the two must not drift apart: the obstacle report and the scope
    # report should use the same words for the same thing.
    if namer is not None and NAMER not in probe:
        failures.append(
            "%s exists but %s does not use it - two copies of the naming "
            "means the scope and the obstacle report can start describing "
            "the same wall differently" % (NAMER, PROBE))

    # 3. Materials come from the engine's own flags.
    materials = function_body(draw, MATERIALS)
    if materials is None:
        failures.append(
            "could not find %s - the materials would have to come from a "
            "table of the mod's own, which drifts from what the engine uses "
            "for footsteps and impacts" % MATERIALS)
    else:
        used = set(re.findall(r'\bSURF_[A-Z0-9_]+\b', materials))
        unknown = sorted(used - engine_flags)
        if unknown:
            failures.append(
                "%s tests %s, which %s does not define"
                % (MATERIALS, ", ".join(unknown), SURFACEFLAGS))
        elif not used:
            failures.append(
                "%s names no surface flags at all, so every surface would be "
                "described without its material" % MATERIALS)
        else:
            print("[look] %s uses %d of the engine's own surface flags: %s"
                  % (MATERIALS, len(used), ", ".join(sorted(used))))

    # 4. The sky is not given a distance.
    if "SURF_SKY" not in probe:
        failures.append(
            "%s does not special-case SURF_SKY. The skybox is not something "
            "the player can reach, and a distance to it is the distance to "
            "the edge of the map" % PROBE)
    else:
        print("[look] %s treats the skybox as open sky, without a distance"
              % PROBE)

    # 5. The narration exists and is driven by the zoom state.
    narrator = function_body(draw, NARRATOR)
    if narrator is None:
        failures.append("could not find %s - nothing calls the probe" % NARRATOR)
    else:
        for field in ("zoomedBinoc", "zoomed"):
            if field not in narrator:
                failures.append(
                    "%s does not read cg.%s, so it cannot tell which of the "
                    "binoculars and the scope is up" % (NARRATOR, field))
        if PROBE + "(" not in narrator.replace(" ", ""):
            failures.append("%s never calls %s" % (NARRATOR, PROBE))
        if not failures:
            print("[look] %s is driven by the engine's own zoom state"
                  % NARRATOR)

    if failures:
        print()
        for failure in failures:
            print("[look] FAIL %s" % failure)
        sys.exit(1)

    print("[look] ok")


if __name__ == "__main__":
    main()

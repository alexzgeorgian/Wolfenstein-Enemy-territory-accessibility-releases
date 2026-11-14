#!/usr/bin/env python3
"""Check the build progress is spoken while aiming at the construction.

Why this exists
---------------
The build progress was read from the cursor hint, the number beside the
pliers icon. A tester building the pump on Oasis, aiming at it with the
look keys, heard "Pliers, build here" and then nothing: the server stops
sending that hint to a player whose crosshair is on a partly built
construction of their own team (G_CheckForCursorHints returns early).
The completion hint is withheld the same way.

The same figure is the construction's own angles2[0], which is in every
snapshot, so the mod reads that when the hint is withheld and the pliers
are out. This test reads the server to confirm both halves of that are
still true, and the client to confirm it uses them:

  * the server still withholds the hint - if it ever stops, the
    fallback can go;
  * the server still keeps the progress in angles2[0] and puts it back
    to zero in the frame the work finishes - which is what the client
    reads, and how it hears the construction finish;
  * the client reads the construction's own figure when the hint is not
    there, and calls a drop from ninety percent to nothing a finish.

Usage
-----
    ./build_progress_test.py <engine-root>
"""

import argparse
import os
import re
import sys

G_MAIN = os.path.join("src", "game", "g_main.c")
G_WEAPON = os.path.join("src", "game", "g_weapon.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone" % (name, where))
    depth, i = 0, found.end() - 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[found.end():i]
        i += 1
    sys.exit("could not find the end of %s" % name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    g_main = read(args.root, G_MAIN)
    g_weapon = read(args.root, G_WEAPON)
    draw = read(args.root, DRAW)
    failures = []

    # --- the server ------------------------------------------------------
    hints = body_of(g_main, "G_CheckForCursorHints", G_MAIN)
    withheld = re.search(
        r"G_ConstructionIsPartlyBuilt\s*\(\s*checkEnt\s*\).*?"
        r"s\.teamNum\s*!=\s*ent->client->sess\.sessionTeam.*?\}\s*else\s*\{[^{}]*?return\s*;",
        hints, re.S)
    if withheld:
        print("[build] the server still withholds the hint from a player "
              "aiming at their own construction")
    else:
        print("[build] note: the server no longer seems to withhold the hint "
              "from a player aiming at their own construction - the "
              "fallback may no longer be needed")

    trying = body_of(g_weapon, "TryConstructing", G_WEAPON)
    if not re.search(r"constructible->s\.angles2\[0\]\s*\+=", trying) \
            or not re.search(r"constructible->s\.angles2\[0\]\s*=\s*0\s*;", trying):
        failures.append(
            "the server no longer raises a construction's angles2[0] as it is "
            "built and puts it back to zero when it finishes - the client "
            "reads exactly that")

    # --- the client ------------------------------------------------------
    narrate = body_of(draw, "ETA_NarrateBuildProgress", DRAW)
    nearby = body_of(draw, "ETA_NearbyConstructionProgress", DRAW)
    if "ETA_NearbyConstructionProgress" not in narrate \
            or "WP_PLIERS" not in narrate:
        failures.append(
            "the build progress does not fall back to the construction's own "
            "figure with the pliers out, so aiming at it is silent")
    if "ET_CONSTRUCTIBLE" not in nearby or "angles2[0]" not in nearby \
            or "teamNum" not in nearby:
        failures.append(
            "the fallback does not read an own-team construction's angles2[0]")
    finish = re.search(r"value\s*<=\s*0\s*&&\s*lastValue\s*>=\s*(\d+)", narrate)
    if not finish:
        failures.append(
            "a construction's figure dropping to nothing is not heard as it "
            "finishing, so aiming at it never hears \"Construction complete\"")
    elif not 200 <= int(finish.group(1)) <= 250:
        failures.append(
            "the finish is recognised from %s of 255, which is not near the "
            "end of the climb" % finish.group(1))
    if "SpeakBuildComplete" not in narrate:
        failures.append("nothing says the construction is complete")

    if failures:
        print()
        for failure in failures:
            print("[build] FAIL %s" % failure)
        return 1

    print("build_progress_test: the build is counted out and finished "
          "wherever the player aims")
    return 0


if __name__ == "__main__":
    sys.exit(main())

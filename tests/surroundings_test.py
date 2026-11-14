#!/usr/bin/env python3
"""Check "what is around me" names things properly and points the right way.

Why this exists
---------------
A tester could hear a truck and had no way to know it was there. The
surroundings key (F9) answers with the open ways and the walls by compass
point, any window, and the named things close by. Two parts of it can be
wrong without anything else noticing:

  * the names. Most things are named from their model file, so
    "models/mapobjects/vehicles/truck_base.md3" has to come out as
    "truck", and "crate2.md3" as "crate" - not "truck base", not a path,
    not the copy number. The naming code is lifted out of the patched
    engine and compiled against the engine's own string helpers here,
    then given real paths;
  * the eight directions. They are traced at compass bearings and named
    with the compass words, and ET's yaw runs the other way from a
    compass with north at 90. A direction traced one way and named the
    other would send a player to the wall they were told was open. The
    yaw expression is read out of the engine and checked against the
    compass convention the rest of the mod uses.

The openings spoken while walking ("Opening to the east") probe the
four compass points the same way and are checked the same way. When
they are news is the library's decision, and the HUD narrator smoke
test covers it.

Usage
-----
    ./surroundings_test.py <engine-root>

Run it against an ET: Legacy checkout with the patch series applied.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

DRAW = os.path.join("src", "cgame", "cg_draw.c")

NAMES = (
    ("models/mapobjects/vehicles/truck_base.md3", "truck"),
    ("models/mapobjects/tanks_sd/tank_base.md3", "tank"),
    ("models/mapobjects/tanktrap/tanktrap.md3", "tank trap"),
    ("models/mapobjects/supplystands/stand_health.md3", "health cabinet"),
    ("models/mapobjects/crates/crate2.md3", "crate"),
    ("models/mapobjects/furniture/chair_office3.md3", "chair"),
    ("models/mapobjects/misc/radio_set_01.md3", "radio"),
    ("models/mapobjects/misc/street_sign_07.md3", "street sign"),
    ("wall_03.mdc", "wall"),
)


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function(text, signature, where):
    found = re.search(signature, text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone" % (signature, where))
    depth, i = 0, text.index("{", found.end() - 1)
    start = found.start()
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    sys.exit("could not find the end of %s" % signature)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    draw = read(root, DRAW)
    failures = []

    # --- the names ---------------------------------------------------------
    namer = function(draw, r"static void ETA_NameFromModelPath\s*\([^)]*\)\s*\{", DRAW)

    # q_shared.c reports errors through the engine; the naming code never
    # reaches them, so they only need to link.
    harness = ['#include "q_shared.h"', '#include <stdio.h>', '#include <stdlib.h>',
               "void QDECL Com_Error(int code, const char *fmt, ...) { exit(2); }",
               "void QDECL Com_Printf(const char *fmt, ...) { }",
               namer,
               "int main(void)", "{", "    char out[64];", "    int failures = 0;"]
    for path, expected in NAMES:
        harness.append(
            '    ETA_NameFromModelPath("%s", out, sizeof(out));'
            ' if (strcmp(out, "%s") != 0) { printf("FAIL %s -> \\"%%s\\", expected \\"%s\\"\\n", out); failures++; }'
            % (path, expected, path, expected))
    harness += ["    return failures ? 1 : 0;", "}"]

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "names.c")
        binary = os.path.join(tmp, "names")
        with open(source, "w") as handle:
            handle.write("\n".join(harness) + "\n")
        build = subprocess.run(
            ["cc", "-std=gnu99", "-w", "-I", os.path.join(root, "src", "qcommon"),
             "-I", os.path.join(root, "src"), "-o", binary, source,
             os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted naming code does not compile against the "
                     "engine:\n%s" % build.stderr[-2000:])
        run = subprocess.run([binary], capture_output=True, text=True)
        if run.returncode != 0:
            failures.append("model files are not named as a person would "
                            "say them:\n  %s"
                            % run.stdout.strip().replace("\n", "\n  "))
        else:
            print("[around] %d model paths come out as the word for the "
                  "thing" % len(NAMES))

    # --- the directions ----------------------------------------------------
    surround = function(draw, r"void CG_AccessibilitySurroundings\s*\(\s*void\s*\)\s*\{", DRAW)
    yaw = re.search(r"VectorSet\s*\(\s*angles\s*,\s*0\.0f\s*,\s*([^,]+),\s*0\.0f\s*\)",
                    surround)
    if not yaw:
        failures.append("could not read the yaw each direction is traced at")
    else:
        expression = yaw.group(1).replace("(float)", "").replace("f", "")
        # The compass: north is yaw 90 and east yaw 0 (hud_narrator.h), so
        # compass point d (0 north, 1 north-east, 2 east ...) is yaw 90 - 45d.
        for d in range(8):
            got = eval(expression, {"d": d}) % 360
            want = (90 - 45 * d) % 360
            if abs(got - want) > 0.01:
                failures.append(
                    "compass point %d is traced at yaw %g but named as if it "
                    "were at yaw %g - a player told a way is open would walk "
                    "into the wall" % (d, got, want))
                break
        else:
            print("[around] each of the eight directions is traced where its "
                  "name points")

    if "FacingName((ETA_Facing)d)" not in surround.replace(" ", ""):
        failures.append("the directions are not named from the compass's "
                        "own words")

    if "MASK_PLAYERSOLID" not in surround:
        failures.append(
            "the ways out are not traced against what the player collides "
            "with, so an open way could be one the player cannot walk")

    # --- the openings while walking ---------------------------------------
    # The same trap at a quarter of the resolution: north, east, south and
    # west are the library's directions 0 to 3, and each has to be traced
    # at its own compass point.
    walk = function(draw, r"static void ETA_NarrateOpenings\s*\(\s*void\s*\)\s*\{", DRAW)
    yaw = re.search(r"VectorSet\s*\(\s*angles\s*,\s*0\.0f\s*,\s*([^,]+),\s*0\.0f\s*\)",
                    walk)
    if not yaw:
        failures.append("could not read the yaw each opening is probed at")
    else:
        expression = yaw.group(1).replace("(float)", "").replace("f", "")
        for d in range(4):
            got = eval(expression, {"d": d}) % 360
            want = (90 - 90 * d) % 360
            if abs(got - want) > 0.01:
                failures.append(
                    "opening direction %d is probed at yaw %g but spoken as "
                    "if it were at yaw %g - \"opening to the east\" at a "
                    "street on the west" % (d, got, want))
                break
        else:
            print("[around] each opening is probed where its name points")
    if "MASK_PLAYERSOLID" not in walk:
        failures.append("the openings are not probed against what the "
                        "player collides with")
    if "eta_openingCallouts.integer" not in walk:
        failures.append("the openings do not listen to their setting, so "
                        "turning them off in the menu does nothing")
    if not re.search(r"ETA_HudNarrator_BearingFromYaw\s*\(\s*vectoyaw\s*\(\s*velocity", walk):
        failures.append(
            "the way of travel is not turned into a compass bearing with "
            "the compass's own conversion, so the side left to the wall-"
            "ahead callout could be a side the player is passing")
    passive = re.search(r"if\s*\(\s*!ETA_HudNarrator_PassiveHeld\s*\(\s*cg\.time\s*\)\s*\)\s*\{(.*?)\n\t\}",
                        draw, re.S)
    if not passive or not re.search(r"\bETA_NarrateOpenings\s*\(\s*\)\s*;", passive.group(1)):
        failures.append(
            "ETA_NarrateOpenings is not called with the rest of the scenery, "
            "so it is either never heard or talks over an answer the "
            "player asked for")

    if failures:
        print()
        for failure in failures:
            print("[around] FAIL %s" % failure)
        return 1

    print("surroundings_test: things are named as a person would say them, "
          "and each direction, on the key and while walking, is traced "
          "where its name points")
    return 0


if __name__ == "__main__":
    sys.exit(main())

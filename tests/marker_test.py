#!/usr/bin/env python3
"""Check the player's own marker can be heard, reached, and forgotten.

Why this exists
---------------
The marker is a destination the player chooses - a square picked on the
command map, or the spot they are standing on - and the mod then walks
them to it with a ping and distance callouts. A tester asked for it
because the objective guidance only ever points where the map's script
says, and a sighted player goes wherever they decide to.

Each of its failures is silent, and each is a way of walking a blind
player somewhere wrong or nowhere:

  * a marker that outlives its map points at a square on a map that is
    no longer loaded - the same letters and numbers, a different place;
  * a ping placed at the marker itself is out of the engine's hearing
    range for any marker worth setting, so it plays as silence exactly
    when it is needed;
  * a marker nobody clears when it is reached keeps pinging from under
    the player's feet, with no direction left to give;
  * a spot marker is put down where the player stands, so unless
    arriving waits for them to have left, it is "reached" on the frame
    it is placed.

The turn instructions are not checked here: they go through the same
call as the objective's, and tests/bearing_regression_test.py lifts
every chain written that way and checks it against the engine's maths.
Nor is whether one ping a second is the right rate. That needs ears.

The way round the walls is found by the library's search, which the
navigation smoke test runs on drawn plans; this checks the marker uses
it, judges the walk by the map's collision with floor underfoot, and
throws the way away whenever the marker changes.

Usage
-----
    ./marker_test.py <engine-root>

Run it against an ET: Legacy checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the marker this test guards is "
                 "gone, and passing without it would mean nothing"
                 % (name, where))
    depth, i = 0, found.end() - 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[found.end():i]
        i += 1
    sys.exit("could not find the end of %s in %s" % (name, where))


def define(text, name):
    found = re.search(r"#define\s+%s\s+([0-9.]+)f?" % re.escape(name), text)
    return float(found.group(1)) if found else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    commandmap_raw = read(args.root, COMMANDMAP)
    commandmap = strip_comments(commandmap_raw)
    main_c = strip_comments(read(args.root, MAIN))
    draw = strip_comments(read(args.root, DRAW))
    failures = []

    # --- a new map forgets the marker ---------------------------------
    reset = body_of(commandmap, "CG_AccessibilityMarkerReset", COMMANDMAP)
    if "eta_marker" not in reset:
        failures.append(
            "CG_AccessibilityMarkerReset does not touch the marker, so it "
            "survives into the next map and points at a square there")
    if not re.search(r"\bCG_AccessibilityMarkerReset\s*\(\s*\)\s*;", main_c):
        failures.append(
            "nothing in %s calls CG_AccessibilityMarkerReset, so a marker "
            "set on one map is still set on the next - the same square name "
            "somewhere else entirely" % MAIN)
    else:
        print("[marker] a new map forgets the marker")

    # --- the ping can be heard ----------------------------------------
    frame = body_of(commandmap, "CG_AccessibilityMarkerFrame", COMMANDMAP)
    beacon = define(commandmap_raw, "ETA_MARKER_BEACON_DISTANCE")
    door = define(draw, "ETA_DOOR_CUE_RANGE") or define(
        read(args.root, DRAW), "ETA_DOOR_CUE_RANGE")

    if "trap_S_AddLoopingSound" not in frame:
        failures.append("the marker has no sound at all")
    elif beacon is None:
        failures.append("ETA_MARKER_BEACON_DISTANCE is gone, so nothing "
                        "says how far out the ping is placed")
    elif not re.search(r"MIN\s*\([^;]*ETA_MARKER_BEACON_DISTANCE", frame):
        failures.append(
            "the ping is not held to ETA_MARKER_BEACON_DISTANCE. Placed at "
            "the marker itself it is out of earshot for any marker worth "
            "setting, and plays as silence")
    elif door is not None and beacon > door:
        failures.append(
            "the ping is placed %g units out, further than the %g the door "
            "creak is trusted to be heard at" % (beacon, door))
    else:
        print("[marker] the ping sits %g units toward the marker, inside "
              "hearing range" % beacon)

    # --- reaching it clears it ----------------------------------------
    arrived = re.search(r"if\s*\(\s*arrived\s*\)\s*\{(.*?)\breturn\s*;", frame,
                        re.S)
    if not arrived or not re.search(r"eta_marker\.active\s*=\s*qfalse",
                                    arrived.group(1)):
        failures.append(
            "reaching the marker does not clear it, so it keeps pinging from "
            "under the player's feet with no direction left to give")
    else:
        print("[marker] reaching the marker says so and clears it")

    # --- a spot is not reached where it was placed --------------------
    place = body_of(commandmap, "CG_AccessibilityMarkerPlace", COMMANDMAP)
    if not re.search(r"eta_marker\.leftIt\s*=\s*qfalse", place):
        failures.append(
            "placing a spot marker does not wait for the player to leave "
            "it, so it is reached on the frame it is placed")
    if not re.search(r"leftIt\s*&&", frame):
        failures.append(
            "arriving at a spot does not check the player has been away")
    if not any("leftIt" in f for f in failures):
        print("[marker] a spot is only reached after walking away from it")

    # --- the ping follows the way, not the straight line ------------------
    # A tester reported the ping leading them into walls: it sat straight
    # toward the marker. It now points along a walkable way found by the
    # library's search, and each of these would quietly put it back.
    if not re.search(r"ETA_MarkerTarget\s*\(\s*target\s*\)", frame) \
            or re.search(r"VectorSubtract\s*\(\s*eta_marker\.origin\s*,\s*eye", frame):
        failures.append(
            "the ping is placed straight toward the marker again, not along "
            "the way there, so it leads into the wall in between")
    if not re.search(r"\bETA_RouteFrame\s*\(\s*\)\s*;", frame):
        failures.append("nothing looks for the way to the marker")

    move = body_of(commandmap, "ETA_RouteMoveExact", COMMANDMAP)
    if "trap_CM_BoxTrace" not in move or "MASK_PLAYERSOLID" not in move:
        failures.append(
            "the way is not judged by the map's own collision")
    if "CG_Trace(" in move:
        failures.append(
            "the way is judged with entities in it, so every closed door "
            "sends it the long way round")
    if not re.search(r"fraction\s*>=\s*1\.0f", move) or "normal[2]" not in move:
        failures.append(
            "the way does not check there is floor to stand on, so it walks "
            "off ledges")

    way = body_of(commandmap, "ETA_MarkerSpeakWay", COMMANDMAP)
    if "ETA_MarkerTarget" not in way:
        failures.append(
            "\"turn left\" still points straight at the marker while the "
            "ping points round the wall - the two would disagree")

    for name in ("CG_AccessibilityMarkerReset", "CG_AccessibilityMarkerClear",
                 "CG_AccessibilityMarkerPlace"):
        if "ETA_RouteForget" not in body_of(commandmap, name, COMMANDMAP):
            failures.append(
                "%s keeps the old way, so a new marker is walked to along "
                "the way to the last one" % name)
    if not any("way" in f for f in failures):
        print("[marker] the ping and the turn follow a walkable way round "
              "the walls, found afresh for every marker")

    if failures:
        print()
        for failure in failures:
            print("[marker] FAIL %s" % failure)
        return 1

    print("marker_test: the marker is forgotten with its map, heard, and "
          "cleared when reached")
    return 0


if __name__ == "__main__":
    sys.exit(main())

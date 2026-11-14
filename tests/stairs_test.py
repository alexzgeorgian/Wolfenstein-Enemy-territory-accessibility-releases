#!/usr/bin/env python3
"""Check the stairs report measures stairs, and stays quiet about ramps.

Why this exists
---------------
This feature is owed to the fix before it. The obstacle report used to
trace a ray from the player's eye and announce whatever it hit, which
meant it found the upright face of every stair in the game and called it
a wall while the player walked up it without difficulty. The cure was to
probe with the player's own bounding box lifted by the engine's step
height, so that anything a player simply walks over stops being an
obstacle.

That was right, and it left stairs completely silent. A sighted player
sees a staircase from the far side of a room. Someone playing by ear had
been hearing them - wrongly, as walls - and after the fix heard nothing
at all, which is the same thing the mod says about an open corridor.

So the report has to be a measurement rather than a look, and this pins
the three ways of getting that wrong:

  * Measuring against the wrong window. Ground within the engine's own
    step height is somewhere the player can walk to; ground outside it
    is a wall or a drop, and both of those already have narration. The
    window has to be the engine's STEPSIZE, not a number that felt
    about right.

  * Calling a ramp a staircase. A player told to expect steps and given
    a slope is looking for something that is not there, in the dark, on
    a surface they may fall off. A tread is flat - these are built from
    flat brushes and come back at exactly 1.0 - so the flatness test has
    to be far stricter than the engine's MIN_WALK_NORMAL, which only
    asks whether a surface can be walked on at all. Nearly everything
    can.

  * Measuring both treads from the player's feet. Three steps up is
    well outside a step-height window measured from the boots, so the
    second probe would find nothing and every staircase in the game
    would be reported as a single step. The second tread has to be
    measured from the first.

What it does NOT check
----------------------
Whether the probe reaches far enough ahead to be useful, or whether
"stairs up" is the phrase a player wants. Those need ears.

Usage
-----
    ./stairs_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
LOCAL = os.path.join("src", "game", "bg_local.h")

# Every state the report can reach. All four have to be reachable: the
# difference between one step and a flight of them is the whole reason
# there are four rather than two.
STATES = ("ETA_STAIRS_STEP_UP", "ETA_STAIRS_STEP_DOWN",
          "ETA_STAIRS_UP", "ETA_STAIRS_DOWN")


def read(root, relative, what):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - %s" % (relative, root, what))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


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


def body_of(text, name, where):
    start = text.find(name)
    if start < 0:
        sys.exit("could not find %s in %s - the stairs narration this test "
                 "exists to guard is gone, and passing without it would "
                 "mean nothing" % (name, where))
    end = text.find("\n}", start)
    if end < 0:
        sys.exit("could not find the end of %s in %s" % (name, where))
    return text[start:end]


def defined(text, name):
    found = re.search(r'#define\s+%s\s+(-?[0-9.]+)f?' % re.escape(name), text)
    return float(found.group(1)) if found else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    args = parser.parse_args()

    draw = strip_comments(read(args.root, DRAW, "is the patch series applied?"))
    local = strip_comments(read(args.root, LOCAL,
                                "is this an engine checkout?"))

    failures = []

    probe = body_of(draw, "ETA_GroundRiseAhead", DRAW)
    report = body_of(draw, "ETA_NarrateStairsAhead", DRAW)

    # --- the probe measures, against the engine's own step -------------
    if "CG_Trace" not in probe:
        failures.append(
            "ETA_GroundRiseAhead does not trace anything, so it is not "
            "measuring the ground - it is asserting something about it")

    if "ETA_DROP_STEP_UNITS" not in probe:
        failures.append(
            "the probe's window is not the engine's step height. Ground "
            "inside that window is somewhere the player can walk to and is "
            "therefore a step; ground outside it is a wall or a drop, and "
            "both of those already have their own narration")

    step = defined(draw, "ETA_DROP_STEP_UNITS")
    engine_step = re.search(r'#define\s+STEPSIZE\s+([0-9.]+)', local)

    if step is None:
        failures.append("ETA_DROP_STEP_UNITS is gone from %s" % DRAW)
    elif not engine_step:
        failures.append("STEPSIZE is gone from %s, so the mod's copy of it "
                        "is now unverified" % LOCAL)
    elif step != float(engine_step.group(1)):
        failures.append(
            "the mod steps over %g units but the engine's STEPSIZE is %s"
            % (step, engine_step.group(1)))

    if "plane.normal" not in probe:
        failures.append(
            "the probe does not look at the surface it hit, so it cannot "
            "tell a tread from a slope")

    # --- a ramp must not be called a staircase -------------------------
    flat = defined(draw, "ETA_STAIR_FLAT")
    walkable = re.search(r'#define\s+MIN_WALK_NORMAL\s+([0-9.]+)', local)

    if flat is None:
        failures.append(
            "ETA_STAIR_FLAT is gone - without a flatness test every ramp "
            "in the game is a staircase, and a player sent to feel for "
            "steps that are not there is worse off than one told nothing")
    elif "ETA_STAIR_FLAT" not in probe:
        failures.append("the probe does not use ETA_STAIR_FLAT")
    elif not walkable:
        failures.append("MIN_WALK_NORMAL is gone from %s" % LOCAL)
    elif flat <= float(walkable.group(1)):
        failures.append(
            "the tread test (%g) is no stricter than the engine's "
            "MIN_WALK_NORMAL (%s). That one asks whether a surface can be "
            "walked on at all, which nearly everything can - at this "
            "threshold every slope in the game reports as stairs"
            % (flat, walkable.group(1)))
    elif flat >= 1.0:
        failures.append(
            "the tread test is %g, which no real surface reaches once the "
            "trace arithmetic has been through a float - nothing would "
            "ever be called stairs" % flat)

    # --- a step has to be smaller than the window it is found in -------
    rise = defined(draw, "ETA_STAIR_MIN_RISE")

    if rise is None:
        failures.append(
            "ETA_STAIR_MIN_RISE is gone - without a floor on it, ground "
            "that is a fraction of a unit off level is a step, and most "
            "of this game's ground is")
    elif step is not None and rise >= step:
        failures.append(
            "the smallest step worth speaking (%g) is not smaller than the "
            "step-height window it has to be found in (%g), so nothing can "
            "ever qualify" % (rise, step))

    # --- the second tread is measured from the first -------------------
    calls = re.findall(r'ETA_GroundRiseAhead\s*\(([^;]*?)\)\s*[;)]',
                       report, re.S)

    if len(calls) < 2:
        failures.append(
            "the report probes the ground %d time(s). One reading cannot "
            "tell a kerb from a staircase, and that difference is why "
            "there are four states rather than two" % len(calls))
    else:
        froms = []
        for call in calls[:2]:
            arguments = [a.strip() for a in call.split(",")]
            froms.append(arguments[3] if len(arguments) > 3 else "?")

        if froms[0] == froms[1]:
            failures.append(
                "both probes measure from the same height (%s). Three "
                "steps up is well outside a step-height window measured "
                "from the boots, so the second probe finds nothing and "
                "every staircase in the game is reported as a single step"
                % froms[0])

    # --- all four states have to be reachable --------------------------
    for state in STATES:
        if state not in report:
            failures.append(
                "%s is never produced, so that half of the report cannot "
                "happen" % state)

    if "ETA_HudNarrator_SpeakStairs" not in report:
        failures.append("the report never speaks anything")

    # --- only from the ground ------------------------------------------
    if "groundEntityNum" not in report:
        failures.append(
            "the report does not require the player to be on the ground - "
            "in the air every reading describes wherever they have fallen "
            "to by the time it is spoken")

    # --- and not over the top of the narration that owns the surface ---
    if "PMF_LADDER" not in report:
        failures.append(
            "a ladder is not a staircase, and nothing here excludes one")

    # --- ordering: scenery before the objective callout ----------------
    stairs_call = draw.find("ETA_NarrateStairsAhead();")
    # ET: Legacy calls the distance on the way to the marker only; the
    # objective's own straight-line distance was taken out for it.
    objective_call = draw.find("CG_AccessibilityMarkerApproach();"
                               if args.engine == "etlegacy"
                               else "ETA_NarrateObjectiveApproach();")

    if stairs_call < 0 or objective_call < 0:
        failures.append(
            "could not find both call sites, so the order that decides "
            "which report survives cannot be checked")
    elif stairs_call > objective_call:
        failures.append(
            "the stairs report is spoken after the objective callout. "
            "Speech delivers a new line by cutting off the one in "
            "progress, so the later one wins - and a tester lost an "
            "objective distance to a scenery report exactly this way")

    if failures:
        print("stairs_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("stairs_test: %s - the ground ahead is measured inside the "
          "engine's own step height, treads are required flat (%g, against "
          "MIN_WALK_NORMAL %s), the second is measured from the first, and "
          "it is spoken before the objective callout"
          % (args.engine, flat, walkable.group(1) if walkable else "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

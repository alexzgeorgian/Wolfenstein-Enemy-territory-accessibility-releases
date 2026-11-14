#!/usr/bin/env python3
"""Check the obstacle report only fires when the player is actually stopped.

Why this exists
---------------
This shipped wrong, and the way it was wrong is worth keeping written
down because it is not obvious from the code.

The narration used to trace a ray from the player's eye along their view
and announce whatever it hit within about two and a half metres. That
reads as reasonable and is answering the wrong question: a ray from the
eye says what the player is *looking at*, and the thing worth announcing
is what is *stopping* them. Those differ constantly.

A tester reported hearing "wall, 0 metres" while walking on perfectly
well. Two causes, both everywhere in this game:

  * Stairs. Every step has an upright face with a vertical normal, so it
    is not floor and is therefore a "wall" - on every staircase in the
    game, while the player climbs it without noticing.
  * Any wall beside a corridor. Glance sideways while running past and
    the ray finds it, though nothing is in the way.

And "0 metres" itself came from truncation: the distance is an int, so
everything nearer than a metre reported as nought.

That fix was only half of one, and the same tester came back. It
changed the *shape* of the probe and left its *aim* alone - still the
view yaw - so it went on answering "what am I looking at", just with a
fatter instrument. They could walk forward many metres and still hear
the wall, because running down a corridor while glancing sideways is
the commonest thing in this game.

So there are two more rules now, and they are what "blocked" actually
means:

  * the probe is aimed by the player's own movement keys, turned into
    the world by their view - the direction they are *asking* to go.
    Nothing can block you in a direction you are not trying to move in;
  * and it says nothing at all unless the player is asking to move and
    failing to. Someone covering ground is not blocked, whatever is
    beside them.

The fix is to ask the engine the question the player cares about - can I
move forward - with the tool the engine itself uses: a trace of the
player's own bounding box, lifted at the base by the engine's step
height. A stair riser passes under a box lifted like that, exactly as
the player's feet pass over it. So this test requires:

  * the probe to be a box trace of the player's own mins/maxs, not a ray
    (a ray is passed as NULL bounds, which is what the old code did);
  * the base to be lifted by the step height, or stairs come straight
    back;
  * the player to be on the ground, since "blocked" means nothing while
    falling;
  * no distance in the announcement, because against something you are
    up against it is always nought - that was the part that read as
    broken.

It also pins the ordering. The same tester lost an objective-distance
callout to a scenery report: speech delivers a new line by cutting off
the one in progress, so of two reports in one frame the *later* one
survives. Scenery has to be spoken before the objective callout, not
after, and nothing about that is visible at either call site without
this check.

What it does NOT check
----------------------
Whether the probe distance feels right, or whether the wording is the
one a player wants to hear. Those need ears.

Usage
-----
    ./obstacle_blocking_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
LOCAL = os.path.join("src", "game", "bg_local.h")


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
        sys.exit("could not find %s in %s - the narration this test guards "
                 "is gone, and passing without it would mean nothing"
                 % (name, where))
    end = text.find("\n}", start)
    if end < 0:
        sys.exit("could not find the end of %s in %s" % (name, where))
    return text[start:end]


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
    body = body_of(draw, "ETA_NarrateObstacleAhead", DRAW)

    # --- the probe must be the player's body, not a ray ----------------
    trace = re.search(r'CG_Trace\s*\(([^;]*)\)\s*;', body, re.S)
    if not trace:
        failures.append(
            "ETA_NarrateObstacleAhead does not trace anything - it cannot "
            "know whether the player is blocked")
    else:
        arguments = [a.strip() for a in trace.group(1).split(",")]
        # CG_Trace(&trace, start, mins, maxs, end, passEnt, mask)
        if len(arguments) < 7:
            failures.append("the CG_Trace call has an unexpected shape: %s"
                            % trace.group(1).strip())
        else:
            mins, maxs = arguments[2], arguments[3]
            if mins == "NULL" or maxs == "NULL":
                failures.append(
                    "the probe passes NULL bounds, which is a ray and not a "
                    "body. A ray answers 'what am I looking at' - it finds "
                    "the upright face of every stair in the game and "
                    "announces it as a wall while the player walks up it")

    if "ps->mins" not in body or "ps->maxs" not in body:
        failures.append(
            "the probe does not use the player's own bounding box, so it is "
            "not asking whether the player can move; it also stops being "
            "correct when they crouch")

    if "ETA_DROP_STEP_UNITS" not in body:
        failures.append(
            "the probe's base is not lifted by the engine's step height - "
            "that lift is the whole fix, and without it every staircase "
            "reports as a wall again")

    # ... and that constant has to still be the engine's step size.
    step = re.search(r'#define\s+ETA_DROP_STEP_UNITS\s+([0-9.]+)f?', draw)
    engine_step = re.search(r'#define\s+STEPSIZE\s+([0-9.]+)', local)
    if not step:
        failures.append("ETA_DROP_STEP_UNITS is gone from %s" % DRAW)
    elif not engine_step:
        failures.append("STEPSIZE is gone from %s, so the mod's copy of it "
                        "is now unverified" % LOCAL)
    elif float(step.group(1)) != float(engine_step.group(1)):
        failures.append(
            "the mod steps over %s units but the engine's STEPSIZE is %s - "
            "a probe lifted by the wrong amount either reports stairs as "
            "walls or walks through things that block"
            % (step.group(1), engine_step.group(1)))

    # --- aimed where the player is going, not where they look --------
    if "cmd.forwardmove" not in body or "cmd.rightmove" not in body:
        failures.append(
            "the probe is not aimed by the player's movement keys. Aimed by "
            "the view instead, it answers 'what am I looking at' - which is "
            "the bug this whole report was rewritten to stop, and a tester "
            "hit it a second time after the first rewrite: metres of walking "
            "with a wall announced the entire way, because they were "
            "glancing sideways down a corridor")

    if "trap_GetUserCmd" not in body:
        failures.append(
            "the probe never reads the player's own movement input, so it "
            "cannot know which way they are trying to go")

    # --- and only while they are actually stopped ---------------------
    if "velocity" not in body:
        failures.append(
            "the report does not look at how fast the player is moving. "
            "Someone covering ground is not blocked, whatever is beside "
            "them - and that is exactly what was reported twice")

    if "ETA_OBSTACLE_STOPPED_SPEED" not in body:
        failures.append(
            "there is no speed below which the player counts as stopped, so "
            "the report can fire while they are walking perfectly well")

    speed = re.search(r'#define\s+ETA_OBSTACLE_STOPPED_SPEED\s+([0-9.]+)f?',
                      draw)
    if speed and float(speed.group(1)) > 100.0:
        failures.append(
            "the stopped threshold is %s units per second, which is most of "
            "a walking pace - a player making perfectly good progress would "
            "still be told what is beside them" % speed.group(1))

    if "groundEntityNum" not in body:
        failures.append(
            "the narration does not require the player to be on the ground "
            "- while falling there is nothing to be blocked from doing")

    if "MASK_PLAYERSOLID" not in body:
        failures.append(
            "the probe does not use MASK_PLAYERSOLID, so it is not testing "
            "what actually stops a player")

    # --- no distance in the announcement -------------------------------
    speak = re.search(r'ETA_HudNarrator_SpeakLookAhead\s*\(\s*([^;]*)\)\s*;',
                      body, re.S)
    if not speak:
        failures.append("the narration no longer speaks anything")
    else:
        arguments = [a.strip() for a in speak.group(1).split(",")]
        if len(arguments) < 2 or not arguments[1].startswith("-"):
            failures.append(
                "the obstacle is announced with a distance (%s). It only "
                "fires against something the player is up against, so the "
                "number is always nought - and \"0 metres\" is exactly the "
                "report that was called noise"
                % (arguments[1] if len(arguments) > 1 else "?"))

    # --- ordering: the objective callout must win a same-frame collision
    obstacle_call = draw.find("ETA_NarrateObstacleAhead();")
    # ET: Legacy calls the distance on the way to the marker only; the
    # objective's own straight-line distance was taken out for it.
    objective_call = draw.find("CG_AccessibilityMarkerApproach();"
                               if args.engine == "etlegacy"
                               else "ETA_NarrateObjectiveApproach();")

    if obstacle_call < 0 or objective_call < 0:
        failures.append(
            "could not find both call sites, so the order that decides "
            "which report survives cannot be checked")
    elif obstacle_call > objective_call:
        failures.append(
            "the obstacle report is spoken after the objective callout. "
            "Speech delivers a new line by cutting off the one in progress, "
            "so the later one wins - and a tester lost an objective "
            "distance to a scenery report exactly this way. Scenery goes "
            "first")

    if failures:
        print("obstacle_blocking_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("obstacle_blocking_test: %s - the obstacle report probes the "
          "player's own box lifted by the engine's step, only from the "
          "ground, and is spoken before the objective callout"
          % args.engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())

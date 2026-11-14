#!/usr/bin/env python3
"""Check the spoken compass points agree with the game's own compass.

Why this exists
---------------
Telling a player they are facing north when the game's compass says
south is the worst failure this mod can have. Every other defect here
has been silence or a missing word: the player hears nothing and knows
something is wrong. This one is confident, plausible, and wrong in the
direction they then walk.

Nothing in the C compiles differently if the conversion is backwards,
and no play session catches it quickly either - a player with no sight
has no second opinion to check it against. Only the engine does.

ET: Legacy draws a ring of cardinal points around the square compass,
and computes which one sits at the top from the view yaw. That code is
the game's own answer to the question the mod is answering, so this
lifts the expression and the label table straight out of
cg_commandmap.c, evaluates both it and the mod's formula over a full
turn, and requires them to agree at every degree.

One wrinkle, found by this test and worth writing down. The engine's
expression is `angle = fmodf(-yaw + 180, 360)`, and C's fmodf keeps the
sign of its left operand. View yaw is not centred on zero - it comes
either from the packed network angle, which is non-negative, or from
vectoangles, which returns [0, 360) - so for any yaw past 180 the
engine's angle is negative, every `angle < 22.5 + index * 45` test
succeeds at index 0, and the game labels the top of its own square
compass "W" for the entire back half of a turn.

That is an upstream defect, not a convention for the mod to copy. So
the comparison here is against the engine's selection given a wrapped
angle, over all 360 degrees; and separately, verbatim against the
engine's own expression over the range where fmodf cannot go negative,
where the two must agree exactly. The convention being checked - which
label belongs to which heading - is the same either way, and it is the
part that matters.

The 2010 release has no such ring to read. What it does share is the
engine-wide yaw convention that the ring is built on - AngleVectors puts
yaw 0 along +x and yaw 90 along +y - so there the check is that the mod
still places north at yaw 90 and east at yaw 0, and that its eight
points are evenly spaced and in clockwise order. That is weaker, and
deliberately so: it is what this tree can actually support, and the
strong form runs on the other engine over the same shared code.

Usage
-----
    ./compass_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied. The mod's side
is read from this repository, which is where the conversion lives.
"""

import argparse
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NARRATOR = os.path.join(HERE, "..", "src", "accessibility", "hud",
                        "hud_narrator.c")
COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")

# The eight points, in the order the mod's ETA_Facing enum declares them.
# Read from the header rather than assumed, below.
HEADER = os.path.join(HERE, "..", "src", "accessibility", "hud",
                      "hud_narrator.h")


def read(path, what):
    if not os.path.isfile(path):
        sys.exit("no %s - %s" % (path, what))
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


def mod_enum_order():
    """ETA_Facing's members, in declaration order."""
    text = strip_comments(read(HEADER, "the mod's narrator header"))
    match = re.search(r'typedef enum ETA_Facing\s*\{([^}]*)\}', text, re.S)
    if not match:
        sys.exit("could not find ETA_Facing in hud_narrator.h - the compass "
                 "this test exists to guard is gone")
    return re.findall(r'\b(ETA_FACING_[A-Z]+)\b', match.group(1))


def mod_names():
    """The spoken word per ETA_Facing member, in table order."""
    text = strip_comments(read(NARRATOR, "the mod's narrator"))
    start = text.find("ETA_HudNarrator_FacingName")
    if start < 0:
        sys.exit("could not find ETA_HudNarrator_FacingName - the compass "
                 "this test exists to guard is gone")
    body = text[start:text.index("};", start)]
    return re.findall(r'"([a-z-]+)"', body)


def mod_constants():
    """The two numbers the mod's conversion is built out of."""
    text = read(NARRATOR, "the mod's narrator")

    sector = re.search(r'#define ETA_FACING_SECTOR_DEGREES\s+([0-9.]+)', text)
    north = re.search(r'return ETA_HudNarrator_NormalizeDegrees\(\s*'
                      r'([0-9.]+)f\s*-\s*yawDegrees\s*\)', text)

    if not sector or not north:
        sys.exit("could not read the mod's compass conversion out of "
                 "hud_narrator.c - this test is out of date with the mod, "
                 "and passing without reading it would defeat its purpose")

    return float(sector.group(1)), float(north.group(1))


def mod_settle_ms():
    """How long a new compass point must be held before it is spoken."""
    text = read(NARRATOR, "the mod's narrator")
    settle = re.search(r'#define ETA_FACING_SETTLE_MS\s+([0-9]+)', text)

    if not settle:
        sys.exit("could not read ETA_FACING_SETTLE_MS out of hud_narrator.c "
                 "- this test is out of date with the mod, and passing "
                 "without reading it would defeat its purpose")

    return int(settle.group(1))


def engine_yaw_speed(root):
    """cl_yawspeed's default: how fast a held key turns the view.

    Read out of the engine rather than written down here, because it is
    the engine's number and the whole point of the check is that the
    mod's timing has to sit underneath it.
    """
    # Both trees ship it, in different files: ET: Legacy moved its cvar
    # registrations out to cl_cvars.c, the 2010 drop still does them in
    # cl_main.c. Looking in both rather than picking one is what keeps
    # this from silently skipping on the tree it was not written against.
    for name in ("cl_cvars.c", "cl_main.c", "cl_input.c"):
        path = os.path.join(root, "src", "client", name)
        if not os.path.isfile(path):
            continue

        with open(path, "r", errors="replace") as handle:
            found = re.search(r'Cvar_Get\(\s*"cl_yawspeed"\s*,\s*"([0-9.]+)"',
                              handle.read())

        if found:
            return float(found.group(1))

    return None


def mod_facing(yaw, sector, north_yaw):
    """The mod's ETA_HudNarrator_FacingFromYaw, in Python."""
    compass = (north_yaw - yaw) % 360.0
    return int(compass / sector + 0.5) % 8


def engine_cardinals(commandmap_c):
    """ET: Legacy's own label ring and the yaw expression that indexes it."""
    text = strip_comments(commandmap_c)

    ring = re.search(r'cardinalPoints\[CARDINAL_POINTS_NUMBER\]\s*=\s*\{'
                     r'([^}]*)\}', text)
    if not ring:
        sys.exit("could not find the cardinalPoints ring in %s - this test "
                 "is out of date with the engine, and passing without "
                 "reading it would defeat its purpose" % COMMANDMAP)

    labels = re.findall(r'"([A-Z]+)"', ring.group(1))

    if len(labels) != 8:
        sys.exit("read %d cardinal point(s) out of the engine, expected 8"
                 % len(labels))

    # The engine picks the label at the top of the compass from the view
    # yaw with this expression, then walks the ring in 45 degree steps.
    expr = re.search(r'float angle\s*=\s*-cg\.refdefViewAngles\[YAW\]\s*'
                     r'\+\s*([0-9.]+);', text)
    step = re.search(r'if\s*\(angle\s*<\s*([0-9.]+)f\s*\+\s*'
                     r'\(index\s*\*\s*([0-9]+)\)\)', text)

    if not expr or not step:
        sys.exit("could not read the engine's cardinal-point selection out "
                 "of %s - this test is out of date with the engine, and "
                 "passing without reading it would defeat its purpose"
                 % COMMANDMAP)

    return labels, float(expr.group(1)), float(step.group(1)), float(step.group(2))


def engine_facing(yaw, labels, offset, half, step, wrap):
    """The engine's own CG_DrawSquareCompassCase selection, in Python.

    `wrap` chooses whether the angle is brought into [0, 360) first.
    False is the engine's literal code, fmodf and all; True is what that
    code means, and is the only one of the two that is right for a yaw
    past 180. See the module docstring.
    """
    angle = (-yaw + offset) % 360.0 if wrap else math.fmod(-yaw + offset, 360.0)

    index = 8
    for candidate in range(8):
        if angle < half + candidate * step:
            index = candidate
            break

    return labels[index % 8]


# The engine writes its ring in initials; the mod speaks them in words.
SPOKEN = {
    "N": "north", "NE": "north-east", "E": "east", "SE": "south-east",
    "S": "south", "SW": "south-west", "W": "west", "NW": "north-west",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=["etlegacy", "id-software"])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    order = mod_enum_order()
    names = mod_names()
    sector, north_yaw = mod_constants()

    print("[compass] mod enum:  %s" % ", ".join(order))
    print("[compass] mod words: %s" % ", ".join(names))
    print("[compass] mod puts north at yaw %g, %g degrees per point"
          % (north_yaw, sector))

    failures = []

    # --- the callout has to arrive while the key is still held ---------
    #
    # Holding a turn key moves the view at cl_yawspeed, so the view
    # occupies each sector for sector/cl_yawspeed seconds. The mod waits
    # for a new sector to be held for ETA_FACING_SETTLE_MS before
    # speaking it. If the settle is the longer of the two, the sector
    # under the view always changes first, the timer always restarts,
    # and holding the key announces *nothing* - the heading only arrives
    # after the player lets go.
    #
    # That is not hypothetical. It shipped: 45/140 = 321 ms in a sector
    # against a 350 ms settle, a 29 ms miss, and the compass was silent
    # for the whole of every keyboard turn. A player found it by holding
    # the key and waiting. Nothing in the C could, and the smoke test's
    # "slow turn" dwelt for 800 ms, which no key can produce.
    yaw_speed = engine_yaw_speed(root)
    settle = mod_settle_ms()

    if yaw_speed is None:
        failures.append(
            "could not read cl_yawspeed out of the engine, so the compass "
            "timing cannot be checked against the speed a held key "
            "actually turns at. Both trees register it; if one has moved "
            "it again, follow it rather than letting this check pass on "
            "nothing")
    else:
        dwell_ms = sector / yaw_speed * 1000.0

        print("[compass] a held key turns at %g deg/s, so each point is "
              "occupied for %.0f ms; the settle is %d ms"
              % (yaw_speed, dwell_ms, settle))

        if settle >= dwell_ms:
            failures.append(
                "the settle (%d ms) is not shorter than the time a held "
                "turn key spends in one compass point (%.0f ms at "
                "cl_yawspeed %g). The sector changes before the settle "
                "completes, so the timer restarts every time and holding "
                "the key announces nothing at all - the heading arrives "
                "only after the player lets go"
                % (settle, dwell_ms, yaw_speed))
        elif settle > dwell_ms * 0.75:
            failures.append(
                "the settle (%d ms) is within a quarter of a key turn's "
                "dwell time (%.0f ms). That leaves no room for a frame "
                "landing badly or a player who has raised cl_yawspeed a "
                "little, and the failure is total silence rather than a "
                "late word" % (settle, dwell_ms))
        else:
            print("[compass] a held key is announced while it is held")

    if len(order) != 8 or len(names) != 8:
        sys.exit("[compass] FAIL the mod has %d enum member(s) and %d word(s) "
                 "- a compass is eight points" % (len(order), len(names)))

    # The enum and the word table are two hand-written lists in the same
    # order, and nothing but this pairs them up.
    for member, word in zip(order, names):
        if member.split("_")[-1].lower() != word.replace("-", ""):
            failures.append(
                "%s is spoken as %r - the enum and the word table have "
                "drifted apart, so every direction past this one is a "
                "different direction than the code thinks"
                % (member, word))

    if args.engine == "etlegacy":
        commandmap = read(os.path.join(root, COMMANDMAP),
                          "is this an ET: Legacy checkout?")
        labels, offset, half, step = engine_cardinals(commandmap)

        print("[compass] engine ring: %s" % ", ".join(labels))
        print("[compass] engine picks the top point from "
              "(-yaw + %g), %g degree half-sector, %g degree steps"
              % (offset, half, step))

        disagreements = []

        # Over the whole turn, against the engine's selection with the
        # angle wrapped the way the mod wraps it.
        for degree in range(0, 360):
            yaw = float(degree)
            want = SPOKEN[engine_facing(yaw, labels, offset, half, step,
                                        wrap=True)]
            got = names[mod_facing(yaw, sector, north_yaw)]

            if want != got:
                disagreements.append((degree, want, got))

        # And verbatim, over the range where the engine's own fmodf
        # cannot hand it a negative angle. Nothing is being excused here:
        # this half is the strict check, and it is strict precisely
        # because no wrapping of ours stands between the two.
        strict = 0
        for degree in range(-180, 181):
            yaw = float(degree)
            if math.fmod(-yaw + offset, 360.0) < 0.0:
                continue
            strict += 1
            want = SPOKEN[engine_facing(yaw, labels, offset, half, step,
                                        wrap=False)]
            got = names[mod_facing(yaw, sector, north_yaw)]

            if want != got:
                disagreements.append((degree, want, got))

        if disagreements:
            for degree, want, got in disagreements[:8]:
                failures.append(
                    "at yaw %d the game's compass reads %s and the mod says "
                    "%s" % (degree, want, got))
            if len(disagreements) > 8:
                failures.append(
                    "...and at %d more of the 360 degrees checked"
                    % (len(disagreements) - 8))
        else:
            print("[compass] agrees with the game's own compass at all 360 "
                  "degrees, and verbatim with its own expression at %d of "
                  "them" % strict)
    else:
        # No ring to read here. Check the convention the ring rests on.
        for yaw, expected in ((0.0, "east"), (90.0, "north"),
                              (180.0, "west"), (270.0, "south")):
            got = names[mod_facing(yaw, sector, north_yaw)]
            if got != expected:
                failures.append(
                    "at yaw %g the engine's own axes put the player facing "
                    "%s and the mod says %s" % (yaw, expected, got))

        # Evenly spaced, and turning one way walks the ring one way.
        seen = [names[mod_facing(float(d), sector, north_yaw)]
                for d in range(0, 360)]
        runs = []
        for word in seen:
            if not runs or runs[-1][0] != word:
                runs.append([word, 0])
            runs[-1][1] += 1

        if len(runs) not in (8, 9):
            failures.append(
                "a full turn passes through %d run(s) of compass point, "
                "expected 8 - the points are not evenly spaced"
                % len(runs))

        print("[compass] a full turn visits %d point(s) in order: %s"
              % (len(runs), " ".join(word for word, _ in runs)))

    if failures:
        print()
        for failure in failures:
            print("[compass] FAIL %s" % failure)
        sys.exit(1)

    print("[compass] ok")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check the drop warning uses the engine's own falling-damage ladder.

Why this exists
---------------
"Deadly drop ahead" is the most dangerous sentence this mod says. Every
other announcement is a description the player can act on or ignore; this
one tells them a route will kill them, and they will walk the long way
round because of it. The mirror failure is worse: a drop announced as a
harmless ledge that takes their last forty health.

So none of the judgement is the mod's. ET decides falling damage in
PM_CrashLand, from the speed the player lands at:

    delta = v * v * 0.0001

and compares delta against a fixed ladder - nothing at all below one
threshold, EV_FALL_NDIE (death outright) above another. Those two numbers
are what the mod's ETA_FALL_DELTA_INJURE and ETA_FALL_DELTA_DEADLY must
be, and this reads them out of bg_pmove.c rather than trusting a comment.

The probe measures a height, not a landing speed, so the library converts
one to the other. A fall from rest reaches v * v = 2 * g * h, so

    h = delta * 10000 / (2 * g)

That is a small piece of physics sitting between the engine's numbers and
a claim about whether a player will survive, and getting it wrong is
silent: every value it produces is a plausible-looking distance. The
factor of two is the whole hazard - dropping it doubles every threshold,
so a fall that kills gets announced as a ledge. This checks the formula
as written, and then checks the heights it produces are the right size
for a person.

What it does NOT check
----------------------
Whether the probe finds the right ledge. That needs a running game and a
map. This checks that the numbers it classifies with are the engine's.

Usage
-----
    ./fall_hazard_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

PMOVE = os.path.join("src", "game", "bg_pmove.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
NARRATOR = os.path.join("src", "accessibility", "hud", "hud_narrator.c")

# ET's own default gravity, used only to sanity-check the scale of the
# heights. The mod itself never hardcodes it - it reads ps->gravity, so a
# server that changes gravity moves the warning with it.
DEFAULT_GRAVITY = 800.0

QU_TO_METERS = 0.0254


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


def crash_land(pmove_c):
    """The body of PM_CrashLand, comments removed."""
    text = strip_comments(pmove_c)
    start = text.find("PM_CrashLand")
    if start < 0:
        sys.exit("could not find PM_CrashLand in %s - the engine no longer "
                 "decides falling damage where this test reads it, and the "
                 "thresholds the mod warns on are now unverified" % PMOVE)

    # Far enough to cover the whole ladder without running into whatever
    # follows; the end marker below is what actually bounds it.
    end = text.find("\nstatic ", start + 1)
    if end < 0:
        end = len(text)
    return text[start:end]


def engine_ladder(body):
    """The delta thresholds PM_CrashLand compares against, and the fatal one."""
    thresholds = [float(value)
                  for value in re.findall(r'delta\s*>\s*([0-9]+(?:\.[0-9]+)?)',
                                          body)]

    if not thresholds:
        sys.exit("read no 'delta > N' comparisons out of PM_CrashLand - the "
                 "engine's ladder is not where this test looks, and a pass "
                 "here would mean nothing")

    fatal = re.search(r'delta\s*>\s*([0-9]+(?:\.[0-9]+)?)\s*\)\s*\{?\s*'
                      r'PM_AddEventExt\(\s*EV_FALL_NDIE', body)
    if not fatal:
        sys.exit("could not find the EV_FALL_NDIE branch in PM_CrashLand - "
                 "the mod calls a drop deadly on the strength of it")

    # The engine's own formula for delta, which is what makes the
    # library's conversion back to a height meaningful.
    if not re.search(r'delta\s*=\s*delta\s*\*\s*delta\s*\*\s*0\.0001', body):
        sys.exit("PM_CrashLand no longer squares the landing speed and "
                 "scales it by 0.0001 - the height conversion in the "
                 "library is derived from that exact expression")

    # The lowest threshold that actually does damage. The ladder is a
    # descending else-if chain, so each branch's body is everything
    # between its own comparison and the next one. Matching a threshold
    # and an event in one regular expression does not work here: the
    # branches share a line shape, and an earlier version of this test
    # skipped past several of them and reported the wrong band while
    # still passing on one engine.
    comparisons = list(re.finditer(r'delta\s*>\s*([0-9]+(?:\.[0-9]+)?)',
                                   body))
    damaging = []

    for index, match in enumerate(comparisons):
        end = (comparisons[index + 1].start()
               if index + 1 < len(comparisons) else len(body))
        branch = body[match.end():end]

        # Only a branch that actually hurts the player counts. The engine
        # also compares against the same numbers to clear velocity and to
        # print debug output, and a short fall plays a sound and does no
        # damage at all.
        if re.search(r'EV_FALL_(?:DMG_[0-9]+|NDIE)', branch):
            damaging.append(float(match.group(1)))

    if not damaging:
        sys.exit("found no EV_FALL_DMG_* or EV_FALL_NDIE branches in "
                 "PM_CrashLand - the 'drop ahead' band has nothing behind it")

    return min(damaging), float(fatal.group(1))


def mod_deltas(draw_c):
    """The two thresholds the integration classifies a drop with."""
    text = strip_comments(draw_c)
    found = {}
    for name in ("ETA_FALL_DELTA_INJURE", "ETA_FALL_DELTA_DEADLY"):
        match = re.search(r'#define\s+%s\s+([0-9]+(?:\.[0-9]+)?)f?' % name,
                          text)
        if not match:
            sys.exit("could not find %s in %s - the drop warning is no "
                     "longer classified where this test checks it" %
                     (name, DRAW))
        found[name] = float(match.group(1))
    return found["ETA_FALL_DELTA_INJURE"], found["ETA_FALL_DELTA_DEADLY"]


def library_conversion(narrator_c):
    """The expression the library turns a delta into a height with."""
    text = strip_comments(narrator_c)
    start = text.find("ETA_HudNarrator_FallHeightForDelta")
    if start < 0:
        sys.exit("could not find ETA_HudNarrator_FallHeightForDelta in %s" %
                 NARRATOR)

    body = text[start:text.find("\n}", start)]

    match = re.search(r'return\s+delta\s*\*\s*10000\.0f\s*/\s*'
                      r'\(\s*2\.0f\s*\*\s*gravity\s*\)\s*;', body)
    if not match:
        sys.exit(
            "the library no longer converts a delta to a height with\n"
            "    delta * 10000 / (2 * gravity)\n"
            "which is the inverse of the engine's own delta = v*v*0.0001\n"
            "for a fall from rest (v*v = 2*g*h). Dropping the factor of two\n"
            "doubles every threshold and gets a fatal drop announced as a\n"
            "ledge, which is exactly the failure this whole test exists for.")

    def height(delta, gravity):
        return delta * 10000.0 / (2.0 * gravity)

    return height


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    parser.add_argument("--library", default=None,
                        help="accessibility-mode checkout (default: this one)")
    args = parser.parse_args()

    library_root = args.library or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))

    body = crash_land(read(args.root, PMOVE,
                           "is this an engine checkout?"))
    engine_injure, engine_deadly = engine_ladder(body)

    mod_injure, mod_deadly = mod_deltas(
        read(args.root, DRAW, "is the patch series applied?"))

    height = library_conversion(
        read(library_root, NARRATOR, "is this the accessibility checkout?"))

    failures = []

    if mod_injure != engine_injure:
        failures.append(
            "the mod warns of an injuring drop at delta %g, but the engine's "
            "lowest damaging step is %g" % (mod_injure, engine_injure))

    if mod_deadly != engine_deadly:
        failures.append(
            "the mod calls a drop deadly at delta %g, but the engine kills "
            "at %g (EV_FALL_NDIE)" % (mod_deadly, engine_deadly))

    if mod_injure >= mod_deadly:
        failures.append(
            "the injuring threshold (%g) is not below the deadly one (%g), "
            "so every dangerous drop would be classified the same way"
            % (mod_injure, mod_deadly))

    # The heights those deltas work out to, at the gravity ET ships with.
    # A fall that hurts should be about a storey, and one that kills a
    # few storeys. Any conversion error large enough to matter puts both
    # of these somewhere absurd at once - the same trick the metres check
    # plays with the size of a person.
    injure_m = height(engine_injure, DEFAULT_GRAVITY) * QU_TO_METERS
    deadly_m = height(engine_deadly, DEFAULT_GRAVITY) * QU_TO_METERS

    if not 4.0 <= injure_m <= 9.0:
        failures.append(
            "a fall starts hurting at %.1f m, which is not a believable "
            "height for one - the conversion from the engine's landing "
            "speed is wrong" % injure_m)

    if not 9.0 <= deadly_m <= 20.0:
        failures.append(
            "a fall becomes fatal at %.1f m, which is not a believable "
            "height for one - the conversion from the engine's landing "
            "speed is wrong" % deadly_m)

    if deadly_m <= injure_m:
        failures.append("the fatal height is not above the injuring one")

    # Lower gravity means further to fall before the same landing speed.
    if not height(engine_deadly, 400.0) > height(engine_deadly, 800.0):
        failures.append(
            "halving gravity did not move the fatal drop further down, so "
            "the height does not actually depend on the gravity in play")

    if failures:
        print("fall_hazard_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("fall_hazard_test: %s - drop bands are the engine's own ladder "
          "(hurts above delta %g / %.1f m, kills above delta %g / %.1f m at "
          "default gravity)"
          % (args.engine, engine_injure, injure_m, engine_deadly, deadly_m))
    return 0


if __name__ == "__main__":
    sys.exit(main())

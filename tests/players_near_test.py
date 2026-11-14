#!/usr/bin/env python3
"""Check that players near you are said fairly: never through a wall.

Why this exists
---------------
A tester heard nothing of the players around them - an enemy stepping
out, a wounded teammate, a weapon dropped on the floor - and asked for
it to be said. The snapshot the game sends carries far more than a
sighted player can see: enemies behind walls, across the map in the
same area. Saying those would be a wallhack. So what the callouts may
use is held to what sight gives:

  * an enemy only with a clear line to their body or head, and only in
    the view unless they are close enough to hear;
  * a disguised covert op believed, as a sighted player believes it -
    except where the game itself reveals the disguise;
  * things on the ground only in clear sight;
  * an enemy body offered for its uniform only to a covert op, only an
    enemy's, and only while the uniform is still on it;
  * the callouts behind the hold an answer the player asked for puts on
    the scenery.

Each of those is a line of code that can quietly go, and the result
still compiles, talks and sounds helpful. This reads the patched engine
and fails when one is missing.

Usage
-----
    ./players_near_test.py <engine-root>
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?" % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def body_of(text, name):
    found = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is gone"
                 % (name, DRAW))
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

    draw = strip_comments(read(args.root, DRAW))
    main_c = read(args.root, MAIN)
    failures = []

    gather = body_of(draw, "ETA_GatherAwareness")
    seen = body_of(draw, "ETA_SeenAsEnemy")
    clear = body_of(draw, "ETA_ClearLine")
    narrate = body_of(draw, "ETA_NarrateAwareness")

    # --- the line of sight is a real one --------------------------------
    if not re.search(r"CG_Trace\s*\([^;]*MASK_SOLID\s*\)", clear) \
            or "fraction >= 1.0f" not in clear.replace(" ", " "):
        failures.append("ETA_ClearLine is not a solid-only trace that must "
                        "reach the point, so 'in sight' no longer means sight")

    # --- enemies -------------------------------------------------------
    enemy = re.search(r"if\s*\(\s*ETA_SeenAsEnemy\s*\(\s*other\s*\)\s*\)\s*\{(.*?)\n\t\t\t\}\n\t\t\telse",
                      gather, re.S)
    if not enemy:
        failures.append("could not find the enemy branch of the gathering - "
                        "the rules this test guards have moved")
    else:
        block = enemy.group(1)
        sight = re.search(r"if\s*\(\s*!\s*ETA_ClearLine\s*\([^)]*\)\s*&&\s*!\s*ETA_ClearLine\s*\([^)]*\)\s*\)\s*\{\s*continue\s*;",
                          block)
        cone = re.search(r"meters\s*>\s*10\.0f[^)]*fabs\s*\(\s*thing\.leftOfView\s*\)\s*>\s*halfView[^{]*\{\s*continue\s*;",
                         block, re.S)
        if not sight:
            failures.append("an enemy is listed without a clear line to them - "
                            "the callouts would say enemies through walls")
        else:
            print("[players] an enemy is said only with a clear line to body or head")
        if not cone:
            failures.append("an enemy out of view and out of earshot is still "
                            "listed - more than a sighted player knows")
        else:
            print("[players] out of view, an enemy is said only within hearing")

    if "PW_OPS_DISGUISED" not in seen or "SK_FIELDOPS_ENEMY_RECOGNITION" not in seen:
        failures.append("a disguise is not believed, or its one exception is "
                        "missing - the callouts would see through a covert op "
                        "a sighted player could not, or miss one they could")
    else:
        print("[players] a disguise is believed, except where the game reveals it")

    # --- the ground ----------------------------------------------------
    item = re.search(r"ET_ITEM(.*?)thing\.kind\s*=\s*ETA_AWARE_ITEM", gather, re.S)
    if not item or "ETA_ClearLine" not in item.group(1):
        failures.append("things on the ground are listed through walls")
    body = re.search(r"ET_CORPSE(.*?)thing\.kind\s*=\s*ETA_AWARE_BODY", gather, re.S)
    if not body or "covert" not in body.group(0) or "time2" not in body.group(1) \
            or "ETA_ClearLine" not in body.group(1) \
            or not re.search(r"modelindex\s*==\s*cgs\.clientinfo\[[^]]*\]\.team", body.group(1)):
        failures.append("an enemy body is offered to somebody who cannot take "
                        "its uniform, or one that is ours, already stripped, or "
                        "out of sight")
    elif not re.search(r"covert\s*=\s*\(qboolean\)\s*\(\s*ps->stats\[STAT_PLAYER_CLASS\]\s*==\s*PC_COVERTOPS",
                       gather):
        failures.append("the covert-op test reads something other than the "
                        "player's class")
    else:
        print("[players] items in sight, and enemy bodies only to a covert op")

    # --- the hold, and the switches ------------------------------------
    if not re.search(r"if\s*\(\s*held\s*\)\s*\{\s*return\s*;", narrate):
        failures.append("the callouts do not stand down while an answer the "
                        "player asked for is being spoken")
    if not re.search(r"ETA_NarrateAwareness\s*\(\s*ETA_HudNarrator_PassiveHeld\s*\(\s*cg\.time\s*\)",
                     draw):
        failures.append("the callouts are not told when the scenery is held")
    else:
        print("[players] the callouts stand down while an answer is spoken")

    for cvar in ("eta_playerCallouts", "eta_groundCallouts"):
        if not re.search(r'\{\s*&%s\s*,\s*"%s"\s*,\s*"1"\s*\}' % (cvar, cvar), main_c):
            failures.append("%s is not registered, on by default" % cvar)
        if cvar not in narrate:
            failures.append("%s does not switch the callouts" % cvar)

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        sys.exit(1)

    print("players_near_test: players and things near you are said as far as "
          "sight and hearing reach, and no further")


if __name__ == "__main__":
    main()

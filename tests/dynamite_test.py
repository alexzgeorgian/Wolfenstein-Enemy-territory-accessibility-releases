#!/usr/bin/env python3
"""Check thrown dynamite can be found again, and armed.

The tester threw their dynamite and could not arm it: the game said it
was "set, but NOT armed", and nothing said where it had rolled. Each
part of the fix rests on something the game itself does, which this
checks against the game's own code:

- dynamite is armed when G_ArmDynamite stamps effect1Time, so a missile
  without it is still to be armed - and the cgame reads it that way;
- each throw carries its thrower and team (G_PreFilledMissileEntity),
  so "your dynamite" is the player's own;
- a throw comes to rest through G_SetOrigin with its time stamped, so
  "dynamite down" is said once per throw, when it has stopped;
- dynamite is sent to every player wherever it is, so F lists it only
  in sight - never through a wall;
- the game sends the same defuse icon for the team's own dynamite as
  for the enemy's, so over the team's own the hint says "arm";
- the aim point is inside the box the pliers reach for, and the search
  for the dynamite under the crosshair reaches as far as the pliers do;
- the callout is not held back behind the scenery: it is the answer to
  the throw.

    ./dynamite_test.py <engine-root>
"""

import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
G_WEAPON = os.path.join("src", "game", "g_weapon.c")
G_MISSILE = os.path.join("src", "game", "g_missile.c")
G_MISC = os.path.join("src", "game", "g_misc.c")
G_MAIN = os.path.join("src", "game", "g_main.c")
BG_PUBLIC = os.path.join("src", "game", "bg_public.h")


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def function_body(text, name):
    match = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return None
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    root = os.path.abspath(sys.argv[1])
    failures = []

    draw = strip_comments(read(os.path.join(root, DRAW)))
    weapon = strip_comments(read(os.path.join(root, G_WEAPON)))
    missile = strip_comments(read(os.path.join(root, G_MISSILE)))
    misc = strip_comments(read(os.path.join(root, G_MISC)))
    gmain = strip_comments(read(os.path.join(root, G_MAIN)))
    bg_public = read(os.path.join(root, BG_PUBLIC))

    # --- what the game does ---------------------------------------------
    arm = function_body(weapon, "G_ArmDynamite") or ""
    if not re.search(r"traceEnt->s\.effect1Time\s*=\s*level\.time", arm):
        failures.append("G_ArmDynamite no longer marks armed dynamite with "
                        "effect1Time - armed and unarmed cannot be told apart")
    prefill = function_body(misc, "G_PreFilledMissileEntity") or ""
    if not re.search(r"ent->s\.clientNum\s*=\s*clientNum;", prefill) \
            or not re.search(r"ent->s\.teamNum\s*=\s*teamNum;", prefill):
        failures.append("a thrown missile no longer carries its thrower and "
                        "team")
    bounce = function_body(missile, "G_BounceMissile") or ""
    if not re.search(r"G_SetOrigin\(ent, trace->endpos\);\s*ent->s\.time = level\.time;", bounce):
        failures.append("dynamite coming to rest is no longer stamped with "
                        "its time - one throw cannot be told from the next")
    if not re.search(r"case ET_MISSILE:\s*if \(ps->stats\[STAT_PLAYER_CLASS\] == PC_ENGINEER\)", gmain) \
            or "hintType = HINT_DISARM;" not in gmain:
        failures.append("the game no longer sends one defuse icon for all "
                        "dynamite an engineer looks at")
    reach = re.search(r"#define\s+CH_BREAKABLE_DIST\s+(\d+)", bg_public)
    box = re.search(r"\{\s*WP_DYNAMITE,.*?\{\s*\{[^}]*\},\s*\{[^}]*\}\s*\},\s*"
                    r"\{\s*\{\s*-?[0-9.]+f,\s*-?[0-9.]+f,\s*(-?[0-9.]+)f\s*\},\s*"
                    r"\{\s*-?[0-9.]+f,\s*-?[0-9.]+f,\s*(-?[0-9.]+)f\s*\}\s*\}", weapon)
    if not reach or not box:
        sys.exit("could not read the pliers' reach or the dynamite's box")
    if not failures:
        print("[dynamite] the game marks arming with effect1Time, stamps a "
              "throw at rest, and sends one icon both ways round")

    # --- what the mod does with it --------------------------------------
    use = function_body(draw, "ETA_DynamiteUse") or ""
    if not re.search(r"es->teamNum == team\)\s*\{\s*return es->effect1Time \? ETA_DYNAMITE_NONE : ETA_DYNAMITE_TO_ARM;", use) \
            or "return es->effect1Time ? ETA_DYNAMITE_TO_DEFUSE : ETA_DYNAMITE_NONE;" not in use:
        failures.append("the team's own unarmed dynamite is not the one to "
                        "arm, or an enemy's armed one not the one to defuse")

    lift = re.search(r"#define\s+ETA_DYNAMITE_AIM_LIFT\s+([0-9.]+)f", draw)
    low, high = float(box.group(1)), float(box.group(2))
    if not lift or not low < float(lift.group(1)) < high:
        failures.append("F aims at dynamite outside the box the pliers reach "
                        "for (%g to %g units up)" % (low, high))

    targets = function_body(draw, "CG_AccessibilityUseTargets") or ""
    case = re.search(r"case ET_MISSILE:(.*?)case ET_CORPSE:", targets, re.S)
    if not case or "ETA_DynamiteUse(es)" not in case.group(1) or "engineer" not in case.group(1):
        failures.append("F does not turn an engineer to dynamite on the "
                        "ground")
    elif "needSight" in case.group(1):
        failures.append("dynamite is listed for F without being in sight - "
                        "the game sends it through walls")
    elif '"Your dynamite, not armed"' not in case.group(1):
        failures.append("the player's own dynamite is not named as theirs")
    else:
        print("[dynamite] F turns an engineer to dynamite in sight: their "
              "own to arm, the enemy's to defuse")

    ahead = function_body(draw, "ETA_DynamiteAhead") or ""
    if not re.search(r"best\s*=\s*CH_BREAKABLE_DIST\s*\+", ahead):
        failures.append("the dynamite under the crosshair is not looked for "
                        "as far as the pliers reach")
    crosshair = function_body(draw, "ETA_NarrateInteractionHint") or ""
    if not re.search(r"what == ETA_INTERACT_DISARM && ETA_DynamiteAhead\(\) == ETA_DYNAMITE_TO_ARM\)\s*\{\s*what = ETA_INTERACT_ARM_DYNAMITE;", crosshair):
        failures.append("over the team's own dynamite the hint still says "
                        "\"defuse\"")
    else:
        print("[dynamite] over the team's own dynamite the pliers' hint "
              "says \"arm\"")

    down = function_body(draw, "ETA_NarrateDynamiteDown") or ""
    if "es->clientNum != ps->clientNum" not in down or "TR_STATIONARY" not in down \
            or "said[j].time == es->time" not in down:
        failures.append("where the dynamite came to rest is not said once "
                        "per throw, for the player's own")
    elif "ETA_HudNarrator_RelativeDirection(" not in down or "ETA_QU_TO_METERS" not in down:
        failures.append("the dynamite is said to be down without where")
    frame = function_body(draw, "CG_DrawActive") or ""
    call = frame.find("ETA_NarrateDynamiteDown();")
    held = frame.find("if (!ETA_HudNarrator_PassiveHeld(")
    if call < 0:
        failures.append("the dynamite callout is never run")
    elif held >= 0 and call > held:
        failures.append("the dynamite callout waits behind the scenery")
    if not [f for f in failures if "down" in f or "callout" in f]:
        print("[dynamite] where a throw came to rest is said once, with the "
              "distance and the side")

    if failures:
        for failure in failures:
            print("[dynamite] FAIL %s" % failure)
        sys.exit(1)

    print("dynamite_test: thrown dynamite can be found and armed")


if __name__ == "__main__":
    main()

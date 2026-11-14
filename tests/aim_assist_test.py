#!/usr/bin/env python3
"""Check the aiming keys: the right way round, and the lock only where fair.

Why this exists
---------------
A tester asked for a key that turns them to the thing they can use, and
an enemy lock-on, after a match in which they barely brought one enemy
down. Both turn the view by holding the engine's own turn and look keys
until the target is reached. What can quietly go wrong:

  * a sign flipped, so the view turns away from the target and never
    arrives - every frame pressing the wrong key, compiling cleanly;
  * the lock running on anybody's server. Keeping the sights on an enemy
    for the player is aim assistance; on somebody else's server it is a
    cheat against everyone there. It must run only in a game the player
    hosts, or where the server's host has said yes;
  * the lock seeing more than sight does - an enemy through a wall, or
    out of view and out of earshot, or one the server stopped sending;
  * a key left held: the view would keep turning after the lock is let
    go, after the player turns by hand, or into the next map;
  * the build count talked over again by the players-near-you callouts,
    which is what silenced it for the tester in beta-0.01.8.

Usage
-----
    ./aim_assist_test.py <engine-root>
"""

import argparse
import os
import re
import sys

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?" % (relative, root))
    with open(path, "r", errors="replace") as handle:
        text = handle.read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is gone"
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
    sys.exit("could not find the end of %s" % name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    console = read(args.root, CONSOLE)
    draw = read(args.root, DRAW)
    failures = []

    # The steering is two functions: the angles core, shared with the
    # ladder climb, and the wrapper that aims it at a point.
    steer = (body_of(console, "ETA_AimSteerAngles", CONSOLE)
             + body_of(console, "ETA_AimSteer", CONSOLE))
    keys = body_of(console, "ETA_AimKeys", CONSOLE)
    turn_key = body_of(console, "ETA_TurnKey", CONSOLE)
    lock_down = body_of(console, "CG_AccessibilityAimLockDown_f", CONSOLE)
    lock_up = body_of(console, "CG_AccessibilityAimLockUp_f", CONSOLE)
    turn_down = body_of(console, "CG_AccessibilityTurnDown", CONSOLE)
    shutdown = body_of(console, "CG_AccessibilityTurnShutdown", CONSOLE)
    allowed = body_of(draw, "CG_AccessibilityAimAssistAllowed", DRAW)
    aimable = body_of(draw, "ETA_EnemyAimable", DRAW)
    aim_point = body_of(draw, "CG_AccessibilityEnemyAimPoint", DRAW)
    awareness = body_of(draw, "ETA_NarrateAwareness", DRAW)
    build = body_of(draw, "ETA_NarrateBuildProgress", DRAW)

    # --- the right way round -------------------------------------------
    # Turning right lowers the yaw and looking down raises the pitch
    # (CL_AdjustAngles). So a target at a higher yaw is on the left, and
    # one at a higher pitch is below.
    if not re.search(r"yawError\s*=\s*AngleSubtract\s*\(\s*wanted\[YAW\]\s*,\s*ps->viewangles\[YAW\]\s*\)", steer) \
            or not re.search(r"pitchError\s*=\s*AngleSubtract\s*\(\s*wanted\[PITCH\]\s*,\s*ps->viewangles\[PITCH\]\s*\)", steer):
        failures.append("the aim errors are not measured as target minus view")
    elif not re.search(r"yaw\s*=\s*yawError\s*>\s*0\.0f\s*\?\s*-1\s*:\s*1", steer):
        failures.append("a target to the left does not press the left key - "
                        "the view would turn away from it and never arrive")
    elif not re.search(r"pitch\s*=\s*pitchError\s*>\s*0\.0f\s*\?\s*1\s*:\s*-1", steer):
        failures.append("a target below does not look down")
    elif not re.search(r'direction\s*<\s*0\s*\?\s*"left"\s*:\s*"right"', turn_key) \
            or not re.search(r'pitch\s*<\s*0\s*\?\s*"lookup"\s*:\s*"lookdown"', keys):
        failures.append("-1 no longer means left and up in the keys the aim "
                        "holds, so the signs above mean the opposite")
    else:
        print("[aim] left is left and down is down, measured target minus view")

    # --- the lock only where it is fair ----------------------------------
    gate = re.search(r"if\s*\(\s*!\s*CG_AccessibilityAimAssistAllowed\s*\(\s*\)\s*\)\s*\{[^}]*return\s*;",
                     lock_down)
    acquire = lock_down.find("ETA_AimAcquire")
    if not gate or acquire < 0 or gate.start() > acquire:
        failures.append("the enemy lock runs without first asking whether aim "
                        "assistance is allowed here - on somebody else's "
                        "server that is a cheat")
    trues = re.findall(r"return\s+([^;]+);", allowed)
    if "cgs.localServer" not in allowed \
            or not re.search(r'CS_SERVERINFO\s*\)\s*,\s*"eta_aimAssist"', allowed) \
            or any(r.strip() == "qtrue" for r in trues[1:]) or len(trues) != 2:
        failures.append("aim assistance is allowed somewhere other than a game "
                        "the player hosts or a server that says eta_aimAssist 1")
    if not failures or all("allowed" not in f for f in failures):
        print("[aim] the lock runs only in a game you host, or where the server allows it")

    # --- what the lock may see ---------------------------------------------
    if "ETA_SeenAsEnemy" not in aimable or "EF_DEAD" not in aimable:
        failures.append("the lock does not follow the disguise rule, or locks "
                        "on to an enemy already down")
    if not re.search(r"!\s*ETA_ClearLine\s*\([^)]*\)\s*&&\s*!\s*ETA_ClearLine\s*\([^)]*\)[^{]*\{\s*return\s+qfalse",
                     aimable):
        failures.append("the lock can hold an enemy through a wall")
    if not re.search(r"meters\s*>\s*10\.0f\s*&&\s*fabs\s*\(\s*CG_AccessibilityLeftOfView", aimable):
        failures.append("the lock can take an enemy out of view and out of "
                        "earshot")
    if "cg.snap->entities" not in aim_point:
        failures.append("the lock keeps following an enemy the server stopped "
                        "sending")
    if not [f for f in failures if "lock" in f and "allowed" not in f]:
        print("[aim] an enemy only in clear sight, in view or within hearing, "
              "and only while the server sends them")

    # --- nothing left held ----------------------------------------------
    if "ETA_AimStop" not in lock_up:
        failures.append("letting go of the lock key does not let go of the view")
    if not re.search(r"eta_aim\.mode\s*!=\s*ETA_AIM_NONE\s*\)\s*\{\s*ETA_AimStop", turn_down):
        failures.append("turning by hand does not take over from an aim, so "
                        "the two fight over the same keys")
    if "ETA_AimStop" not in shutdown:
        failures.append("a map change or shutdown can leave an aim's key held, "
                        "and the view turning into the next map")
    stop = body_of(console, "ETA_AimStop", CONSOLE)
    if not re.search(r"ETA_AimKeys\s*\(\s*0\s*,\s*0\s*\)", stop) or "ETA_TurnBoost(qfalse)" not in stop:
        failures.append("stopping an aim does not let go of every key and the "
                        "turn speed it borrowed")
    if not [f for f in failures if "held" in f or "let go" in f or "takes over" in f]:
        print("[aim] every way an aim ends lets go of the keys")

    # --- the lock by itself ------------------------------------------------
    auto = body_of(console, "ETA_AutoLock", CONSOLE)
    for needed, why in (
            ("CG_AccessibilityAimAssistAllowed", "runs where aim assistance is not "
             "allowed - a cheat on somebody else's server"),
            ("eta_autoLock.integer", "cannot be switched off"),
            ("CG_AccessibilityBuildBusy", "would swing the view off a build being "
             "counted out"),
            ("cgs.autoMapExpanded", "would turn the view while the map is open"),
            ("ETA_AIM_AUTO_METERS", "reaches further than the callouts do"),
            ("manualUntil", "fights a player turning by hand")):
        if needed not in auto:
            failures.append("the lock by itself %s" % why)
    if not re.search(r"eta_aim\.manualUntil\s*=\s*cg\.time\s*\+\s*ETA_AIM_MANUAL_MS", turn_down):
        failures.append("a turn by hand does not keep the lock by itself off, so "
                        "it takes the view straight back")
    frame = body_of(console, "CG_AccessibilityAimFrame", CONSOLE)
    if not re.search(r"eta_aim\.automatic\s*&&\s*\(\s*cgs\.autoMapExpanded\s*\|\|\s*CG_AccessibilityBuildBusy",
                     frame):
        failures.append("a lock taken by itself does not stand down when the "
                        "map opens or a build starts")
    if not [f for f in failures if "by itself" in f]:
        print("[aim] the lock by itself asks the same question, and stands down "
              "for a turn, the map and a build")

    # --- the one use key: uses, turns, and loses nothing --------------------
    use_down = body_of(console, "CG_AccessibilityActivateDown_f", CONSOLE)
    use_up = body_of(console, "CG_AccessibilityActivateUp_f", CONSOLE)
    through = re.search(r"if\s*\(\s*hint\s*\|\|\s*count\s*<=\s*0\s*\)\s*\{\s*(?:/\*.*?\*/\s*)?"
                        r"(?:if\s*\(\s*eta_aim\.mode\s*==\s*ETA_AIM_FOLLOW\s*\)\s*\{\s*ETA_AimStop\s*\(\s*\)\s*;\s*\}\s*)?"
                        r"(?:/\*.*?\*/\s*)?(?:if\s*\(\s*!hint[^{]*\{[^}]*\}\s*)?"
                        r"ETA_UseKey\s*\(\s*qtrue\s*\)\s*;\s*return\s*;",
                        use_down, re.S)
    if not through or "CG_AccessibilityUseTargets" not in use_down \
            or not re.search(r"cursorHintIcon\s*!=\s*HINT_NONE", use_down):
        failures.append("the use key no longer uses what is under the crosshair, "
                        "or does nothing with nothing close by - it would lose "
                        "what the plain key did")
    elif not re.search(r"ETA_UseInReach\(&list\[index\]\)\s*\)\s*\{\s*ETA_AimStartSnap\s*\([^;]*\)\s*;\s*eta_use\.pending\s*=\s*\(qboolean\)!list\[index\]\.locked",
                       use_down):
        failures.append("the use key does not use a thing in reach once it has "
                        "turned to it")
    elif "ETA_AIM_CYCLE_MS" not in use_down:
        failures.append("pressing the use key again does not move on to the next "
                        "thing - the turn that once had a key of its own is lost")
    elif "ETA_UseKey(qfalse)" not in use_up:
        failures.append("letting go of the use key does not let go of the use")
    else:
        print("[aim] the use key uses what it is on, turns to what it is not on "
              "and uses it in reach, and moves on when pressed again")
    if re.search(r'"accessibilityAimUse"', console):
        failures.append("the separate key for turning to things is back - the "
                        "tester asked for one key, the use key")

    # --- things to use, only when F is pressed --------------------------
    # The view once turned to a thing to use by itself when the player
    # stopped beside it. In matches it pulled the view away from where the
    # tester was looking, and they asked for it gone: F is enough.
    if "ETA_AutoUse" in console or "eta_autoUse" in console:
        failures.append("the view still turns to things to use by itself - the "
                        "tester asked for that gone; F is enough")
    else:
        print("[aim] things to use are turned to only when F is pressed")

    # --- doors on F ---------------------------------------------------------
    # The tester found F passed doors by. In reach F pressed use quietly,
    # and a door that would not open for them - on Oasis all three are
    # Axis doors - did nothing and said nothing. Every thing F turns to
    # is now said, and a door that will not open is not pressed at.
    targets = body_of(draw, "CG_AccessibilityUseTargets", DRAW)
    if "target.locked" not in targets or '"Locked door"' not in targets \
            or "CG_AccessibilityDoorModel(es->modelindex, &opens) && !opens" not in targets:
        failures.append("a door this player cannot open is not told from one "
                        "they can - neither the key-locked kind nor another team's")
    elif not re.search(r"if \(ETA_UseInReach\(&list\[index\]\)\)\s*\{\s*"
                       r"ETA_AimStartSnap\(&list\[index\], list\[index\]\.name\);\s*"
                       r"eta_use\.pending = \(qboolean\)!list\[index\]\.locked;", use_down):
        failures.append("a thing in reach is used without being said, or a "
                        "locked door is pressed at")
    else:
        print("[aim] F says what it turned to, in reach too, and a door that "
              "will not open is said as locked rather than pressed at")

    # --- the build count is not talked over -----------------------------
    if not re.search(r"eta_buildBusyUntil\s*=\s*cg\.time\s*\+", build):
        failures.append("the build count does not say it is running, so the "
                        "callouts cannot wait for it")
    if not re.search(r"UpdateAwareness\s*\([^;]*building\s*\?\s*0\s*:\s*1", awareness):
        failures.append("the callouts do not stop interrupting while a build "
                        "is counted out - the tester heard no build progress")
    else:
        print("[aim] the callouts wait while a build is counted out")

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        sys.exit(1)

    print("aim_assist_test: the aiming keys turn the right way, let go when "
          "they should, and lock on only where it is fair")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check the ladder finder and the climb agree with the game's own ladders.

A ladder in ET is not an entity: it is a face of the map marked
SURF_LADDER, found by the player's movement code tracing ahead of them
(PM_CheckLadderMove), and climbed by the view and the walk keys together
(PM_LadderMove). The mod finds ladders and climbs them for a blind
player by pressing those same keys - so every part of it is only right
while it agrees with that movement code, and every disagreement is a
player walking off a ledge:

- the finder must test the same surface flag, with the same collision
  the player's movement uses, or it says ladders the game will not let
  anyone climb;
- each climb's view must make PM_LadderMove go the way the climb says:
  the upscale it computes from the view's pitch, times the walk key's
  sign, has to come out positive going up and negative going down. A
  pitch on the wrong side of that formula climbs the wrong way;
- the use key must climb before it turns to other things, and the
  game's own ladder icon must not count as "something under the
  crosshair to use", which would hand the key to the plain use action
  that does nothing on a ladder;
- the walk keys the climb holds must be let go - at the end, when the
  player turns by hand, and when the cgame shuts down - or the player
  keeps walking into the next map.

    ./ladder_climb_test.py <engine-root>
"""

import math
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
PREDICT = os.path.join("src", "cgame", "cg_predict.c")
PMOVE = os.path.join("src", "game", "bg_pmove.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?" % (relative, root))
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

    draw = strip_comments(read(root, DRAW))
    console = strip_comments(read(root, CONSOLE))
    predict = strip_comments(read(root, PREDICT))
    pmove = strip_comments(read(root, PMOVE))

    # --- the finder tests what the game tests --------------------------
    hit = function_body(draw, "ETA_LadderHit")
    near = function_body(draw, "CG_AccessibilityLadderNear")
    if hit is None or near is None:
        sys.exit("no ladder finder in %s" % DRAW)

    check = function_body(pmove, "PM_CheckLadderMove")
    if check is None or "SURF_LADDER" not in check:
        failures.append("the game's own ladder test no longer looks for "
                        "SURF_LADDER - the finder is checking against "
                        "something else now")
    if "SURF_LADDER" not in hit:
        failures.append("the finder does not test SURF_LADDER, the flag the "
                        "game climbs by")
    else:
        print("[ladder] found by SURF_LADDER, the game's own ladder flag")

    if near.count("ETA_LadderCentre(out)") < 2:
        failures.append("a found ladder is not moved to its middle before it "
                        "is climbed - aimed at its edge, the climb walks into "
                        "the wall beside it")
    else:
        print("[ladder] aimed at the middle of the ladder, not its edge")

    mask = re.search(r"#define\s+ETA_LADDER_MASK\s+\((.*?)\)\s*$", draw, re.M)
    player_mask = re.search(r"cg_pmove\.tracemask\s*=\s*(MASK_PLAYERSOLID & ~CONTENTS_BODY);", predict)
    if not mask or not player_mask or re.sub(r"\s", "", mask.group(1)) != re.sub(r"\s", "", player_mask.group(1)):
        failures.append("the finder does not collide with what the player's "
                        "own movement collides with")
    elif near.count("ETA_LADDER_MASK") < 3:
        failures.append("not every ladder trace uses the player's collision")
    else:
        print("[ladder] traced with the player's own collision: %s" % mask.group(1))

    # --- each climb goes the way it says ------------------------------
    up = re.search(r"\bupscale\s*=\s*\(pml\.forward\[2\]\s*\+\s*([0-9.]+)f?\)\s*\*\s*([0-9.]+)f?", pmove)
    climb = function_body(console, "ETA_ClimbFrame")
    if not up or climb is None:
        sys.exit("could not read PM_LadderMove's upscale or the climb")

    offset, gain = float(up.group(1)), float(up.group(2))

    def upscale(pitch):
        # The engine's pitch is positive looking down; forward[2] is the
        # view's upward component.
        forward_z = -math.sin(math.radians(pitch))
        return max(-1.0, min(1.0, (forward_z + offset) * gain))

    pitches = {}
    for case, pattern in (("up", r"if \(eta_climb\.goesUp\)\s*\{\s*wanted\[PITCH\]\s*=\s*(-?[0-9.]+)f"),
                          ("behind", r"else if \(eta_climb\.behind\)\s*\{\s*wanted\[PITCH\]\s*=\s*(-?[0-9.]+)f"),
                          ("front", r"else\s*\{\s*wanted\[PITCH\]\s*=\s*(-?[0-9.]+)f")):
        m = re.search(pattern, climb)
        if not m:
            failures.append("could not read the climb's pitch going %s" % case)
        else:
            pitches[case] = float(m.group(1))

    walk = re.search(r"ETA_ClimbMove\(eta_climb\.behind \? -1 : 1\)", climb)
    if not walk:
        failures.append("the climb no longer walks backward off the edge for a "
                        "ladder under the player and forward otherwise")

    if len(pitches) == 3 and walk:
        # vertical wish = upscale * walk key; up must climb, down must descend
        results = {
            "up": upscale(pitches["up"]) * 1,
            "front": upscale(pitches["front"]) * 1,
            "behind": upscale(pitches["behind"]) * -1,
        }
        if results["up"] <= 0.5:
            failures.append("climbing up looks at pitch %g, where the game "
                            "climbs at %.2f of full speed - not up"
                            % (pitches["up"], results["up"]))
        if results["front"] >= -0.5:
            failures.append("climbing down a ladder ahead looks at pitch %g, "
                            "where walking forward climbs at %.2f - not down"
                            % (pitches["front"], results["front"]))
        if results["behind"] >= -0.5:
            failures.append("climbing down a ladder under the edge looks at "
                            "pitch %g, where walking backward climbs at %.2f "
                            "- not down" % (pitches["behind"], results["behind"]))
        if not [f for f in failures if "pitch" in f]:
            print("[ladder] by the game's own formula: up %+.2f, down ahead "
                  "%+.2f, down behind %+.2f" % (results["up"], results["front"],
                                                results["behind"]))

    # --- the use key climbs first, and the ladder icon is not a hint --
    activate = function_body(console, "CG_AccessibilityActivateDown_f")
    if activate is None:
        sys.exit("no use key handler")
    flat = re.sub(r"\s+", " ", activate)
    # Something chosen with ] and [ comes first by design, a ladder too;
    # the order that matters here is for everything after the choice.
    after_choice = max(0, flat.find("count = (cg.snap && cg.predictedPlayerState.pm_type == PM_NORMAL && !hint)"))
    if "cg.cursorHintIcon != HINT_LADDER" not in flat:
        failures.append("the game's ladder icon counts as something to use, "
                        "so F does the plain use action on a ladder, which "
                        "is nothing")
    ladder_at = flat.find("ETA_ClimbStart(", after_choice)
    snap_at = flat.find("ETA_AimStartSnap(", after_choice)
    if ladder_at < 0 or snap_at < 0 or ladder_at > snap_at:
        failures.append("the use key does not try the ladder before turning "
                        "to other things")
    else:
        print("[ladder] F climbs a ladder before turning to other things, "
              "and the ladder icon does not stop it")

    # --- F finds a ladder heard from further off -----------------------
    # The ladders read from the map are on the use key's list, so F turns
    # to one like anything else to use and says it; but only one in
    # sight, and never one pressed for the player on arrival.
    targets = function_body(draw, "CG_AccessibilityUseTargets") or ""
    if "eta_mapLadders[i]" not in targets or "target.ladder    = qtrue" not in targets:
        failures.append("the map's ladders are not on the use key's list, so "
                        "F cannot find a ladder it can hear")
    elif "ETA_SeesPoint(eye, seen, -1)" not in targets:
        failures.append("F would turn to a ladder behind a wall")
    if not re.search(r"if \(list\[index\]\.ladder\)\s*\{\s*ETA_AimStartSnap\(&list\[index\],\s*count > 1", activate):
        failures.append("a ladder turned to is not said, or the use key is "
                        "pressed at it on arrival - which does nothing")
    if "list[other].ladder" not in activate:
        failures.append("a ladder within reach is weighed against itself on "
                        "the list, so F turns to it instead of climbing")
    if not [f for f in failures if "F " in f or "ladder turned" in f or "weighed" in f]:
        print("[ladder] F turns to a ladder in sight and says it, and climbs it "
              "once there")

    # --- the keys are given back --------------------------------------
    keys = re.findall(r'#define\s+ETA_\w+\s+"(99\d)"', console)
    if len(keys) != len(set(keys)):
        failures.append("two of the mod's pressed keys share a number: %s - "
                        "letting go of one lets go of the other" % sorted(keys))

    stop = function_body(console, "ETA_ClimbStop")
    if stop is None or "ETA_ClimbMove(0)" not in stop:
        failures.append("stopping a climb does not let go of the walk key")
    shutdown = function_body(console, "CG_AccessibilityTurnShutdown")
    if shutdown is None or "ETA_ClimbStop(" not in shutdown:
        failures.append("a climb running at a map change keeps walking into "
                        "the next map")
    turn = function_body(console, "CG_AccessibilityTurnDown")
    if turn is None or "ETA_ClimbStop(" not in turn:
        failures.append("turning by hand does not take over from a climb")
    frame = function_body(console, "CG_AccessibilityAimFrame")
    if frame is None or "ETA_ClimbFrame()" not in frame:
        failures.append("nothing runs the climb")
    if not [f for f in failures if "climb" in f and "pitch" not in f]:
        print("[ladder] the walk keys are let go at the end, on a turn by "
              "hand and at shutdown")

    if failures:
        for failure in failures:
            print("[ladder] FAIL %s" % failure)
        sys.exit(1)

    print("ladder_climb_test: ladders are found and climbed the way the "
          "game's own movement climbs them")


if __name__ == "__main__":
    main()

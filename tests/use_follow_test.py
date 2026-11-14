#!/usr/bin/env python3
"""Check F keeps the player facing what it turned them to while they walk.

The tester chose a weapon a few metres off with the bracket keys, F
turned them to it, and walking there the view drifted off it: they
arrived facing elsewhere and could not pick it up. And a weapon on the
floor two and a half metres off was "in reach" to F, but out of the
reach of the game's own use, which is measured from the eyes.

This checks, against the patched engine:

- F on a chosen thing out of reach turns to it and stays on it - every
  frame the view is steered to where it is now - and says once when it
  is in reach, "F to use";
- the choice is kept all the walk, and let go of the lock when a turn
  key is pressed, another thing is chosen, or it is out of sight a while;
- a thing on the ground is in reach by the distance from the eyes, inside
  the game's own CH_ACTIVATE_DIST; anything else as before.

    ./use_follow_test.py <engine-root>
"""

import os
import re
import sys

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
BG_PUBLIC = os.path.join("src", "game", "bg_public.h")


def read(root, relative):
    path = os.path.join(root, relative)
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
        return ""
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    console = read(root, CONSOLE)
    code = strip_comments(console)
    failures = []

    if "ETA_AIM_FOLLOW" not in code:
        sys.exit("no follow in %s - the feature this test measures is gone" % CONSOLE)

    # --- the game's reach ---------------------------------------------------
    reach = re.search(r"#define\s+CH_ACTIVATE_DIST\s+(\d+)", read(root, BG_PUBLIC))
    ours = re.search(r"#define\s+ETA_USE_EYE_REACH\s+([\d.]+)f", console)
    in_reach = function_body(code, "ETA_UseInReach")
    if not reach or not ours:
        failures.append("the game's use reach, or F's for a thing on the ground, is gone")
    elif float(ours.group(1)) >= float(reach.group(1)):
        failures.append("F calls a thing on the ground in reach at %s from the eyes; the game's use reaches %s"
                        % (ours.group(1), reach.group(1)))
    elif "ET_ITEM" not in in_reach or "Distance(eye, target->point) <= ETA_USE_EYE_REACH" not in in_reach \
            or "viewheight" not in in_reach:
        failures.append("a thing on the ground is not in reach by the eyes")
    else:
        print("[follow] a thing on the ground is in reach within %s of the eyes; the game's use reaches %s"
              % (ours.group(1), reach.group(1)))

    activate = function_body(code, "CG_AccessibilityActivateDown_f")
    if activate.count("ETA_UseInReach(&list[index])") < 2 or "ETA_USE_REACH_METERS)" in activate.split("list[0].stairs")[0]:
        failures.append("F does not judge reach the same way for a chosen thing and the nearest")

    # --- following -----------------------------------------------------------
    start = function_body(code, "ETA_AimStartFollow")
    frame = function_body(code, "ETA_FollowFrame")
    aim = function_body(code, "CG_AccessibilityAimFrame")
    step = function_body(code, "ETA_ChooseStep")
    turn = function_body(code, "CG_AccessibilityTurnDown")
    for ok, what in (
            (re.search(r"if \(!list\[index\]\.ladder && !list\[index\]\.locked && !reach\)\s*\{\s*ETA_AimStartFollow\(&list\[index\], NULL\);",
                       activate),
             "F on a chosen thing out of reach does not stay on it"),
            ("eta_aim.mode      = ETA_AIM_FOLLOW;" in start and "ETA_AimStartSnap(target, label ? label : target->name);" in start,
             "the follow does not turn to the thing and say it first"),
            (re.search(r"if \(eta_aim\.mode == ETA_AIM_FOLLOW\)\s*\{\s*ETA_FollowFrame\(\);\s*return;", aim),
             "the follow is not run every frame"),
            ("ETA_AimSteer(eta_aim.point, 1.0f);" in frame and "VectorCopy(target->point, eta_aim.point);" in frame
             and "ETA_ChooseFind(list, count, target)" in frame,
             "the view is not steered to where the thing is now"),
            ("%s, in reach, F to use" in console and "eta_aim.saidReach = qtrue;" in frame,
             "arriving in reach is not said, once"),
            ("eta_choose.at = cg.time;" in frame, "the choice runs out on a long walk"),
            ("is out of sight. F turns to it again" in console and "ETA_FOLLOW_LOST_MS" in frame,
             "a thing out of sight is followed forever, or let go of without a word"),
            ("if (eta_aim.mode == ETA_AIM_FOLLOW)" in step and "ETA_AimStop();" in step,
             "choosing another thing does not let go of the one being walked to"),
            ("if (eta_aim.mode != ETA_AIM_NONE)" in turn and "ETA_AimStop();" in turn,
             "a turn key does not take the view back")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "follow" in f or "steered" in f or "said" in f or "choice" in f
            or "sight" in f or "turn key" in f or "choosing" in f]:
        print("[follow] F on a chosen thing out of reach keeps the view on it every frame, says once it is "
              "in reach, keeps the choice, and lets go on a turn key, a new choice, or out of sight")

    # --- F by itself ---------------------------------------------------------
    # The tester found F by itself said nothing on reaching the nearest
    # thing: only a thing chosen with the bracket keys was followed. Now the
    # nearest is followed too, and F on arrival uses it, not the next one.
    tail = activate[activate.rfind("if (ETA_UseInReach(&list[index]))"):]
    plain = strip_comments(activate)
    for ok, what in (
            (re.search(r"if \(!list\[index\]\.locked\)\s*\{\s*ETA_AimStartFollow\(&list\[index\],", tail),
             "F by itself on a thing out of reach does not stay on it"),
            (re.search(r"if \(eta_aim\.mode == ETA_AIM_FOLLOW && ETA_UseInReach\(&eta_aim\.follow\)\)\s*\{"
                       r"[^}]*ETA_ChooseFind\(list, count, &eta_aim\.follow\)[^}]*\{\s*ETA_AimStartSnap\(&list\[j\]"
                       r"[^}]*eta_use\.pending\s*=", plain),
             "F pressed on arriving at what it followed moves on to the next one, or does not use it"),
            (re.search(r"if \(hint \|\| count <= 0\)\s*\{\s*if \(eta_aim\.mode == ETA_AIM_FOLLOW\)\s*\{\s*ETA_AimStop\(\);",
                       plain),
             "F using what it followed under the crosshair keeps following it, and says it is out of sight once gone")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "by itself" in f or "arriving" in f or "under the crosshair" in f]:
        print("[follow] F by itself keeps the view on the nearest thing out of reach and says once it is in "
              "reach; F on arrival uses it, and lets go")

    if failures:
        for failure in failures:
            print("[follow] FAIL %s" % failure)
        sys.exit(1)
    print("use_follow_test: F keeps you facing what you chose, or the nearest thing, while you walk to it")


if __name__ == "__main__":
    main()

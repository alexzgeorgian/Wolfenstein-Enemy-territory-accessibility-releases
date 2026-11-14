#!/usr/bin/env python3
"""Check ] and [ choose what F turns to, and F9 says where you are.

The tester could not dynamite the Old City wall on Oasis: several things
to use were close together, and F took the nearest, or whatever the
crosshair was already on. So ] and [ step through the things to use and
say each without turning, and F turns to the one chosen. They also knew
they were indoors but not where, so F9 says the place.

This checks:

- the choose keys walk the very list F uses, from the nearest, round
  and round, and say each without turning the view;
- F takes the choice before the crosshair and before a ladder in reach,
  uses it only in reach and never presses at a locked door or a ladder;
- the choice stays while the player walks to it - F again turns to it,
  not to the nearest - and is let go once used, or once it is gone;
- both keys are offered by the installer on keys the game's own layout
  leaves free, are console commands, are on the Key Binds page and in
  the game's binding list, and are bound in the shipped config;
- F9's indoors or outdoors carries the place name.

    ./use_chooser_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")
UI_SHARED = os.path.join("src", "ui", "ui_shared.c")
DEFAULT_CFG = os.path.join("etmain", "default.cfg")
KEYS_MENU = os.path.join(REPO, "release", "ui", "options_accessibility_keys.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")


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

    console = strip_comments(read(os.path.join(root, CONSOLE)))
    draw = strip_comments(read(os.path.join(root, DRAW)))

    # --- the choosing ------------------------------------------------------
    step = function_body(console, "ETA_ChooseStep") or ""
    if "CG_AccessibilityUseTargets(list, ETA_AIM_MAX_TARGETS)" not in step:
        failures.append("the choose keys do not walk the list F uses")
    elif "index = step > 0 ? 0 : count - 1;" not in step \
            or "index = (index + step + count) % count;" not in step:
        failures.append("the choose keys do not start at the nearest, or do "
                        "not go round the list")
    elif "ETA_AimSay(" not in step or "ETA_AimStartSnap" in step:
        failures.append("choosing turns the view, or does not say the choice")
    elif not re.search(r'va\("%s, %d of %d", list\[index\]\.name, index \+ 1, count\)', step):
        failures.append("the choice is not said with its place in the list")
    else:
        print("[choose] ] and [ walk F's list from the nearest, round, said "
              "with \"2 of 4\" and without turning")

    activate = function_body(console, "CG_AccessibilityActivateDown_f") or ""
    take = activate.find("ETA_ChooseTake(list, count, &index)")
    hint_use = activate.find("if (hint || count <= 0)")
    ladder = activate.find("CG_AccessibilityLadderNear(&ladder)")
    if take < 0 or take > hint_use or take > ladder:
        failures.append("F does not take the choice before the crosshair and "
                        "a ladder in reach")
    elif not re.search(r"qboolean reach = ETA_UseInReach\(&list\[index\]\);", activate) \
            or not re.search(r"eta_use\.pending = \(qboolean\)\(!list\[index\]\.ladder && !list\[index\]\.locked && reach\);",
                             activate):
        failures.append("F uses the chosen thing out of reach, or presses at a "
                        "locked door or a ladder")
    else:
        print("[choose] F turns to the chosen thing before anything else, and "
              "uses it only in reach")
    taken = function_body(console, "ETA_ChooseTake") or ""
    if taken.count("eta_choose.held = qfalse;") < 2 or "ETA_CHOOSE_HOLD_MS" not in taken:
        failures.append("a choice gone from the list is not let go, or is kept forever")

    # The tester, turned to a gun out of reach, walked up and pressed F
    # again, and was turned to whatever was nearest: the choice had been
    # let go the moment F turned to it. It is kept until it is used.
    chosen = activate[take:hint_use]
    frame = function_body(console, "CG_AccessibilityAimFrame") or ""
    if not re.search(r"if \(!list\[index\]\.ladder && !list\[index\]\.locked\)\s*\{\s*"
                     r"eta_choose\.held\s*= qtrue;\s*eta_choose\.at\s*= cg\.time;\s*"
                     r"eta_choose\.target = list\[index\];", chosen):
        failures.append("the choice is let go once F turns to it, so walking up "
                        "and pressing F again turns to the nearest thing instead")
    elif not re.search(r"if \(use && eta_choose\.held && eta_choose\.target\.entityNum >= 0 "
                       r"&& eta_choose\.target\.entityNum == body\)\s*\{\s*eta_choose\.held = qfalse;", frame) \
            or frame.find("eta_choose.held = qfalse;") < frame.find("is in the way, and would be picked up"):
        failures.append("the choice is not let go once used, or is let go when "
                        "something on the ground kept it from being used")
    else:
        print("[choose] the choice stays while you walk to it, each F turning to "
              "it again, and is let go once used")

    # --- the keys ----------------------------------------------------------
    stock = read(os.path.join(root, DEFAULT_CFG))
    ui = read(os.path.join(root, UI_MAIN))
    shared = read(os.path.join(root, UI_SHARED))
    menu = read(KEYS_MENU)
    autoexec = read(AUTOEXEC)
    for key, command in (("]", "accessibilityUseNext"), ("[", "accessibilityUsePrev")):
        if re.search(r"^bind\s+\"?%s\"?\s" % re.escape(key), stock, re.M | re.I):
            failures.append("%s is bound in the game's own layout - %s would "
                            "steal it" % (key, command))
        if not re.search(r"\{\s*'%s',\s*\"%s\",\s*NULL,\s*\d+\s*\}" % (re.escape(key), command), ui):
            failures.append("the installer does not offer %s on %s" % (command, key))
        if not re.search(r'\{\s*"%s",\s*CG_Accessibility\w+_f\s*\}' % command, console):
            failures.append("%s is not a console command" % command)
        if '"%s"' % command.lower() not in shared:
            failures.append("the game's binding list does not know %s" % command)
        if '"%s"' % command not in menu:
            failures.append("the Key Binds page has no row for %s" % command)
        if not re.search(r"^bind %s\s+%s\s*$" % (re.escape(key), command), autoexec, re.M):
            failures.append("autoexec.cfg does not bind %s to %s" % (key, command))
    if not [f for f in failures if "bind" in f or "command" in f or "Key Binds" in f or "steal" in f]:
        print("[choose] ] and [ are free in the game's layout, and offered "
              "everywhere a key is set")

    # --- where you are -------------------------------------------------------
    surroundings = function_body(draw, "CG_AccessibilitySurroundings") or draw
    if not re.search(r'ETA_Speech_Say\(place \? va\("%s, %s", (cover|what), place\) : (cover|what)\);', surroundings) \
            or "const char *place = ETA_LocationName();" not in surroundings:
        failures.append("F9 says indoors or outdoors without the place's name")
    else:
        print("[place] F9 says indoors or outdoors with the place's name")

    if failures:
        for failure in failures:
            print("[choose] FAIL %s" % failure)
        sys.exit(1)
    print("use_chooser_test: ] and [ choose what F turns to, and F9 says "
          "where you are")


if __name__ == "__main__":
    main()

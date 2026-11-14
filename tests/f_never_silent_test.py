#!/usr/bin/env python3
"""Check F always says something when there is nothing to turn to.

The tester pressed F on a Mac and nothing happened at all - while ] and
F, on something chosen, worked. F said nothing in two cases:

- nothing to use within its range: it pressed the game's use, silently;
- the game's crosshair icon showing for something use does nothing with
  - a thing to shoot or knife, water, a locked door, a use already done:
  F took it for something to use, pressed the game's use, silently, and
  never turned to the thing beside it.

This checks, against the patched engine:

- those icons are not taken for something to use, so F goes on to turn
  to the nearest thing; the icons use does act on still are;
- with nothing to turn to, F says so, naming the range it searched, and
  still presses use - but not when the player cannot act (dead, or
  watching), where use has other jobs.

    ./f_never_silent_test.py <engine-root>
"""

import os
import re
import sys

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")

# Icons the game's use does nothing with.
INERT = ("HINT_BREAKABLE", "HINT_BREAKABLE_DYNAMITE", "HINT_KNIFE", "HINT_WATER",
         "HINT_DOOR_LOCKED", "HINT_DOOR_ROTATING_LOCKED", "HINT_RESTRICTED",
         "HINT_BAD_USER", "HINT_COMPLETED", "HINT_NO_DARM_FIRST_REVIVE", "HINT_LADDER")
# Icons it acts on: these must still count as something under the crosshair.
ACTIVE = ("HINT_ACTIVATE", "HINT_DOOR", "HINT_MG42", "HINT_HEALTH", "HINT_AMMO",
          "HINT_BUTTON", "HINT_WEAPON", "HINT_TANK", "HINT_UNIFORM")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function_body(text, name):
    found = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s - the feature this test guards is gone" % name)
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
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    code = re.sub(r"/\*.*?\*/", "", read(root, CONSOLE), flags=re.S)
    activate = function_body(code, "CG_AccessibilityActivateDown_f")
    failures = []

    hint = re.search(r"hint\s*=\s*\(qboolean\)\((.*?)\);", activate, re.S)
    if not hint:
        sys.exit("could not find how F reads the crosshair icon")
    hint = hint.group(1)
    missing = [name for name in INERT if not re.search(r"cg\.cursorHintIcon\s*!=\s*%s\b" % name, hint)]
    if missing:
        failures.append("F takes these icons for something to use, and does nothing: %s" % ", ".join(missing))
    taken = [name for name in ACTIVE if re.search(r"\b%s\b" % name, hint)]
    if taken:
        failures.append("F no longer uses what is under the crosshair for: %s" % ", ".join(taken))
    if not missing and not taken:
        print("[F] icons use does nothing with are passed over, so F turns to the nearest thing; "
              "the ones use acts on are still used")

    nothing = re.search(r"if \(hint \|\| count <= 0\)\s*\{(.*?)ETA_UseKey\(qtrue\);\s*return;", activate, re.S)
    said = re.search(r'ETA_Speech_Say\("Nothing to use within (\d+) meters"\)', nothing.group(1)) if nothing else None
    if not said or not re.search(r"if \(!hint && cg\.snap && cg\.predictedPlayerState\.pm_type == PM_NORMAL\)",
                                 nothing.group(1)):
        failures.append("F with nothing to turn to is silent, or speaks while the player cannot act")
    else:
        rng = re.search(r"#define ETA_USE_RANGE\s+([\d.]+)f?", read(root, DRAW))
        scale = re.search(r"#define ETA_QU_TO_METERS\s+([\d.]+)f?", read(root, LOCAL))
        if not rng or not scale:
            failures.append("F's range or the metre scale is gone")
        elif int(float(rng.group(1)) * float(scale.group(1))) != int(said.group(1)):
            failures.append("F says it looked within %s meters, but looks within %.1f"
                            % (said.group(1), float(rng.group(1)) * float(scale.group(1))))
        else:
            print("[F] with nothing to turn to, F says \"Nothing to use within %s meters\" and still "
                  "presses use" % said.group(1))

    if failures:
        for failure in failures:
            print("[F] FAIL %s" % failure)
        sys.exit(1)
    print("f_never_silent_test: F always says something")


if __name__ == "__main__":
    main()

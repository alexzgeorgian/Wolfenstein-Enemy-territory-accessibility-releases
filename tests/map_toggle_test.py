#!/usr/bin/env python3
"""Check the map key opens and closes the map instead of being held.

Why this exists
---------------
The command map survey walks the map with the keypad under one hand,
and the stock map key shows the map only while it is held. A tester
asked not to have to hold it. With eta_mapToggle on (the default) one
press opens the map and the next closes it, and each is said out loud,
because an open map and a closed one sound the same.

Three ways it breaks without anything else noticing:

  * the release still closes the map, so the toggle does nothing;
  * a second press opens it again instead of closing it, so it can
    never be closed;
  * closing it skips the survey's own cleanup, so the next time the map
    opens the cursor is wherever it was left, not on the player.

Usage
-----
    ./map_toggle_test.py <engine-root>
"""

import argparse
import os
import re
import sys

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\(\s*void\s*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone" % (name, where))
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
    main_c = read(args.root, MAIN)
    failures = []

    up = body_of(console, "CG_AutomapExpandUp_f", CONSOLE)
    down = body_of(console, "CG_AutomapExpandDown_f", CONSOLE)
    collapse = body_of(console, "CG_AutomapCollapse", CONSOLE)

    if not re.search(r"if\s*\(\s*eta_mapToggle\.integer\s*\)\s*\{\s*return\s*;", up):
        failures.append("letting go of the map key still closes the map when "
                        "it is meant to be a switch")

    closing = re.search(r"if\s*\(\s*eta_mapToggle\.integer\s*&&\s*cgs\.autoMapExpanded\s*\)"
                        r"\s*\{(.*?)return\s*;", down, re.S)
    if not closing or "CG_AutomapCollapse" not in closing.group(1):
        failures.append("a press with the map open does not close it, so a "
                        "switched map can never be put away")
    elif '"Map closed"' not in closing.group(1):
        failures.append("closing the map is silent")
    if '"Map open"' not in down:
        failures.append("opening the map is silent")

    if "CG_AccessibilityMapClosed" not in collapse:
        failures.append("putting the map away skips the survey's cleanup, so "
                        "the cursor is left where it was")

    if not re.search(r'\{\s*&eta_mapToggle\s*,\s*"eta_mapToggle"\s*,\s*"1"\s*\}', main_c):
        failures.append("eta_mapToggle is not in the settings table with a "
                        "default of on")

    if failures:
        for failure in failures:
            print("[map] FAIL %s" % failure)
        return 1

    print("map_toggle_test: one press opens the map, the next closes it, and "
          "both are said")
    return 0


if __name__ == "__main__":
    sys.exit(main())

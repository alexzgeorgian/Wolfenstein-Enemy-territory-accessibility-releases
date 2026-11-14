#!/usr/bin/env python3
"""Check the only distances called on the way are the marker's.

The tester asked for the first guide's objective announcement - "40
meters to objective", counted in a straight line to the objective's own
point - to give way to the marker's. The marker is put where the player
can stand and is led to by the way they can walk, so the two named
different places and different numbers, both on the same walk. So:

- the objective's own distance is no longer called on the way;
- the marker's is, with up or down in the marker's own name -
  "Marker is 4 meters above you" - never the objective's, since a
  marker on a room or a sniper spot is no objective;
- every place the marker is put says its height in that name.

    ./marker_distance_only_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRAW = os.path.join("src", "cgame", "cg_draw.c")
COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
NAV = os.path.join(REPO, "src", "accessibility", "navigation", "navigation_system.c")


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
    draw = strip_comments(read(os.path.join(root, DRAW)))
    commandmap = strip_comments(read(os.path.join(root, COMMANDMAP)))
    nav = strip_comments(read(NAV))
    failures = []

    if "CG_AccessibilityMarkerApproach();" not in draw:
        sys.exit("the marker's distances are not called - the feature this test measures is gone")

    if "ETA_NavigationSystem_UpdateApproach(" in draw or "ETA_NarrateObjectiveApproach" in draw:
        failures.append("the objective's own straight-line distance is still called on the way")
    else:
        print("[distance] the objective's straight-line distance is no longer called on the way")

    said = function_body(nav, "ETA_NavigationSystem_AnnounceMarkerHeight")
    approach = function_body(commandmap, "CG_AccessibilityMarkerApproach")
    if '"Marker is %s"' not in said:
        failures.append("the marker's height is not said in the marker's name")
    elif not re.search(r"if \(ETA_NavigationSystem_UpdateMarkerApproach\(ETA_MarkerDistance\(\)\) && !eta_marker\.square\)\s*\{\s*"
                       r"ETA_NavigationSystem_AnnounceMarkerHeight\(", approach):
        failures.append("the marker's distances on the way do not say up or down")
    else:
        print("[distance] the marker's distances on the way say up or down, as the marker's")

    if "ETA_NavigationSystem_AnnounceHeight(" in commandmap:
        failures.append("somewhere the marker is put, its height is said as the objective's")
    elif commandmap.count("ETA_NavigationSystem_AnnounceMarkerHeight(") < 5:
        failures.append("not every place the marker is put says its height")
    else:
        print("[distance] wherever the marker is put, its height is the marker's")

    if failures:
        for failure in failures:
            print("[distance] FAIL %s" % failure)
        sys.exit(1)
    print("marker_distance_only_test: the only distances on the way are the marker's")


if __name__ == "__main__":
    main()

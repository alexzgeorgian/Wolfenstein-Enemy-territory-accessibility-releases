#!/usr/bin/env python3
"""Check the objectives are followed in the map's order, not by distance.

Why this exists
---------------
A tester playing a map on their own spent a match walking between
things that could not be started yet. The narration was pointing at
whichever objective was *nearest*, and ET's maps run their objectives
in sequence - so the nearest one is usually the wrong one, and there
was no way to discover that except by wandering.

The order is not this mod's to invent, and that is the whole point of
this check. ET's map scripts set each objective's state with a numbered
command, keyed per team, counting from one; the engine's own error
message for that command states what the values mean:

    status parameter must be 0 (default), 1 (complete) or 2 (failed)

So the mod reads those, and this test reads them back out of the engine
and fails if they ever stop meaning that. A mod that quietly decided 1
meant "in progress" would send a player to an objective that was
already finished, confidently, with nothing on screen to contradict it
- and a player on their own has no second opinion at all.

Three things it pins:

  * the mod takes the numbering and the states from the engine's
    configstrings rather than from anything of its own;
  * the three state values still mean what the mod assumes;
  * the chooser consults the running order *before* falling back to
    distance. Order first is the entire fix; with the fallback first
    the nearest objective wins again and nothing has changed.

It also pins the link between an objective's number and its place on
the map. That is the map author's objflags bitmask - the engine's own
comment calls it "which commandmap objectives this entity belongs to" -
and it is the same test the stock command map uses to highlight the
objective selected in the limbo panel. Inventing a different link would
point the player at the wrong building.

What it does NOT check
----------------------
Whether the wording is right, or whether hearing "objective 2 of 4" is
what a player wants at that moment. Those need ears.

Usage
-----
    ./objective_order_test.py <engine-root>

ET: Legacy only - the 2010 tree has no objective status configstring.
Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
SCRIPT = os.path.join("src", "game", "g_script_actions.c")
PUBLIC = os.path.join("src", "game", "bg_public.h")
NARRATOR = os.path.join("src", "accessibility", "hud", "hud_narrator.h")


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


def body_of(text, signature, where):
    start = text.find(signature)
    if start < 0:
        sys.exit("could not find %s in %s - the narration this test guards "
                 "is gone, and passing without it would mean nothing"
                 % (signature, where))
    brace = text.find("{", start)
    depth, i, n = 0, brace, len(text)
    while i < n:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1:i]
        i += 1
    sys.exit("could not find the end of %s in %s" % (signature, where))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy", choices=("etlegacy",))
    parser.add_argument("--library", default=None,
                        help="accessibility-mode checkout (default: this one)")
    args = parser.parse_args()

    library_root = args.library or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))

    commandmap = strip_comments(read(args.root, COMMANDMAP,
                                     "is the patch series applied?"))
    console = strip_comments(read(args.root, CONSOLE,
                                  "is the patch series applied?"))
    script = read(args.root, SCRIPT, "is this an engine checkout?")
    public = read(args.root, PUBLIC, "is this an engine checkout?")
    narrator = read(library_root, NARRATOR,
                    "is this the accessibility checkout?")

    failures = []

    # --- the engine still says what the mod assumes -------------------
    #
    # Read straight out of the error message the engine raises for a bad
    # value, which is the only place the meanings are written down.
    documented = re.search(
        r'status parameter must be\s+0\s*\(default\)\s*,\s*1\s*\(complete\)'
        r'\s*or\s*2\s*\(failed\)', script)

    if not documented:
        failures.append(
            "the engine no longer documents its objective status values as "
            "0 default, 1 complete, 2 failed. The mod reads those numbers "
            "and speaks them as facts, so this test can no longer tell "
            "whether it is telling the truth")

    if not re.search(r'Info_SetValueForKey\s*\(\s*cs\s*,\s*va\s*\(\s*"%s%i"',
                     script):
        failures.append(
            "the engine no longer keys objective status per team and "
            "number, so the mod's reading of the running order is against "
            "a format that has changed")

    # The mod's enum has to line up with those numbers.
    for name, value in (("ETA_OBJECTIVE_PENDING", 0),
                        ("ETA_OBJECTIVE_COMPLETE", 1),
                        ("ETA_OBJECTIVE_FAILED", 2)):
        if name not in narrator:
            failures.append("%s is gone from the library" % name)

    order = re.search(r'ETA_OBJECTIVE_PENDING\s*=\s*0\s*,\s*'
                      r'ETA_OBJECTIVE_COMPLETE\s*,\s*'
                      r'ETA_OBJECTIVE_FAILED', narrator, re.S)
    if not order:
        failures.append(
            "the library's objective states are no longer in the engine's "
            "own order starting at 0. They are read straight from the "
            "engine's numbers, so a reordering silently turns \"complete\" "
            "into \"failed\"")

    # --- the mod reads the engine, not itself -------------------------
    state = body_of(commandmap, "int CG_AccessibilityObjectiveState(",
                    COMMANDMAP)

    if "CS_MULTI_OBJECTIVE" not in state:
        failures.append(
            "the objective state does not come from CS_MULTI_OBJECTIVE, so "
            "it is not the state the map script set and not the one the "
            "player's own objective panel shows")

    count = body_of(commandmap, "int CG_AccessibilityObjectiveCount(",
                    COMMANDMAP)

    if "CS_MULTI_INFO" not in count:
        failures.append(
            "the objective count does not come from CS_MULTI_INFO")

    # --- the running order decides, before distance -------------------
    chooser = body_of(console, "qboolean CG_AccessibilityObjective(", CONSOLE)

    current_at = chooser.find("CG_AccessibilityCurrentObjective")
    nearest_at = chooser.find("CG_AccessibilityNearestObjective")

    if current_at < 0:
        failures.append(
            "the objective chooser never asks which objective is next. It "
            "picks by distance, which is the defect: a map's objectives run "
            "in sequence, so the nearest one is usually one that cannot be "
            "started yet")
    elif nearest_at >= 0 and current_at > nearest_at:
        failures.append(
            "the chooser falls back to the nearest objective before "
            "consulting the map's running order. Order first is the whole "
            "fix; this way round the nearest wins again and nothing has "
            "changed")

    # --- the number-to-place link is the engine's own -----------------
    by_number = body_of(commandmap,
                        "qboolean CG_AccessibilityObjectiveByNumber(",
                        COMMANDMAP)

    if "objflags" not in by_number:
        failures.append(
            "nothing links an objective's number to a place on the map "
            "through objflags - the bitmask the map author sets and the "
            "stock command map uses to highlight a selected objective. Any "
            "other link would be the mod's invention and would point the "
            "player at the wrong building")

    if "1 <<" not in by_number:
        failures.append(
            "the objflags test is not a bitmask test, so an objective "
            "number is being compared against a field that holds a set of "
            "them")

    if "objflags" not in read(args.root, os.path.join("src", "cgame",
                                                      "cg_servercmds.c"),
                              "is this an engine checkout?"):
        failures.append(
            "the client no longer receives objflags, so the link the mod "
            "relies on does not arrive")

    # --- a failed objective must not trap the player ------------------
    nxt = body_of(commandmap, "int CG_AccessibilityCurrentObjective(",
                  COMMANDMAP)

    if "== 0" not in nxt:
        failures.append(
            "the next objective is not chosen as the first one still "
            "pending. Stopping at a failed objective would stand the "
            "player in front of something that is not coming back")

    # --- MAX_OBJECTIVES still bounds the arrays -----------------------
    if not re.search(r'#define\s+MAX_OBJECTIVES\s+\d+', public):
        failures.append("MAX_OBJECTIVES is gone from %s" % PUBLIC)

    if failures:
        print("objective_order_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("objective_order_test: %s - the running order and the three "
          "states are the engine's own, the chooser follows the order "
          "before distance, and an objective's place comes from the map "
          "author's own objflags" % args.engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())

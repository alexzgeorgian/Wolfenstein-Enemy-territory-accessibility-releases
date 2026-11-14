#!/usr/bin/env python3
"""Check that the navigation narration can actually find an objective.

Why this exists
---------------
Every spoken distance, every "turn left toward the objective", and the
objective audio cue all need one thing first: somewhere to point. For
six releases the ET: Legacy integration got that from
`CS_MAIN_AXIS_OBJECTIVE` / `CS_MAIN_ALLIES_OBJECTIVE` alone.

Those two configstrings are written in exactly one place in the whole
engine - `G_ScriptAction_SetMainObjective`, the map script command
`wm_set_main_objective` - and that function returns quietly when a script
does not call it. Most maps do not. So on most maps the lookup returned
NULL, every navigation announcement in the mod was skipped, and a blind
player heard silence that was indistinguishable from the feature being
broken. It took a play session to find, because it compiled, linked,
passed every check, and was wrong only to the person listening.

The fix is a fallback onto the command map's own live objective list.
This guards it, in two directions:

1. **Nothing announces a direction it did not get from the resolver.**
   Any function that calls the distance, route-correction or
   objective-direction APIs must also call the one function that decides
   what the target is. A new announcement wired straight to some other
   lookup is the original bug all over again.

2. **The resolver handles every objective type the engine has.** The
   server's own "only the objectives" filter in `g_teammapdata.c` says
   which `ME_*` map entity types count as objectives. The resolver has
   to place all of them. Missing one is silent in exactly the same way:
   fine on maps that happen not to use it, nothing to say on maps that
   do. That is how `ME_COMMANDMAP_MARKER` went unhandled.

Usage
-----
    ./objective_source_test.py <engine-root> --engine {etlegacy,id-software}

Exits non-zero if either property has stopped holding.
"""

import argparse
import os
import re
import sys

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
TEAMMAPDATA = os.path.join("src", "game", "g_teammapdata.c")

# The narration files that may announce a direction or a distance.
SPEAKERS = [
    os.path.join("src", "cgame", "cg_consolecmds.c"),
    os.path.join("src", "cgame", "cg_playerstate.c"),
]

# Calls that commit the mod to a claim about where the objective is.
ANNOUNCEMENTS = (
    "ETA_NavigationSystem_AnnounceDistance",
    "ETA_NavigationSystem_AnnounceRouteCorrection",
    "ETA_AudioCueSystem_PlayObjectiveDirectionCue",
)

# Per engine: the one function that decides what the target is, and the
# one that resolves a map entity's position. The two integrations name
# them differently because the engines differ - ET: Legacy has a "main
# objective" concept to prefer first, the 2010 release has none.
ENGINES = {
    "etlegacy": {
        "resolver": "CG_AccessibilityObjective",
        "placer": "CG_AccessibilityMapObjectiveAt",
    },
    "id-software": {
        "resolver": "ETA_CurrentObjective",
        "placer": "ETA_MapObjectiveAt",
    },
}

ME_TYPE = re.compile(r'\bME_[A-Z0-9_]+\b')
# The server's own list of the types that are objectives, as it writes it:
# a run of `mEnt->type != ME_FOO && ...` tests.
OBJECTIVE_FILTER = re.compile(
    r'mEnt->type\s*!=\s*ME_[A-Z0-9_]+(?:\s*&&\s*mEnt->type\s*!=\s*ME_[A-Z0-9_]+)+')


def strip_comments(text):
    """C source with comments and string literals blanked out."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        two = text[i:i + 2]
        if two == "/*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif two == "//":
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text[i] in "\"'":
            quote = text[i]
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def function_bodies(text):
    """Every `name(...) { ... }` in text, as {name: body}.

    Brace-matched rather than regexed to the closing brace, so a function
    with nested blocks is not cut short at the first `}`.
    """
    bodies = {}
    for match in re.finditer(r'(?:^|\n)[^\n;{}()]*?\b([A-Za-z_][A-Za-z0-9_]*)\s*'
                             r'\([^;{}]*\)\s*\{', text):
        name = match.group(1)
        depth = 0
        i = match.end() - 1
        start = i
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    bodies[name] = text[start:i]
                    break
            i += 1
    return bodies


def engine_objective_types(root):
    """The ME_* types the server itself treats as objectives."""
    path = os.path.join(root, TEAMMAPDATA)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                 % (TEAMMAPDATA, root))

    with open(path, "r", errors="replace") as handle:
        text = strip_comments(handle.read())

    types = set()
    for run in OBJECTIVE_FILTER.findall(text):
        types.update(ME_TYPE.findall(run))

    # These filters exclude the player markers alongside the objectives
    # in the wider ones; they are not objectives.
    types = {t for t in types if not t.startswith("ME_PLAYER")}

    if not types:
        sys.exit("could not find the server's objective-type filter in %s - "
                 "this test is out of date with the engine, and passing "
                 "without reading it would defeat its purpose" % TEAMMAPDATA)

    return types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", required=True, choices=sorted(ENGINES))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    names = ENGINES[args.engine]
    resolver = names["resolver"]
    placer = names["placer"]

    failures = []

    # 1. Nothing announces a direction it did not get from the resolver.
    for relative in SPEAKERS:
        path = os.path.join(root, relative)
        if not os.path.isfile(path):
            sys.exit("no %s under %s" % (relative, root))

        with open(path, "r", errors="replace") as handle:
            bodies = function_bodies(strip_comments(handle.read()))

        for name, body in sorted(bodies.items()):
            announced = [a for a in ANNOUNCEMENTS if a + "(" in body.replace(" ", "")]
            if not announced:
                continue

            if resolver + "(" in body.replace(" ", ""):
                print("[objective] %s: %s via %s"
                      % (os.path.basename(relative), name, resolver))
                continue

            failures.append(
                "%s in %s calls %s but never calls %s - it is pointing the "
                "player somewhere the one resolver did not choose"
                % (name, relative, ", ".join(announced), resolver))

    # 2. The resolver places every objective type the engine has.
    commandmap = os.path.join(root, COMMANDMAP)
    if not os.path.isfile(commandmap):
        sys.exit("no %s under %s" % (COMMANDMAP, root))

    with open(commandmap, "r", errors="replace") as handle:
        bodies = function_bodies(strip_comments(handle.read()))

    if placer not in bodies:
        sys.exit("could not find %s in %s - the navigation fallback this "
                 "test exists to guard is gone" % (placer, COMMANDMAP))

    handled = set(ME_TYPE.findall(bodies[placer]))
    expected = engine_objective_types(root)

    print("[objective] engine calls %d type(s) objectives: %s"
          % (len(expected), ", ".join(sorted(expected))))
    print("[objective] %s places %d: %s"
          % (placer, len(handled), ", ".join(sorted(handled))))

    for missing in sorted(expected - handled):
        failures.append(
            "%s does not place %s, which the engine counts as an objective - "
            "navigation would have nothing to say on maps that use it"
            % (placer, missing))

    if failures:
        print()
        for failure in failures:
            print("[objective] FAIL %s" % failure)
        sys.exit(1)

    print("[objective] ok")


if __name__ == "__main__":
    main()

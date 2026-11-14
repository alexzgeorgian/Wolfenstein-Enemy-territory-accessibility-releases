#!/usr/bin/env python3
"""Check the way to the marker goes up the way a player can go up.

The marker's way was a walk on the flat and up stairs. An objective on
a floor above - the Oasis command post - is often reached only by a
ledge to jump onto or a ladder, and a player who cannot see it was led
straight at the wall underneath. The way now knows both, and each rests
on a number from the game that this checks against the game itself:

- a ledge is "jumped" only as high as the game's jump lifts the feet:
  JUMP_VELOCITY against the gravity in play, plus the step the probe
  already stands on;
- the probe's step is the game's own STEPSIZE, so a ledge a step can
  take is never called a jump;
- ladders are joined to the way from the list read out of the map, the
  moment it is read, with the old map's ladders cleared first;
- the way stops at a jump or a ladder rather than looking past it, says
  "Jump" when the player reaches one, and waits while the player climbs;
- keypad plus puts the marker on the objective, and is offered in every
  place a key is: the bind table, the game's binding list, the Key Binds
  page and the shipped config.

    ./route_up_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")
UI_SHARED = os.path.join("src", "ui", "ui_shared.c")
BG_LOCAL = os.path.join("src", "game", "bg_local.h")
BG_PUBLIC = os.path.join("src", "game", "bg_public.h")
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


def number(text, name):
    match = re.search(r"#define\s+%s\s+([0-9.]+)f?\b" % re.escape(name), text)
    return float(match.group(1)) if match else None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    root = os.path.abspath(sys.argv[1])
    failures = []

    commandmap = strip_comments(read(os.path.join(root, COMMANDMAP)))
    draw = strip_comments(read(os.path.join(root, DRAW)))
    console = strip_comments(read(os.path.join(root, CONSOLE)))
    bg_local = read(os.path.join(root, BG_LOCAL))
    bg_public = read(os.path.join(root, BG_PUBLIC))

    # --- how high a jump is -------------------------------------------
    velocity = number(bg_local, "JUMP_VELOCITY")
    gravity = number(bg_public, "DEFAULT_GRAVITY")
    stepsize = number(bg_local, "STEPSIZE")
    lift = number(commandmap, "ETA_ROUTE_JUMP_LIFT")
    slope = number(commandmap, "ETA_ROUTE_SLOPE_LIFT")
    move = function_body(commandmap, "ETA_RouteMoveExact")
    if None in (velocity, gravity, stepsize, lift, slope) or move is None:
        sys.exit("could not read the jump, the gravity, the step or the "
                 "route probe's lifts")

    apex = velocity * velocity / (2.0 * gravity)
    probe_step = re.search(r"mins\s*=\s*\{[^}]*-24\.0f\s*\+\s*([0-9.]+)f\s*\}", move)
    if not probe_step or float(probe_step.group(1)) != stepsize:
        failures.append("the route probe does not stand on the game's own "
                        "step of %g" % stepsize)
    highest = stepsize + lift
    if highest > apex:
        failures.append("the way calls a ledge of %g units a jump, but the "
                        "game's jump lifts the feet only %.1f - the player "
                        "would be told to jump onto something they cannot"
                        % (highest, apex))
    elif not slope < lift:
        failures.append("the jump's lift is no higher than the slope's, so "
                        "nothing would ever be a jump")
    else:
        print("[route] a ledge up to %g units is a jump; the game's jump "
              "lifts the feet %.1f" % (highest, apex))

    if "ETA_PATH_JUMP" not in move or not re.search(r"plane\.normal\[2\] < 0\.7f", move):
        failures.append("the route probe does not tell a ledge's sheer face "
                        "from a walkable slope (steeper than MIN_WALK_NORMAL), so a ledge would be walked at")

    walkable = function_body(commandmap, "ETA_RouteWalkable") or ""
    if not re.search(r"if \(b\[2\] > a\[2\] \+ 18\.0f\)", walkable) or not re.search(r"plane\.normal\[2\] < 0\.7f", walkable):
        failures.append("the straight-line check does not stop at a sheer "
                        "face below a higher floor - the ping would lead "
                        "through the wall under it")

    # --- ladders join the way -----------------------------------------
    load = function_body(draw, "CG_AccessibilityLoadLadders") or ""
    links = function_body(draw, "ETA_LadderLinks") or ""
    if "ETA_LadderLinks()" not in load:
        failures.append("the ladders read from the map are never handed to "
                        "the way-finder")
    clear_at = links.find("ETA_PathFinder_ClearLinks();")
    add_at = links.find("ETA_PathFinder_AddLink(")
    if clear_at < 0 or add_at < 0 or clear_at > add_at:
        failures.append("the last map's ladders are not cleared before this "
                        "map's are added")
    for kind in ("ETA_PATH_LADDER_UP", "ETA_PATH_LADDER_DOWN"):
        if kind not in links:
            failures.append("ladders are not joined %s" % kind.split("_")[-1].lower())
    if not [f for f in failures if "ladder" in f]:
        print("[route] every ladder with a floor at each end joins the way, "
              "up and down")

    # --- the way stops at an edge, says jump, and waits on a ladder -----
    follow = function_body(commandmap, "ETA_RouteFollow") or ""
    frame = function_body(commandmap, "ETA_RouteFrame") or ""
    say = function_body(commandmap, "ETA_RouteSayJump") or ""
    if "special - 1" not in follow:
        failures.append("the way looks past a jump or a ladder, and leads "
                        "into the wall under it")
    if "CG_AccessibilityClimbing()" not in follow:
        failures.append("climbing a ladder is taken for straying from the "
                        "way, and a new one is searched from mid air")
    if "overEdge" not in frame:
        failures.append("the ping looks for a way round the very ledge or "
                        "ladder the way goes up")
    if '"Jump up"' not in say or "ETA_Speech_Say" not in say:
        failures.append("a jump on the way is never said")
    if not [f for f in failures if "way" in f or "jump" in f.lower()]:
        print("[route] the way stops at a jump or a ladder, says the jump, "
              "and waits out a climb")

    # --- the key ------------------------------------------------------
    command = "accessibilityMarkerObjective"
    if not re.search(r'\{\s*"%s",\s*CG_AccessibilityMarkerObjective_f\s*\}' % command, console):
        failures.append("%s is not a console command" % command)
    ui = read(os.path.join(root, UI_MAIN))
    if not re.search(r'\{\s*K_KP_PLUS,\s*"%s"' % command, ui):
        failures.append("keypad plus is not given %s" % command)
    if '"%s"' % command.lower() not in read(os.path.join(root, UI_SHARED)):
        failures.append("the game's binding list does not know %s, so the "
                        "Key Binds row could not change it" % command)
    if '"%s"' % command not in read(KEYS_MENU):
        failures.append("the Key Binds page has no row for %s" % command)
    if not re.search(r"^bind KP_PLUS\s+%s\s*$" % command, read(AUTOEXEC), re.M):
        failures.append("autoexec.cfg does not bind keypad plus to %s" % command)
    objective = function_body(commandmap, "CG_AccessibilityMarkerObjective") or ""
    if "CG_AccessibilityObjective(" not in objective or "ETA_NavigationSystem_AnnounceMarkerHeight" not in objective:
        failures.append("the marker is not put on the objective, or its "
                        "height is not said")
    # The tester's ask: not only the current objective, but a choice of
    # them - a press again soon after moves on round the list.
    cycle_ms = re.search(r"#define\s+ETA_MARKER_CYCLE_MS\s+(\d+)", commandmap)
    if not cycle_ms or "CG_AccessibilityObjectiveList(" not in objective:
        failures.append("Marker On Objective only ever takes the current "
                        "objective - there is no way to choose another")
    elif not re.search(r"cg\.time - eta_objectiveCycle\.lastPress < ETA_MARKER_CYCLE_MS", objective) \
            or "(eta_objectiveCycle.index + 1) % eta_objectiveCycle.count" not in objective:
        failures.append("a second press does not move on to the next "
                        "objective, round the list")
    elif '"Marker on %s, %d of %d"' not in objective:
        failures.append("the objective chosen is not said with its place in "
                        "the list")
    else:
        print("[route] pressing again within %ss moves the marker to the "
              "next objective, said as \"2 of 7\"" % (int(cycle_ms.group(1)) // 1000))
    if not [f for f in failures if command in f or "marker" in f]:
        print("[route] keypad plus puts the marker on the objective, from "
              "every place a key is set")

    if failures:
        for failure in failures:
            print("[route] FAIL %s" % failure)
        sys.exit(1)

    print("route_up_test: the way up goes where the game lets a player go")


if __name__ == "__main__":
    main()

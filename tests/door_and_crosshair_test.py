#!/usr/bin/env python3
"""Check the door beacon names doors, and the crosshair cue stays honest.

Why this exists
---------------
Two features, two very different ways of being wrong.

The door beacon has to be a door. ET_MOVER covers lifts, tank barriers
and movable bridges as well as doors, so an entity-type test alone would
put a creak on things that do not open, and a player would walk to a wall
on the strength of it. The engine already knows which is which: the
server stamps its cursor-hint type onto the entity and replicates it, so
HINT_DOOR and its locked and rotating variants are the classification to
use, and this fails if the narration stops using them.

That field is overloaded, which is the trap. `dmgFlags` carries damage
information on players and a sound range on speakers, so reading it
without first checking the entity type invents doors out of whatever
happens to be standing nearby - on some maps, intermittently, with
nothing in the code to suggest it.

The crosshair cue has a different failure, and a more serious one. The
stock HUD draws a *teammate's* name under the crosshair and deliberately
says nothing for an enemy: a sighted player knows an enemy is there
because they can see them. So the enemy cue restores what sight gives,
which is fair - but only as far as sight goes. A covert operative in an
enemy uniform looks like a teammate, and the game is deceiving the
sighted player on purpose. If this cue saw through that, it would not be
parity any more, it would be an advantage no player has ever had.

So the rule, and what this pins: the cue says what a sighted player would
believe, including when the game is lying to them. The one exception is
the Field Ops skill that reveals disguises, where the game itself tells
the truth - the same exception the stock HUD makes, read out of the same
place.

What it does NOT check
----------------------
Whether the creak is audible at the right distance, or whether the tick
is fast enough to catch a sweep. Those need ears.

Usage
-----
    ./door_and_crosshair_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
PUBLIC = os.path.join("src", "game", "bg_public.h")
MOVER = os.path.join("src", "game", "g_mover.c")

# Every hint the engine stamps on something that opens. Read back out of
# the engine below rather than trusted from here.
DOOR_HINTS = ("HINT_DOOR", "HINT_DOOR_ROTATING",
              "HINT_DOOR_LOCKED", "HINT_DOOR_ROTATING_LOCKED")


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


def body_of(text, name, where):
    start = text.find(name)
    if start < 0:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone, and passing without it would mean nothing"
                 % (name, where))
    end = text.find("\n}", start)
    if end < 0:
        sys.exit("could not find the end of %s in %s" % (name, where))
    return text[start:end]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    args = parser.parse_args()

    draw = strip_comments(read(args.root, DRAW, "is the patch series applied?"))
    public = strip_comments(read(args.root, PUBLIC,
                                 "is this an engine checkout?"))
    mover = strip_comments(read(args.root, MOVER,
                                "is this an engine checkout?"))

    failures = []

    # --- the engine still classifies doors the way we read them --------
    for hint in ("HINT_DOOR", "HINT_DOOR_ROTATING"):
        if hint not in public:
            sys.exit("%s is gone from the engine's hint list - this test "
                     "reads the mod against it and can no longer tell "
                     "whether the beacon names doors" % hint)

    if not re.search(r'dmgFlags\s*=\s*HINT_DOOR', mover):
        sys.exit("the engine no longer stamps HINT_DOOR onto the door "
                 "entity, so the client has nothing to identify a door "
                 "with and the beacon is running on something else")

    # --- the beacon must use those hints, not the entity type alone ----
    beacon = body_of(draw, "ETA_BeaconDoors", DRAW)
    door_test = body_of(draw, "ETA_HintIsDoor", DRAW)

    named = [hint for hint in DOOR_HINTS if hint in door_test]
    if len(named) < 2:
        failures.append(
            "the door test names only %s - ET_MOVER also covers lifts, "
            "tank barriers and movable bridges, so without the engine's "
            "own hint the beacon creaks at things that do not open"
            % (", ".join(named) or "nothing"))

    if "ETA_HintIsDoor" not in beacon:
        failures.append(
            "ETA_BeaconDoors does not test whether the entity is a door at "
            "all")

    # The overload guard: entity type checked before dmgFlags is trusted.
    if "ET_MOVER" not in beacon:
        failures.append(
            "ETA_BeaconDoors does not check the entity is a mover before "
            "reading dmgFlags - that field carries damage information on "
            "players and a sound range on speakers, so it would invent "
            "doors out of whatever is standing nearby")

    if "HINT_DOOR_LOCKED" not in strip_comments(read(args.root, DRAW, "")):
        failures.append(
            "nothing distinguishes a locked door - hearing that a door "
            "will not open is the half of this that saves a walk")

    # A beacon on every door on the map would be a wall of creaking.
    if not re.search(r'ETA_DOOR_CUE_RANGE', beacon):
        failures.append(
            "ETA_BeaconDoors has no range limit, so every door on the map "
            "would sound at once")

    # --- the crosshair cue -------------------------------------------
    crosshair = body_of(draw, "ETA_NarrateCrosshair", DRAW)

    if "PW_OPS_DISGUISED" not in crosshair:
        failures.append(
            "the crosshair cue does not check for a disguise - a covert "
            "operative in an enemy uniform looks like a teammate to a "
            "sighted player, and a cue that saw through that would be an "
            "advantage no player has ever had")

    if "SK_FIELDOPS_ENEMY_RECOGNITION" not in crosshair:
        failures.append(
            "the disguise exception is missing - the stock HUD does reveal "
            "a disguise to a Field Ops with that skill, so withholding it "
            "here makes the cue worse than what a sighted player gets")

    # It must ride the engine's own crosshair result, which is traced and
    # therefore cannot see through a wall.
    if "crosshairEntNum" not in crosshair:
        failures.append(
            "the crosshair cue does not use the engine's own crosshair "
            "entity - anything else would be a trace of our own, and the "
            "one thing it must never do is report through a wall")

    if "MAX_CLIENTS" not in crosshair:
        failures.append(
            "the crosshair cue does not restrict itself to players, so it "
            "would fire on doors, crates and dynamite")

    # Friend and foe must be different sounds, or the cue is worse than
    # nothing: it would say "someone" at the moment you decide to shoot.
    if not ("ETA_LOOP_CROSSHAIR_ENEMY" in crosshair
            and "ETA_LOOP_CROSSHAIR_TEAMMATE" in crosshair):
        failures.append(
            "the crosshair cue does not use two different sounds for a "
            "teammate and an enemy")

    # --- team doors, which the server leaves unstamped -----------------
    #
    # The server stamps the door hint only when a door has no allowteams
    # list. A tester found the creak silent, and that was why: on an
    # objective map most doors are team doors. So ET: Legacy's beacon also
    # reads the map's own entity list for func_door and func_door_rotating,
    # and whether this player's team may open each - which has to be the
    # server's own rule, or the "locked" creak lies.
    if args.engine == "etlegacy":
        spawn_path = os.path.join("src", "cgame", "cg_spawn.c")
        spawn = strip_comments(read(args.root, spawn_path,
                                    "is the patch series applied?"))
        g_spawn = strip_comments(read(args.root, os.path.join(
            "src", "game", "g_spawn.c"), "is this an engine checkout?"))
        g_utils = strip_comments(read(args.root, os.path.join(
            "src", "game", "g_utils.c"), "is this an engine checkout?"))

        if re.search(r'if\s*\(\s*!\s*ent->allowteams\s*\)\s*\{?\s*'
                     r'ent->s\.dmgFlags\s*=\s*HINT_DOOR', mover):
            print("[doors] the server still stamps only doors with no team "
                  "list - team doors need the map's own list")

        for classname in ("func_door", "func_door_rotating"):
            if not re.search(r'\{\s*"%s"\s*,\s*SP_ETA_door' % classname, spawn):
                failures.append(
                    "the cgame does not note %s from the map's entity list, "
                    "so team doors of that kind are silent" % classname)

        if "CG_AccessibilityDoorModel" not in beacon:
            failures.append(
                "the beacon never asks the map's door list, so every team "
                "door - most doors on an objective map - is silent")

        server_words = re.findall(r'strstr\s*\(\s*str\s*,\s*"([a-z]+)"\s*\)',
                                  g_spawn)
        door_parse = body_of(spawn, "SP_ETA_door", spawn_path)
        our_words = re.findall(r'strstr\s*\(\s*lower\s*,\s*"([a-z]+)"\s*\)',
                               door_parse)
        if not server_words:
            sys.exit("could not read the server's allowteams words out of "
                     "g_spawn.c - this test is out of date with the engine")
        if sorted(server_words) != sorted(our_words):
            failures.append(
                "the door list reads allowteams as %s, the server as %s - a "
                "door would creak locked for a team that can open it, or "
                "open for one that cannot" % (our_words, server_words))

        opens = body_of(spawn, "CG_AccessibilityDoorModel", spawn_path)
        rule = body_of(g_utils, "G_AllowTeamsAllowed",
                       os.path.join("src", "game", "g_utils.c"))
        for piece in ("PW_OPS_DISGUISED", "TEAM_SPECTATOR"):
            if piece in rule and piece not in opens:
                failures.append(
                    "the server's door rule considers %s and the mod's does "
                    "not, so the locked creak disagrees with the door" % piece)

        if not any("door list" in f or "team door" in f or "locked creak" in f
                   for f in failures):
            print("[doors] team doors come from the map's list, read and "
                  "judged by the server's own rules")

    if failures:
        print("door_and_crosshair_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("door_and_crosshair_test: %s - the beacon is restricted to the "
          "engine's own door hints (%s) behind an entity-type guard, and "
          "the crosshair cue respects a disguise and its one exception"
          % (args.engine, ", ".join(named)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

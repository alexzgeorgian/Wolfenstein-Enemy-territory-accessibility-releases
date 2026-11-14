#!/usr/bin/env python3
"""Check the map survey reports the command map, and nothing else.

Why this exists
---------------
This is the feature with the largest gap between what it is and what it
could quietly become. Reading out the command map is parity: the server
decides what to send a player's team - their teammates, the enemies
their team has actually spotted, the mines they have detected - and a
sighted player takes all of it in with one glance at the same screen.
Saying it out loud gives a blind player the same glance.

Reading out anything *else* is cheating, and it would not look like
cheating in the diff. cg_entities is right there, in the same file,
holding every entity in the snapshot - including enemies nobody spotted.
One loop over the wrong array turns an accessibility feature into a
wallhack, compiles clean, and is invisible to every other check here.

So the rule this pins: the survey's knowledge of who is where comes from
mapEntities, the parsed command map list, and the only use of
cg_entities is to locate more precisely somebody who is *already* on
that list. That is not extra information - it is the same player, placed
properly, because the server rounds map positions to 128-unit steps
before sending them.

The disguise rule is the same one the crosshair cue follows and is here
for the same reason. A covert operative in an enemy uniform shows on the
command map as a teammate, on purpose, and the engine has its own check
for when that illusion holds. Seeing through it would be an advantage no
sighted player has ever had.

It also pins the two things that make the survey safe to live on the
arrow keys: every command does nothing unless the command map is
actually up, and the binds never take a key that is already spoken for.
Together those are why a feature on the arrow keys costs a stock install
nothing and costs a left-handed layout nothing either.

What it does NOT check
----------------------
Whether the squares are a useful size, whether the reading order for
"next thing" is predictable, or whether the sentence is short enough to
listen to. Those need ears.

Usage
-----
    ./map_survey_test.py <engine-root>

ET: Legacy only - the 2010 tree has no command map entity list.
Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
UI = os.path.join("src", "ui", "ui_main.c")
TEAMMAP = os.path.join("src", "game", "g_teammapdata.c")
SPAWN = os.path.join("src", "cgame", "cg_spawn.c")

# The survey's own commands, and the keys they are meant to reach.
COMMANDS = (
    "accessibilityMapNorth",
    "accessibilityMapSouth",
    "accessibilityMapEast",
    "accessibilityMapWest",
    "accessibilityMapUp",
    "accessibilityMapDown",
    "accessibilityMapHere",
    "accessibilityMapNext",
)

# Anything that moves the player or the view. No survey key may be
# taken from one of these, whatever else the allowlist in
# keyboard_reachable_test.py permits.
MOVEMENT = re.compile(r'[+-](forward|back|moveleft|moveright|moveup|movedown|'
                      r'left|right|lookup|lookdown|strafe|speed|attack|'
                      r'activate|prone|mlook)')

# Everything that walks the cursor has to refuse while the map is down.
GATED = (
    "CG_AccessibilityMapStep",
    "CG_AccessibilityMapLayer",
    "CG_AccessibilityMapHome",
    "CG_AccessibilityMapNext",
)


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
        sys.exit("could not find %s in %s - the survey this test guards is "
                 "gone, and passing without it would mean nothing"
                 % (signature.split("(")[0], where))
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
    args = parser.parse_args()

    commandmap = strip_comments(read(args.root, COMMANDMAP,
                                     "is the patch series applied?"))
    console = strip_comments(read(args.root, CONSOLE,
                                  "is the patch series applied?"))
    ui = strip_comments(read(args.root, UI, "is the patch series applied?"))
    teammap = strip_comments(read(args.root, TEAMMAP,
                                  "is this an engine checkout?"))

    failures = []

    contents = body_of(commandmap,
                       "static qboolean ETA_MapCellContents(", COMMANDMAP)
    origin = body_of(commandmap,
                     "static qboolean ETA_MapEntityOrigin(", COMMANDMAP)

    # --- the source of who-is-where must be the command map ----------
    if "mapEntities[" not in contents:
        failures.append(
            "ETA_MapCellContents does not walk mapEntities, so whatever it "
            "is reporting is not the command map. That list is the whole "
            "fairness argument: it is what the server chose to send this "
            "player's team")

    if "mapEntityCount" not in contents:
        failures.append(
            "ETA_MapCellContents does not bound itself by mapEntityCount")

    # The wallhack, which would not look like one in the diff.
    if "cg_entities" in contents:
        failures.append(
            "ETA_MapCellContents reads cg_entities directly. That array "
            "holds every entity in the snapshot, including enemies nobody "
            "spotted - reporting from it would turn this into a wallhack "
            "that compiles clean. Positions are refined in "
            "ETA_MapEntityOrigin, for entries already on the command map, "
            "and nowhere else")

    if "cg_entities" not in origin:
        failures.append(
            "ETA_MapEntityOrigin no longer refines a player's position from "
            "the snapshot. The server rounds map positions to 128-unit "
            "steps, so without this every spoken distance is coarse even "
            "for somebody standing in front of you")

    # ... and the refinement must be restricted to real clients.
    if "MAX_CLIENTS" not in origin:
        failures.append(
            "ETA_MapEntityOrigin does not bound its client lookup by "
            "MAX_CLIENTS before indexing cg_entities")

    # --- flags and doors: fixtures, from the map's own entity list ----
    #
    # The two things the survey says that the command map leaves out.
    # Both are fixtures a sighted player sees by looking, and both must
    # come from the list the map itself declares - never from the
    # snapshot, where they would come with everything else in it.
    for call, what in (("CG_AccessibilityFlag(", "the flags"),
                       ("CG_AccessibilityDoorAt(", "the doors")):
        if call not in contents:
            failures.append(
                "the survey does not report %s, which the command map leaves "
                "out and a blind player has no other way to find" % what)

    spawn = strip_comments(read(args.root, SPAWN, "is the patch series applied?"))
    for name in ("int CG_AccessibilityFlagCount(",
                 "qboolean CG_AccessibilityFlag(",
                 "qboolean CG_AccessibilityDoorAt("):
        body = body_of(spawn, name, SPAWN)
        if "cg_entities" in body or "cg.snap" in body:
            failures.append(
                "%s reads the snapshot. Flags and doors are to come from the "
                "map's own entity list, read once when the map loads" % name)

    # --- the disguise illusion must hold ------------------------------
    if "CG_DisguiseMapCheck" not in contents:
        failures.append(
            "the survey does not use the engine's own disguise check. A "
            "covert operative in an enemy uniform shows on the command map "
            "as a teammate on purpose; counting them as an enemy would be "
            "an advantage no sighted player has ever had")

    # That check has to still exist and still be about disguises.
    if "PW_OPS_DISGUISED" not in commandmap:
        failures.append(
            "CG_DisguiseMapCheck no longer tests PW_OPS_DISGUISED, so what "
            "the survey is asking it is no longer the disguise question")

    # --- the player's own map filters are honoured --------------------
    for name, what in (("CC_FILTER_LANDMINES", "landmines"),
                       ("CC_FILTER_SPAWNS", "spawn points")):
        if name not in contents:
            failures.append(
                "the survey ignores %s, so it would announce %s a player "
                "has deliberately filtered off their own map" % (name, what))

    # --- floors are kept apart ----------------------------------------
    if "CG_CurLayerForZ" not in commandmap:
        failures.append(
            "nothing separates the map's layers, so on a multi-storey map "
            "a roof and a cellar are reported as the same square")

    # --- the server still decides what this team can see --------------
    if "G_SendMapEntityInfo" not in teammap:
        failures.append(
            "G_SendMapEntityInfo is gone from %s - the whole parity "
            "argument rests on the server choosing what each team is sent, "
            "and this test can no longer see that it does" % TEAMMAP)

    # --- nothing happens while the map is down ------------------------
    for name in GATED:
        gate = body_of(commandmap, "void %s(" % name, COMMANDMAP)

        if "cgs.autoMapExpanded" not in gate:
            failures.append(
                "%s does not require the command map to be up. That gate is "
                "what lets the survey share the keypad with selectbuddy "
                "without taking it away from the game - with it gone, a "
                "keypad key does two things at once" % name)

        if "eta_mapCallouts" not in gate:
            failures.append("%s cannot be turned off" % name)

    # --- the commands exist and are reachable -------------------------
    for command in COMMANDS:
        if '"%s"' % command not in console:
            failures.append(
                "%s is not in the command table, so the bind for it would "
                "resolve to nothing and do so silently" % command)

        if '"%s"' % command not in ui:
            failures.append(
                "%s is never bound to a key, so it exists and is "
                "unreachable" % command)

    # --- and the binds do not steal --------------------------------
    # Not anchored on "static": the installer lost that when the controls
    # reset needed to call it back through a console command, and a test
    # that pins a function's linkage fails on a change that cannot
    # possibly affect what it is checking.
    binds = body_of(ui, "void UI_AccessibilityInstallBinds(", UI)

    # Every command the survey has must be on a key, and this is what
    # says so - rather than a list of keys written down here, which
    # would have to be edited every time the layout moves and would
    # have nothing to say about a command that quietly lost its key.
    for command in COMMANDS:
        row = re.search(r'\{\s*(K_[A-Z0-9_]+)\s*,\s*"%s"\s*,\s*([^,}]+)'
                        % re.escape(command), binds)
        if not row:
            failures.append(
                "%s is never claimed for any key by the installer, so it "
                "exists and nobody can reach it" % command)
            continue

        key, replaces = row.group(1), row.group(2).strip()

        # The third field is `replaces`; a fourth carries the generation
        # that decides whether a player has been offered this key yet.
        # Reading the row's last field instead would pass on a bind that
        # declares it replaces movement, which is the thing being
        # guarded against.
        #
        # The survey moved to the keypad when the arrow keys were given
        # to turning and looking, and the keypad is not free - it holds
        # selectbuddy. So "replaces nothing" is no longer the rule.
        # What is still the rule, and is the whole point, is that no
        # survey key is taken from movement or from aiming: a key that
        # walks you while you are reading the map is worse than a key
        # you have to bind by hand.
        if replaces != "NULL" and MOVEMENT.search(replaces):
            failures.append(
                "the %s bind for %s declares it replaces %s. That is "
                "movement or aiming - the arrow keys are movement in ET's "
                "left-handed layout - and a survey key that also walks you "
                "is worse than one you have to bind by hand"
                % (key, command, replaces))

    # The installer's own rule has to still be there, or the table above
    # is checked against nothing.
    if "trap_Key_GetBindingBuf" not in binds:
        failures.append(
            "the bind installer no longer looks at what a key is already "
            "bound to before taking it")

    if failures:
        print("map_survey_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("map_survey_test: %s - the survey reports the command map, plus "
          "the map's own flags and doors, respects the disguise and the player's "
          "own filters, and its %d command(s) do nothing while the map is "
          "down" % (args.engine, len(COMMANDS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

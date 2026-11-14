#!/usr/bin/env python3
"""Check the construction, demolition and flag sounds mark what they claim to.

Three sounds, placed in the world: hammer taps on a site the player's
team can build, a fuse hiss on an enemy objective they can blow up, and
a bell on a flag they can capture. Each
is only as honest as the entity it is hung on, and both get that from
the game's own objective markers rather than from the construction
itself. So this checks the mod's side and the engine's side together:

The mod's side, in ETA_BeaconSites:

- the build sound goes on a construction indicator of the player's own
  team, or of team 3 (either team builds it) - never the enemy's, which
  would send an engineer to build for the other side;
- the demolition sound goes on an explosive indicator of the other
  team - never the player's own, which would send them to blow up what
  they are meant to defend;
- the bell rings on a flagpole only while the player's team does not
  hold it and the map lets their side raise it, and who holds it is read
  with the server's own animation numbers;
- spectators hear none of it, it stops while dead or in limbo, and
  eta_siteCues turns it off;
- it is heard further than a door but not across the map;
- it is called every frame, and its sounds are in the loop table.

The engine's side, which the mod's rules lean on:

- the construction indicator is removed once the construction is built
  (so a finished site falls silent);
- a construction that can be destroyed gets an explosive indicator when
  it is finished, carrying the builder's team (so the enemy hears it as
  a target, and only if it really can be destroyed);
- the explosive indicator is removed with the objective (so a destroyed
  target falls silent).

An upstream change to any of those would leave the mod's code looking
right and the sounds lying, which is what this exists to catch.

    ./site_cues_test.py <engine-root>
"""

import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
SPAWN = os.path.join("src", "cgame", "cg_spawn.c")
TEAM = os.path.join("src", "game", "g_team.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")
TRIGGER = os.path.join("src", "game", "g_trigger.c")
WEAPON = os.path.join("src", "game", "g_weapon.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?" % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def function_body(text, name):
    match = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return None
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def define(text, name):
    match = re.search(r"#define\s+%s\s+([0-9.]+)f?" % name, text)
    return float(match.group(1)) if match else None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    root = os.path.abspath(sys.argv[1])
    failures = []

    draw_raw = read(root, DRAW)
    draw = strip_comments(draw_raw)
    body = function_body(draw, "ETA_BeaconSites")

    if body is None:
        sys.exit("no ETA_BeaconSites in %s - the sounds are not there at all" % DRAW)

    flat = re.sub(r"\s+", " ", body)

    # --- who hears what -------------------------------------------------
    build = re.search(r"if \(es->eType == ET_CONSTRUCTIBLE_INDICATOR && \(([^{]*?)\)\s*\)\s*\{\s*which = ETA_LOOP_BUILD_SITE", flat)
    if not build:
        failures.append("the build sound is not tied to a construction "
                        "indicator - it could mark anything")
    else:
        rule = build.group(1)
        if "es->teamNum == team" not in rule or "es->teamNum == 3" not in rule:
            failures.append("the build sound is not limited to the player's "
                            "own team's sites (and team 3, either side's): %r"
                            % rule)
        if "!=" in rule:
            failures.append("the build sound is put on a site of the other "
                            "team - an engineer would build for the enemy")
        else:
            print("[sites] build sound: own team's construction indicators, "
                  "and those either team builds")

    demolish = re.search(r"else if \(es->eType == ET_EXPLOSIVE_INDICATOR && ([^{]*?)\)\s*\{\s*which = ETA_LOOP_DEMOLITION_TARGET", flat)
    if not demolish:
        failures.append("the demolition sound is not tied to an explosive "
                        "indicator")
    else:
        rule = demolish.group(1)
        if "es->teamNum != team" not in rule:
            failures.append("the demolition sound is not limited to the "
                            "other team's objectives - a player would be "
                            "sent to blow up what they defend: %r" % rule)
        elif "TEAM_AXIS" not in rule or "TEAM_ALLIES" not in rule:
            failures.append("the demolition sound does not insist on an "
                            "objective owned by a real side")
        else:
            print("[sites] demolition sound: the other side's explosive "
                  "indicators only")

    # --- flags ---------------------------------------------------------
    flag = re.search(r"else if \(es->eType == ET_TRAP && es->teamNum == 1\)\s*\{(.*?)which = ETA_LOOP_FLAG", flat)
    if not flag:
        failures.append("the flag bell is not tied to a flagpole")
    elif not re.search(r"!takeable \|\| holder == team\s*\)\s*\{\s*continue", flag.group(1)):
        failures.append("the flag bell rings on a flag the player's team "
                        "already holds, or one the map keeps from their side")
    else:
        print("[sites] flag bell: only a flag the player's side can take and "
              "does not hold")

    if not re.search(r"ETA_WatchFlags\(\);", draw):
        failures.append("nothing keeps who holds each flag up to date, so the "
                        "map survey would say it wrongly")

    spawn = strip_comments(read(root, SPAWN))
    team_c = strip_comments(read(root, TEAM))
    if not re.search(r'\{\s*"team_WOLF_checkpoint",\s*SP_ETA_flag\s*\}', spawn):
        failures.append("the flags are not read from the map's entity list")

    anim = dict((name, int(value)) for name, value in
                re.findall(r"#define\s+WCP_ANIM_(\w+)\s+(\d+)", team_c))
    holder_fn = function_body(spawn, "CG_AccessibilityFlagHolderFromFrame")
    if not anim or holder_fn is None:
        failures.append("could not read the flag animations or the mod's "
                        "reading of them")
    else:
        cases, mapping = [], {}
        for line in holder_fn.splitlines():
            line = line.strip()
            m = re.match(r"case (\d+):", line)
            if m:
                cases.append(int(m.group(1)))
            m = re.match(r"return (TEAM_\w+);", line)
            if m and cases:
                for c in cases:
                    mapping[c] = m.group(1)
                cases = []
        expect = {
            "TEAM_AXIS": ("RAISE_AXIS", "AXIS_RAISED", "AMERICAN_TO_AXIS"),
            "TEAM_ALLIES": ("RAISE_AMERICAN", "AMERICAN_RAISED", "AXIS_TO_AMERICAN"),
        }
        wrong = []
        for side, names in expect.items():
            for name in names:
                if name not in anim or mapping.get(anim[name]) != side:
                    wrong.append(name)
        for name in ("NOFLAG", "AXIS_FALLING", "AMERICAN_FALLING"):
            if name in anim and anim[name] in mapping:
                wrong.append(name)
        if wrong:
            failures.append("the mod reads these flag animations as the wrong "
                            "holder: %s" % ", ".join(sorted(wrong)))
        else:
            print("[sites] flag holder read with the server's own WCP_ANIM "
                  "numbers")

    # AXIS_ONLY and ALLIED_ONLY are the server's spawnflags for a flag one
    # side alone may raise.
    only = dict((name, int(value)) for name, value in
                re.findall(r"#define\s+(AXIS_ONLY|ALLIED_ONLY)\s+(\d+)", team_c))
    takeable = function_body(spawn, "CG_AccessibilityFlag")
    if len(only) != 2 or takeable is None:
        failures.append("could not read which side may raise a flag")
    else:
        flat_take = re.sub(r"\s+", " ", takeable)
        if ("team == TEAM_AXIS && !(flags & %d)" % only["ALLIED_ONLY"] not in flat_take
                or "team == TEAM_ALLIES && !(flags & %d)" % only["AXIS_ONLY"] not in flat_take):
            failures.append("the mod's rule for who may raise a flag is not "
                            "the server's AXIS_ONLY / ALLIED_ONLY")
        else:
            print("[sites] a flag kept to one side is offered only to that side")

    if not re.search(r"team != TEAM_AXIS && team != TEAM_ALLIES\s*\)\s*\{\s*return", flat):
        failures.append("a spectator would hear one team's sites")
    if "pm_type != PM_NORMAL" not in flat or "!eta_siteCues.integer" not in flat:
        failures.append("the sounds do not stop when dead or in limbo, or "
                        "eta_siteCues does not turn them off")
    if "ETA_SITE_CUE_RANGE" not in flat:
        failures.append("the sounds have no range - every objective on the "
                        "map would be heard at once")

    site_range = define(draw_raw, "ETA_SITE_CUE_RANGE")
    door_range = define(draw_raw, "ETA_DOOR_CUE_RANGE")
    if site_range is None or door_range is None:
        failures.append("could not read the site and door ranges")
    elif not (door_range < site_range <= 1500):
        failures.append("the site range (%g) should be further than a door "
                        "(%g) but within about forty metres" % (site_range, door_range))
    else:
        print("[sites] heard within %g units, about %d metres (doors %g)"
              % (site_range, round(site_range / 40), door_range))

    if not re.search(r"ETA_BeaconSites\(\);", draw):
        failures.append("ETA_BeaconSites is never called, so neither sound "
                        "plays")

    # --- the sounds exist and are switchable -----------------------------
    local = strip_comments(read(root, LOCAL))
    main_c = strip_comments(read(root, MAIN))
    for enum in ("ETA_LOOP_BUILD_SITE", "ETA_LOOP_DEMOLITION_TARGET", "ETA_LOOP_FLAG"):
        if enum not in local:
            failures.append("%s is not one of the mod's loop sounds" % enum)

    # The loop table is indexed by the enum, so the two lists must be in
    # the same order.
    enum_body = re.search(r"typedef enum\s*\{([^}]*)\}\s*eta_loopSoundType_t", local)
    table = re.search(r"eta_loopSounds\[\]\s*=\s*\{(.*?)\};", main_c, re.S)
    if enum_body and table:
        order = [e.strip().split("=")[0].strip() for e in enum_body.group(1).split(",") if e.strip()]
        paths = re.findall(r'"sound/accessibility/([a-z_]+)\.wav"', table.group(1))
        expect = {"ETA_LOOP_BUILD_SITE": "build_site",
                  "ETA_LOOP_DEMOLITION_TARGET": "demolition_target",
                  "ETA_LOOP_FLAG": "flag_capture"}
        for enum, wav in expect.items():
            if enum in order and (order.index(enum) >= len(paths)
                                  or paths[order.index(enum)] != wav):
                failures.append("%s does not index %s.wav in the loop table - "
                                "the wrong sound would play" % (enum, wav))
        if all(e in order for e in expect):
            print("[sites] the loop table plays build_site.wav, "
                  "demolition_target.wav and flag_capture.wav for them")
    else:
        failures.append("could not read the loop sound enum and table")

    if not re.search(r'&eta_siteCues,\s*"eta_siteCues",\s*"1"', main_c):
        failures.append("eta_siteCues is not registered on by default")

    # --- the engine keeps its side of it ---------------------------------
    trigger = strip_comments(read(root, TRIGGER))
    weapon = strip_comments(read(root, WEAPON))

    think = function_body(trigger, "constructible_indicator_think")
    if not think or not re.search(r"angles2\[1\]\s*!=\s*0", think) or "G_FreeEntity(ent)" not in think:
        failures.append("the engine no longer removes a construction "
                        "indicator once it is built - a finished site would "
                        "keep tapping")
    else:
        print("[sites] engine: a built site's indicator is removed")

    if not re.search(r'e->classname\s*=\s*"explosive_indicator";.*?e->s\.eType\s*=\s*ET_EXPLOSIVE_INDICATOR;'
                     r'.*?AXIS_CONSTRUCTIBLE\)\s*\{\s*e->s\.teamNum\s*=\s*TEAM_AXIS', weapon, re.S):
        failures.append("the engine no longer gives a finished, destructible "
                        "construction an explosive indicator with its "
                        "builder's team - built enemy constructions would "
                        "not be heard as targets")
    else:
        print("[sites] engine: a finished destructible construction becomes "
              "the other side's target")

    explode = function_body(trigger, "explosive_indicator_think")
    if not explode or "!parent->inuse" not in explode or "G_FreeEntity(ent)" not in explode:
        failures.append("the engine no longer removes an explosive indicator "
                        "with its objective - a destroyed target would keep "
                        "hissing")
    else:
        print("[sites] engine: a destroyed target's indicator is removed")

    if failures:
        for failure in failures:
            print("[sites] FAIL %s" % failure)
        sys.exit(1)

    print("site_cues_test: construction sites, demolition targets and flags "
          "are marked for the right side, and fall silent when done")


if __name__ == "__main__":
    main()

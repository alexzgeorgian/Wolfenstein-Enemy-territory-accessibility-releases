#!/usr/bin/env python3
"""Check a covert op can find an enemy's uniform with F, and take it.

The tester, playing a covert op, killed an enemy and could not take the
uniform: it was not on the F list, even with the bracket keys. Each part
of the fix rests on something the game itself does, which this checks
against the game's own code:

- a uniform is taken only from a body (Do_UniformStealing wants
  ET_CORPSE), and the body is left only once the enemy gives up waiting
  for a medic - shot again while down, limbo leaves none. So an enemy
  lying wounded is listed for a covert op as that, with "don't shoot",
  and never pressed at;
- the game takes the uniform only for use held on the body a while
  (BODY_VALUE counted up a step at a time), longer than F's tap; so F
  holds use for the player until it is taken, for longer than the game
  asks;
- taking it marks the body (time2 = 1), and that is what tells the
  player it is on;
- the server keeps a body's box round its belt (tag_ubelt), so that is
  where F aims;
- with the crosshair already on the body, F takes the uniform too.

    ./uniform_test.py <engine-root>
"""

import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")
G_CMDS = os.path.join("src", "game", "g_cmds.c")
G_CLIENT = os.path.join("src", "game", "g_client.c")
G_ACTIVE = os.path.join("src", "game", "g_active.c")


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


def case_body(text, label):
    start = text.find("case %s:" % label)
    if start < 0:
        return ""
    end = re.search(r"\n\t\tcase [A-Z_]+:|\n\t\tdefault:", text[start + 1:])
    return text[start:start + 1 + end.start()] if end else text[start:]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    console = read(os.path.join(root, CONSOLE))
    local = read(os.path.join(root, LOCAL))
    steal = strip_comments(function_body(read(os.path.join(root, G_CMDS)), "Do_UniformStealing"))
    client = read(os.path.join(root, G_CLIENT))
    active = strip_comments(read(os.path.join(root, G_ACTIVE)))
    failures = []

    if "ETA_UniformFrame" not in console:
        sys.exit("no uniform taking in %s - the feature this test measures is gone" % CONSOLE)

    # --- the game's own rules -----------------------------------------------
    value = re.search(r"BODY_VALUE\(traceEnt\)\s*>=\s*(\d+)", steal)
    step = re.search(r"BODY_VALUE\(traceEnt\)\s*\+=\s*(\d+)", steal)
    gap = re.search(r"level\.time\s*-\s*BODY_LAST_ACTIVATE\(traceEnt\)\s*>=\s*(\d+)", steal)
    hold = re.search(r"#define\s+ETA_UNIFORM_HOLD_MS\s+(\d+)", console)
    if "traceEnt->s.eType == ET_CORPSE" not in steal or not (value and step and gap):
        failures.append("the game's uniform taking is not what this fix was built on")
    elif not hold:
        failures.append("F has no hold for taking a uniform")
    else:
        needed = int(value.group(1)) // int(step.group(1)) * int(gap.group(1))
        if int(hold.group(1)) < needed + 1000:
            failures.append("F holds use %s ms, and the game asks %d ms and more" % (hold.group(1), needed))
        else:
            print("[uniform] the game takes a uniform for use held %d ms; F holds it up to %s ms"
                  % (needed, hold.group(1)))

    limbo = function_body(client, "limbo")
    if not (re.search(r"if \(makeCorpse\)\s*\{[^}]*CopyToBodyQue\(ent\)", limbo)
            and "limbo(ent, (client->ps.stats[STAT_HEALTH] > GIB_HEALTH));" in active):
        failures.append("the game no longer leaves a body only for an enemy not shot to pieces")
    down = case_body(function_body(draw, "CG_AccessibilityUseTargets"), "ET_PLAYER")
    if not ("if (!covert)" in down and "don't shoot" in down and "target.locked = qtrue;" in down):
        failures.append("an enemy lying wounded is not listed to a covert op, warned not to shoot, and left unpressed")
    else:
        print("[uniform] an enemy down is listed to a covert op: a body comes once they give up, don't shoot")

    if "traceEnt->s.time2 = 1;" not in steal:
        failures.append("the game no longer marks a body whose uniform is taken")
    frame = function_body(console, "ETA_UniformFrame")
    if "currentState.time2 == 1" not in frame or "Uniform taken" not in frame:
        failures.append("the uniform being taken is not told")
    elif "No uniform taken" not in frame or "eta_use.bodyUntil" not in frame:
        failures.append("a uniform not taken in time is not told")
    else:
        print("[uniform] taken, or not in time, is said")

    body = case_body(function_body(draw, "CG_AccessibilityUseTargets"), "ET_CORPSE")
    if '"tag_ubelt"' not in function_body(client, "CopyToBodyQue"):
        failures.append("the game no longer puts a body's box round its belt")
    elif '"tag_ubelt"' not in body or "target.uniform   = qtrue;" not in body:
        failures.append("F does not aim at the belt of an enemy body, or mark it as a uniform")
    else:
        print("[uniform] F aims at the body's belt, where the game keeps its box")

    if not re.search(r"qboolean\s+uniform;", local):
        failures.append("the things F turns to cannot carry a uniform")

    down_f = function_body(console, "CG_AccessibilityActivateDown_f")
    up_f = function_body(console, "CG_AccessibilityActivateUp_f")
    aim = function_body(console, "CG_AccessibilityAimFrame")
    for ok, what in (
            (down_f.count("eta_use.uniform = list[index].uniform;") == 2,
             "the chosen thing, or the nearest, is not taken as a uniform"),
            ("cg.cursorHintIcon == HINT_UNIFORM" in down_f and "ETA_UniformStart(" in down_f,
             "with the crosshair already on the body, F does not take the uniform"),
            ("ETA_UniformStart(body);" in aim and "ETA_UniformFrame();" in aim,
             "arriving at a body does not hold use until the uniform is on"),
            ("!eta_use.bodyUntil" in up_f, "letting go of F stops the uniform being taken")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "F " in f or "arriving" in f or "letting go" in f]:
        print("[uniform] F, chosen or nearest or under the crosshair, holds use on the body until done")

    if failures:
        for failure in failures:
            print("[uniform] FAIL %s" % failure)
        sys.exit(1)
    print("uniform_test: an enemy's uniform is found with F, and taken")


if __name__ == "__main__":
    main()

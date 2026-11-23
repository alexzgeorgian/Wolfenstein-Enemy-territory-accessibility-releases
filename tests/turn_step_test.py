#!/usr/bin/env python3
"""Check a tap on a turn key lands on the right compass point, the right way.

Why this exists
---------------
A tap on Left or Right turns the view to the next of the eight compass
points and says it as it lands - the way a flick of the mouse turns. The
mod cannot write the view angles, so it does what a player does: presses
the engine's own +left or +right, makes them faster for the length of
the step, and lets go at the right moment.

That puts three silent failures within one wrong character:

  * a step computed in the wrong direction. The engine lowers the yaw
    for +right; a step that raised it would press the right key and aim
    for a point behind the player, spin the long way round, and name a
    point the player never meant. This project has shipped mirrored
    bearings twice, so the direction is read out of the engine here and
    the step arithmetic is compiled and run against it, not re-typed;
  * a key pressed without a key number of its own. "-right" with no
    number releases every key on the button, including the player's own
    finger on it; a step must only ever let go of what it pressed;
  * a key left down, or the speed boost left on, when the map changes.
    The client outlives the cgame, so the view would keep turning into
    the next map, or every later turn would run five times too fast.

Usage
-----
    ./turn_step_test.py <engine-root>

Run it against an ET: Legacy checkout with the patch series applied.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
INPUT = os.path.join("src", "client", "cl_input.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function(text, name, where):
    found = re.search(r"static\s+float\s+%s\s*\([^)]*\)\s*\{" % re.escape(name),
                      text)
    if not found:
        sys.exit("could not find %s in %s - the turn step this test guards "
                 "is gone" % (name, where))
    depth, i = 0, found.end() - 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[found.start():i + 1]
        i += 1
    sys.exit("could not find the end of %s" % name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    console = read(args.root, CONSOLE)
    main_c = read(args.root, MAIN)
    client = read(args.root, INPUT)
    failures = []

    # --- which way the engine turns for +right ---------------------------
    right = re.search(r"viewangles\[YAW\]\s*([-+])=\s*[^;]*KB_RIGHT", client)
    left = re.search(r"viewangles\[YAW\]\s*([-+])=\s*[^;]*KB_LEFT", client)
    if not right or not left or right.group(1) == left.group(1):
        sys.exit("could not read which way +left and +right move the yaw out "
                 "of %s - this test is out of date with the engine" % INPUT)
    right_sign = -1 if right.group(1) == "-" else 1
    print("[turn] the engine %s the yaw for +right"
          % ("lowers" if right_sign < 0 else "raises"))

    # --- the step goes that way, and lands on the next point -------------
    define = re.search(r"#define\s+ETA_TURN_STEP_MARGIN\s+([0-9.]+)f?", console)
    if not define:
        sys.exit("ETA_TURN_STEP_MARGIN is gone from %s" % CONSOLE)
    next_point = function(console, "ETA_TurnNextPoint", CONSOLE)

    # direction 1 is Right in the mod; the engine's sign for +right says
    # which way the yaw has to move for it.
    cases = [
        # yaw, direction, expected yaw of the point it stops on
        (90.0, 1, 90.0 + 45.0 * right_sign),    # north, right: north-east
        (90.0, -1, 90.0 - 45.0 * right_sign),   # north, left: north-west
        (80.0, 1, 90.0 + 45.0 * right_sign if right_sign > 0 else 45.0),
        (50.0, 1, 90.0 if right_sign > 0 else 0.0),  # 5 short of north-east
        (0.0, -1, 45.0 if right_sign < 0 else -45.0),
    ]

    harness = ["#include <math.h>", "#include <stdio.h>",
               "#define ETA_TURN_STEP_MARGIN %sf" % define.group(1),
               next_point, "int main(void)", "{", "    int failures = 0;"]
    for yaw, direction, expected in cases:
        harness.append(
            '    { float got = ETA_TurnNextPoint(%.1ff, %d);'
            ' if (fabsf(got - (%.1ff)) > 0.01f) { printf("FAIL yaw %.1f %s: '
            'stops at %%.1f, expected %.1f\\n", got); failures++; } }'
            % (yaw, direction, expected, yaw,
               "right" if direction > 0 else "left", expected))
    harness += ["    return failures ? 1 : 0;", "}"]

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "turn.c")
        binary = os.path.join(tmp, "turn")
        with open(source, "w") as handle:
            handle.write("\n".join(harness) + "\n")
        build = subprocess.run(["cc", "-std=gnu99", "-o", binary, source, "-lm"],
                               capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted step arithmetic does not compile:\n%s"
                     % build.stderr)
        run = subprocess.run([binary], capture_output=True, text=True)
        if run.returncode != 0:
            failures.append(
                "a tap does not land on the next compass point in the "
                "direction the engine turns for that key:\n  %s"
                % run.stdout.strip().replace("\n", "\n  "))
        else:
            print("[turn] a tap lands on the next compass point, the way "
                  "the engine turns for that key")

    # The key the step presses for direction 1 must be +right.
    key = re.search(r'direction\s*<\s*0\s*\?\s*"left"\s*:\s*"right"', console)
    if not key:
        failures.append(
            "could not confirm a step to the right presses +right - if the "
            "mapping is reversed, every tap turns the wrong way")

    # --- only ever its own keys ------------------------------------------
    for command in re.findall(r'trap_SendConsoleCommand\s*\(([^;]*)\)\s*;',
                              function_body(console, "ETA_TurnKey")
                              + function_body(console, "ETA_TurnBoost")):
        if "ETA_TURN_KEY_" not in command:
            failures.append(
                "a turn command is sent without a key number of its own "
                "(%s). A bare release lets go of the player's own key on the "
                "same button" % command.strip())
    numbers = re.findall(r'#define\s+ETA_TURN_KEY_[A-Z]+\s+"(\d+)"', console)
    if len(numbers) != 2 or len(set(numbers)) != 2 or any(int(n) < 256 for n in numbers):
        failures.append(
            "the step's key numbers must be two distinct numbers no "
            "keyboard sends (256 and up); found %s" % numbers)
    else:
        print("[turn] the step presses and releases only its own keys (%s)"
              % ", ".join(numbers))

    # --- and lets go of everything when the cgame goes -------------------
    shutdown = function_body(console, "CG_AccessibilityTurnShutdown")
    if not re.search(r"ETA_TurnBoost\s*\(\s*qfalse\s*\)", shutdown) \
            or "ETA_TurnKey" not in shutdown:
        failures.append(
            "CG_AccessibilityTurnShutdown does not release the turn keys and "
            "the speed boost, so a map change mid-step leaves the view "
            "turning, or every later turn five times too fast")
    if not re.search(r"\bCG_AccessibilityTurnShutdown\s*\(\s*\)\s*;", main_c):
        failures.append(
            "nothing in %s calls CG_AccessibilityTurnShutdown" % MAIN)
    boost = function_body(console, "ETA_TurnBoost")
    if "savedYaw" not in boost or '"cl_yawspeed"' not in boost:
        failures.append(
            "ETA_TurnBoost does not put cl_yawspeed back to what it was")
    # The walk key turns faster - and walks the player at half speed for
    # as long as it is held: every turn slowed the tester down.
    if "+speed" in boost:
        failures.append(
            "ETA_TurnBoost holds the walk key, which slows the player to a "
            "walk for every turn")
    if not any("CG_AccessibilityTurnShutdown" in f or "speed boost" in f
               for f in failures):
        print("[turn] a map change lets go of the keys and the speed boost")

    if failures:
        print()
        for failure in failures:
            print("[turn] FAIL %s" % failure)
        return 1

    print("turn_step_test: a tap turns the way the engine does, presses only "
          "its own keys, and lets go of them")
    return 0


def function_body(text, name):
    found = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s - the turn step this test guards is "
                 "gone" % name)
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


if __name__ == "__main__":
    sys.exit(main())

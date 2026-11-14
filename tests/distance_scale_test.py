#!/usr/bin/env python3
"""Check that spoken distances are in real metres.

Why this exists
---------------
The mod tells players how far away the objective is, in metres. The
engine measures in Quake units, and nothing in either engine says what a
Quake unit is worth - both integrations carry a constant,
`ETA_QU_TO_METERS`, set from id Tech 3's external convention of one unit
to the inch. It was a value taken on faith, and the READMEs said so.

It does not have to be. The engine states the size of a human being in
several independent places, and a human being is a thing with known
dimensions. If the conversion is right, all of them land on a person; if
it is wrong, they all land on a giant or a child together.

So this reads the player's bounding box and the three view heights out
of the engine being built against, converts them with the mod's own
constant, and requires each to come out human. It will fail if somebody
changes the constant to something implausible, and it will fail if the
engine ever rescales its players out from under the mod - which would
silently make every spoken distance wrong while everything still
compiled.

What it cannot check is a map's *intended* real-world size. Nobody
published one, and no asset states it. The player is the only object in
the game whose true dimensions are known independently, which is why it
is the thing measured here.

Usage
-----
    ./distance_scale_test.py <engine-root>

Run it against an engine checkout with the patch series applied. Works
on both supported trees - the constants are identical in each.
"""

import argparse
import os
import re
import sys

CLIENT = os.path.join("src", "game", "g_client.c")
PUBLIC = os.path.join("src", "game", "bg_public.h")
LOCAL = os.path.join("src", "cgame", "cg_local.h")

VEC3 = r'\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\}'
MINS = re.compile(r'\bplayerMins\s*\[?\]?\s*=\s*' + VEC3)
MAXS = re.compile(r'\bplayerMaxs\s*\[?\]?\s*=\s*' + VEC3)
CONVERSION = re.compile(r'#define\s+ETA_QU_TO_METERS\s+([0-9.]+)f?')


def strip_comments(text):
    """C source with comments blanked out.

    Not cosmetic: both trees carry a commented-out earlier player box
    just above the live one, and matching that instead reads a person
    56 units tall. The test caught it on its first run, because it
    prints the box it read rather than only its verdict.
    """
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
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def define(text, name):
    match = re.search(r'^\s*#define\s+%s\s+(-?\d+)\s*$' % name, text, re.M)
    if not match:
        sys.exit("could not read %s out of %s - this test is out of date "
                 "with the engine, and passing without reading it would "
                 "defeat its purpose" % (name, PUBLIC))
    return int(match.group(1))


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return strip_comments(handle.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)

    client = read(root, CLIENT)
    public = read(root, PUBLIC)
    local = read(root, LOCAL)

    conversion = CONVERSION.search(local)
    if not conversion:
        sys.exit("could not find ETA_QU_TO_METERS in %s - the patch series "
                 "is not applied, or the constant this test exists to check "
                 "is gone" % LOCAL)
    metres_per_unit = float(conversion.group(1))

    mins = MINS.search(client)
    maxs = MAXS.search(client)
    if not mins or not maxs:
        sys.exit("could not read playerMins/playerMaxs out of %s" % CLIENT)

    floor = int(mins.group(3))
    ceiling = int(maxs.group(3))
    half_width = int(maxs.group(1))

    stand_view = define(public, "DEFAULT_VIEWHEIGHT")
    crouch_view = define(public, "CROUCH_VIEWHEIGHT")
    prone_view = define(public, "PRONE_VIEWHEIGHT")

    # The origin sits `-floor` units above the feet, so a view height is
    # measured from there rather than from the ground. crouchMaxZ is how
    # g_client.c derives the crouched box from the two view heights.
    ground = -floor
    crouch_ceiling = ceiling - (stand_view - crouch_view)

    # Ranges wide enough for any adult, narrow enough that a conversion
    # wrong by even 20% falls out of all of them at once.
    checks = [
        ("standing height", ceiling + ground, 1.60, 2.00,
         "an adult, head to heel"),
        ("eye height, standing", stand_view + ground, 1.45, 1.85,
         "eyes sit a little below the crown"),
        ("crouched height", crouch_ceiling + ground, 1.00, 1.45,
         "a crouching adult"),
        ("eye height, crouched", crouch_view + ground, 0.80, 1.25,
         "eyes when crouched"),
        ("eye height, prone", prone_view + ground, 0.20, 0.60,
         "eyes when lying down"),
    ]

    print("[scale] ETA_QU_TO_METERS = %g (1 unit = %.2f cm)"
          % (metres_per_unit, metres_per_unit * 100))
    print("[scale] player box %d..%d units tall, %d wide"
          % (floor, ceiling, half_width * 2))

    failures = []

    for name, units, low, high, why in checks:
        metres = units * metres_per_unit
        ok = low <= metres <= high
        print("[scale]   %-22s %4d u -> %.2f m   %s"
              % (name, units, metres, "ok" if ok else "OUT OF RANGE"))
        if not ok:
            failures.append(
                "%s comes out at %.2f m, outside %.2f-%.2f m (%s). Either "
                "ETA_QU_TO_METERS is wrong or the engine has rescaled its "
                "players - every spoken distance is wrong by the same "
                "factor either way"
                % (name, metres, low, high, why))

    if failures:
        print()
        for failure in failures:
            print("[scale] FAIL %s" % failure)
        sys.exit(1)

    print("[scale] ok")


if __name__ == "__main__":
    main()

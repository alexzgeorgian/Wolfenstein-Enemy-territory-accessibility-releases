#!/usr/bin/env python3
"""Check the install guide's claims about the game are still true.

Why this exists
---------------
A tester reported a bug: waking up with the Thompson and hearing that
there were no rounds in reserve. The mod was right - an Allied medic
spawns with one clip and no spare, and the engine's own class table says
so in a comment. Nothing was broken; the report happened because a
player who cannot see the HUD has no second opinion, and a correct zero
is indistinguishable from a mod that lost the number.

The fix was a paragraph in the install guide saying so, with the actual
figures. That paragraph is now a factual claim about someone else's
code, shipped to players, in a document nothing else checks. If ET:
Legacy rebalances the medic, the guide keeps telling players a confident
falsehood and explains away a real bug - which is worse than never
having written it.

So this reads the numbers out of the engine's class table and requires
the guide to agree.

Usage
-----
    ./guide_claims_test.py <engine-root>

Run it against an ET: Legacy checkout. The patch series need not be
applied - the claims are about the stock game.
"""

import argparse
import os
import re
import sys

CLASSES = os.path.join("src", "game", "bg_classes.c")
HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.join(HERE, "..", "release", "INSTALL.md.in")


def read(path, what):
    if not os.path.isfile(path):
        sys.exit("no %s - %s" % (path, what))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


# A row is { weapon, skill, skillLevel, startingAmmo, startingClip },
# the last two being the reserve and the loaded clip.
ROW = re.compile(r'\{\s*(WP_[A-Z0-9_]+)\s*,\s*SK_[A-Z0-9_]+\s*,\s*'
                 r'[A-Z0-9_]+\s*,\s*(\d+)\s*,\s*(\d+)\s*\}')


def medic_primaries(classes_c):
    """Both medics' primary weapons, and what each spawns holding.

    The table is nested initialisers. Within a class block the rows run
    melee first, then the primary-weapon list - so the primary is the
    second row, and taking the first match after PC_MEDIC would read the
    knife instead. This test did exactly that on its first run.

    Both teams are read rather than one, because the guide's claim is
    about medics and not about a side.
    """
    found = []

    for match in re.finditer(r'PC_MEDIC', classes_c):
        block = classes_c[match.start():match.start() + 1500]
        rows = ROW.findall(block)

        if len(rows) < 2:
            continue

        weapon, reserve, clip = rows[1]
        found.append((weapon, int(reserve), int(clip)))

    if len(found) != 2:
        sys.exit("read %d medic class block(s) out of %s, expected 2 (one "
                 "per team) - this test is out of date with the engine, and "
                 "passing without reading them would defeat its purpose"
                 % (len(found), CLASSES))

    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="an ET: Legacy checkout")
    args = parser.parse_args()

    classes_c = read(os.path.join(os.path.abspath(args.root), CLASSES),
                     "is this an ET: Legacy checkout?")
    guide = read(GUIDE, "the shipped install guide template")

    primaries = medic_primaries(classes_c)

    for weapon, reserve, clip in primaries:
        print("[guide] engine: a medic's %s spawns with %d loaded and %d "
              "in reserve" % (weapon, clip, reserve))

    failures = []

    # The guide states one pair of numbers for both teams, so the two
    # have to agree before that sentence can be true.
    if len({(r, c) for _, r, c in primaries}) != 1:
        failures.append(
            "the two medics no longer spawn with the same ammo (%s), so the "
            "guide cannot state one figure for both"
            % ", ".join("%s %d/%d" % (w, c, r) for w, r, c in primaries))

    weapon, reserve, clip = primaries[0]

    claim = re.search(r'A medic spawns \*"(\d+) loaded, (\d+) in\s*'
                      r'reserve"\* - (\w+) for the Allies, ([\w ]+) for the '
                      r'Axis', guide)

    if not claim:
        sys.exit("[guide] FAIL the install guide no longer makes the medic "
                 "ammo claim in the form this test can read. Either it was "
                 "reworded - in which case fix this test - or it was "
                 "dropped, in which case a tester will report that zero as "
                 "a bug again.")

    said_clip, said_reserve = int(claim.group(1)), int(claim.group(2))
    said_weapons = [claim.group(3).strip(), claim.group(4).strip()]

    print("[guide] guide:  a medic spawns %d loaded, %d in reserve, with %s"
          % (said_clip, said_reserve, " and ".join(said_weapons)))

    engine_weapons = {w for w, _, _ in primaries}

    for said in said_weapons:
        # "MP 40" in prose is WP_MP40 in the table.
        token = "WP_" + said.upper().replace(" ", "")
        if token not in engine_weapons:
            failures.append(
                "the guide names %r as a medic's primary, but the engine's "
                "medics carry %s" % (said, ", ".join(sorted(engine_weapons))))

    if said_clip != clip:
        failures.append(
            "the guide says the medic spawns with %d loaded, the engine "
            "gives %d" % (said_clip, clip))

    if said_reserve != reserve:
        failures.append(
            "the guide says the medic spawns with %d in reserve, the engine "
            "gives %d - so the guide would be explaining away a number the "
            "player is not actually hearing" % (said_reserve, reserve))

    if failures:
        print()
        for failure in failures:
            print("[guide] FAIL %s" % failure)
        sys.exit(1)

    print("[guide] ok")


if __name__ == "__main__":
    main()

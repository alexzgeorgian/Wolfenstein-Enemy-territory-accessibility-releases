#!/usr/bin/env python3
"""Check that the stance narration says which posture the player is in.

Why this exists
---------------
The mod announces standing, crouched and prone. Two things about that are
easy to get wrong in a way that compiles, links, runs, and is wrong only
to the person listening.

**Prone sets the crouch flag too.** `PM_CheckProne` (`bg_pmove.c`) does
`pm_flags |= PMF_DUCKED` on the way down - "crouched as well" in the
engine's own comment - so a player who is prone has *both* flags set.
Narration that tests `PMF_DUCKED` first therefore calls every prone
player crouched, and never says "prone" at all. Both orders look equally
reasonable reading the code; only the engine says which is right.

**Posture is predicted locally.** It changes on the frame the key is
pressed, while `cg.snap->ps` is still a round trip behind. Reading the
snapshot makes the announcement arrive late, and late is the same defect
0022 had to fix in the weapon narration after it shipped.

So this derives the overlap from the engine rather than trusting a
comment, then requires the narration to test the flags in the order that
overlap forces, from the state that is current.

Usage
-----
    ./stance_narration_test.py <engine-root>

Run it against an engine checkout with the patch series applied. Works on
both supported trees.
"""

import argparse
import os
import re
import sys

PMOVE = os.path.join("src", "game", "bg_pmove.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")

FUNCTION = "ETA_NarrateStanceChange"

# How many lines apart the two flag-sets may be and still count as the
# same "going prone" block. Generous: the point is that they co-occur.
PRONE_WINDOW = 6


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


def function_body(text, name):
    """The brace-matched body of name, or None."""
    match = re.search(r'\b%s\s*\([^;{}]*\)\s*\{' % re.escape(name), text)
    if not match:
        return None

    depth = 0
    i = match.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return strip_comments(handle.read())


def prone_implies_ducked(pmove):
    """Whether the engine sets PMF_DUCKED where it sets EF_PRONE."""
    lines = pmove.splitlines()
    prone = [i for i, line in enumerate(lines)
             if re.search(r'eFlags\s*\|=\s*EF_PRONE\b', line)]
    ducked = [i for i, line in enumerate(lines)
              if re.search(r'pm_flags\s*\|=\s*PMF_DUCKED\b', line)]

    if not prone:
        sys.exit("could not find the engine going prone in %s - this test is "
                 "out of date with the engine, and passing without reading it "
                 "would defeat its purpose" % PMOVE)

    for p in prone:
        for d in ducked:
            if abs(p - d) <= PRONE_WINDOW:
                return True, p + 1, d + 1

    return False, prone[0] + 1, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)

    pmove = read(root, PMOVE)
    draw = read(root, DRAW)

    body = function_body(draw, FUNCTION)
    if body is None:
        sys.exit("could not find %s in %s - the stance narration this test "
                 "exists to guard is gone" % (FUNCTION, DRAW))

    failures = []

    overlaps, prone_line, ducked_line = prone_implies_ducked(pmove)

    if overlaps:
        print("[stance] engine sets PMF_DUCKED (%s:%d) where it sets EF_PRONE "
              "(%s:%d): prone implies crouched"
              % (PMOVE, ducked_line, PMOVE, prone_line))
    else:
        print("[stance] engine no longer sets PMF_DUCKED alongside EF_PRONE")

    prone_at = body.find("EF_PRONE")
    ducked_at = body.find("PMF_DUCKED")

    if prone_at < 0 or ducked_at < 0:
        failures.append(
            "%s no longer tests both EF_PRONE and PMF_DUCKED, so it cannot be "
            "telling the three stances apart" % FUNCTION)
    elif overlaps and ducked_at < prone_at:
        failures.append(
            "%s tests PMF_DUCKED before EF_PRONE, but the engine sets both "
            "when a player goes prone (%s:%d) - so every prone player would "
            "be announced as crouched, and \"prone\" would never be spoken"
            % (FUNCTION, PMOVE, ducked_line))
    else:
        print("[stance] %s tests EF_PRONE first" % FUNCTION)

    # Posture is predicted; the snapshot lags it by a round trip.
    if "predictedPlayerState" not in body:
        failures.append(
            "%s does not read cg.predictedPlayerState. Posture is predicted "
            "locally, so anything else announces it a round trip late - the "
            "same defect 0022 had to fix in the weapon narration" % FUNCTION)
    else:
        print("[stance] %s reads cg.predictedPlayerState" % FUNCTION)

    if re.search(r'\bcg\.snap\s*->\s*ps\s*\.\s*(eFlags|pm_flags)', body) \
       or re.search(r'ps\s*=\s*&\s*cg\.snap\s*->\s*ps', body):
        failures.append(
            "%s takes its stance flags from cg.snap->ps, which lags the "
            "predicted state" % FUNCTION)

    if failures:
        print()
        for failure in failures:
            print("[stance] FAIL %s" % failure)
        sys.exit(1)

    print("[stance] ok")


if __name__ == "__main__":
    main()

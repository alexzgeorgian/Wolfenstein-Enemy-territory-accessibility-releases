#!/usr/bin/env python3
"""Check the up-and-down look report says what is there, not what angle.

Why this exists
---------------
The compass callout answers "which way am I facing" and it is a yaw
report: it names north and south and says nothing at all about the other
axis. A player who tipped the view up got no acknowledgement that
anything had happened, and no way to tell a ceiling a foot above them
from open sky.

The obvious fix is the wrong one. Saying the angle - *"forty degrees
up"* - is honest and useless: forty degrees up is the sky in a field and
a ceiling in a cellar, and which of those it is, is the whole question.
So the pitch is only a trigger, and what gets spoken is the engine's own
trace along the line the player is actually looking down.

Three things about that have to stay true and none of them is a compile
error:

**It has to be the trace, not the angle.** A report built from the
number would compile, sound plausible, and be wrong indoors.

**It has to wait for the aim to settle.** A sweep from the floor to the
sky passes through everything in between, and narrating the journey
buries the destination. The same reason the compass waits.

**It has to stand down while zoomed, on the flag this engine actually
writes.** The binocular narration already answers this question at the
range the player chose, and two voices on one trace is worse than one.
The trap is specific and has bitten this project once already: the 2010
tree declares `cg.zoomed` and assigns it nowhere, so a guard written
against it is a guard that never fires. This test requires whichever
flag the guard names to be one the tree assigns.

Usage
-----
    ./look_around_test.py <engine-root> [--engine etlegacy|id-software]

Run it against an engine checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CGAME = os.path.join("src", "cgame")

REPORT = "ETA_NarrateLookAround"
PROBE = "ETA_DescribeLookAhead"
SETTLE = "ETA_HudNarrator_UpdateLookPitch"
RESET = "ETA_HudNarrator_ResetLookPitch"
SPEAK = "ETA_HudNarrator_SpeakLookAhead"


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


def function_body(text, name):
    match = re.search(r'\b%s\s*\([^;{}]*\)\s*\{' % re.escape(name), text)
    if not match:
        return None
    depth, i = 0, match.end() - 1
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


def assigned_flags(root):
    """Every cg.<flag> the cgame actually writes to.

    Read rather than listed, because the whole point is that a flag can
    be declared and never assigned - and the declaration is what a
    person writing the guard looks at.
    """
    found = set()
    base = os.path.join(root, CGAME)
    for name in sorted(os.listdir(base)):
        if not name.endswith((".c", ".h")):
            continue
        with open(os.path.join(base, name), "r", errors="replace") as handle:
            text = strip_comments(handle.read())
        for flag in re.findall(r'\bcg\.(\w+)\s*=(?!=)', text):
            found.add(flag)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    draw_path = os.path.join(root, DRAW)
    if not os.path.isfile(draw_path):
        sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                 % (DRAW, root))

    with open(draw_path, "r", errors="replace") as handle:
        draw = strip_comments(handle.read())

    body = function_body(draw, REPORT)
    if body is None:
        sys.exit("could not find %s in %s - the up-and-down report this test "
                 "exists to guard is gone" % (REPORT, DRAW))

    tight = body.replace(" ", "").replace("\t", "").replace("\n", "")
    failures = []

    # 1. What is spoken is the trace, not the angle.
    if PROBE not in body or SPEAK not in body:
        failures.append(
            "%s does not go through %s and %s. The only honest answer to "
            "\"what am I looking at\" is the engine's own collision - a "
            "report built from the pitch number alone calls a cellar "
            "ceiling open sky and compiles perfectly" % (REPORT, PROBE, SPEAK))
    else:
        print("[lookaround] the report is %s, spoken by %s" % (PROBE, SPEAK))

    if re.search(r'"[^"]*degree', body):
        failures.append(
            "%s speaks an angle. Degrees are what the player cannot act on: "
            "the same angle is the sky outdoors and a ceiling indoors, and "
            "naming it instead of tracing it throws away the answer"
            % REPORT)

    # 2. It is the pitch, predicted, and it is not the compass's yaw.
    if "predictedPlayerState.viewangles[PITCH]" not in tight:
        failures.append(
            "%s does not read cg.predictedPlayerState.viewangles[PITCH]. "
            "The snapshot's angles lag a local turn by a round trip, which "
            "on a look is long enough to feel, and the yaw is the compass "
            "callout's job" % REPORT)
    if "viewangles[YAW]" in tight:
        failures.append(
            "%s reads the yaw. That is the compass callout's axis; this one "
            "exists because the compass says nothing about the other"
            % REPORT)

    # 3. It waits for the aim to settle, and the wait gates the speech
    #    rather than merely being consulted somewhere in the body.
    if SETTLE not in body:
        failures.append(
            "%s no longer goes through %s, so it speaks every frame the "
            "player holds the look key - which buries the destination "
            "under the journey" % (REPORT, SETTLE))
    else:
        gate = re.search(r'if\(!%s\([^)]*\)\)\{[^}]*return;' % re.escape(SETTLE),
                         tight)
        if not gate:
            failures.append(
                "%s calls %s but does not return when it says the aim has "
                "not settled. Consulting it and speaking anyway is the same "
                "as not consulting it" % (REPORT, SETTLE))
        else:
            index_settle = tight.find(SETTLE)
            index_probe = tight.find(PROBE)
            if index_probe >= 0 and index_probe < index_settle:
                failures.append(
                    "%s traces before it checks whether the aim settled, so "
                    "the cost is paid every frame and the ordering says the "
                    "settle is an afterthought" % REPORT)
            else:
                print("[lookaround] the trace is behind the settle check")

    # 4. The state is reset on the paths that bail, or the first look
    #    after a respawn reports against an angle from the last life.
    if RESET not in body:
        failures.append(
            "%s never calls %s, so the band held from before a respawn, a "
            "limbo screen or the callouts being switched off is compared "
            "against the new view and the first report is owed to nothing"
            % (REPORT, RESET))

    # 5. The callout setting is honoured.
    if "eta_facingCallouts" not in body:
        failures.append(
            "%s ignores eta_facingCallouts. It is the same setting the "
            "compass uses and the guide says so; a player who turned the "
            "direction narration off still gets this" % REPORT)

    # 6. It stands down while zoomed - on a flag the tree writes.
    zoom_flags = re.findall(r'cg\.(zoomed\w*)', body)
    if not zoom_flags:
        failures.append(
            "%s does not stand down while zoomed. The binocular narration "
            "is already answering the same question on the same trace, at "
            "the range the player chose" % REPORT)
    else:
        written = assigned_flags(root)
        for flag in sorted(set(zoom_flags)):
            if flag not in written:
                failures.append(
                    "%s guards on cg.%s, which nothing in %s ever assigns - "
                    "so the guard can never be true and the report talks "
                    "over the binoculars. This is exactly how the 2010 "
                    "tree's scope narration was silent for six releases"
                    % (REPORT, flag, CGAME))
            else:
                print("[lookaround] stands down on cg.%s, which the tree "
                      "assigns" % flag)

    # 7. And it is actually called.
    # The definition is written (void), a call site is (), so this
    # counts call sites and not the function itself.
    calls = len(re.findall(r'\b%s\s*\(\s*\)\s*;' % re.escape(REPORT), draw))
    if calls < 1:
        failures.append(
            "%s is defined but never called from %s, so none of the above "
            "reaches a player" % (REPORT, DRAW))

    if failures:
        print()
        for failure in failures:
            print("[lookaround] FAIL %s" % failure)
        sys.exit(1)

    print("look_around_test: %s - the up-and-down report traces what is "
          "there, waits for the aim to settle, and yields to the zoom"
          % args.engine)


if __name__ == "__main__":
    main()

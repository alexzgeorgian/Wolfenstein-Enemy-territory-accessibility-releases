#!/usr/bin/env python3
"""Check the scoreboard, the player stats and the top shots are spoken.

Why this exists
---------------
All three are windows a sighted player holds a key to look at. A tester
reported them silent. They are also easy to make silent again without
anything else noticing, because each is two halves a moment apart: the
key sends a request, and the answer arrives later as a server command.
The mod speaks the answer when it arrives, so it has to be told the key
was pressed, and the answer handler has to speak.

The scoreboard has a trap of its own. The server sends it as "sc0" and,
only when the players do not fit, "sc1" - they are not the two teams.
Speaking on "sc1" is silence on every ordinary server; speaking straight
from "sc0" reads half a full server's board. Both are sent in the same
server frame, so the mod waits one client frame. This reads the server's
own sender to confirm that is still how it works.

Usage
-----
    ./scoreboard_speech_test.py <engine-root>

Run it against an ET: Legacy checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
SERVERCMDS = os.path.join("src", "cgame", "cg_servercmds.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
G_CMDS = os.path.join("src", "game", "g_cmds.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone, and passing without it would mean nothing"
                 % (name, where))
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    console = read(args.root, CONSOLE)
    servercmds = read(args.root, SERVERCMDS)
    draw = read(args.root, DRAW)
    g_cmds = read(args.root, G_CMDS)
    failures = []

    # --- each key tells the mod, whether or not it asks the server ------
    keys = (
        ("CG_ScoresDown_f", "CG_AccessibilityScoresPressed", "scoreboard"),
        ("CG_StatsDown_f", "CG_AccessibilityStatsPressed", "player stats"),
        ("CG_topshotsDown_f", "CG_AccessibilityTopshotsPressed", "top shots"),
    )
    for command, hook, what in keys:
        body = body_of(console, command, CONSOLE)
        asked = re.search(r"%s\s*\(\s*qtrue\s*\)" % hook, body)
        cached = re.search(r"%s\s*\(\s*qfalse\s*\)" % hook, body)
        if not asked or not cached:
            failures.append(
                "%s does not call %s both when it asks the server (qtrue) "
                "and when it reuses what it has (qfalse), so the %s is "
                "silent on one of the two presses" % (command, hook, what))
        else:
            print("[scores] the %s key tells the mod on both kinds of press"
                  % what)

    # --- and each answer is spoken when it arrives -----------------------
    answers = (
        ("CG_parseWeaponStatsGS_cmd", "eta_statsPending", "player stats"),
        ("CG_topshotsParse_cmd", "eta_topshotsPending", "top shots"),
    )
    for handler, pending, what in answers:
        body = body_of(servercmds, handler, SERVERCMDS)
        if not re.search(r"ETA_AnswerDue\s*\(\s*&\s*%s\s*\)" % pending, body) \
                or "ETA_ReportSpeak" not in body:
            failures.append(
                "%s never speaks the %s it has just parsed" % (handler, what))
        else:
            print("[scores] the %s are spoken when they arrive" % what)

    # --- the scoreboard: one frame after it arrives ----------------------
    parse = body_of(servercmds, "CG_ParseScore", SERVERCMDS)
    if re.search(r"team\s*==\s*TEAM_ALLIES\s*&&", parse):
        failures.append(
            "the scoreboard waits for the allies' half, which is \"sc1\" - "
            "and the server sends sc1 only when the players do not fit in "
            "sc0, so on an ordinary server it is never spoken")
    if "ETA_SpeakScores" in parse:
        failures.append(
            "the scoreboard is spoken straight from CG_ParseScore, before "
            "a second message from the same server frame can arrive - half "
            "a full server's board")
    if not re.search(r"eta_scoresReady\s*=\s*qtrue", parse):
        failures.append(
            "CG_ParseScore never marks the scoreboard ready to speak")
    if not re.search(r"\bCG_AccessibilityScoresFrame\s*\(\s*\)\s*;", draw):
        failures.append(
            "nothing calls CG_AccessibilityScoresFrame, so a scoreboard "
            "marked ready is never spoken")

    # The server: sc0 first and as full as it will go, then - only if
    # players are left over - sc1.
    sc0 = g_cmds.find('"sc0 %i %i"')
    sc1 = g_cmds.find('"sc1"', sc0 + 1) if sc0 >= 0 else -1
    between = g_cmds[sc0:sc1] if 0 <= sc0 < sc1 else ""
    if not re.search(r"if\s*\(\s*i\s*==\s*numSorted\s*\)\s*\{\s*return\s*;",
                     between):
        failures.append(
            "could not confirm the server still sends sc1 only for players "
            "that did not fit in sc0 - the scoreboard's timing rests on that")
    if not any("scoreboard" in f or "sc0" in f or "sc1" in f for f in failures):
        print("[scores] the scoreboard is spoken once it is whole, the frame "
              "after it arrives")

    # --- answers expire ---------------------------------------------------
    due = body_of(servercmds, "ETA_AnswerDue", SERVERCMDS)
    if "ETA_ANSWER_WAIT_MS" not in due or not re.search(r"\*\s*pendingSince\s*=\s*0", due):
        failures.append(
            "an answer does not expire once it is used or too old, so a "
            "reply that never came makes the board speak out of nowhere "
            "the next time scores arrive")

    if failures:
        print()
        for failure in failures:
            print("[scores] FAIL %s" % failure)
        return 1

    print("scoreboard_speech_test: the scoreboard, the stats and the top "
          "shots are spoken when their answers arrive")
    return 0


if __name__ == "__main__":
    sys.exit(main())

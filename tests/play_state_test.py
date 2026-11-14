#!/usr/bin/env python3
"""Check "spectating" and "in play" are told apart the way the game does.

A sighted player knows at a glance whether they are in the match: their
own weapon in front of them and a HUD, or a "SPECTATING" banner and
somebody else's view. Without sight the two sound alike, so the mod says
which it is when it changes, and the status key opens with it.

Each rule here is one way that could quietly say the wrong thing:

- Watching somebody - as a spectator, or from limbo between lives - the
  snapshot's player state is the watched player's, marked PMF_FOLLOW by
  the server, and PMF_LIMBO as well in limbo. A mod reading the team or
  the health from that state would announce the watched player's life
  as the player's own. So the team must come from the player's own
  client info, and "down" must only be read when nobody is being
  watched.
- The server must still mark following and limbo that way, or the
  rules above are checking nothing.
- The change is an event - it is what everything else is about - so it
  is not held back by the quiet after a question, and the status key
  opens with it.

    ./play_state_test.py <engine-root>
"""

import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
ACTIVE = os.path.join("src", "game", "g_active.c")


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
    match = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return None
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    root = os.path.abspath(sys.argv[1])
    failures = []

    draw = strip_comments(read(root, DRAW))
    console = strip_comments(read(root, CONSOLE))
    active = strip_comments(read(root, ACTIVE))

    now = function_body(draw, "ETA_PlayStateNow")
    if now is None:
        sys.exit("no ETA_PlayStateNow in %s" % DRAW)
    flat = re.sub(r"\s+", " ", now)

    # --- whose team -----------------------------------------------------
    if "cgs.clientinfo[cg.clientNum].team" not in flat:
        failures.append("the team is not read from the player's own client "
                        "info - watching someone, it would be theirs")
    if re.search(r"ps->persistant\[PERS_TEAM\]", flat):
        failures.append("the team is read from the snapshot's player state, "
                        "which is the watched player's while following")

    # --- whose life -----------------------------------------------------
    watch_at = flat.find("PMF_FOLLOW")
    limbo_at = flat.find("return ETA_PLAY_LIMBO")
    down_at = flat.find("return ETA_PLAY_DOWN")
    health_at = flat.find("STAT_HEALTH")
    if min(watch_at, limbo_at, down_at, health_at) < 0:
        failures.append("could not find the following, limbo and down rules")
    elif not (limbo_at < health_at < down_at):
        failures.append("health is read before limbo and following are ruled "
                        "out, so a watched player's death is announced as "
                        "the player's own")
    elif "PMF_LIMBO" not in flat[:limbo_at] or "|| watch" not in flat[:limbo_at]:
        failures.append("limbo is not recognised both by PMF_LIMBO and by "
                        "watching someone from a team")
    else:
        print("[state] the team is the player's own, and a watched player's "
              "health is never taken for theirs")

    # --- the server still marks it that way -----------------------------
    if not re.search(r"pm_flags \|= PMF_FOLLOW;\s*ent->client->ps\.pm_flags \|= PMF_LIMBO;", active):
        failures.append("the server no longer marks a limbo player watching a "
                        "teammate with PMF_FOLLOW and PMF_LIMBO")
    else:
        print("[state] engine: limbo following is still PMF_FOLLOW and PMF_LIMBO")

    # --- said, and not held back ----------------------------------------
    frame_call = re.search(r"\n\tETA_NarratePlayState\(\);", draw)
    held = re.search(r"if \(!ETA_HudNarrator_PassiveHeld\(cg\.time\)\)\s*\{(.*?)\n\t\}", draw, re.S)
    if not frame_call:
        failures.append("the change is never said")
    elif held and "ETA_NarratePlayState" in held.group(1):
        failures.append("the change is held back behind the quiet after a "
                        "question")
    else:
        print("[state] said when it changes, not held back")

    status = function_body(console, "CG_AccessibilityStatus_f")
    if status is None:
        failures.append("no status key")
    else:
        flat_status = re.sub(r"\s+", " ", status)
        state_at = flat_status.find("CG_AccessibilitySpeakPlayState()")
        health_said = flat_status.find("ETA_HudNarrator_SpeakHealth(")
        if state_at < 0 or (health_said >= 0 and state_at > health_said):
            failures.append("the status key does not open with whether the "
                            "player is in play")
        else:
            print("[state] the status key opens with it")

    if failures:
        for failure in failures:
            print("[state] FAIL %s" % failure)
        sys.exit(1)

    print("play_state_test: spectating, in play, down and limbo are told "
          "apart by the game's own flags")


if __name__ == "__main__":
    main()

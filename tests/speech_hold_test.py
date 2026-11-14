#!/usr/bin/env python3
"""Check the scenery stops talking over an answer the player asked for.

Why this exists
---------------
A tester lost the same objective distance twice. The first time it was
a wall report arriving in the same frame, and the answer to that was
ordering: speech delivers a new line by cutting off the one in
progress, so of two reports in one frame the later one survives, and
the scenery was moved to speak first.

The second time they were pressing the objectives key deliberately, and
the wall report still destroyed the answer. Ordering could not have
prevented it and never could have: the key speaks on one frame and the
per-frame narration runs on the next, and the next frame always wins.
Two reports a frame apart are not in the same frame at all.

So there is a hold. A report the player asked for - the status key, the
health and ammo keys, the objectives key, the repeat key, a step of the
map survey - keeps the passive narration quiet for a few seconds
afterwards. Being talked over while asking a question is worse than
missing a piece of scenery.

Three things this pins, and each is a way the hold could be quietly
useless:

  * the on-demand commands actually set it. A hold nothing ever takes
    is a feature that exists and does nothing;
  * the passive narration actually checks it, at the one place they are
    all called, rather than in some of them;
  * the drop warning does NOT check it. The single thing allowed to cut
    off an answer is being told you are about to walk off something
    that will kill you, and a hold that silenced that would have turned
    a courtesy into a hazard.

What it does NOT check
----------------------
Whether four seconds is the right length. That needs ears: too short
and the answer still gets cut, too long and the scenery feels dead.

Usage
-----
    ./speech_hold_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
NARRATOR = os.path.join("src", "accessibility", "hud", "hud_narrator.c")

# Every key that answers a question the player asked.
ASKED = (
    "CG_AccessibilityStatus_f",
    "CG_AccessibilityHealth_f",
    "CG_AccessibilityAmmo_f",
    "CG_AccessibilityRepeat_f",
)

# Passive reports. None of these is a response to something the player
# just pressed, so none of them is entitled to interrupt an answer.
PASSIVE = (
    "ETA_NarrateObstacleAhead",
    "ETA_NarrateFacing",
    "ETA_NarrateLookAround",
    "ETA_NarrateWater",
)

# The exception, and the reason for it.
HAZARD = "ETA_NarrateDropAhead"

# The player's own marker, ET: Legacy only. The three keys answer a
# question, the distance callouts are scenery, and arriving is not held
# back: it is the end of the walk the marker exists for, and it happens
# once.
MARKER_ASKED = (
    "CG_AccessibilityMarkerPlace_f",
    "CG_AccessibilityMarkerWhere_f",
    "CG_AccessibilityMarkerClear_f",
)
MARKER_PASSIVE = ("CG_AccessibilityMarkerApproach",)
MARKER_ARRIVAL = "CG_AccessibilityMarkerFrame"


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


def signature(name):
    """Both trees write this differently: (void) here, ( void ) there."""
    return name + "("


def body_of(text, signature, where):
    start = text.find(signature)
    if start < 0:
        sys.exit("could not find %s in %s - the narration this test guards "
                 "is gone, and passing without it would mean nothing"
                 % (signature, where))
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


def guarded_region(draw):
    """The block the passive narration is called from, behind the hold."""
    # Both trees write their conditions differently - (x) here, ( x )
    # there - so this matches the call rather than a spelling of it.
    found = re.search(r'if\s*\(\s*!\s*ETA_HudNarrator_PassiveHeld\s*\(', draw)
    if not found:
        return None
    at = found.start()

    brace = draw.find("{", at)
    depth, i, n = 0, brace, len(draw)
    while i < n:
        if draw[i] == "{":
            depth += 1
        elif draw[i] == "}":
            depth -= 1
            if depth == 0:
                return draw[brace + 1:i]
        i += 1
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    parser.add_argument("--library", default=None,
                        help="accessibility-mode checkout (default: this one)")
    args = parser.parse_args()

    library_root = args.library or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))

    draw = strip_comments(read(args.root, DRAW, "is the patch series applied?"))
    console = strip_comments(read(args.root, CONSOLE,
                                  "is the patch series applied?"))
    narrator = strip_comments(read(library_root, NARRATOR,
                                   "is this the accessibility checkout?"))

    failures = []

    # --- the library actually has a hold that expires -----------------
    if "ETA_HudNarrator_PassiveHeld" not in narrator:
        failures.append(
            "the library has no hold at all, so nothing protects an answer "
            "the player asked for")

    # The 2010 tree answers everything through one status key: it has no
    # separate health, ammo or objectives keys to hold from.
    asked = ASKED if args.engine == "etlegacy" else ("CG_AccessibilityStatus_f",
                                                     "CG_AccessibilityRepeat_f")
    # ET: Legacy calls the distance on the way to the marker only; the
    # 2010 tree has no marker and keeps the objective's.
    passive = PASSIVE
    if args.engine == "etlegacy":
        asked = asked + MARKER_ASKED
        passive = passive + MARKER_PASSIVE
    else:
        passive = passive + ("ETA_NarrateObjectiveApproach",)

    # --- the keys set it ----------------------------------------------
    for name in asked:
        body = body_of(console, signature(name), CONSOLE)

        if "ETA_HudNarrator_HoldPassive" not in body:
            failures.append(
                "%s does not hold the scenery off. The player pressed a key "
                "to ask a question, and the next frame's wall report will "
                "cut the answer off mid-sentence - which is what was "
                "reported, twice" % name)

    # The objectives key is the one it happened on, and it is not a
    # CG_Accessibility function, so it is checked by name. The 2010 tree
    # has no such key.
    objectives = (body_of(console, signature("CG_objectivesDown_f"), CONSOLE)
                  if args.engine == "etlegacy" else "ETA_HudNarrator_HoldPassive")
    if "ETA_HudNarrator_HoldPassive" not in objectives:
        failures.append(
            "the objectives key does not hold the scenery off - that is the "
            "exact key the tester was pressing when the answer was destroyed")

    # --- stopping speech clears it ------------------------------------
    stop = body_of(console, signature("CG_AccessibilityStopSpeech_f"), CONSOLE)
    if "ETA_HudNarrator_ReleasePassive" not in stop:
        failures.append(
            "the stop-speech key leaves the hold standing, so a player who "
            "asked for silence gets silence plus several more seconds of "
            "the scenery refusing to speak")

    # --- the passive narration is behind it ---------------------------
    region = guarded_region(draw)

    if region is None:
        failures.append(
            "nothing in %s is behind ETA_HudNarrator_PassiveHeld, so the "
            "hold is set and never honoured" % DRAW)
    else:
        for name in passive:
            if not re.search(r'\b%s\s*\(\s*\)\s*;' % re.escape(name), region):
                failures.append(
                    "%s is called outside the hold, so it can still talk "
                    "over an answer the player asked for" % name)

        # --- and the hazard is not ------------------------------------
        if re.search(r'\b%s\s*\(\s*\)\s*;' % re.escape(HAZARD), region):
            failures.append(
                "%s is behind the hold. A drop warning is the one report "
                "worth interrupting anything - holding it back to protect "
                "a health readout would turn a courtesy into a hazard"
                % HAZARD)

        if args.engine == "etlegacy" and re.search(
                r'\b%s\s*\(\s*\)\s*;' % re.escape(MARKER_ARRIVAL), region):
            failures.append(
                "%s is behind the hold, so \"Marker reached\" can be lost to "
                "an answer the player asked for a moment before - and it is "
                "said once, the moment they get there" % MARKER_ARRIVAL)

    if not re.search(r'\b%s\s*\(\s*\)\s*;' % re.escape(HAZARD), draw):
        failures.append("%s is no longer called at all" % HAZARD)

    if args.engine == "etlegacy" and not re.search(
            r'\b%s\s*\(\s*\)\s*;' % re.escape(MARKER_ARRIVAL), draw):
        failures.append("%s is no longer called at all, so the marker has "
                        "no sound and is never reached" % MARKER_ARRIVAL)

    # --- the hold has to end by itself --------------------------------
    held = body_of(narrator, "int ETA_HudNarrator_PassiveHeld(", NARRATOR)

    if "nowMs" not in held:
        failures.append(
            "the hold does not look at the clock, so it cannot expire - the "
            "scenery would go quiet at the first key press and stay quiet")

    hold_ms = re.search(r'#define\s+ETA_HUD_HOLD_MS\s+(\d+)',
                        read(library_root,
                             os.path.join("src", "accessibility", "hud",
                                          "hud_narrator.h"),
                             "is this the accessibility checkout?"))

    if not hold_ms:
        failures.append("ETA_HUD_HOLD_MS is gone")
    elif not 1000 <= int(hold_ms.group(1)) <= 10000:
        failures.append(
            "the hold is %s ms, which is either too short to cover the "
            "longest answer the mod gives or long enough that the scenery "
            "reads as broken" % hold_ms.group(1))

    if failures:
        print("speech_hold_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("speech_hold_test: %s - every on-demand report holds the scenery "
          "off, the passive narration is behind that hold, and the drop "
          "warning is not" % args.engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())

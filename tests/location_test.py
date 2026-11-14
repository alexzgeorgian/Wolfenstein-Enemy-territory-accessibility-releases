#!/usr/bin/env python3
"""Check the spoken location is the engine's own, and always has an answer.

Why this exists
---------------
"I am at the Old City Wall" is only worth saying if it is the same thing
a sighted teammate would say. If the mod invented its own names, or
rounded to its own grid, a blind player calling out a position would be
describing a map nobody else is looking at - fluent, confident, and
useless to the people they are talking to.

So the words have to come from the engine, by both of its routes:

  * CG_GetLocationMsg, which reads the map's own location file and picks
    the nearest named place that is actually in the player's view. ET:
    Legacy ships these files for the stock maps and hundreds more.
  * BG_GetLocationString, the command map's lettered grid, for maps with
    no location file at all.

The second one matters more than it looks. Without a fallback the
feature would simply go silent on any map lacking a location file, and
silence is indistinguishable from "nothing here" - the player would have
no way to tell a quiet map from a broken mod. So this fails if the
fallback is ever dropped.

Two further things it pins:

  * The names are authored for the screen and carry ET's colour codes.
    Handing "^1Allied Command Post" to a screen reader makes it
    pronounce the markup, so Q_CleanStr must be applied.
  * "Unknown" is the engine's way of saying it has no named place. It
    must never be spoken as though it were one.

What it does NOT check
----------------------
Whether the announcement arrives at a useful moment. That is the settle
time, which is library behaviour and is covered by the smoke test.

Usage
-----
    ./location_test.py <engine-root>

ET: Legacy only - the 2010 GPL release has no location system at all.
Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
LOCATIONS = os.path.join("src", "cgame", "cg_locations.c")
MISC = os.path.join("src", "game", "bg_misc.c")
NARRATOR = os.path.join("src", "accessibility", "hud", "hud_narrator.c")


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


def body_of(text, name, where):
    start = text.find(name)
    if start < 0:
        sys.exit("could not find %s in %s - the location narration this "
                 "test exists to guard is gone, and passing without it "
                 "would mean nothing" % (name, where))
    end = text.find("\n}", start)
    if end < 0:
        sys.exit("could not find the end of %s in %s" % (name, where))
    return text[start:end]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy", choices=("etlegacy",),
                        help="ET: Legacy only; the 2010 tree has no locations")
    parser.add_argument("--library", default=None,
                        help="accessibility-mode checkout (default: this one)")
    args = parser.parse_args()

    library_root = args.library or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))

    draw = strip_comments(read(args.root, DRAW, "is the patch series applied?"))
    console = strip_comments(read(args.root, CONSOLE,
                                  "is the patch series applied?"))
    locations = read(args.root, LOCATIONS, "is this an ET: Legacy checkout?")
    misc = read(args.root, MISC, "is this an engine checkout?")

    failures = []

    name_fn = body_of(draw, "ETA_LocationName", DRAW)

    # --- the words must be the engine's, by both routes ----------------
    if "CG_GetLocationMsg" not in name_fn:
        failures.append(
            "ETA_LocationName does not call CG_GetLocationMsg - the named "
            "places are the map's own data and the whole point is that a "
            "teammate recognises the words")

    if "BG_GetLocationString" not in name_fn:
        failures.append(
            "ETA_LocationName has no grid fallback (BG_GetLocationString) - "
            "on any map without a location file the feature would go "
            "silent, and silence reads as 'nothing here' rather than as "
            "'this map has no names'")

    # Both of those have to still exist in the engine where we call them.
    if "char *CG_GetLocationMsg" not in locations:
        failures.append("CG_GetLocationMsg is gone from %s" % LOCATIONS)

    if "char *BG_GetLocationString" not in misc:
        failures.append("BG_GetLocationString is gone from %s" % MISC)

    # --- the engine's "no answer" must not be spoken as an answer ------
    if "Unknown" not in name_fn:
        failures.append(
            'ETA_LocationName does not test for "Unknown" - that is the '
            "engine's way of saying it has no named place here, and "
            'announcing "Unknown" as a location is worse than announcing '
            "the grid square")

    # ... and the engine must still use that exact word for it.
    if '"Unknown"' not in locations:
        failures.append(
            'CG_GetLocationMsg no longer returns "Unknown" when it has no '
            "named place - the mod tests for that exact string, so the "
            "test above is now checking for something that never happens")

    # --- colour codes must come off ------------------------------------
    if "Q_CleanStr" not in name_fn:
        failures.append(
            "ETA_LocationName does not strip colour codes with Q_CleanStr - "
            "the shipped location files are full of them and a screen "
            "reader pronounces the markup")

    # --- the status key must answer it too -----------------------------
    if "CG_AccessibilitySpeakLocation" not in console:
        failures.append(
            "the status key does not report the location - passive "
            "announcement is damped by two seconds, so being able to ask "
            "is the only way to get an answer on demand")

    speak = body_of(draw, "CG_AccessibilitySpeakLocation", DRAW)
    if "ETA_HudNarrator_SpeakLocation" not in speak:
        failures.append(
            "CG_AccessibilitySpeakLocation does not actually speak the "
            "location")

    # --- the overhead probe must only claim what it measured -----------
    overhead = body_of(draw, "ETA_OverheadState", DRAW)

    if "SURF_SKY" not in overhead:
        failures.append(
            "ETA_OverheadState does not test SURF_SKY - open sky is the "
            "only half of this that can actually be proven, and it is "
            "proven by the engine's own flag on the sky surface")

    # The spoken words live in the library, not here. An earlier version
    # of this test looked for them in the engine file, where they have
    # never been - so it passed no matter what they said.
    narrator = strip_comments(read(library_root, NARRATOR,
                                   "is this the accessibility checkout?"))
    names = body_of(narrator, "ETA_HudNarrator_OverheadName", NARRATOR)

    if re.search(r'\bindoors?\b', names, re.I):
        failures.append(
            "the overhead state is spoken as \"indoors\" - a trace that "
            "hits a ceiling has not proven indoors, only that something "
            "is overhead, and that something may be a bridge, a tunnel "
            "or an awning. The honest word is \"under cover\"")

    if "under cover" not in names or "sky" not in names:
        failures.append(
            "the overhead names are no longer \"under cover\" and open "
            "sky - those two are exactly what the probe can prove")

    # The absence of a measurement must stay an absence: no name, so
    # nothing is spoken, rather than a plausible-sounding default.
    if "return NULL" not in names:
        failures.append(
            "ETA_HudNarrator_OverheadName no longer returns NULL for the "
            "unknown state, so a frame with no measurement would announce "
            "something anyway")

    if failures:
        print("location_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("location_test: %s - the spoken place is the engine's own named "
          "location with the map grid as fallback, colour codes stripped, "
          "and it is on the status key as well as announced" % args.engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())

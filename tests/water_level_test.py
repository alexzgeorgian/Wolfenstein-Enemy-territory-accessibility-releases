#!/usr/bin/env python3
"""Check the water narration is the engine's own waterlevel, not a guess.

Why this exists
---------------
The engine knows exactly how deep the player is: PM_SetWaterLevel works
it out every movement frame by testing three points up the player's own
bounding box against MASK_WATER. But the answer lives in pmove_t and
never reaches the playerstate, so the cgame cannot read it - it has to
ask the same question again for itself.

That makes ETA_WaterLevel a transcription, and transcriptions drift. The
failure mode is quiet and nasty: a copy that samples at slightly the
wrong heights still returns 0 to 3, still changes as the player wades in,
still sounds completely authoritative - and is wrong about exactly the
levels the words are pinned to.

Because the words are not descriptions of how deep the water looks. Each
one is a claim about something the movement code does at that level:

  * "Deep water" (2)  - PM_CheckJump routes a jump into PM_WaterMove at
                        waterlevel > 1, so jumping here swims instead.
  * "Swimming"   (3)  - PM_PmoveSingle enters PM_WaterMove outright at
                        waterlevel > 2, and PM_CrashLand cancels falling
                        damage entirely at waterlevel == 3.

So this reads PM_SetWaterLevel out of the engine, reads ETA_WaterLevel
out of the patched cgame, and requires the sampling to agree line for
line. Then it re-derives the two thresholds above from the engine's own
movement code and requires the mod's enum to sit at the same numbers.

What it does NOT check
----------------------
Whether the water sounds right when you walk into it. That needs ears.

Usage
-----
    ./water_level_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

PMOVE = os.path.join("src", "game", "bg_pmove.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
HEADER = os.path.join("src", "accessibility", "hud", "hud_narrator.h")

# The engine's levels, and what the mod is allowed to call each one.
EXPECTED_ENUM = [
    ("ETA_WATER_DRY", 0),
    ("ETA_WATER_SHALLOW", 1),
    ("ETA_WATER_DEEP", 2),
    ("ETA_WATER_SWIMMING", 3),
]


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


def function_body(text, name, where):
    """Everything from a function's name to the closing brace in column 0."""
    start = text.find(name)
    if start < 0:
        sys.exit("could not find %s in %s - %s" % (name, where,
                                                   "this test is out of date "
                                                   "and a pass would mean "
                                                   "nothing"))
    end = text.find("\n}", start)
    if end < 0:
        sys.exit("could not find the end of %s in %s" % (name, where))
    return text[start:end]


def normalise(expression):
    """Whitespace and the pm-> / ps-> prefix removed, so the two copies compare."""
    expression = re.sub(r'\bpm\s*->\s*ps\s*->', "", expression)
    expression = re.sub(r'\bps\s*->', "", expression)
    expression = re.sub(r'\bpm\s*->', "", expression)
    expression = re.sub(r'\(\s*int\s*\)', "", expression)
    return re.sub(r'\s+', "", expression)


def sample_heights(body):
    """The three z heights a waterlevel probe samples, in order."""
    heights = [normalise(value)
               for value in re.findall(r'point\s*\[\s*2\s*\]\s*=\s*([^;]+);',
                                       body)]
    return heights


def sample_defs(body):
    """How sample1 and sample2 are worked out."""
    found = {}
    for name in ("sample1", "sample2"):
        match = re.search(r'\b%s\s*=\s*([^;]+);' % name, body)
        if match:
            found[name] = normalise(match.group(1))
    return found


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

    pmove = strip_comments(read(args.root, PMOVE, "is this an engine checkout?"))
    draw = strip_comments(read(args.root, DRAW, "is the patch series applied?"))
    header = read(library_root, HEADER, "is this the accessibility checkout?")

    engine = function_body(pmove, "PM_SetWaterLevel", PMOVE)
    mod = function_body(draw, "ETA_WaterLevel", DRAW)

    failures = []

    # --- the sampling itself -------------------------------------------
    engine_heights = sample_heights(engine)
    mod_heights = sample_heights(mod)

    if len(engine_heights) != 3:
        sys.exit("PM_SetWaterLevel no longer samples three heights (found "
                 "%d) - the mod's copy is modelled on it and this test can "
                 "no longer tell whether they agree" % len(engine_heights))

    if mod_heights != engine_heights:
        failures.append(
            "ETA_WaterLevel samples at different heights from "
            "PM_SetWaterLevel:\n      engine: %s\n      mod:    %s"
            % (" | ".join(engine_heights), " | ".join(mod_heights) or "(none)"))

    engine_samples = sample_defs(engine)
    mod_samples = sample_defs(mod)

    if engine_samples != mod_samples:
        failures.append(
            "the sample offsets are worked out differently:\n"
            "      engine: %s\n      mod:    %s"
            % (engine_samples, mod_samples))

    if "MASK_WATER" not in mod:
        failures.append(
            "ETA_WaterLevel does not test against MASK_WATER - the engine "
            "counts lava and slime as water too, and a copy that only "
            "looked for CONTENTS_WATER would call a lava pit dry")

    # The mod must return the same four levels the engine does.
    returned = sorted(set(int(value)
                          for value in re.findall(r'return\s+([0-9]+)\s*;',
                                                  mod)))
    if returned != [0, 1, 2, 3]:
        failures.append(
            "ETA_WaterLevel returns %s, but the engine's waterlevel is 0 to 3"
            % (returned or "nothing"))

    # --- the words, and what the engine does at each level --------------
    match = re.search(r'typedef enum\s*ETA_Water\s*\{([^}]*)\}', header, re.S)
    if not match:
        sys.exit("could not find the ETA_Water enum in %s" % HEADER)

    names = re.findall(r'\b(ETA_WATER_[A-Z]+)\b', match.group(1))
    expected_names = [name for name, _ in EXPECTED_ENUM]

    if names != expected_names:
        failures.append(
            "the ETA_Water enum is %s, expected %s in that order - the "
            "integration casts the engine's waterlevel straight to it, so "
            "the order is the mapping" % (names, expected_names))

    # "Swimming" has to be the level the engine itself calls swimming.
    swim = re.search(r'waterlevel\s*>\s*([0-9]+)[^;{]*\)\s*\{?[^}]*?'
                     r'PM_WaterMove', pmove, re.S)
    if not swim:
        failures.append(
            "could not find the engine's own swim threshold (a waterlevel "
            "test guarding PM_WaterMove) - the word \"swimming\" is pinned "
            "to it")
    else:
        # "> 2" means level 3 is the first swimming level.
        first_swimming = int(swim.group(1)) + 1
        if first_swimming != dict(EXPECTED_ENUM)["ETA_WATER_SWIMMING"]:
            failures.append(
                "the engine begins swimming at waterlevel %d, but the mod "
                "says \"swimming\" at %d"
                % (first_swimming,
                   dict(EXPECTED_ENUM)["ETA_WATER_SWIMMING"]))

    # Falling damage is cancelled outright at the swimming level, which is
    # what lets the drop warning treat a landing in deep water as safe.
    if not re.search(r'waterlevel\s*==\s*3', pmove):
        failures.append(
            "the engine no longer cancels falling damage at waterlevel 3 - "
            "the drop narration's reasoning about water depends on it")

    if failures:
        print("water_level_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("water_level_test: %s - ETA_WaterLevel samples exactly where "
          "PM_SetWaterLevel does (%s), and the words sit at the levels the "
          "movement code switches on"
          % (args.engine, " | ".join(engine_heights)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

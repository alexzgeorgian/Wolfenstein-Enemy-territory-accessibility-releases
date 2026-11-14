#!/usr/bin/env python3
"""Check the mod's own sounds exist, are usable, and are the ones it asks for.

Why this exists
---------------
A sound the engine cannot find plays silence and says nothing about it.
No error, no log line, no difference from a cue that simply decided not
to fire. It is the quietest failure this project has, and every version
of it has shipped at least once somewhere: a path with a typo, a file
that was never added to the package, a cvar pointing at a name that
changed.

These four are worse than the rest, because unlike every other cue they
are not sounds the game already owns. They are generated and packed into
the pk3 by the release build, so there are three separate places the
chain can break - the generator, the packaging, and the name the mod
registers - and a break in any of them is inaudible.

So this walks the whole chain:

  * every sound path the mod registers is one the generator produces;
  * every sound the generator produces is one the mod registers (a file
    nobody asks for is dead weight, and usually means a rename landed on
    one side only);
  * the generator is deterministic, because the release archive's
    checksum has to be reproducible from source;
  * what it produces is actually playable by this engine - mono, so the
    engine can position it in 3D, and seamless, so a looping cue does
    not click once a second forever.

The mono check is not pedantry. These are positional cues whose entire
job is to point somewhere; a stereo file is played as-is and stops
pointing anywhere at all, which sounds like a working feature that has
simply stopped being useful.

Usage
-----
    ./cue_sounds_test.py <engine-root>

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile
import wave

MAIN = os.path.join("src", "cgame", "cg_main.c")
GENERATOR = os.path.join("release", "make-cue-sounds.py")

PREFIX = "sound/accessibility/"

# The engine's native format for effects. A file at another rate still
# plays, but these are generated so there is no reason not to match.
EXPECT_RATE = 22050
EXPECT_CHANNELS = 1
EXPECT_WIDTH = 2

# How close to zero both ends of a loop have to sit. A loop point is a
# discontinuity; anything much above this is an audible click, once per
# cycle, for as long as the cue is running.
SEAM_LIMIT = 64


def read(root, relative, what):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - %s" % (relative, root, what))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def registered_sounds(main_c):
    """Every sound/accessibility path the mod asks the engine for."""
    found = sorted(set(re.findall(r'"(%s[a-z0-9_]+\.wav)"' % re.escape(PREFIX),
                                  main_c)))
    if not found:
        sys.exit("the mod registers no sounds under %s at all - either the "
                 "cue table is gone or it was renamed, and this test would "
                 "otherwise pass by checking nothing" % PREFIX)
    return found


def generate(library_root, outdir):
    script = os.path.join(library_root, GENERATOR)
    if not os.path.isfile(script):
        sys.exit("no %s - the sounds cannot be built from source" % GENERATOR)

    result = subprocess.run([sys.executable, script, outdir],
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("the sound generator failed:\n%s" % (result.stderr or
                                                      result.stdout))
    return sorted(name for name in os.listdir(outdir) if name.endswith(".wav"))


def inspect(path):
    """Format, and how far from zero the two ends of the loop sit."""
    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.getnframes()
        raw = handle.readframes(frames)

    problems = []
    if channels != EXPECT_CHANNELS:
        problems.append("%d channels, not mono - the engine positions a mono "
                        "source in 3D itself, and a stereo file is played as "
                        "it is, so the cue stops pointing anywhere" % channels)
    if rate != EXPECT_RATE:
        problems.append("%d Hz, expected %d" % (rate, EXPECT_RATE))
    if width != EXPECT_WIDTH:
        problems.append("%d-bit, expected %d-bit" % (width * 8,
                                                     EXPECT_WIDTH * 8))
    if frames == 0:
        problems.append("no audio at all")
        return problems, frames / float(rate or 1)

    if channels == EXPECT_CHANNELS and width == EXPECT_WIDTH:
        first = struct.unpack("<h", raw[0:2])[0]
        last = struct.unpack("<h", raw[-2:])[0]
        if max(abs(first), abs(last)) > SEAM_LIMIT:
            problems.append(
                "the loop seam is not at silence (%d/%d) - a looping cue "
                "clicks once per cycle for as long as it plays"
                % (abs(first), abs(last)))

    return problems, frames / float(rate)


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

    asked = registered_sounds(read(args.root, MAIN,
                                   "is the patch series applied?"))

    failures = []

    with tempfile.TemporaryDirectory() as first:
        produced = generate(library_root, first)

        asked_names = [path[len(PREFIX):] for path in asked]

        for name in asked_names:
            if name not in produced:
                failures.append(
                    "the mod registers %s%s but the generator does not "
                    "produce it - the engine would find nothing there and "
                    "play silence without complaining" % (PREFIX, name))

        for name in produced:
            if name not in asked_names:
                failures.append(
                    "the generator produces %s but nothing registers it - "
                    "usually a rename that landed on one side only" % name)

        for name in produced:
            problems, seconds = inspect(os.path.join(first, name))
            for problem in problems:
                failures.append("%s: %s" % (name, problem))
            if seconds <= 0.0:
                failures.append("%s: zero length" % name)

        # Determinism: the release archive's checksum has to be
        # reproducible from source, and a seeded generator that drifts
        # would move it for no visible reason.
        with tempfile.TemporaryDirectory() as second:
            generate(library_root, second)
            for name in produced:
                with open(os.path.join(first, name), "rb") as a, \
                     open(os.path.join(second, name), "rb") as b:
                    if a.read() != b.read():
                        failures.append(
                            "%s differs between two runs of the generator - "
                            "the release archive's checksum would move on "
                            "every build" % name)

    if failures:
        print("cue_sounds_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("cue_sounds_test: %s - %d generated sound(s), each registered by "
          "the mod, mono %d Hz, seamless, and identical across runs"
          % (args.engine, len(asked), EXPECT_RATE))
    return 0


if __name__ == "__main__":
    sys.exit(main())

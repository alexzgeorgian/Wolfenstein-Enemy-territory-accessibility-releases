#!/usr/bin/env python3
"""Check that the spoken ground matches the ground the engine plays.

Why this exists
---------------
A class without binoculars or a scoped weapon - which is most classes,
most of the time - had nothing at all told to it about its surroundings.
The ground is the part of them that is always underfoot, and the engine
already decides what it is made of, once per footstep, to pick which
footstep sound to play.

So the narration hangs off that same decision: the mod speaks a word
chosen by the engine's footstep type rather than by a probe of its own.
That is the whole design, and it only holds if the word and the sound
actually correspond. A table indexed by an enum is exactly the thing
that silently goes wrong when the enum gains a member in the middle, and
the failure would be a player being told they are on metal while the
game plays gravel - confidently wrong, and wrong about the one thing
they cannot check.

So this reads three things out of the engine:

  * the footstep_t enum, in order, from bg_public.h
  * the sound file the engine registers for each of those types
  * the mod's own table of words

and requires them to line up: one word per type, in the same order, each
word recognisable in the filename the engine plays for it.

That last check is what pins FOOTSTEP_NORMAL to "Stone" - the engine
loads stone1.wav through stone4.wav for it, and "Normal" would be a
word that told the player nothing.

Usage
-----
    ./footing_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

PUBLIC = os.path.join("src", "game", "bg_public.h")
MAIN = os.path.join("src", "cgame", "cg_main.c")
EVENT = os.path.join("src", "cgame", "cg_event.c")

def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an engine checkout?"
                 % (relative, root))
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


def footstep_enum(public_h):
    """FOOTSTEP_* in declaration order, without the FOOTSTEP_TOTAL marker."""
    text = strip_comments(public_h)
    match = re.search(r'typedef enum\s*\{([^}]*?FOOTSTEP_TOTAL[^}]*)\}', text,
                      re.S)
    if not match:
        sys.exit("could not find the footstep_t enum in %s - this test is "
                 "out of date with the engine, and passing without reading "
                 "it would defeat its purpose" % PUBLIC)

    names = re.findall(r'\b(FOOTSTEP_[A-Z0-9_]+)\b', match.group(1))

    if names[-1] != "FOOTSTEP_TOTAL":
        sys.exit("FOOTSTEP_TOTAL is no longer last in footstep_t (%s) - the "
                 "mod sizes its table by it and uses it as the 'no sound' "
                 "marker, so both of those assumptions are now wrong"
                 % ", ".join(names))

    return names[:-1]


def footstep_sounds(main_c):
    """FOOTSTEP_* -> the sound filename stem the engine registers for it."""
    # The footstep sounds are registered through a Com_sprintf into a
    # scratch buffer inside a loop, so the filename lives in the sprintf
    # and the type in the assignment that follows it.
    sounds = dict(
        (name, stem)
        for stem, name in re.findall(
            r'"sound/player/footsteps/([a-z_]+)%i\.wav"[^;]*;\s*'
            r'cgs\.media\.footsteps\[\s*(FOOTSTEP_[A-Z0-9_]+)\s*\]',
            main_c, re.S))

    if not sounds:
        sys.exit("could not read any footstep sound registrations out of %s "
                 "- this test is out of date with the engine, and passing "
                 "without reading them would defeat its purpose" % MAIN)

    return sounds


def mod_words(event_c):
    """The mod's spoken word per footstep type, in table order."""
    text = strip_comments(event_c)
    start = text.find("eta_footstepNames[FOOTSTEP_TOTAL]")
    if start < 0:
        sys.exit("could not find eta_footstepNames in %s - the narration "
                 "this test exists to guard is gone" % EVENT)

    body = text[start:text.index("};", start)]
    return re.findall(r'"([^"]+)"', body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=["etlegacy", "id-software"])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    order = footstep_enum(read(root, PUBLIC))
    # The comments beside each word are what pairs them with the enum, so
    # the mod's table is read with comments intact and the words alone are
    # matched positionally - the comments are documentation, not the link.
    words = mod_words(read(root, EVENT))
    sounds = footstep_sounds(read(root, MAIN))

    print("[footing] engine has %d footstep type(s): %s"
          % (len(order), ", ".join(order)))
    print("[footing] mod supplies %d word(s): %s"
          % (len(words), ", ".join(words)))

    failures = []

    if len(words) != len(order):
        failures.append(
            "the engine has %d footstep types and the mod has %d words. The "
            "table is indexed by the type itself, so a mismatch means every "
            "word past the difference names the wrong surface"
            % (len(order), len(words)))
        order = order[:len(words)]

    for index, (name, word) in enumerate(zip(order, words)):
        stem = sounds.get(name)

        if stem is None:
            failures.append(
                "the engine registers no footstep sound for %s, so there is "
                "nothing to check %r against - either the engine changed or "
                "this test can no longer read it" % (name, word))
            continue

        # Substring either way, so "Wood" matches wood*.wav and "Stone"
        # matches stone*.wav without the test having to carry a
        # translation table of its own - a table that would be the
        # obvious place to hide exactly the mistake this is looking for.
        wanted = word.lower()

        if wanted not in stem and stem not in wanted:
            failures.append(
                "%s (index %d) plays %s*.wav but the mod says %r - a player "
                "told one thing while hearing another has no way to tell "
                "which is right" % (name, index, stem, word))
            continue

        print("[footing]   %-18s %-10s plays %s*.wav"
              % (name, repr(word), stem))

    if failures:
        print()
        for failure in failures:
            print("[footing] FAIL %s" % failure)
        sys.exit(1)

    print("[footing] ok")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check the scope narration reads a live flag and is not cut off.

Why this exists
---------------
A tester reported the binoculars working and the scope saying nothing -
no announcement, no description of the view. Two separate defects, one
per engine, both invisible to every other check here.

**The flag nothing writes.** The 2010 tree declares `cg.zoomed` *and*
`cg.zoomedScope` in cg_local.h and assigns only the second one;
`CG_SetSniperZoom` sets it for WP_FG42SCOPE, WP_GARAND_SCOPE and
WP_K43_SCOPE. The mirror read `cg.zoomed`, which nothing in that client
ever sets, so its scope branch was unreachable. It compiled, linked and
passed everything.

**The report that purged the report.** Scoping a rifle is a weapon
change in both engines - WP_FG42 and WP_FG42_SCOPE are different
weapons. The zoom flag flips the instant the key is pressed, so the
scope line goes out immediately; the playerstate's weapon catches up a
few hundred milliseconds later and the weapon narration then spoke a
*second* report, which the speech backend delivers by purging the first.
The scope line is the longer one, so it was the one destroyed - and the
name replacing it was identical before and after, because a scoped
weapon carries its parent's description.

That is why the binoculars were fine: +zoom changes no weapon, so
nothing arrives afterwards to cut it off.

So this requires, on each engine, that:

  * the flag the zoom narration reads is one the engine actually assigns
  * the weapon narration declines to speak on a scope toggle

Usage
-----
    ./zoom_state_test.py <engine-root> [--engine etlegacy|id-software]
"""

import argparse
import os
import re
import sys


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this the engine checkout this test "
                 "expects?" % (relative, root))
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


def zoom_flag_read(draw_c):
    """The cg.* flag the scope branch of ETA_NarrateZoom tests."""
    text = strip_comments(draw_c)
    start = text.find("ETA_ZOOM_SCOPE;")
    if start < 0:
        sys.exit("could not find the scope branch of the zoom narration - "
                 "this test is out of date with the mod, and passing "
                 "without reading it would defeat its purpose")

    # The `else if (cg.X)` immediately before it.
    window = text[max(0, start - 200):start]
    flags = re.findall(r'cg\.(\w+)', window)
    if not flags:
        sys.exit("could not read which flag the scope branch tests")
    return flags[-1]


def assigned_flags(root, files):
    """Every cg.<field> the client assigns to, across the given files."""
    found = set()
    for relative in files:
        path = os.path.join(root, relative)
        if not os.path.isfile(path):
            continue
        with open(path, "r", errors="replace") as handle:
            body = strip_comments(handle.read())
        for m in re.finditer(r'cg\.(\w+)\s*(?:=[^=]|\+=|-=)', body):
            found.add(m.group(1))
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--engine", default="etlegacy",
                        choices=["etlegacy", "id-software"])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    failures = []

    cgame = os.path.join("src", "cgame")
    sources = [os.path.join(cgame, f) for f in os.listdir(
        os.path.join(root, cgame)) if f.endswith(".c")]

    flag = zoom_flag_read(read(root, os.path.join(cgame, "cg_draw.c")))
    written = assigned_flags(root, sources)

    print("[zoom] the scope branch reads cg.%s" % flag)

    if flag not in written:
        failures.append(
            "nothing in the client ever assigns cg.%s, so the scope branch "
            "can never be taken and every scope is silent. The 2010 tree "
            "declares cg.zoomed and cg.zoomedScope and writes only the "
            "second" % flag)
    else:
        print("[zoom] cg.%s is assigned by the engine - the branch is live"
              % flag)

    # The weapon narration must stand down on a scope toggle, or its
    # report purges the scope report a few hundred ms later.
    if args.engine == "etlegacy":
        guard_file = os.path.join(cgame, "cg_draw.c")
        marker = "WEAPON_TYPE_SCOPED"
    else:
        guard_file = os.path.join(cgame, "cg_playerstate.c")
        marker = "ETA_IsScopeToggle"

    whole = strip_comments(read(root, guard_file))

    speaks = whole.find("ETA_HudNarrator_SpeakWeapon")
    if speaks < 0:
        sys.exit("could not find the weapon announcement in %s - this test "
                 "is out of date with the mod" % guard_file)

    # Scope this to the function that makes the announcement, from its
    # start to the call. Three narrower or wider readings were wrong
    # first:
    #
    #   the whole file  - passed on the engine's own use of the constant
    #   a byte window   - passed on the mod's helper being defined nearby
    #   the nearest if  - failed on ET: Legacy, which guards with an
    #                     early return rather than an inline condition
    #
    # A function-sized region accepts both shapes and excludes both
    # neighbours, because a guard that is not in this function cannot be
    # holding this call back.
    start = whole.rfind("\n}\n", 0, speaks)
    guard = whole[start if start >= 0 else 0:speaks]

    if marker not in guard:
        failures.append(
            "%s announces a weapon change without excluding a scope toggle "
            "(no %s), so scoping speaks the weapon again a few hundred "
            "milliseconds after the scope line and purges it mid-sentence"
            % (guard_file, marker))
    else:
        print("[zoom] %s stands down on a scope toggle" % guard_file)

    if failures:
        print()
        for failure in failures:
            print("[zoom] FAIL %s" % failure)
        sys.exit(1)

    print("[zoom] ok")


if __name__ == "__main__":
    main()

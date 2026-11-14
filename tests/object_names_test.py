#!/usr/bin/env python3
"""Check nothing the narrator meets is called "Object".

The tester heard "Object" on several maps, again and again, instead of
what the thing was: whatever a trace met that was not a player, the
map's walls or a thing with a name of its own was called that - the
binoculars' and the scope's report, the look keys and the obstacle
callout all share ETA_DescribeTraceHit in cg_draw.c. This checks:

- the word "Object" is never said for anything;
- the kinds of thing the game knows - a mounted gun, a cabinet, a
  landmine or dynamite, a construction, a dynamite target, a body - are
  said by name, a construction and a dynamite target with the objective
  they belong to;
- a part of the map with no name of its own is said as the wall or
  ground it is, with the objective close by when there is one.

    ./object_names_test.py <engine-root>
"""

import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function_body(text, name):
    match = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return ""
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    failures = []

    hit = strip_comments(function_body(draw, "ETA_DescribeTraceHit"))
    kinds = strip_comments(function_body(draw, "ETA_EntityKindName"))
    if not hit or not kinds:
        sys.exit("no ETA_DescribeTraceHit or ETA_EntityKindName in %s - the naming this test "
                 "checks is gone" % DRAW)

    code = strip_comments(draw)
    if re.search(r'"Object"', code):
        failures.append('"Object" is still said for something')
    else:
        print('[names] "Object" is said for nothing')

    for kind, said in (("ET_MG42_BARREL", "Mounted machine gun"), ("ET_CABINET_H", "Health cabinet"),
                       ("ET_CABINET_A", "Ammo cabinet"), ("WP_LANDMINE", "Landmine"),
                       ("WP_DYNAMITE", "Dynamite"), ("ET_CORPSE", "Body"),
                       ("ET_AAGUN", "Anti-aircraft gun"), ("ET_ALARMBOX", "Alarm box")):
        if kind not in kinds or '"%s"' % said not in kinds:
            failures.append("%s is not said as %r" % (kind, said))
    for kind, said in (("ET_CONSTRUCTIBLE", "construction"), ("ET_EXPLOSIVE", "dynamite target")):
        if kind not in kinds or ('"%%s, %s"' % said) not in kinds:
            failures.append("%s is not said with the objective it belongs to" % kind)
    if not [f for f in failures if "said" in f and "Object" not in f]:
        print("[names] guns, cabinets, mines, bodies, constructions and targets are said by name")

    if "ETA_EntityKindName(es, trace->endpos, out, outSize)" not in hit \
            or "ETA_DescribeSurface(trace, surface, sizeof(surface));" not in hit \
            or "ETA_ObjectiveNear(trace->endpos)" not in hit:
        failures.append("a part of the map with no name is not said as the wall or ground it is, "
                        "with the objective close by")
    else:
        print("[names] a nameless part of the map is said as its wall or ground, with the objective close by")

    if failures:
        for failure in failures:
            print("[names] FAIL %s" % failure)
        sys.exit(1)
    print("object_names_test: what the narrator meets is said as what it is")


if __name__ == "__main__":
    main()

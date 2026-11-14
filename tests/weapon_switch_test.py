#!/usr/bin/env python3
"""Check that silencing the scope toggle silenced only the scope toggle.

Why this exists
---------------
Raising a rifle's scope is a weapon change in this engine: WP_FG42 and
WP_FG42_SCOPE are two different weapons, each the other's weapAlts. The
mod used to announce that as a weapon change, which arrived a few hundred
milliseconds after the zoom narration had already said "Scope" and
described the view - and destroyed it, because the second report was
delivered by cutting off the first. That was the silent scope, and the
fix was to stop treating a scope toggle as a weapon change.

The danger in that fix is over-reach, and the tester asked the exact
right question about it: does switching weapons with the number keys
still work? Because weapAlts is not only used for scopes. A mortar and a
machine gun being set down, and a rifle grenade being fitted, are the
same kind of pairing - and those have no zoom narration covering them, so
for them the weapon report is the only announcement there is. Silencing
them would make setting up a mortar completely silent, and nothing about
that failure is visible from the code that caused it.

So this walks the engine's own weapon table, works out every pair of
weapons that are mutually each other's weapAlts, and splits them by
whether the engine marks one side scoped. Then it requires:

  * every scoped pair to be covered - the engine's zoom state follows
    exactly the weapons it marks scoped, so the zoom narration speaks for
    each one that this suppression silences;
  * the zoom narration to announce leaving a scope as well as entering
    one, or coming out of a scope would be the new silence;
  * every non-scoped pair to still be announced as a weapon change.

The two engines reach the same place by different routes - ET: Legacy has
a weapon-type flag to test, the 2010 release has three named weapons in a
switch - so this checks each one the way that tree actually works.

Usage
-----
    ./weapon_switch_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

MISC = os.path.join("src", "game", "bg_misc.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
VIEW = os.path.join("src", "cgame", "cg_view.c")
WEAPONS = os.path.join("src", "cgame", "cg_weapons.c")
PLAYERSTATE = os.path.join("src", "cgame", "cg_playerstate.c")


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


def weapon_table(misc_c):
    """WP_* -> its table row, split on top-level commas."""
    lines = misc_c.split("\n")
    start = None
    for index, line in enumerate(lines):
        if "weaponTable[WP_NUM_WEAPONS]" in line:
            start = index
            break
    if start is None:
        sys.exit("could not find weaponTable in %s - this test walks it to "
                 "decide which pairs may be silenced, and cannot do that "
                 "without it" % MISC)

    rows = {}
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped.startswith("{ WP_"):
            continue
        body = stripped[1:stripped.rindex("},")] if "}," in stripped \
            else stripped[1:]

        fields, depth, current = [], 0, ""
        for char in body:
            if char in "{(":
                depth += 1
            elif char in ")}":
                depth -= 1
            if char == "," and depth == 0:
                fields.append(current.strip())
                current = ""
            else:
                current += char
        fields.append(current.strip())
        rows[fields[0]] = fields

    if len(rows) < 20:
        sys.exit("read only %d weapons out of the table - the parse is "
                 "wrong and a pass here would mean nothing" % len(rows))
    return rows


def weapon_type(fields):
    for field in fields:
        if field.startswith("WEAPON_TYPE_"):
            return field
    return ""


def mutual_pairs(rows):
    """Pairs of weapons that are each other's weapAlts, split by scoped-ness."""
    scoped, plain = set(), set()
    for name, fields in rows.items():
        alt = fields[4]
        if alt == name or alt not in rows:
            continue
        if rows[alt][4] != name:
            continue
        pair = tuple(sorted((name, alt)))
        if "SCOPED" in weapon_type(fields) or "SCOPED" in weapon_type(rows[alt]):
            scoped.add(pair)
        else:
            plain.add(pair)
    return scoped, plain


def narrate_weapon_change(draw_c):
    text = strip_comments(draw_c)
    start = text.find("ETA_NarrateWeaponChange")
    if start < 0:
        sys.exit("could not find ETA_NarrateWeaponChange in %s" % DRAW)
    end = text.find("\n}", start)
    return text[start:end]


def zoom_says_off(draw_c):
    """Whether the zoom narration announces leaving a scope, not only entering."""
    text = strip_comments(draw_c)
    start = text.find("ETA_NarrateZoom")
    if start < 0:
        sys.exit("could not find ETA_NarrateZoom in %s - the suppression "
                 "this test checks is only safe because that function "
                 "speaks instead" % DRAW)
    body = text[start:text.find("\n}", start)]
    return "ETA_ZOOM_OFF" in body and "SpeakZoom" in body


def check_etlegacy(root, failures):
    rows = weapon_table(read(root, MISC, "is this an engine checkout?"))
    scoped, plain = mutual_pairs(rows)

    if not scoped:
        sys.exit("found no scoped weapAlts pairs in the weapon table - the "
                 "suppression under test would have nothing to silence, so "
                 "a pass would be meaningless")

    body = narrate_weapon_change(read(root, DRAW,
                                      "is the patch series applied?"))

    # The suppression must be restricted by the engine's own scoped flag.
    if "WEAPON_TYPE_SCOPED" not in body:
        failures.append(
            "ETA_NarrateWeaponChange silences weapAlts pairs without "
            "testing WEAPON_TYPE_SCOPED, so it also silences %s - and none "
            "of those have zoom narration to speak for them"
            % ", ".join("%s/%s" % pair for pair in sorted(plain)))

    # And it must require the pairing to be mutual, both ways round.
    if body.count("weapAlts") < 2:
        failures.append(
            "ETA_NarrateWeaponChange does not check weapAlts in both "
            "directions - a one-way match silences changes between weapons "
            "that are not a toggle at all")

    # The engine's zoom state has to follow the same flag, or the pairs
    # being silenced here are not actually covered by the zoom narration.
    view = strip_comments(read(root, VIEW, "is this an engine checkout?"))
    # CG_ZoomIn_f and CG_ZoomOut_f are defined first and both start with
    # this name, so an ordinary find lands in the wrong function - which
    # is how an earlier version of this test reported CG_Zoom broken when
    # it was fine.
    match = re.search(r'\bvoid\s+CG_Zoom\s*\(\s*void\s*\)', view)
    start = match.start() if match else -1
    if start < 0:
        failures.append("could not find CG_Zoom in %s" % VIEW)
    else:
        zoom_body = view[start:view.find("\n}", start)]
        if "WEAPON_TYPE_SCOPED" not in zoom_body or "cg.zoomed" not in zoom_body:
            failures.append(
                "CG_Zoom no longer sets cg.zoomed from WEAPON_TYPE_SCOPED - "
                "the scope toggles this suppression silences are then "
                "covered by nothing at all")

    return scoped, plain


def check_id_software(root, failures):
    """The 2010 tree names its scoped weapons instead of flagging them."""
    weapons = strip_comments(read(root, WEAPONS,
                                  "is this an engine checkout?"))
    start = weapons.find("CG_SetSniperZoom")
    if start < 0:
        sys.exit("could not find CG_SetSniperZoom in %s - it is what decides "
                 "which weapons zoom in this tree" % WEAPONS)

    body = weapons[start:weapons.find("\n}", start)]

    # The weapons that actually raise a scope are the ones this function
    # turns the scope on for.
    # Split the switch into its cases by hand. A regular expression with
    # a negated character class cannot do this - the text being skipped
    # contains the very letters the class has to exclude, which is how an
    # earlier version of this test read no weapons at all and said so.
    engine_scoped = set()
    cases = list(re.finditer(r'case\s+(WP_[A-Z0-9_]+)\s*:', body))
    for index, case in enumerate(cases):
        end = cases[index + 1].start() if index + 1 < len(cases) else len(body)
        # Any non-zero value: this tree stores a fade time in the same
        # field, so the FG 42 scope sets 1 while the Garand and K43
        # scopes set 900. Matching the literal 1 finds only the first,
        # which is how an earlier version of this test accused the mod of
        # silencing two weapons the engine does scope.
        assigned = re.search(r'zoomedScope\s*=\s*([0-9]+)',
                             body[case.end():end])
        if assigned and int(assigned.group(1)) != 0:
            engine_scoped.add(case.group(1))

    if not engine_scoped:
        sys.exit("read no scoped weapons out of CG_SetSniperZoom - a pass "
                 "here would mean nothing")

    state = strip_comments(read(root, PLAYERSTATE,
                                "is the patch series applied?"))
    match = re.search(r'scoped\s*\[\s*\]\s*=\s*\{([^}]*)\}', state)
    if not match:
        failures.append(
            "could not find the mod's list of scoped weapons in %s - the "
            "scope toggle is silenced by naming them, so the list is the "
            "whole of the restriction" % PLAYERSTATE)
        return set(), set()

    mod_scoped = set(re.findall(r'\bWP_[A-Z0-9_]+\b', match.group(1)))

    if mod_scoped != engine_scoped:
        failures.append(
            "the mod silences the scope toggle for %s, but the engine "
            "raises a scope for %s - anything in the first list and not "
            "the second is a weapon change silenced with nothing speaking "
            "in its place"
            % (", ".join(sorted(mod_scoped)), ", ".join(sorted(engine_scoped))))

    return {(name, name) for name in engine_scoped}, set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    args = parser.parse_args()

    failures = []

    if args.engine == "etlegacy":
        scoped, plain = check_etlegacy(args.root, failures)
    else:
        scoped, plain = check_id_software(args.root, failures)

    # Whichever tree, coming out of a scope must still say something, or
    # the fix for the silent scope created a silent unscope.
    if not zoom_says_off(read(args.root, DRAW, "is the patch series applied?")):
        failures.append(
            "the zoom narration no longer announces ETA_ZOOM_OFF - "
            "lowering a scope is silenced as a weapon change and would "
            "then be announced by nothing at all")

    if failures:
        print("weapon_switch_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("weapon_switch_test: %s - %d scope toggle(s) silenced and spoken "
          "for by the zoom narration; %d other weapAlts pair(s) still "
          "announced as weapon changes%s"
          % (args.engine, len(scoped), len(plain),
             (" (" + ", ".join("%s/%s" % pair for pair in sorted(plain)) + ")")
             if plain else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

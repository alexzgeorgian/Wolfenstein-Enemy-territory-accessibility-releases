#!/usr/bin/env python3
"""Check that every weapon a player can hold has a name to speak.

Why this exists
---------------
Grenades announced their ammo and no name at all. Both grenades have an
empty `desc` in the engine's weapon table, the mod passed that empty
string to the narrator, the input guard correctly refused it, and the
player was left with half a report. It shipped, and only a play session
found it.

Grenades were merely the pair everyone carries. Fifteen of the
fifty-five weapons have no `desc`, and the rest of that list is class
signature kit - the medic's health packs, the engineer's landmines, the
covert ops' scoped rifles, the field ops' smoke marker. Every one of
them would have been silent in the same way, waiting for somebody to
play that class.

The mod now falls back to the item's pickup name, and supplies a name
itself for the two the engine only names with an internal token. That is
three sources, and a weapon added upstream could miss all three without
anything noticing - which is precisely how this got here.

So this walks every weapon a player can actually select, resolves the
name the mod would speak using the same three sources in the same order,
and fails if any comes out empty or obviously not a name.

"Can actually select" is the engine's own list, not a guess: the weapon
bank table the number keys use, plus each of those weapons' alternates -
scopes, silencers, akimbo, set-up modes - since those are what the
player's hands end up holding.

The other half of this test is the opposite defect. Preferring `desc`
meant the medic's syringe announced itself as "MEDIC" - the class, not
the weapon - followed by an ammo count, and a medic had no way to tell
it apart by ear from the health pack they were also carrying. The mod
now skips `desc` for that one weapon and falls through to the engine's
own pickup name, "Syringe".

A hand-written skip list is exactly the sort of thing that rots, and the
tempting general rule - "prefer the pickup name when it is longer" -
is actively wrong: it renames the Sten to "Sten gun", the FG 42 to
"FG 42 Paratroop Rifle Scope" and dynamite to "Dynamite Weapon". So the
rule is narrow and checkable: skip `desc` only where it is one of the
engine's own player class names. This test derives that set from
BG_ClassnameForNumber and requires the mod's list to match it exactly,
in both directions.

Usage
-----
    ./weapon_name_test.py <engine-root>

Run it against an ET: Legacy checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

MISC = os.path.join("src", "game", "bg_misc.c")
WEAPONS = os.path.join("src", "cgame", "cg_weapons.c")
CLASSES = os.path.join("src", "game", "bg_classes.c")

# A name that is really an internal token rather than something to say.
TOKENISH = re.compile(r'^(nopickup|BLANK$|[a-z]+[A-Z])')


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


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an ET: Legacy checkout?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def weapon_table(misc):
    """Per weapon: its item id, its desc, and its listed alternates."""
    start = misc.index("weaponTable_t weaponTable[WP_NUM_WEAPONS] =")
    body = misc[start:misc.index("\n};", start)]

    table = {}
    for line in body.splitlines():
        head = re.match(r'\s*\{\s*(WP_[A-Z0-9_]+)\s*,\s*(ITEM_[A-Z0-9_]+)\s*,', line)
        if not head:
            continue
        desc = re.search(r'"([^"]*)"\s*,\s*WS_[A-Z0-9_]+', line)
        alts = re.findall(r'\bWP_[A-Z0-9_]+\b', line)
        table[head.group(1)] = {
            "item": head.group(2),
            "desc": desc.group(1) if desc else None,
            "alts": alts,
        }

    if not table:
        sys.exit("could not read weaponTable out of %s - this test is out of "
                 "date with the engine, and passing without reading it would "
                 "defeat its purpose" % MISC)
    return table


def pickup_names(misc):
    """item id -> the pickup name the engine gives it."""
    il = misc[misc.index("gitem_t bg_itemlist[]"):]
    names, current = {}, None
    for line in il.splitlines():
        head = re.match(r'\s*(ITEM_[A-Z0-9_]+),\s*$', line)
        if head:
            current = head.group(1)
            continue
        if current:
            pick = re.match(r'\s*"([^"]*)",\s*//\s*pickup', line)
            if pick:
                names[current] = pick.group(1)
                current = None
    return names


def selectable(weapons_c, table):
    """Weapons reachable from the number keys, plus their alternates."""
    if "weapon_t weapBanksMultiPlayer" not in weapons_c:
        sys.exit("could not find weapBanksMultiPlayer in %s - this test is "
                 "out of date with the engine, and passing without reading "
                 "it would defeat its purpose" % WEAPONS)
    banks = weapons_c[weapons_c.index("weapon_t weapBanksMultiPlayer"):]
    banks = banks[:banks.index("\n};")]

    reachable = set()
    for weapon in re.findall(r'\bWP_[A-Z0-9_]+\b', banks):
        reachable.add(weapon)

    # Alternates: a scoped rifle or a set-up MG is what the hands hold.
    for weapon in list(reachable):
        for alt in table.get(weapon, {}).get("alts", []):
            reachable.add(alt)

    reachable.discard("WP_NONE")
    return sorted(w for w in reachable if w in table)


def class_names(classes_c):
    """The engine's own player class names, from BG_ClassnameForNumber."""
    text = strip_comments(classes_c)
    start = text.find("BG_ClassnameForNumber(int classNum)")
    if start < 0:
        sys.exit("could not find BG_ClassnameForNumber in %s - this test is "
                 "out of date with the engine, and passing without reading "
                 "it would defeat its purpose" % CLASSES)
    body = text[start:text.index("\n}", start)]
    names = {n.lower() for n in re.findall(r'return\s+"([^"^]+)"', body)}

    if len(names) < 5:
        sys.exit("read only %d class name(s) out of BG_ClassnameForNumber "
                 "- expected the five ET classes" % len(names))
    return names


def mod_skips_desc(weapons_c):
    """Weapons the mod refuses to name from `desc`."""
    text = strip_comments(weapons_c)
    start = text.find("CG_AccessibilityDescriptionNamesTheWeapon(weapon_t weap)")
    if start < 0:
        sys.exit("could not find CG_AccessibilityDescriptionNamesTheWeapon in "
                 "%s - the syringe fix this test exists to guard is gone"
                 % WEAPONS)
    body = text[start:text.index("\n}", start)]
    return set(re.findall(r'weap\s*!=\s*(WP_[A-Z0-9_]+)', body))


def mod_fallbacks(weapons_c):
    """The names the mod supplies itself."""
    text = strip_comments(weapons_c)
    start = text.find("eta_weaponNameFallbacks")
    if start < 0:
        sys.exit("could not find eta_weaponNameFallbacks in %s - the fallback "
                 "this test exists to guard is gone" % WEAPONS)
    body = text[start:text.index("};", start)]
    return dict(re.findall(r'\{\s*(WP_[A-Z0-9_]+)\s*,\s*"([^"]*)"\s*\}', body))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    misc = read(root, MISC)
    weapons_c = read(root, WEAPONS)
    classes_c = read(root, CLASSES)

    table = weapon_table(misc)
    pickups = pickup_names(misc)
    fallbacks = mod_fallbacks(weapons_c)
    skipped = mod_skips_desc(weapons_c)
    classes = class_names(classes_c)
    reachable = selectable(weapons_c, table)

    print("[weapons] %d weapon(s) in the table, %d reachable from the banks"
          % (len(table), len(reachable)))
    print("[weapons] mod supplies %d fallback name(s): %s"
          % (len(fallbacks), ", ".join(sorted(fallbacks)) or "none"))

    failures = []
    from_desc = from_fallback = from_pickup = 0

    # Which weapons the engine's own data says are mislabelled: `desc` is
    # one of its player class names rather than the weapon's.
    expected_skips = {
        weapon for weapon, entry in table.items()
        if (entry["desc"] or "").lower() in classes
    }

    print("[weapons] engine class names: %s" % ", ".join(sorted(classes)))
    print("[weapons] desc names a class for: %s"
          % (", ".join(sorted(expected_skips)) or "nothing"))
    print("[weapons] mod skips desc for:    %s"
          % (", ".join(sorted(skipped)) or "nothing"))

    for weapon in sorted(expected_skips - skipped):
        failures.append(
            "%s has desc %r, which is one of the engine's player class "
            "names, so it would be announced as a class rather than a "
            "weapon - the mod must skip its desc"
            % (weapon, table[weapon]["desc"]))

    for weapon in sorted(skipped - expected_skips):
        failures.append(
            "the mod skips %s's desc %r, but that is not one of the "
            "engine's class names - the skip list may only hold weapons "
            "the engine itself mislabels, or it becomes the mod renaming "
            "things upstream named correctly"
            % (weapon, table.get(weapon, {}).get("desc")))

    # Skipping only helps if there is something better to fall through to.
    for weapon in sorted(skipped & set(table)):
        landing = pickups.get(table[weapon]["item"], "")
        if not landing:
            failures.append(
                "%s's desc is skipped but its item %s has no pickup name, "
                "so it would be announced as %r - a skip has to land on a "
                "real name" % (weapon, table[weapon]["item"], "Weapon"))
        elif TOKENISH.match(landing):
            failures.append(
                "%s's desc is skipped and it falls through to %r, which is "
                "an internal token rather than a name"
                % (weapon, landing))
        else:
            print("[weapons]   %-24s -> %r (pickup name, desc %r skipped)"
                  % (weapon, landing, table[weapon]["desc"]))

    for weapon in reachable:
        entry = table[weapon]

        if entry["desc"] and weapon not in skipped:
            from_desc += 1
            continue

        if weapon in skipped:
            # Already reported above, and checked there.
            from_pickup += 1
            continue

        if weapon in fallbacks:
            from_fallback += 1
            print("[weapons]   %-24s -> %r (mod)" % (weapon, fallbacks[weapon]))
            continue

        name = pickups.get(entry["item"], "")

        if not name:
            failures.append(
                "%s has no desc, no mod fallback, and its item %s has no "
                "pickup name - it would be announced with no name at all, "
                "which is how the grenades shipped"
                % (weapon, entry["item"]))
            continue

        if TOKENISH.match(name):
            failures.append(
                "%s would be announced as %r, which is an internal token "
                "rather than a name - it needs an entry in "
                "eta_weaponNameFallbacks" % (weapon, name))
            continue

        from_pickup += 1
        print("[weapons]   %-24s -> %r (pickup name)" % (weapon, name))

    print("[weapons] named by the engine's description: %d, by pickup name: "
          "%d, by the mod: %d" % (from_desc, from_pickup, from_fallback))

    if failures:
        print()
        for failure in failures:
            print("[weapons] FAIL %s" % failure)
        sys.exit(1)

    print("[weapons] ok")


if __name__ == "__main__":
    main()

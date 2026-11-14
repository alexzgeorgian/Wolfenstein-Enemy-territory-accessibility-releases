#!/usr/bin/env python3
"""Check that the weapon banks the mod takes over are still dead.

Why this exists
---------------
The mod installs its own key bindings and has one rule that makes that
safe: it never replaces a binding the player already has. There is
exactly one exception. Keys 9 and 0 are bound by the stock config to
`weaponbank 9` and `weaponbank 10`, and neither command can do anything:

- `CG_WeaponBank_f` rejects any bank outside 1..MAX_WEAP_BANKS_MP-1.
  With MAX_WEAP_BANKS_MP at 10, `weaponbank 10` is thrown out before it
  reaches the table, so the 0 key has never done anything at all.
- Bank 9's row in `weapBanksMultiPlayer` is empty, so `weaponbank 9`
  resolves to no weapon.

Every letter A-Z is bound by the stock config, so those two dead keys
are the only ones within reach of the movement hand that cost a player
nothing. Taking them is right *while they stay dead*.

That is an assumption about somebody else's engine, and assumptions rot.
If ET: Legacy ever fills bank 9, or raises the bank ceiling so bank 10
becomes reachable, the mod would start silently stealing a key that had
begun doing something real - and the player would find their weapon
missing mid-match with no way to tell why.

So this fails the build instead. It reads both facts out of the engine
being built against, not out of a note in a comment.

Usage
-----
    ./weapon_bank_test.py <engine-root>

Run it against an ET: Legacy tree. It exits non-zero if either bank has
come alive.
"""

import argparse
import os
import re
import sys

WEAPONS = os.path.join("src", "cgame", "cg_weapons.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")

# The keys the mod claims, and the command each must still be.
CLAIMED = [("9", 9), ("0", 10)]

MAX_BANKS = re.compile(r'#define\s+MAX_WEAP_BANKS_MP\s+(\d+)')
GUARD = re.compile(r'bank\s*<=\s*0\s*\|\|\s*bank\s*>=\s*MAX_WEAP_BANKS_MP')
TABLE = re.compile(r'weapon_t\s+weapBanksMultiPlayer\s*\[[^\]]*\]\s*\[[^\]]*\]\s*=\s*\{(.*?)\n\};',
                   re.DOTALL)


def rows(text):
    """The bank table's rows, in order, as lists of entries."""
    match = TABLE.search(text)
    if not match:
        sys.exit("could not find weapBanksMultiPlayer in %s - this test is "
                 "out of date with the engine, and passing without reading "
                 "the table would defeat its purpose" % WEAPONS)

    out = []
    for line in match.group(1).splitlines():
        line = line.split("//", 1)[0].strip()
        if not line.startswith("{"):
            continue
        body = line[1:line.rindex("}")] if "}" in line else line[1:]
        out.append([e.strip() for e in body.split(",") if e.strip()])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    weapons_path = os.path.join(root, WEAPONS)
    local_path = os.path.join(root, LOCAL)

    for path in (weapons_path, local_path):
        if not os.path.isfile(path):
            sys.exit("no %s under %s - is this an ET: Legacy checkout?"
                     % (os.path.relpath(path, root), root))

    with open(weapons_path, "r", errors="replace") as handle:
        weapons = handle.read()
    with open(local_path, "r", errors="replace") as handle:
        local = handle.read()

    limit = MAX_BANKS.search(local)
    if not limit:
        sys.exit("could not read MAX_WEAP_BANKS_MP from %s" % LOCAL)
    limit = int(limit.group(1))

    if not GUARD.search(weapons):
        sys.exit("CG_WeaponBank_f no longer rejects out-of-range banks the "
                 "way this test expects - the reasoning behind claiming the "
                 "0 key has changed and needs re-checking by hand")

    table = rows(weapons)
    print("[banks] MAX_WEAP_BANKS_MP = %d, %d row(s) in weapBanksMultiPlayer"
          % (limit, len(table)))

    failures = []

    for key, bank in CLAIMED:
        if bank >= limit:
            print("[banks]   key %s -> weaponbank %d: out of range (>= %d), dead"
                  % (key, bank, limit))
            continue

        if bank >= len(table):
            failures.append("weaponbank %d is within range but the table has "
                            "no row %d - this test cannot tell whether key %s "
                            "is safe to take" % (bank, bank, key))
            continue

        entries = [e for e in table[bank] if e != "0"]
        if entries:
            failures.append("weaponbank %d now holds %s, so key %s is no "
                            "longer a dead key - the mod must stop claiming "
                            "it, or claim it only with the player's consent"
                            % (bank, ", ".join(entries), key))
        else:
            print("[banks]   key %s -> weaponbank %d: empty row, dead"
                  % (key, bank))

    if failures:
        print()
        for failure in failures:
            print("[banks] FAIL %s" % failure)
        sys.exit(1)

    print("[banks] ok")


if __name__ == "__main__":
    main()

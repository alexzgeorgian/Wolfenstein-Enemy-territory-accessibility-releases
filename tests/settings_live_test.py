#!/usr/bin/env python3
"""Check a setting changed mid-game is actually read.

Why this exists
---------------
Registering a cvar fills the module's own copy of it exactly once. The
engine does not push later changes into that copy - something has to ask,
with trap_Cvar_Update, and if nothing does, the module goes on reading the
value it was handed when the map loaded.

Every one of this mod's settings was in that state on ET: Legacy. A player
could turn the door cues off from the console, see the new value stored,
see it in their config, and hear the door cues carry on exactly as before
until the map changed. It compiled, it stored the value, and it did
nothing - the same shape of failure as narration wired to a backend nobody
started.

The 2010 tree never had it, which is the interesting part: it put its
settings in the engine's own cvarTable, and CG_UpdateCvars walks that
table every frame. ET: Legacy's registered them separately, outside the
table, and nothing walked them. One mod, two integrations, one defect.

So this checks the property rather than either mechanism: every setting
the mod registers must be refreshed by something that runs per frame.

Usage
-----
    ./settings_live_test.py <engine-root> [--engine etlegacy|id-software]
"""

import argparse
import os
import re
import sys

MAIN = os.path.join("src", "cgame", "cg_main.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")

REFRESHER = "ETA_UpdateAccessibilitySettings"


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
        sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return strip_comments(handle.read())


def block_of(text, opener):
    """The braced block introduced by `opener`."""
    at = text.find(opener)
    if at < 0:
        return None
    brace = text.find("{", at)
    if brace < 0:
        return None
    depth, i = 0, brace
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace:i + 1]
        i += 1
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    main_c = read(root, MAIN)
    draw_c = read(root, DRAW)

    failures = []

    # Every eta_ setting the module holds a vmCvar_t for. The cue sounds
    # are deliberately not in this list: ETA_CueSound updates each one as
    # it resolves it, which is its own working refresh.
    declared = set(re.findall(r'^vmCvar_t\s+(eta_\w+)\s*;', main_c, re.M))

    if not declared:
        sys.exit("found no eta_ settings in %s - this test is out of date "
                 "with the mod, and passing without reading them would "
                 "defeat its purpose" % MAIN)

    print("[settings] %d setting(s): %s"
          % (len(declared), ", ".join(sorted(declared))))

    # Route one: the engine's own table, which CG_UpdateCvars walks every
    # frame. This is what the 2010 tree does.
    engine_table = block_of(main_c, "cvarTable[]")
    in_engine_table = set()
    if engine_table:
        for name in declared:
            if re.search(r'&\s*%s\s*,' % re.escape(name), engine_table):
                in_engine_table.add(name)

    # Route two: the mod's own list, walked by its own per-frame refresh.
    mod_table = block_of(main_c, "eta_settings[]")
    in_mod_table = set()
    if mod_table:
        for name in declared:
            if re.search(r'&\s*%s\s*,' % re.escape(name), mod_table):
                in_mod_table.add(name)

    refreshed = set()

    if in_engine_table:
        # Only counts if the engine really does walk it.
        updater = block_of(main_c, "CG_UpdateCvars")
        if updater and "trap_Cvar_Update" in updater:
            refreshed |= in_engine_table
            print("[settings] %d via the engine's cvarTable"
                  % len(in_engine_table))
        else:
            failures.append(
                "settings sit in cvarTable but CG_UpdateCvars no longer "
                "refreshes it, so none of them are re-read")

    if in_mod_table:
        body = block_of(main_c, "%s(void)" % REFRESHER)
        if body is None or "trap_Cvar_Update" not in body:
            failures.append(
                "%s is listed in the mod's own settings table but %s does "
                "not call trap_Cvar_Update, so the list refreshes nothing"
                % (", ".join(sorted(in_mod_table)), REFRESHER))
        elif not re.search(r'\b%s\s*\(\s*\)\s*;' % re.escape(REFRESHER), draw_c):
            failures.append(
                "%s exists but nothing calls it from %s, so it never runs "
                "and the settings are read once at map load" % (REFRESHER, DRAW))
        else:
            refreshed |= in_mod_table
            print("[settings] %d via %s, called per frame"
                  % (len(in_mod_table), REFRESHER))

    stale = sorted(declared - refreshed)
    if stale:
        failures.append(
            "nothing re-reads %s. Changing one of these - from the console, "
            "a config or a menu - would store the new value and change "
            "nothing until the map reloaded, with no sign anywhere that it "
            "had been ignored" % ", ".join(stale))

    # And registration must come from the same list as the refresh, or the
    # two drift and the next setting added is stale again.
    if in_mod_table:
        init = block_of(main_c, "ETA_InitAccessibility(void)")
        if init and re.search(r'trap_Cvar_Register\s*\(\s*&\s*eta_\w+\s*,', init):
            failures.append(
                "ETA_InitAccessibility registers a setting by hand as well "
                "as from the table. That is how these went stale in the "
                "first place: a setting added to the registration and "
                "forgotten in the refresh is read once and never again")

    if failures:
        print()
        for failure in failures:
            print("[settings] FAIL %s" % failure)
        sys.exit(1)

    print("settings_live_test: %s - every setting the mod adds is re-read "
          "while the game runs" % args.engine)


if __name__ == "__main__":
    main()

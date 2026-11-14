#!/usr/bin/env python3
"""Check the repeat/stop commands cannot send the engine into a loop.

Why this exists
---------------
The engine picks who answers a console command, and it picks in an order
this project cannot change. Cmd_ExecuteString (qcommon/cmd.c) offers
every command to cgame before ui:

    if (com_cl_running && ... && CL_GameCommand())  return;
    if (com_sv_running && ... && SV_GameCommand())  return;
    if (com_cl_running && ... && UI_GameCommand())  return;

CG_ConsoleCommand returns qtrue for any name in its table, so once a
snapshot exists cgame answers first and ui never sees the command. That
is wrong for "repeat": with the options menu open mid-match, the player
wants the focused menu item, and only ui knows what that is.

So cgame checks the key catcher and, when a menu owns the keyboard,
pushes the request back through the command buffer under a different
name that only ui registers.

"A different name" is the whole safety property. If cgame ever also
registers the name it forwards, the forward comes straight back to
cgame, which forwards again - an unbounded command loop inside the
engine, with no error and no output. The game simply stops. That is a
far worse failure than anything it was protecting against, it cannot
happen in any test that does not run the engine, and a plausible
tidy-up - "these four names belong together, put them in both tables" -
introduces it.

So the tables are read out of the patched engine tree and checked.

Usage
-----
    ./command_wiring_test.py <engine-root>

Run it against an ET: Legacy tree with the patch series applied.
"""

import argparse
import os
import re
import sys

CGAME_TABLE = os.path.join("src", "cgame", "cg_consolecmds.c")
UI_TABLE = os.path.join("src", "ui", "ui_atoms.c")

# { "accessibilityStatus", CG_AccessibilityStatus_f },
TABLE_ROW = re.compile(r'\{\s*"([A-Za-z0-9_+-]+)"\s*,\s*[A-Za-z_]')

# The two engines answer ui commands differently. ET: Legacy's ui_atoms.c
# has a uiConsoleCommand_t table like cgame's; the 2010 GPL release's
# UI_ConsoleCommand is a chain of Q_stricmp comparisons instead. Both
# shapes are read, so this test covers either tree without being told
# which one it is looking at.
STRICMP_BRANCH = re.compile(r'Q_stricmp\s*\(\s*cmd\s*,\s*"([A-Za-z0-9_]+)"')

# trap_SendConsoleCommand(va("%s\n", uiCommand)) is indirect, so the
# forwarded names are read from the call sites that name them.
FORWARD_ARG = re.compile(r'CG_AccessibilityForwardToUI\s*\(\s*"([A-Za-z0-9_]+)"')


def table_names(path, guard):
    """Command names registered inside the accessibility guard block."""
    with open(path, "r", errors="replace") as handle:
        text = handle.read()

    names = set()
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#ifdef " + guard):
            inside = True
            continue
        if inside and stripped.startswith("#endif"):
            inside = False
            continue
        if inside:
            match = TABLE_ROW.search(line)
            if match:
                names.add(match.group(1))
            names.update(STRICMP_BRANCH.findall(line))
    return names, text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout with the patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    cgame_path = os.path.join(root, CGAME_TABLE)
    ui_path = os.path.join(root, UI_TABLE)

    for path in (cgame_path, ui_path):
        if not os.path.isfile(path):
            sys.exit("no %s under %s - is this an ET: Legacy checkout?"
                     % (os.path.relpath(path, root), root))

    cgame_names, cgame_text = table_names(cgame_path, "FEATURE_ACCESSIBILITY")
    ui_names, _ = table_names(ui_path, "FEATURE_ACCESSIBILITY")
    forwarded = set(FORWARD_ARG.findall(cgame_text))

    print("[wiring] cgame registers: %s" % (", ".join(sorted(cgame_names)) or "(none)"))
    print("[wiring] ui registers:    %s" % (", ".join(sorted(ui_names)) or "(none)"))
    print("[wiring] cgame forwards:  %s" % (", ".join(sorted(forwarded)) or "(none)"))

    # Finding nothing means the patches are not applied or the wiring
    # moved, not that the wiring is sound.
    if not cgame_names:
        sys.exit("found no accessibility commands in %s - apply the patch "
                 "series first" % CGAME_TABLE)
    if not ui_names:
        sys.exit("found no accessibility commands in %s - apply the patch "
                 "series first, and if the ui module answers commands some "
                 "third way, teach this test that shape rather than letting "
                 "it pass on an empty set" % UI_TABLE)
    if not forwarded:
        sys.exit("found no forwarded command names in %s - the forwarding "
                 "helper moved and this test no longer checks it" % CGAME_TABLE)

    failures = []

    for name in sorted(forwarded):
        if name in cgame_names:
            failures.append(
                "cgame both forwards and registers `%s`: the forward would "
                "come back to cgame and forward again, looping inside the "
                "engine until the game stops" % name)
        if name not in ui_names:
            failures.append(
                "cgame forwards `%s` but ui does not register it: the "
                "command would fall through to the server and the key would "
                "do nothing in a menu" % name)

    # The names a player binds have to be answerable in the main menu,
    # where cgame declines everything for want of a snapshot.
    for name in sorted(cgame_names - forwarded):
        if name in ("accessibilityRepeat", "accessibilityStopSpeech") \
                and name not in ui_names:
            failures.append(
                "`%s` is registered by cgame but not by ui: in the main "
                "menu CG_ConsoleCommand declines every command for want of "
                "a snapshot, so the key would do nothing there" % name)

    if failures:
        print()
        for failure in failures:
            print("[wiring] FAIL %s" % failure)
        sys.exit(1)

    print("[wiring] ok")


if __name__ == "__main__":
    main()

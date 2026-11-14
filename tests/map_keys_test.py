#!/usr/bin/env python3
"""Check that the map has the keys while it is open, and gives them back.

Why this exists
---------------
With the map open, the arrow keys walked the survey and turned the
player at the same time, and the movement keys still walked. A tester
asked for the map to have the keys while it is open - the arrows walk
the map, nothing moves - and for everything to be as it was once it is
closed. The module takes the keys by setting the client's key catcher,
which is a strong thing to hold:

  * kept after the map closes, the player could not move at all;
  * a held action run while the map is open - walking, firing - would be
    the very thing asked against;
  * one of the mod's own report keys swallowed would go silent;
  * the arrows sent to the wrong direction would walk the map backwards;
  * Escape, which the client takes the keys back on by itself, would
    leave the map open with nothing able to close it.

Usage
-----
    ./map_keys_test.py <engine-root>
"""

import argparse
import os
import re
import sys

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
NEWDRAW = os.path.join("src", "cgame", "cg_newDraw.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?" % (relative, root))
    with open(path, "r", errors="replace") as handle:
        text = handle.read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is gone"
                 % (name, where))
    depth, i = 0, found.end() - 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[found.end():i]
        i += 1
    sys.exit("could not find the end of %s" % name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    console = read(args.root, CONSOLE)
    newdraw = read(args.root, NEWDRAW)
    failures = []

    handler = body_of(console, "CG_AccessibilityMapKeyEvent", CONSOLE)
    catch = body_of(console, "ETA_MapCatchKeys", CONSOLE)
    frame = body_of(console, "ETA_MapCatchFrame", CONSOLE)
    expand = body_of(console, "CG_AutomapExpandDown_f", CONSOLE)
    collapse = body_of(console, "CG_AutomapCollapse", CONSOLE)
    shutdown = body_of(console, "CG_AccessibilityTurnShutdown", CONSOLE)
    key_event = body_of(newdraw, "CG_KeyEvent", NEWDRAW)

    # --- the keys reach the map first ------------------------------------
    # The hook sits behind the feature's #ifdef; the directives themselves
    # are not code.
    code = re.sub(r"^\s*#.*$", "", key_event, flags=re.M)
    first = re.search(r"\{\s*if\s*\(\s*CG_AccessibilityMapKeyEvent\s*\(\s*key\s*,\s*down\s*\)\s*\)\s*\{\s*return\s*;",
                      "{" + code)
    if not first or first.start() != 0:
        failures.append("CG_KeyEvent does not offer the map the key before "
                        "anything else does")

    # --- the arrows walk the map the right way ----------------------------
    for keys, command in ((("K_UPARROW", "K_KP_UPARROW"), "CG_AccessibilityMapNorth_f"),
                          (("K_DOWNARROW", "K_KP_DOWNARROW"), "CG_AccessibilityMapSouth_f"),
                          (("K_RIGHTARROW", "K_KP_RIGHTARROW"), "CG_AccessibilityMapEast_f"),
                          (("K_LEFTARROW", "K_KP_LEFTARROW"), "CG_AccessibilityMapWest_f")):
        pattern = r"case\s+%s\s*:\s*case\s+%s\s*:\s*%s\s*\(\s*\)\s*;\s*return\s+qtrue" % (
            keys[0], keys[1], command)
        if not re.search(pattern, handler):
            failures.append("%s and %s do not walk the map with %s"
                            % (keys[0], keys[1], command))
    if not [f for f in failures if "walk the map" in f]:
        print("[map] the arrows and the keypad arrows walk the map north, south, "
              "east and west")

    # --- nothing held runs, nothing of the mod's goes quiet ----------------
    if not re.search(r"if\s*\(\s*!\s*down\s*\)\s*\{\s*return\s+qtrue\s*;", handler):
        failures.append("a key let go while the map is open is acted on again")
    run = re.search(r"if\s*\(\s*binding\[0\]\s*&&\s*binding\[0\]\s*!=\s*'\+'\s*\)\s*\{\s*trap_SendConsoleCommand",
                    handler)
    if not run:
        failures.append("the map either runs held actions - walking, firing - or "
                        "swallows the mod's own report and marker keys")
    else:
        print("[map] a command that acts once still runs; a held action waits")

    if not re.search(r'Q_stricmp\s*\(\s*binding\s*,\s*"\+mapexpand"\s*\)', handler) \
            or not re.search(r"case\s+K_ESCAPE\s*:\s*CG_AutomapCollapse", handler):
        failures.append("the map key or Escape does not close the map")

    # --- the keys are given back -------------------------------------------
    if not re.search(r"eta_mapToggle\.integer[^}]*ETA_MapCatchKeys\s*\(\s*qtrue\s*\)", expand, re.S):
        failures.append("the map takes the keys even when it is held rather than "
                        "switched - its own release could then never close it")
    if "ETA_MapCatchKeys(qfalse)" not in collapse:
        failures.append("closing the map does not give the keys back - the "
                        "player could not move")
    if "ETA_MapCatchKeys(qfalse)" not in shutdown:
        failures.append("a map change or shutdown can keep the keys")
    if not re.search(r"trap_Key_SetCatcher\s*\(\s*trap_Key_GetCatcher\s*\(\s*\)\s*&\s*~\s*KEYCATCH_CGAME\s*\)", catch) \
            or not re.search(r"trap_Key_SetCatcher\s*\(\s*trap_Key_GetCatcher\s*\(\s*\)\s*\|\s*KEYCATCH_CGAME\s*\)", catch):
        failures.append("taking or giving back the keys disturbs the client's "
                        "other key catchers")
    if "CGAME_EVENT_NONE" not in catch:
        failures.append("the map can take the keys from another panel - the "
                        "limbo menu - that already has them")
    if not re.search(r"!\s*\(\s*trap_Key_GetCatcher\s*\(\s*\)\s*&\s*KEYCATCH_CGAME\s*\)", frame) \
            or "CG_AutomapCollapse" not in frame:
        failures.append("Escape takes the keys back and leaves the map open, "
                        "with nothing left to close it")
    if not [f for f in failures if "keys back" in f or "keep the keys" in f
            or "could not move" in f or "Escape" in f]:
        print("[map] the keys come back on closing, Escape, a map change and "
              "shutdown")

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        sys.exit(1)

    print("map_keys_test: the open map has the keys, walks the right way, and "
          "gives them back")


if __name__ == "__main__":
    main()

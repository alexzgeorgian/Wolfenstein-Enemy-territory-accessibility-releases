#!/usr/bin/env python3
"""Check the loading screen is said: connecting, the map, the bar, ready.

Why this exists
---------------
A tester asked to hear what the loading screen shows - the map, its
briefing, the bar - and to be told when the load was over and the team
and class menu could be opened. Silent, a load is indistinguishable from
a hang. Each part hangs on something that can quietly stop being true:

  * the game's start-up starts the mod's voice only at the end of the
    load, so the load has to start it itself, or nothing it says is
    heard;
  * the briefing has to be said after the map's details are known and
    before the long part of the load begins;
  * the bar's figures must not cut the briefing off, since every speech
    backend drops the line in progress;
  * the connection screen, drawn by the menu module, must speak each
    state once, not the packet counter that ticks beside it;
  * the line that the load is over names the key for the team and class
    menu, by its command - which has to be a real one.

Usage
-----
    ./loading_speech_test.py <engine-root>
"""

import argparse
import os
import re
import sys

MAIN = os.path.join("src", "cgame", "cg_main.c")
INFO = os.path.join("src", "cgame", "cg_info.c")
PANEL = os.path.join("src", "cgame", "cg_loadpanel.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
UI_PANEL = os.path.join("src", "ui", "ui_loadpanel.c")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def body_of(text, name, where):
    found = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone" % (name, where))
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

    main_c = read(args.root, MAIN)
    info = read(args.root, INFO)
    panel = read(args.root, PANEL)
    draw = read(args.root, DRAW)
    console = read(args.root, CONSOLE)
    ui_panel = read(args.root, UI_PANEL)
    failures = []

    init = body_of(main_c, "CG_Init", MAIN)
    begin = init.find("CG_AccessibilityLoadingBegin();")
    arena = init.find("CG_LocateArena();")
    campaign = init.find("CG_LocateCampaign();")
    loadmap = init.find("trap_CM_LoadMap(")
    voice = init.find("ETA_InitAccessibility();")
    if begin < 0:
        failures.append("nothing says the map and its briefing as the load starts")
    elif not (max(arena, campaign) < begin < loadmap):
        failures.append(
            "the briefing is said before the map's details are known, or "
            "after the long part of the load has begun")
    if voice >= 0 and begin >= 0 and voice > begin:
        started = body_of(panel, "CG_AccessibilityLoadingBegin", PANEL)
        if "ETA_AccessibilityRuntime_Init" not in started:
            failures.append(
                "the mod's voice is started only at the end of the load, and "
                "the loading narration does not start it itself - so the "
                "load is silent")
    if not failures:
        print("[loading] the map, its game type and briefing are said as the "
              "load begins, with the voice started for it")

    if not re.search(r"\bCG_AccessibilityLoadingProgress\s*\(\s*\)\s*;",
                     body_of(info, "CG_LoadingString", INFO)):
        failures.append("the loading bar is never said")
    progress = body_of(panel, "CG_AccessibilityLoadingProgress", PANEL)
    if "eta_loadingBriefingUntil" not in progress:
        failures.append(
            "the bar's figures are said over the briefing, cutting it off")
    if "trap_GetHunkData" not in progress:
        failures.append("the figure is not the one the bar is drawn from")

    frame = body_of(panel, "CG_AccessibilityLoadingFrame", PANEL)
    if not re.search(r"\bCG_AccessibilityLoadingFrame\s*\(\s*\)\s*;", draw):
        failures.append("nothing says the load is over")
    command = re.search(r'trap_Key_KeysForBinding\s*\(\s*"([^"]+)"', frame)
    if not command:
        failures.append("the load-over line does not name the team and "
                        "class key")
    elif not re.search(r'\{\s*"%s"' % re.escape(command.group(1)), console, re.I):
        failures.append(
            "the load-over line looks up the key for \"%s\", which is not a "
            "command the game has" % command.group(1))
    if "eta_loadingBriefingUntil" not in frame:
        failures.append("the load-over line cuts the briefing off")
    if not any("load" in f or "briefing" in f or "bar" in f for f in failures):
        print("[loading] the bar is said at each quarter and the end of the "
              "load names the team and class key, neither over the briefing")

    connect = body_of(ui_panel, "UI_LoadPanel_RenderLoadingText", UI_PANEL)
    if "ETA_UiNarrateConnect" not in connect:
        failures.append("the connection screen is silent")
    narrate = body_of(ui_panel, "ETA_UiNarrateConnect", UI_PANEL)
    if "lastState" not in narrate or "connectPacketCount" in narrate:
        failures.append(
            "the connection screen is said on every frame or every packet, "
            "not once per state")
    if not any("connection" in f for f in failures):
        print("[loading] the connection screen says each state once, and a "
              "download by the quarter")

    # On a Mac the briefing is kept and said once the load is over: the
    # load never lets the Mac's event loop run, so what was said as it
    # began was lost. It waits a second past the load, as the Mac
    # announcing the game's window coming back cut the start of a line
    # said at once; and the map is a line of its own, said first, so its
    # name is not what is lost.
    frame = body_of(panel, "CG_AccessibilityLoadingFrame", PANEL)
    title_at = frame.find("ETA_LoadingSay(eta_loadingTitle);")
    briefing_at = frame.find("ETA_LoadingSay(eta_loadingBriefing);")
    team_at = frame.find('"Press %s to choose your team and class"')
    if ("static char eta_loadingBriefing[" not in panel
            or "Q_strncpyz(eta_loadingBriefing, text, sizeof(eta_loadingBriefing));" not in panel
            or '"Loaded. %s. %s."' not in panel
            or briefing_at < 0):
        failures.append("on a Mac the map and its briefing are not said once the load is over")
    elif not 0 <= title_at < briefing_at < team_at:
        failures.append(
            "on a Mac the map, its briefing and the team key are not said "
            "in that order, each a line of its own")
    elif ("ETA_LOADED_WAIT_MS" not in frame
            or not re.search(r"#define ETA_LOADED_WAIT_MS\s+(\d{3,4})\b", panel)
            or frame.find("ETA_LOADED_WAIT_MS") > title_at):
        failures.append("on a Mac the map is said the moment the load ends, "
                        "when the start of it is cut")
    else:
        print("[loading] on a Mac a second after the load: Loaded and the "
              "map, then its briefing, then the team key")

    if failures:
        print()
        for failure in failures:
            print("[loading] FAIL %s" % failure)
        return 1

    print("loading_speech_test: connecting, the map, the bar and the end of "
          "the load are all said")
    return 0


if __name__ == "__main__":
    sys.exit(main())

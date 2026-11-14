#!/usr/bin/env python3
"""Check that hosting a game lets friends in with the plain game, and brings bots.

Why this exists
---------------
The mod's pk3 sits in the legacy folder, and a server asks everybody who
joins for every pk3 in that folder. So a game hosted by a player of this
mod, with the game's own defaults, either turns away a friend without the
mod (a pure server) or hands them the mod to take home (downloads on).
The Hosting page's first row, on by default, starts the server with
neither. Its other rows start Omni-bot with as many bots as chosen -
exactly that many, however many friends join - and change the count
during a match the player hosts.

The ways it breaks without anything visibly wrong:

  * the settings are applied after the map command runs, or not at all,
    so the server starts pure anyway and friends are turned away;
  * omnibot_enable is set after the game module has started - Omni-bot is
    only loaded as a map starts, so no bots come, with nothing said;
  * the bot count is sent before the map is up, to an Omni-bot that does
    not exist yet, so it is lost;
  * choosing no bots leaves omnibot_enable, an archived setting, at 1 from
    an earlier game, so bots keep coming;
  * the page offers a bot count or skill the code then clamps to something
    else, so the row reads out one thing and the game does another.

Usage
-----
    ./hosting_test.py <engine-root> [--menus DIR]
"""

import argparse
import os
import re
import sys

UI_MAIN = os.path.join("src", "ui", "ui_main.c")
G_MAIN = os.path.join("src", "game", "g_main.c")
PAGE = "options_accessibility_hosting.menu"
HOSTGAME_DEFAULTS = os.path.join("etmain", "ui", "hostgame_advanced_default.menu")


def read(path, what):
    if not os.path.isfile(path):
        sys.exit("no %s - %s" % (path, what))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_c_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def with_feature(text, on=True):
    """The text the compiler sees with FEATURE_ACCESSIBILITY on (or off)."""
    out, stack = [], []
    for line in text.splitlines():
        d = line.strip()
        m = re.match(r"#\s*(ifdef|ifndef)\s+(\w+)", d)
        if m:
            if m.group(2) == "FEATURE_ACCESSIBILITY":
                stack.append(on if m.group(1) == "ifdef" else not on)
            else:
                stack.append(None)
            continue
        if re.match(r"#\s*if\b", d):
            stack.append(None)
            continue
        if re.match(r"#\s*else\b", d):
            if stack and stack[-1] is not None:
                stack[-1] = not stack[-1]
            continue
        if re.match(r"#\s*endif\b", d):
            if stack:
                stack.pop()
            continue
        if all(k for k in stack if k is not None):
            out.append(line)
    return "\n".join(out)


def block_after(text, start):
    """The brace-balanced block that opens at or after index start."""
    i = text.find("{", start)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return None


def function_body(text, name):
    found = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not found:
        return None
    return block_after(text, found.end() - 1)


def float_list(page, cvar):
    row = re.search(r'"%s"\s*,\s*cvarFloatList\s*\{([^}]*)\}' % re.escape(cvar),
                    page)
    if not row:
        return None
    return [int(v) for v in re.findall(r'"[^"]*"\s+(-?\d+)', row.group(1))]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    parser.add_argument("--menus",
                        default=os.path.join(here, "..", "release", "ui"),
                        help="the shipped menu directory")
    args = parser.parse_args()

    raw = read(os.path.join(args.root, UI_MAIN), "is the patch series applied?")
    ui_on = strip_c_comments(with_feature(raw, True))
    ui_off = strip_c_comments(with_feature(raw, False))
    page = read(os.path.join(args.menus, PAGE), "the Hosting page")
    failures = []

    # --- Start Server applies the page, after queueing the map ----------
    start = re.search(r'Q_stricmp\s*\(\s*name\s*,\s*"StartServer"\s*\)\s*==\s*0\s*\)',
                      ui_on)
    handler = block_after(ui_on, start.end()) if start else None
    if not handler:
        sys.exit("could not find the StartServer menu script in %s - the "
                 "thing this test guards has moved" % UI_MAIN)

    call = handler.find("UI_AccessibilityHostServer")
    maps = [m.end() for m in re.finditer(r'"wait ; wait ; map %s', handler)]
    if call < 0:
        failures.append("Start Server never applies the Hosting page, so "
                        "the server starts pure and without bots whatever "
                        "the page says")
    elif not maps or call < max(maps):
        failures.append("the Hosting page is applied before the map command "
                        "is queued, so the bot count would be queued ahead "
                        "of the map and sent to an Omni-bot that is not "
                        "running yet")
    else:
        print("[hosting] Start Server applies the page after queueing the map")

    host = function_body(ui_on, "UI_AccessibilityHostServer")
    if host is None:
        sys.exit("no UI_AccessibilityHostServer in %s" % UI_MAIN)

    # --- friends with the plain game -----------------------------------
    plain = re.search(r"if\s*\(\s*eta_hostPlain\.integer\s*\)\s*\{([^}]*)\}", host)
    if not plain \
            or not re.search(r'"sv_pure"\s*,\s*"0"', plain.group(1)) \
            or not re.search(r'"sv_allowDownload"\s*,\s*"0"', plain.group(1)):
        failures.append("friends-with-the-plain-game does not turn off both "
                        "the pure check and downloads. Either one left on is "
                        "a friend turned away, or sent home with the mod")
    else:
        print("[hosting] the plain-game row turns off the pure check and downloads")

    if not re.search(r"trap_Cvar_Update\s*\(\s*&eta_hostPlain\s*\)", host):
        failures.append("the page's values are not re-read on Start Server, "
                        "so a change made on the page takes a restart")

    # --- bots ------------------------------------------------------------
    off = re.search(r"if\s*\(\s*eta_hostBotCount\.integer\s*<=\s*0\s*\)\s*\{([^}]*)\}", host)
    if not off or not re.search(r'"omnibot_enable"\s*,\s*"0"', off.group(1)) \
            or "return" not in off.group(1):
        failures.append("choosing no bots does not turn Omni-bot off. "
                        "omnibot_enable is archived, so a server hosted with "
                        "bots once would have them every time after")

    enable = re.search(r'"omnibot_enable"\s*,\s*"1"', host)
    queued = re.search(r'EXEC_APPEND\s*,\s*va\s*\(\s*"([^"]*)"', host)
    if not enable:
        failures.append("bots on never sets omnibot_enable, so Omni-bot is "
                        "never loaded")
    elif not queued or "difficulty" not in queued.group(1) \
            or "UI_AccessibilityBotCommand(" not in host[queued.start():]:
        failures.append("the bot count and skill are not queued behind the "
                        "map command, so they reach no Omni-bot")
    elif queued.start() < enable.start():
        failures.append("the bot commands are queued before Omni-bot is "
                        "enabled")
    else:
        print("[hosting] Omni-bot is enabled before the map, and the count "
              "and skill are queued behind it")

    game = strip_c_comments(read(os.path.join(args.root, G_MAIN), "engine?"))
    init = re.search(r"case\s+GAME_INIT\s*:(.*?)return\s+0\s*;", game, re.S)
    if not init or "Bot_Interface_Init" not in init.group(1):
        failures.append("the game module no longer starts Omni-bot as the "
                        "map starts. Setting omnibot_enable before the map "
                        "is only right because that is when it is read - "
                        "check where Omni-bot is loaded now")

    # Exactly the count chosen, however many friends join: Omni-bot keeps
    # at least minbots bots, and takes them away only past maxbots players.
    command = function_body(ui_on, "UI_AccessibilityBotCommand") or ""
    if not re.search(r'"bot minbots %i ; bot maxbots %i"\s*,\s*bots\s*,\s*bots', command):
        failures.append("the bot count is not sent as both minbots and maxbots, "
                        "so it is a count of players, not of bots, and friends "
                        "joining send bots away")
    else:
        print("[hosting] the count is of bots: minbots and maxbots both, so "
              "friends joining do not send them away")

    # Changed during a match the player hosts: sent at once, and said.
    live = strip_c_comments(function_body(ui_on, "UI_AccessibilityBotsFrame") or "")
    refresh = function_body(ui_on, "UI_Refresh") or ""
    if "UI_AccessibilityBotsFrame();" not in refresh or '"sv_running"' not in live \
            or "UI_AccessibilityBotCommand(bots)" not in live or "CA_ACTIVE" not in live \
            or '"omnibot_enable"' not in live or "UI_AccessibilityUpdateSay(" not in live:
        failures.append("changing the bot count during a match you host does "
                        "nothing until the next one, or is not said")
    else:
        print("[hosting] changed during a match you host, the bots join or "
              "leave at once, and it is said")

    # --- the Mac: bots need a game module built with them, and Omni-bot ---
    mac = function_body(ui_on, "UI_AccessibilityMacBotsCheck")
    if not mac:
        failures.append("hosting on a Mac never checks for the bots file and "
                        "Omni-bot, so a game with no bots says nothing")
    elif not re.search(r'#ifdef __APPLE__\s*UI_AccessibilityMacBotsCheck\(\);\s*#endif', raw) \
            or not re.search(r'"omnibot_enable",\s*"1"\);\s*UI_AccessibilityMacBotsCheck\(\);', host):
        failures.append("the Mac's bots check is not made as a game with bots "
                        "is hosted")
    elif ("ETA_Update_CheckMacGame(path, ETA_Update_MacGameSha256())" not in mac
          or "/legacy/qagame_mac" not in mac or "/omnibot_et_mac.so" not in mac
          or mac.count('trap_Cvar_Set("eta_botsProblem", "No bots:') != 3
          or "UI_AccessibilityUpdateSay(" in mac):
        failures.append("the Mac's bots check does not look at both the bots "
                        "file and Omni-bot, or does not keep what is missing to "
                        "be said in the match")
    elif mac.find('"%s/legacy/omni-bot"') < 0 or mac.find('"%s/omni-bot"') < mac.find('"%s/legacy/omni-bot"') \
            or 'trap_Cvar_Set("omnibot_path", folder);' not in mac:
        failures.append("Omni-bot is not looked for in the legacy folder first, "
                        "as on Windows, or the game module is not told where it is")
    else:
        print("[hosting] on a Mac, Omni-bot is found in the legacy folder or the "
              "home folder, and what stops bots is kept for the match")

    # --- the bots file kept in step with the version, on a Mac -----------
    keep = function_body(ui_on, "UI_AccessibilityMacGameFrame") or ""
    update = function_body(ui_on, "UI_AccessibilityUpdateFrame") or ""
    if "UI_AccessibilityMacGameFrame();" not in update \
            or "ETA_Update_MacGameUrl(ETA_Update_InstalledVersion(), url, sizeof(url))" not in keep \
            or "ETA_WindowsUpdate_StartDownload(url, download, ETA_UPDATE_MAX_PACKAGE_BYTES)" not in keep \
            or "!Q_stricmp(ETA_WindowsUpdate_DownloadSha256(), expected)" not in keep \
            or "rename(download, target) == 0" not in keep \
            or "ETA_WindowsUpdate_RemoveFile(download);" not in keep:
        failures.append("on a Mac the bots file is not fetched from the release, "
                        "checked against the built-in checksum, and put in place")
    elif "ETA_MAC_GAME_OTHER" not in keep or "ETA_MAC_GAME_ABSENT" not in keep \
            or "omni-bot/omnibot_et_mac.so" not in keep \
            or 'trap_Cvar_VariableValue("eta_updateAsked") == 0.f' not in keep \
            or "etaUpdate.stage != ETA_UPDATE_STAGE_IDLE" not in keep:
        failures.append("the bots file is fetched on a Mac not set up for bots, or "
                        "before the start-up check, or over an update in progress")
    else:
        print("[hosting] on a Mac set up for bots, a bots file from another "
              "version is replaced by this version's, fetched and checked")

    # --- said once the match is up, not over the loading screen ----------
    draw = strip_c_comments(read(os.path.join(args.root, "src", "cgame", "cg_draw.c"), "cg_draw.c"))
    say = function_body(draw, "ETA_SayBotsProblem") or ""
    if "ETA_SayBotsProblem();" not in draw or '"eta_botsProblem"' not in say \
            or "cgs.levelStartTime + 3000" not in say or 'trap_Cvar_Set("eta_botsProblem", "");' not in say \
            or "ETA_Speech_Say(problem);" not in say:
        failures.append("why bots did not come is not said a moment into the "
                        "match, once, where the loading screen cannot talk over it")
    else:
        print("[hosting] why bots did not come is said three seconds into the "
              "match, once")

    # --- the page offers only what the code will do ---------------------
    bots = float_list(page, "eta_hostBotCount")
    skill = float_list(page, "eta_hostBotSkill")
    clamp = re.search(r"Com_Clamp\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*eta_hostBotSkill",
                      host)
    defaults = read(os.path.join(args.root, HOSTGAME_DEFAULTS), "engine?")
    maxclients = re.search(r"setcvar\s+sv_maxclients\s+(\d+)", defaults)

    if not bots or 0 not in bots:
        failures.append("the Bots row has no None, so there is no way to "
                        "host without them")
    elif maxclients and max(bots) + 1 > int(maxclients.group(1)):
        failures.append("the Bots row offers %d bots, with the host more than the %s "
                        "the Host Game screen allows by default - the row "
                        "would promise bots the server has no room for"
                        % (max(bots), maxclients.group(1)))
    if not skill or not clamp:
        failures.append("could not read the Bot skill row or its clamp")
    elif min(skill) < int(clamp.group(1)) or max(skill) > int(clamp.group(2)):
        failures.append("the Bot skill row offers values the code clamps "
                        "away, so the row reads out one skill and the bots "
                        "get another")
    else:
        print("[hosting] the page offers %s bots and skills %s, all honoured"
              % (bots, skill))

    for cvar, default in (("eta_hostPlain", "1"), ("eta_hostBotCount", "-1"),
                          ("eta_hostBotSkill", "2")):
        if not re.search(r'trap_Cvar_Register\s*\([^,]+,\s*"%s"\s*,\s*"%s"\s*,\s*CVAR_ARCHIVE'
                         % (cvar, default), ui_on):
            failures.append("%s is not registered, archived, with default %s"
                            % (cvar, default))

    init_ui = function_body(ui_on, "UI_Init")
    if not init_ui or "UI_AccessibilityRegisterHostCvars" not in init_ui:
        failures.append("the Hosting page's settings are registered only on "
                        "Start Server, so before the first game the page "
                        "reads out empty values")

    # --- and with the feature off, Start Server is the game's own -------
    if "eta_" in (block_after(ui_off, re.search(r'"StartServer"', ui_off).end())
                  or "") or "UI_AccessibilityHostServer" in ui_off:
        failures.append("with FEATURE_ACCESSIBILITY off, Start Server still "
                        "changes the server's settings")
    else:
        print("[hosting] with the feature off, Start Server is the game's own")

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        sys.exit(1)

    print("hosting_test: a hosted game lets friends in with the plain game "
          "and brings the bots the page asks for")


if __name__ == "__main__":
    main()

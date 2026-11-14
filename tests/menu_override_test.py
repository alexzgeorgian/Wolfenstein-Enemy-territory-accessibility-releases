#!/usr/bin/env python3
"""Check the menus the mod ships against the engine they sit on top of.

Why this exists
---------------
The mod ships two menu files, and they carry different risks.

(It shipped four for one release: the keys had a page of their own,
reached by a button added to a copy of the game's CONTROLS menu. The
tester asked for them back on the accessibility page and for CONTROLS
to be left as the game ships it, which also removed a shadowed file.)

`ui/options_accessibility.menu` is the mod's own page. It shadows
nothing - the ui module parses it by name, alongside the game's own menu
list - so the only way it can be wrong is by naming something that does
not exist. A misspelled cvar on a settings row is a control that moves
and changes nothing. A misspelled command on a bind row takes a key away
and binds it to nothing. Both are silent, and both are invisible to
somebody who cannot see the screen: the row still reads out, still
announces a value, still says "bound to V".

`ui/options.menu` is a copy of the game's own, with one button added to
reach that page - and that one genuinely shadows the original. A copy
left in the search path freezes that menu at whatever the engine shipped
the day it was taken. If upstream adds a button there, players of this
mod stop getting it, and nothing anywhere says so. That cannot be
prevented, only made loud: the stock file is recorded beside ours, and
this fails the build when the engine's copy stops matching it.

Usage
-----
    ./menu_override_test.py <engine-root> [--menus DIR]
"""

import argparse
import os
import re
import sys

ENGINE_MENUS = os.path.join("etmain", "ui")
MAIN_C = os.path.join("src", "cgame", "cg_main.c")
CONSOLE_C = os.path.join("src", "cgame", "cg_consolecmds.c")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")

# The mod's own pages. These shadow nothing - the ui module parses each
# by name, in addition to the game's own menu list - so the only way they
# can be wrong is by naming something that does not exist.
PAGES = ("options_accessibility.menu",
         "options_accessibility_environment.menu",
         "options_accessibility_speech.menu",
         "options_accessibility_sound.menu",
         "options_accessibility_keys.menu",
         "options_accessibility_hosting.menu")

# The first page is a menu of the others: each must be opened from
# it, and each must lead back to it. A page nothing opens ships inside
# the pk3 and cannot be reached; a page whose BACK goes somewhere else
# strands a player who cannot see where they have ended up.
HUB = "options_accessibility"

# The game's own menus the mod ships a copy of, each with the one button
# that reaches a page above, and the menu that button opens. A copy in
# the search path freezes that menu at the version it was taken from, so
# each one needs its `.stock` twin recorded beside it.
OVERRIDES = {
    "options.menu": "options_accessibility",
}

UI_SHARED = os.path.join("src", "ui", "ui_shared.c")


def read(path, what):
    if not os.path.isfile(path):
        sys.exit("no %s - %s" % (path, what))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def with_feature(text, on=True):
    """The text the compiler sees with FEATURE_ACCESSIBILITY on (or off).

    Only that one macro is decided. Every other conditional keeps both
    its branches, which is the conservative reading for a test that asks
    whether something is present."""
    out = []
    stack = []  # per open conditional: None if not ours, else keep-flag

    def keeping():
        return all(k for k in stack if k is not None)

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
        if keeping():
            out.append(line)
    return "\n".join(out)


def strip_c_comments(text):
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


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--menus",
                        default=os.path.join(here, "..", "release", "ui"),
                        help="the shipped menu directory")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    menus = os.path.abspath(args.menus)
    failures = []

    page = "".join(
        read(os.path.join(menus, name),
             "the mod's own pages are what this test exists for")
        for name in PAGES)

    ui_main = strip_c_comments(read(os.path.join(root, UI_MAIN),
                                    "is the patch series applied?"))

    for name in PAGES:
        # --- the page is actually loaded -------------------------------
        if name not in ui_main:
            failures.append(
                "nothing in %s parses %s, so the page ships inside the pk3 "
                "and is never loaded - the button would open a menu that "
                "does not exist" % (UI_MAIN, name))
        else:
            print("[menus] %s is parsed by the ui module" % name)

    hub_text = read(os.path.join(menus, PAGES[0]), "the hub page")
    for name in PAGES[1:]:
        menu = name[:-len(".menu")]
        body = read(os.path.join(menus, name), "one of the mod's pages")
        if not re.search(r"\bopen\s+%s\b" % re.escape(menu), hub_text):
            failures.append(
                "nothing on %s opens %s, so the page ships and cannot be "
                "reached" % (PAGES[0], menu))
        elif not re.search(r"onESC\s*\{[^}]*\bopen\s+%s\b" % HUB, body, re.S) \
                or not re.search(r"MSGID_MENU_BACK[^\n]*\bopen\s+%s\b" % HUB,
                                 body):
            failures.append(
                "%s does not lead back to %s from both Escape and BACK, so a "
                "player leaving it lands somewhere they did not come from"
                % (name, HUB))
        else:
            print("[menus] %s opens %s, and it leads back" % (HUB, menu))

    for override, opens in sorted(OVERRIDES.items()):
        stock_name = override + ".stock"
        ours = read(os.path.join(menus, override),
                    "the shipped copy of the engine's %s" % override)
        stock_recorded = read(
            os.path.join(menus, stock_name),
            "the pinned copy of the engine's own %s" % override)

        engine_current = read(
            os.path.join(root, ENGINE_MENUS, override),
            "is this an Enemy Territory checkout? the shipped %s is derived "
            "from this file and cannot be checked without it" % override)

        # --- the shadowed file has not drifted from upstream -----------
        if engine_current != stock_recorded:
            failures.append(
                "the engine's %s has changed since %s was taken. The mod "
                "ships a copy of that menu, which shadows the engine's - so "
                "whatever upstream just changed will not reach anybody "
                "running this mod, and nothing in the game would say so. "
                "Re-derive %s from the new file and update %s beside it"
                % (override, stock_name, override, stock_name))
            continue

        print("[menus] %s still matches the engine it was taken from"
              % stock_name)

        # --- and our copy is that file plus only what it should be -----
        stock_lines = stock_recorded.splitlines()
        our_lines = ours.splitlines()

        added = [l for l in our_lines if l not in stock_lines]
        removed = [l for l in stock_lines if l not in our_lines]

        if not any(opens in line for line in added):
            failures.append(
                "the shipped %s has no button opening %s, so the page "
                "exists and nothing reaches it" % (override, opens))

        # The one button, plus the lines its geometry forces. Four is
        # what the override needs today; more than that and the copy
        # has started carrying changes of its own, which is the thing
        # shadowing a file must never quietly become.
        if len(added) > 4:
            failures.append(
                "the shipped %s differs from the engine's by %d added "
                "line(s): %s. This file shadows the engine's own, so every "
                "line that differs is a line frozen at today's version. It "
                "should be the stock file plus the one button and the "
                "geometry that button forces, and nothing else"
                % (override, len(added),
                   "; ".join(l.strip() for l in added)))

        dropped = [l for l in removed
                   if "WINDOW_HEIGHT" not in l
                   and "MSGID_MENU_BACK" not in l
                   and "MSGID_MENU_ADVANCED" not in l
                   and "MSGID_MENU_DEFAULT" not in l]
        if dropped:
            failures.append(
                "the shipped %s drops line(s) the engine's has: %s. "
                "Shadowing a menu is only defensible while it is additive"
                % (override, "; ".join(l.strip() for l in dropped)))
        else:
            print("[menus] %s is the engine's file plus %d line(s)"
                  % (override, len(added)))

    # --- 4. every row names something real ------------------------------
    cg_main = strip_c_comments(read(os.path.join(root, MAIN_C), "engine?"))
    console = strip_c_comments(read(os.path.join(root, CONSOLE_C), "engine?"))

    # Most settings belong to cgame. The Hosting page's belong to the ui
    # module, because hosting starts from the main menu, before there is
    # any cgame to register them - so they are looked for there, and only
    # in what the compiler sees with the feature on.
    known_cvars = set(re.findall(r'"(eta_[A-Za-z0-9_]+)"', cg_main))
    known_cvars |= set(re.findall(
        r'trap_Cvar_Register\s*\([^,]+,\s*"(eta_[A-Za-z0-9_]+)"',
        with_feature(ui_main)))
    known_commands = set(re.findall(r'"\+?(accessibility[A-Za-z0-9_]*)"', console))

    if not known_cvars or not known_commands:
        sys.exit("read no eta_ settings or accessibility commands out of the "
                 "engine - this test is out of date with the mod, and "
                 "passing without reading them would defeat its purpose")

    used_cvars = set(re.findall(r'"(eta_[A-Za-z0-9_]+)"', page))
    used_commands = set(re.findall(r'"\+?(accessibility[A-Za-z0-9_]*)"', page))

    for name in sorted(used_cvars - known_cvars):
        failures.append(
            "the page has a row for %r, which the mod never registers. The "
            "control would move and change nothing, and would announce its "
            "new value while doing it" % name)

    for name in sorted(used_commands - known_commands):
        failures.append(
            "the page has a bind row for %r, which is not a command the mod "
            "answers. Binding a key to it takes the key away and does "
            "nothing with it" % name)

    print("[menus] the page names %d setting(s) and %d command(s), all real"
          % (len(used_cvars), len(used_commands)))

    # The look and turn rows are the *client's* commands, not the mod's -
    # +left, +lookup and the rest - and they are listed because the
    # game's own controls menu offers no row for turning or looking
    # anywhere. They are checked against the client's table for the same
    # reason: a misspelled one is a row that takes a key and does nothing
    # with it, and reads out perfectly while doing so.
    client_path = os.path.join(root, "src", "client", "cl_input.c")
    if os.path.isfile(client_path):
        client = strip_c_comments(read(client_path, "engine?"))
        client_commands = set(re.findall(r'Cmd_AddCommand\s*\(\s*"([^"]+)"',
                                         client))
        used_client = set(re.findall(r'"([+-][a-z0-9_]+)"', page))

        if not client_commands:
            sys.exit("read no Cmd_AddCommand out of the client - this test "
                     "is out of date with the engine, and passing without "
                     "reading them would defeat its purpose")

        for name in sorted(used_client - client_commands):
            failures.append(
                "a bind row names %r, which the client registers nowhere. "
                "Binding a key to it takes the key away and does nothing "
                "with it" % name)

        if used_client:
            print("[menus] %d look/turn row(s) name real client commands: %s"
                  % (len(used_client), ", ".join(sorted(used_client))))

    # --- and the keys survive a reset to defaults ----------------------
    #
    # Resetting the controls execs the stock config, which binds what the
    # game ships with and drops everything else - every one of this mod's
    # keys. The installer records which generation a player has been
    # offered and never re-offers it, so without a deliberate recovery a
    # single press of DEFAULT takes the status key, the map survey and
    # the look keys away permanently. That button now sits on the same
    # row as the one leading to these very binds.
    defaults = re.search(r'defaultControls[^}]*?\}', ui_main, re.S)
    if not defaults:
        failures.append(
            "could not find the defaultControls handler in %s, so the one "
            "thing that silently destroys every mod bind cannot be checked"
            % UI_MAIN)
    else:
        body = defaults.group(0)

        if "eta_bindsInstalled" not in body:
            failures.append(
                "resetting the controls does not clear eta_bindsInstalled. "
                "The stock config it execs drops every bind this mod added, "
                "and the installer will not offer a generation it has "
                "already offered - so the keys would be gone for good, with "
                "nothing in the game to say why")
        elif "accessibilityInstallBinds" not in body:
            failures.append(
                "resetting the controls clears eta_bindsInstalled but never "
                "runs the installer again, so the keys come back only on "
                "the next launch - and only if the player works out that is "
                "what it takes")
        else:
            print("[menus] resetting the controls puts the mod's keys back")

    # --- 6. every bind row can actually be changed ----------------------
    #
    # A BIND row looks its command up in the ui's own binding table,
    # g_bindings, and nowhere else. A command missing from that table is
    # drawn with whatever key it is on - read from the engine directly -
    # and pressing a new key on it does nothing at all. So the row reads
    # out perfectly and cannot be changed, which is exactly how every key
    # on this page shipped: a tester found it trying to move Look Down.
    shared = with_feature(strip_c_comments(
        read(os.path.join(root, UI_SHARED), "is the patch series applied?")))
    table = re.search(r"g_bindings\[\]\s*=\s*\{(.*?)\n\};", shared, re.S)
    if not table:
        sys.exit("could not find g_bindings in %s - this test is out of date "
                 "with the engine" % UI_SHARED)
    bindable = {c.lower() for c in
                re.findall(r'\{\s*"([^"]+)"', table.group(1))}

    rows = re.findall(r'BIND\([^\n]*?"([^"]+)"\s*,\s*_\(', page)
    if not rows:
        sys.exit("read no BIND rows off the page - this test is out of "
                 "date with the menu")
    stuck = sorted({r for r in rows if r.lower() not in bindable})
    if stuck:
        failures.append(
            "bind row(s) for %s name a command missing from g_bindings in "
            "%s. The row will say which key the command is on, and pressing "
            "a new key on it will do nothing" % (", ".join(stuck), UI_SHARED))
    else:
        print("[menus] all %d bind rows are in the ui's binding table, so "
              "each one can be changed" % len(rows))

    # The table's copy of each key is read once, when the ui starts - and
    # the installer runs after that. Unless it refreshes the copy, the
    # first key a player changes writes the stale one back: the keypad
    # returns to selectbuddy and 9 and 0 to the weapon banks.
    installer = re.search(
        r"void UI_AccessibilityInstallBinds\(void\)\s*\{(.*?)\n\}",
        ui_main, re.S)
    if not installer:
        failures.append("could not find UI_AccessibilityInstallBinds in %s"
                        % UI_MAIN)
    elif "Controls_GetConfig" not in installer.group(1):
        failures.append(
            "UI_AccessibilityInstallBinds changes keys without refreshing "
            "the controls pages' copy of them (Controls_GetConfig). The "
            "first key the player changes afterwards writes that stale copy "
            "back over the keyboard and undoes the install")
    else:
        print("[menus] installing the mod's keys refreshes the controls "
              "pages' copy of the keyboard")

    # --- 7. and the look keys still exist once a match has loaded -------
    #
    # ET: Legacy's cgame deletes +lookup and +lookdown when it starts, and
    # the engine makes an exception so that it may. Nothing puts them
    # back until the game restarts, so the row reads "Look Down, bound to
    # DOWNARROW" and the key does nothing in a match.
    cgame_on = with_feature(console)
    removed = sorted(set(re.findall(
        r'trap_RemoveCommand\s*\(\s*"([+-]look(?:up|down))"', cgame_on)))
    if removed:
        failures.append(
            "with the feature on, the cgame still removes %s when a match "
            "loads, so the look keys on the page do nothing in play"
            % ", ".join(removed))
    else:
        print("[menus] the look keys survive a match loading")

    atoms = os.path.join(root, "src", "ui", "ui_atoms.c")
    if os.path.isfile(atoms):
        if "accessibilityInstallBinds" not in read(atoms, "engine?"):
            failures.append(
                "accessibilityInstallBinds is queued after the controls "
                "reset but no command of that name is registered, so it "
                "runs as an unknown command and the keys stay gone")

    # --- 5. and nothing the mod adds is missing from it -----------------
    #
    # The other direction, and the one that rots: a setting added to the
    # mod and forgotten here is invisible to every player who never opens
    # a config file - which, for a page that exists so they do not have
    # to, is the whole point missed.
    missing_cvars = known_cvars - used_cvars
    # Cue sound paths are settings too, but they are filenames rather
    # than anything a menu control can sensibly offer.
    missing_cvars = {c for c in missing_cvars if not c.startswith("eta_cue")}
    missing_cvars.discard("eta_bindsInstalled")
    # The updater's own bookkeeping: the words of the offer on screen,
    # and whether this run has asked yet. Neither is a choice.
    missing_cvars.discard("eta_updateMessage")
    missing_cvars.discard("eta_updateAsked")

    if missing_cvars:
        failures.append(
            "the mod registers %s but the page has no row for them. A "
            "setting that only exists in a config file is one a player has "
            "to be told about to find"
            % ", ".join(sorted(missing_cvars)))

    missing_commands = known_commands - used_commands
    # The menu-side aliases are internal handover names, not things a
    # player binds - see the comment on the ui command table.
    missing_commands = {c for c in missing_commands if not c.endswith("Menu")
                        and not c.endswith("MenuItem")}

    if missing_commands:
        failures.append(
            "the mod answers %s but the page has no bind row for them, so "
            "they can only be reached by editing a config"
            % ", ".join(sorted(missing_commands)))

    if failures:
        print()
        for failure in failures:
            print("[menus] FAIL %s" % failure)
        sys.exit(1)

    print("menu_override_test: the shipped menus match the engine, name "
          "only real settings and commands, and cover everything the mod "
          "adds")


if __name__ == "__main__":
    main()

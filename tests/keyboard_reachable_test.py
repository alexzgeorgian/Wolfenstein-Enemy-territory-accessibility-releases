#!/usr/bin/env python3
"""Check the game stays playable without a mouse.

Why this exists
---------------
Two defects found in one test session, both of the same shape: a part of
the game that only a mouse can reach, and a player without one hearing
nothing and assuming the mod was broken.

**The scope.** `weapalt` is how a rifle goes to its scope, a mortar and
an MG are set down, and a satchel is detonated. The stock config binds
it to MOUSE2 and to nothing else - it is the only action in default.cfg
with no keyboard key at all. A tester spent a session trying to scope an
FG 42 and hearing no announcement, because they never got into the
scope. The mod now binds it to a key.

**Menu focus.** `Menu_HandleKey` re-runs mouse-move focus on every key
press from wherever the cursor happens to sit. With a hand on the mouse
that is right. From the keyboard alone the cursor never moves, so it
wins every time and the item the arrow keys selected loses focus the
moment a key is pressed. On the join-server screen the server list
carries `onEnter { uiScript JoinServer }`, so a player who has arrowed
to "REFRESH LIST" presses Enter and connects to whatever server was
highlighted. That is what happened.

Both fixes are one line of condition each, in someone else's code, and
either could be dropped by an upstream merge without anything noticing.
So this reads the engine back:

  * every key the mod binds must name a command the engine really has,
    and must be free in the stock right-handed layout
  * a key that is free there but taken in the left-handed layout may
    still be claimed - the installer only ever takes a key that is
    actually unbound, so nothing is stolen - but the install guide has
    to name it, or a left-handed player gets a feature that silently
    is not there and no way to find out why. That documentation is
    checked here, not trusted

    This was relaxed from "free in both layouts" when the command map
    survey arrived. That feature needs four arrow keys and a navigation
    cluster, and ET's left-handed layout puts movement and controls on
    every one of them - there is no four-way cluster free in both, and
    the keypad arrows are `selectbuddy` in both. The old rule was also
    stricter than its own reason: it guarded against silently stealing
    a key, and the installer already cannot do that. What it left
    unguarded was the silence afterwards, which is what the guide
    requirement now covers.
  * `weapalt` must still be mouse-only upstream - if ET: Legacy ever
    gives it a key, the mod should stop claiming one
  * the cursor-moved guard must still stand in front of the focus reset

Usage
-----
    ./keyboard_reachable_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DEFAULT_CFG = os.path.join("etmain", "default.cfg")
LEFT_CFG = os.path.join("etmain", "default_left.cfg")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")

# The only commands a mod bind may take over from an existing config.
#
# Anything not on this list has to be argued for here before it can be
# claimed. The `replaces` field is otherwise a way to take *any* key -
# including movement - by simply naming what is already on it, and a
# mod that can silently rebind +forward is exactly what the rest of
# this file exists to prevent.
#
# The weapon banks are inert: CG_WeaponBank_f rejects any bank outside
# 1..MAX_WEAP_BANKS_MP-1, so "weaponbank 10" never reaches the table,
# and bank 9's row is empty. tests/weapon_bank_test.py fails the build
# if either ever stops being dead.
#
# The accessibilityMap* four are the mod's own binds being moved, not
# taken. The survey held the arrow keys; the arrows now turn and look,
# which stock ET reaches from no key at all, and the survey lands on
# the keypad in the same table. A player who kept what the mod gave
# them keeps all of it, on a different key.
#
# +left and +right are the mod's own binds being moved too. Stock ET puts
# them on no key at all; the mod put them on the arrows, and the arrows
# now go to +accessibilityTurnLeft and +accessibilityTurnRight, which pass
# a hold straight through to those same two commands and turn a tap into
# a step to the next compass point. Nothing a player had is lost: the
# plain turns are still on the Key Binds page, and a player who put
# either on an arrow themselves keeps it, because only the exact command
# this table installed is ever replaced.
#
# selectbuddy is the one entry here that is neither inert nor ours, and
# it is not pretended otherwise. It picks a fireteam member out by slot
# number; five of its eight slots go to the survey's directions. The
# trade was made deliberately and by the person it is for: selectbuddy
# needs a fireteam, a roster whose order you know, and a second command
# after it, while the map survey is how a blind player finds out where
# anything on the map is. Slots 0 and 6 (KP_END, KP_HOME) are left, and
# every one of these keys rebinds like any other.
#
# +activate is not inert and not ours either, and is here because the
# command that replaces it keeps everything it did. The tester asked for
# the turn to "what you can use" to work with the use key itself.
# +accessibilityActivate presses +activate straight through whenever the
# game is already offering something to use under the crosshair, and
# whenever there is nothing close by to turn to; only with nothing under
# the crosshair does it turn first, and then it uses the thing on arrival
# if it is in reach. tests/aim_assist_test.py fails the build if either
# pass-through goes. Only the stock right-handed F is taken, only while it
# is still exactly +activate, and the row rebinds like any other.
#
# Note what is *not* here and cannot be added without the same
# argument: +forward, +back, +moveleft, +moveright and everything else
# in default_left.cfg that sits on a key this mod wants. Those keys are
# left alone by being left alone - the installer only takes a key that
# is empty or holds exactly one of these.
REPLACEABLE = (
    "weaponbank 9",
    "weaponbank 10",
    "accessibilityMapNorth",
    "accessibilityMapSouth",
    "accessibilityMapEast",
    "accessibilityMapWest",
    "selectbuddy 1",
    "selectbuddy 3",
    "selectbuddy 4",
    "selectbuddy 5",
    "selectbuddy 7",
    # Picks the whole fireteam: like the slots above, it needs a fireteam
    # and a second command to do anything with the selection, and keypad
    # plus is where the mod puts the marker on the objective.
    "selectbuddy -1",
    "+left",
    "+right",
    "+activate",
    # Zooms in the small map drawn on screen, and nothing else: no sound,
    # no word, no effect on play. Without sight it does nothing at all,
    # and period is where the mod turns the player toward the marker.
    "mapzoomin",
)


def read(root, relative, required=True):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        if required:
            sys.exit("no %s under %s - is this the engine checkout this "
                     "test expects?" % (relative, root))
        return None
    with open(path, "r", errors="replace") as handle:
        return handle.read()


HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.join(HERE, "..", "release", "INSTALL.md.in")


def install_guide():
    """The shipped install guide, or None when it cannot be found."""
    if not os.path.isfile(GUIDE):
        return None
    with open(GUIDE, "r", errors="replace") as handle:
        return handle.read()


def documents_key(guide, name):
    """Whether the guide names this key where a left-handed player looks.

    Deliberately requires the key to appear in the same passage as the
    left-handed layout rather than merely somewhere in the document. A
    key mentioned only in the general key list tells a left-handed
    player nothing about why it does not work for them.
    """
    lowered = guide.lower()
    anchor = lowered.find("left-handed")

    if anchor < 0:
        return False

    # Every passage that mentions the layout, not just the first: the
    # guide names it in more than one place and only one of them is the
    # section a player would act on.
    while anchor >= 0:
        passage = guide[anchor:anchor + 2500]

        # A key that is a letter or a word is matched as a word; one that
        # is punctuation - [ or ] - as itself, with space or markup round
        # it, since a word boundary never falls either side of it.
        if re.match(r'\w', name):
            pattern = r'\b%s\b' % re.escape(name)
        else:
            pattern = r'(?:^|[\s`*(])%s(?:$|[\s`*),.])' % re.escape(name)

        if re.search(pattern, passage, re.I):
            return True

        anchor = lowered.find("left-handed", anchor + 1)

    return False


def body_of(text, function):
    """The braced body of a function, found by counting braces.

    Anchored on the name followed by an argument list, so a call site
    elsewhere in the file cannot be mistaken for the definition.
    """
    match = re.search(r'\b%s\s*\([^)]*\)\s*\{' % re.escape(function), text)
    if not match:
        return ""

    depth = 0
    start = match.end() - 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def mod_cfg_binds(text):
    """key -> command, from the mod's own autoexec.cfg.

    Separate from stock_binds because the two files are written
    differently: the engine's configs quote every command, the mod's
    does not. Kept apart rather than loosening the engine parser, which
    should stay strict about the format it actually reads.
    """
    return dict((m.group(1).upper(), m.group(2).strip().strip('"'))
                for m in re.finditer(r'^\s*bind\s+(\S+)\s+("?[^"\n]+"?)\s*$',
                                     text, re.M))


def stock_binds(text):
    """key -> command, from a shipped .cfg."""
    return dict((m.group(1).upper(), m.group(2))
                for m in re.finditer(r'^\s*bind\s+(\S+)\s+"([^"]*)"',
                                     text, re.M))


def mod_binds(ui_main_c):
    """The table the mod installs: (key token, command, replaces)."""
    start = ui_main_c.find("UI_AccessibilityInstallBinds")
    if start < 0:
        sys.exit("could not find UI_AccessibilityInstallBinds in %s - the "
                 "binds this test exists to guard are gone" % UI_MAIN)

    body = ui_main_c[start:ui_main_c.index("};", start)]
    rows = re.findall(r'\{\s*(K_[A-Z0-9_]+|\'\\.\'|\'.\')\s*,\s*"([^"]+)"\s*,\s*'
                      r'(NULL|"[^"]*")\s*,\s*(\d+)\s*\}', body)

    if not rows:
        sys.exit("read no bind rows out of UI_AccessibilityInstallBinds - "
                 "this test is out of date with the mod, and passing "
                 "without reading them would defeat its purpose")

    return rows


def key_token_to_cfg_name(token):
    """K_KP_SLASH -> KP_SLASH, K_F5 -> F5, '9' -> 9, '\\'' -> '."""
    if token.startswith("'"):
        inner = token[1:-1]
        if inner.startswith("\\"):
            inner = inner[1:]   # a C escape: '\'' is the apostrophe
        return inner.upper()
    return token[2:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=["etlegacy", "id-software"])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    failures = []

    # --- the focus guard, on both engines -------------------------------
    focus_file = (os.path.join("src", "ui", "ui_menu.c")
                  if args.engine == "etlegacy"
                  else os.path.join("src", "ui", "ui_shared.c"))
    focus = read(root, focus_file)

    if "ETA_MenuCursorMoved" not in focus:
        failures.append(
            "%s no longer defines ETA_MenuCursorMoved, so a parked cursor "
            "takes keyboard focus again on every key press - which is how a "
            "tester pressed Enter on REFRESH LIST and joined a server"
            % focus_file)
    else:
        # The guard has to sit in front of the focus reset, not merely
        # exist somewhere in the file.
        guarded = re.search(
            r'ETA_MenuCursorMoved\s*\(\s*DC->cursorx\s*,\s*DC->cursory\s*\)'
            r'[^;]*?\n(?:[^\n]*\n){0,4}?[^\n]*Menu_HandleMouseMove\s*\(',
            focus, re.S)
        if not guarded:
            failures.append(
                "%s defines ETA_MenuCursorMoved but no longer guards "
                "Menu_HandleMouseMove with it, so the focus reset runs "
                "unconditionally again" % focus_file)
        else:
            print("[keys] %s: the focus reset is behind the cursor-moved "
                  "guard" % focus_file)

    # --- the settings controls answer the keyboard ----------------------
    #
    # Every one of them guarded itself with "is the cursor inside me"
    # *and* "do I have focus". With a hand on the mouse those are one
    # question. From the keyboard they are two, and the first can never
    # be true: arrowing onto a control sets its focus flag and nothing
    # moves the cursor, which stays where it was last pushed. So Enter
    # on a highlighted "Game Type:" did nothing, on the screen where a
    # player is trying to host a game. Checkboxes and yes/no fields sat
    # behind the same line, which is most of the settings in the game.
    item_file = (os.path.join("src", "ui", "ui_menuitem.c")
                 if args.engine == "etlegacy"
                 else os.path.join("src", "ui", "ui_shared.c"))
    items = read(root, item_file)

    if "ETA_ItemTakesKey" not in items:
        failures.append(
            "%s no longer defines ETA_ItemTakesKey, so the settings "
            "controls are back to demanding the mouse cursor sit inside "
            "them - which a keyboard player can never arrange" % item_file)
    else:
        takes = body_of(items, "ETA_ItemTakesKey")

        # Focus still has to be required. Without it every key press
        # would operate a control nobody selected.
        if "WINDOW_HASFOCUS" not in takes:
            failures.append(
                "ETA_ItemTakesKey no longer requires WINDOW_HASFOCUS, so a "
                "key press would operate a control the player never "
                "selected")

        # And the mouse still has to be held to the cursor. A click is
        # an act performed at a place; if this stops testing the rect,
        # clicking anywhere on the screen operates whichever control
        # happens to hold focus, which is a regression for everybody.
        if "Rect_ContainsPoint" not in takes or "K_MOUSE1" not in takes:
            failures.append(
                "ETA_ItemTakesKey no longer holds mouse buttons to the "
                "cursor rectangle, so a click anywhere would operate the "
                "focused control - broken for sighted players, and not "
                "something this mod is entitled to do")

        # Every one of the three has to actually go through it.
        for handler in ("Item_CheckBox_HandleKey",
                        "Item_YesNo_HandleKey",
                        "Item_Multi_HandleKey"):
            if handler not in items:
                failures.append(
                    "%s is gone from %s; the reachability fix cannot be "
                    "checked" % (handler, item_file))
                continue

            body = body_of(items, handler)

            if "ETA_ITEM_REACHED" not in body:
                failures.append(
                    "%s does not go through ETA_ITEM_REACHED, so it is "
                    "keyboard-unreachable again - the control narrates on "
                    "focus and then refuses to change" % handler)

        # The slider is the one that needed inventing rather than
        # un-breaking, because its value comes from where in the bar
        # the pointer was. Both engines get the arrow keys; only ET:
        # Legacy has menus here to walk, so slider_step_test.py checks
        # the arithmetic there and this checks the wiring on both.
        slider = body_of(items, "Item_Slider_HandleKey")

        if "ETA_SliderNudge" not in slider:
            failures.append(
                "Item_Slider_HandleKey no longer steps with "
                "ETA_SliderNudge, so sliders are mouse-only again - "
                "which means volume and mouse sensitivity cannot be set "
                "at all without one")

        for arrow in ("K_LEFTARROW", "K_RIGHTARROW"):
            if arrow not in slider:
                failures.append(
                    "Item_Slider_HandleKey does not answer %s, so a slider "
                    "can only be driven in one direction" % arrow)

        if "Rect_ContainsPoint" not in slider:
            failures.append(
                "Item_Slider_HandleKey no longer tests the pointer against "
                "the bar, so dragging a slider with the mouse is broken - "
                "the keyboard path is an addition, not a replacement")

        if not failures:
            print("[keys] %s: checkbox, yes/no, multi and slider all answer "
                  "the keyboard" % item_file)

    # --- the binds, ET: Legacy only -------------------------------------
    if args.engine != "etlegacy":
        if failures:
            print()
            for failure in failures:
                print("[keys] FAIL %s" % failure)
            sys.exit(1)
        print("[keys] ok")
        return

    stock = stock_binds(read(root, DEFAULT_CFG))
    left_text = read(root, LEFT_CFG, required=False)
    left = stock_binds(left_text) if left_text else {}

    print("[keys] stock layouts bind %d and %d keys"
          % (len(stock), len(left)))

    # weapalt is the reason one of these binds exists. If upstream ever
    # gives it a key, the mod should stop taking one for it.
    weapalt_keys = [k for k, v in stock.items() if v.strip() == "weapalt"]
    keyboard_keys = [k for k in weapalt_keys if not k.startswith("MOUSE")]

    print("[keys] stock binds weapalt to: %s"
          % (", ".join(sorted(weapalt_keys)) or "nothing"))

    if keyboard_keys:
        failures.append(
            "the stock config now reaches weapalt from the keyboard (%s), so "
            "the mod no longer needs to claim a key for it - drop that bind "
            "rather than shadowing upstream"
            % ", ".join(sorted(keyboard_keys)))

    guide = install_guide()

    table = mod_binds(read(root, UI_MAIN))

    for token, command, replaces, _generation in table:
        name = key_token_to_cfg_name(token)

        # The right-handed layout is the one the mod has to work in out
        # of the box, so a clash there is still a hard failure.
        if replaces != "NULL" and replaces.strip('"') not in REPLACEABLE:
            failures.append(
                "the %s bind declares it replaces %r, which is not a command "
                "this project has shown to be inert. Naming what is already "
                "on a key is otherwise a way to take any key at all - "
                "movement included - so a new one has to be added to "
                "REPLACEABLE with the reason it is safe"
                % (name, replaces.strip('"')))
            continue

        existing = stock.get(name)
        if existing is not None and not (replaces != "NULL"
                                         and existing.strip() == replaces.strip('"')):
            failures.append(
                "the mod binds %s to %r, but that key is already used in "
                "default.cfg (%s -> %r) - it would silently steal something "
                "a player relies on" % (name, command, name, existing))
            continue

        taken_left = left.get(name)

        if taken_left is None or (replaces != "NULL"
                                  and taken_left.strip() == replaces.strip('"')):
            if replaces != "NULL":
                print("[keys]   %-10s -> %-24s claimed from %s"
                      % (name, command, replaces.strip('"')))
            else:
                print("[keys]   %-10s -> %-24s free in both layouts"
                      % (name, command))
            continue

        # Free on the right-handed layout, taken on the left-handed one.
        # The installer will leave it alone there, so nothing is stolen -
        # but the player is owed an explanation in the guide.
        if guide is None:
            failures.append(
                "cannot find the install guide, so the documentation this "
                "rule depends on cannot be checked")
        elif not documents_key(guide, name):
            failures.append(
                "the mod binds %s to %r, which is free in default.cfg but "
                "bound in default_left.cfg (%s -> %r). The installer will "
                "not take it there, so nothing is stolen - but a "
                "left-handed player then has a feature that simply is not "
                "there. The install guide has to name %s so they know what "
                "to bind" % (name, command, name, taken_left, name))
        else:
            print("[keys]   %-10s -> %-24s free right-handed, documented "
                  "for left-handed" % (name, command))

    # --- the installer must offer binds added after a player's first run
    #
    # This one shipped wrong for three releases and could only be found
    # by pressing a key and hearing nothing. eta_bindsInstalled was a
    # flag - had the installer ever run - so every key added in a later
    # version was skipped entirely for anyone who had run an earlier
    # one. The health and ammo keys, the scope key and all eight map
    # keys went out that way. A generation per row is what fixes it, and
    # a row without one would silently go back to never being offered.
    installer = read(root, UI_MAIN)
    body = installer[installer.find("UI_AccessibilityInstallBinds"):]
    body = body[:body.find("\n}")]

    for token, command, _replaces, generation in table:
        if int(generation) < 1:
            failures.append(
                "the %s bind has generation %s. Generations start at 1; a "
                "zero would compare as already-offered and the key would "
                "never be installed for anybody"
                % (key_token_to_cfg_name(token), generation))

    if re.search(r'if\s*\(\s*installed\.integer\s*\)', body):
        failures.append(
            "the installer still returns early when eta_bindsInstalled is "
            "set at all. That is the defect: it makes every bind added in "
            "a later version unreachable for anyone who has run an earlier "
            "one, and nothing in the game says so - the key simply does "
            "nothing")

    stored = re.search(r'trap_Cvar_Set\s*\(\s*"eta_bindsInstalled"\s*,\s*([^)]+)\)',
                       body)
    if not stored:
        failures.append(
            "the installer never records what it has offered, so every key "
            "it installs comes back the next launch even if the player "
            "unbound it on purpose")
    elif re.match(r'^\s*"\d+"\s*$', stored.group(1)):
        failures.append(
            "the installer records the literal %s rather than the newest "
            "generation in its own table. A literal goes stale the moment a "
            "row is added: every generation above it is offered again, "
            "including keys the player deliberately unbound"
            % stored.group(1).strip())

    if "generation" not in body:
        failures.append(
            "the installer does not consider which generation of binds a "
            "player has already been offered")

    # --- and the two ways a player gets these keys must agree ----------
    #
    # A bind reaches a player either because the mod installs it or
    # because they copied the shipped autoexec.cfg. The map keys were
    # added to the installer and forgotten in the config, and the
    # installer could not reach an existing player - so both paths were
    # dead at once and the feature simply did not exist.
    cfg_path = os.path.join(HERE, "..", "release", "autoexec.cfg")
    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", errors="replace") as handle:
            cfg = mod_cfg_binds(handle.read())

        # A key the table names twice is the newer generation's: the
        # older row is kept so players who have it get it moved, not so
        # it is installed.
        newest = {}
        for token, command, _replaces, generation in table:
            name = key_token_to_cfg_name(token)
            if name not in newest or int(generation) > newest[name][1]:
                newest[name] = (command, int(generation))

        for name, (command, _generation) in sorted(newest.items()):
            if cfg.get(name, "").strip() != command:
                failures.append(
                    "the mod installs %s -> %r but the shipped autoexec.cfg "
                    "does not (%r). Those are the only two ways a player "
                    "gets a key, and when a new bind lands in one and is "
                    "forgotten in the other the feature is simply absent"
                    % (name, command, cfg.get(name, "not bound")))

        for name, command in sorted(cfg.items()):
            if not command.lstrip("+").startswith("accessibility"):
                continue
            if not any(key_token_to_cfg_name(t) == name
                       for t, _c, _r, _g in table):
                failures.append(
                    "the shipped autoexec.cfg binds %s -> %r but the mod's "
                    "own installer does not, so a player who did not copy "
                    "the config never gets it" % (name, command))
    else:
        failures.append(
            "cannot find release/autoexec.cfg, so the two bind sources "
            "cannot be compared")

    if failures:
        print()
        for failure in failures:
            print("[keys] FAIL %s" % failure)
        sys.exit(1)

    print("[keys] ok")


if __name__ == "__main__":
    main()

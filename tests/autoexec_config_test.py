#!/usr/bin/env python3
"""Check that the shipped autoexec.cfg names things the game actually has.

Why this exists
---------------
`release/autoexec.cfg` is the one file a player edits by hand, and it is
the only configuration surface the mod has. It is also the one place
where a mistake is completely silent.

A misspelled cvar does not fail: the engine creates it as a user cvar
(Cvar_Get's CVAR_USER_CREATED branch), stores the value, and nothing
ever reads it. A misspelled command is worse - `bind h accessibilitStatus`
binds the key successfully and the key then does nothing. A sound path
that is not in the game's assets makes trap_S_RegisterSound return 0,
and the cue plays silence.

Every one of those failures looks, to a blind player testing the mod,
exactly like the mod not working. None of them produces a diagnostic
they can hear. So the names are checked here instead, against the
patched engine tree rather than a list copied into this file - a copied
list agrees with itself forever.

What is checked
---------------
1. Every command bound in the cfg is in a cgame command table.
2. Every eta_ cvar set in the cfg is registered by the integration.
3. Every cue value in the cfg matches the built-in default it claims to
   repeat, so the comments in the cfg stay true.
4. Every cue sound path is one the *stock* engine already registers,
   which is what makes it certain the asset ships with the game.
5. Every command the integration binds *itself*, in ui_main.c, is a real
   command too. Those binds exist so the mod works without the config
   file at all, which means nobody is reading them - they fail exactly
   as silently as a misspelling in the cfg, and with nothing to inspect.

Usage
-----
    ./autoexec_config_test.py <engine-root> [--cfg release/autoexec.cfg]

Run it against an ET: Legacy tree with the patch series applied. It
exits non-zero on any mismatch.
"""

import argparse
import os
import re
import sys

# Command tables live here in both engine trees.
COMMAND_TABLE = os.path.join("src", "cgame", "cg_consolecmds.c")

# The ui module answers some of the same names, so a bound command that
# is not in cgame's table may still be real.
UI_TABLE = os.path.join("src", "ui", "ui_atoms.c")

# And the client itself registers the movement and look commands -
# +forward, +left, +lookup and the rest. Those are not the mod's to
# provide and the patch series does not touch this file, so what is
# read here is the stock engine a player actually runs.
#
# This had to be added the day the arrow keys were bound to turning and
# looking, and it immediately earned itself: `centerview`, which ET's
# own default_left.cfg binds to HOME, is registered by nothing in the
# tree at all. That bind has been dead for as long as the file has
# shipped, and the mod nearly copied it.
CLIENT_TABLE = os.path.join("src", "client", "cl_input.c")

# Cmd_AddCommand("+left", IN_LeftDown);
ADD_COMMAND = re.compile(r'Cmd_AddCommand\s*\(\s*"([^"]+)"')

# Where the integration installs its own default binds.
BIND_INSTALLER = os.path.join("src", "ui", "ui_main.c")

# Rows in the installer's table, in either key form it uses:
#   { K_F5, "accessibilityStatus",  NULL           },
#   { '9',  "accessibilityHealth",  "weaponbank 9" },
# A character literal is as real a key as a K_ constant, and a pattern that
# only understood one of them would quietly check half the table.
# The leading + matters: the look and turn binds the mod installs are
# +lookup and friends, and a pattern that only understood bare words
# skipped exactly the rows that turned out to need checking.
CODE_BIND_ROW = re.compile(
    r'\{\s*(K_[A-Z0-9_]+|\'[^\']\')\s*,\s*"([+-]?[A-Za-z0-9_]+)"\s*[,}]')

# Sounds the mod brings itself, rather than borrowing from the game.
# These are generated into the pk3 by the release build, so they are
# legitimately absent from the engine's own registrations.
MOD_SOUND_PREFIX = "sound/accessibility/"

# Where the stock engine registers the sounds it ships with.
STOCK_SOUNDS = os.path.join("src", "cgame", "cg_main.c")

# { "eta_cueLowHealth", "sound/player/gasp.wav", ... } in the cue table.
CUE_ROW = re.compile(r'\{\s*"(eta_[A-Za-z0-9_]+)"\s*,\s*"([^"]*)"')

# An eta_ cvar registered by a direct call rather than through the cue
# table. Cue sounds are one kind of setting the mod adds; a plain
# on/off like the objective callouts is another, and it still has to be
# registered or the config line is stored and never read.
REGISTER_CALL = re.compile(
    r'trap_Cvar_Register\s*\(\s*&\s*[A-Za-z0-9_]+\s*,\s*'
    r'"(eta_[A-Za-z0-9_]+)"\s*,\s*"([^"]*)"')

# ...and the same settings written as a table row instead, which is how
# both trees do it now: ET: Legacy in its own eta_settings[], the 2010
# tree inside the engine's cvarTable. The registration moved into a loop
# so that registering and refreshing could not drift apart - see
# tests/settings_live_test.py - and this pattern followed it, because a
# scraper that only understands the old shape reports every setting as
# unregistered and is worse than useless.
#
#   { &eta_doorCues,  "eta_doorCues",  "1" },
#   { &eta_doorCues,  "eta_doorCues",  "1", CVAR_ARCHIVE },
SETTING_ROW = re.compile(
    r'\{\s*&\s*[A-Za-z0-9_]+\s*,\s*"(eta_[A-Za-z0-9_]+)"\s*,\s*"([^"]*)"')

# { "accessibilityStatus", CG_AccessibilityStatus_f },
# { "+accessibilityTurnLeft", CG_AccessibilityTurnLeftDown_f },
TABLE_ROW = re.compile(r'\{\s*"([+-]?[A-Za-z0-9_]+)"\s*,\s*[A-Za-z_]')

REGISTER_SOUND = re.compile(r'trap_S_RegisterSound\s*\(\s*"([^"]+)"')


def read_cfg(path):
    """Pull the binds and the seta values out of the config file."""
    binds = []
    setas = []
    with open(path, "r", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            line = line.split("//", 1)[0].strip()
            if not line:
                continue
            fields = re.findall(r'"([^"]*)"|(\S+)', line)
            words = [quoted or bare for quoted, bare in fields]
            if not words:
                continue
            verb = words[0].lower()
            if verb == "bind" and len(words) >= 3:
                # `bind h accessibilityStatus` - the command is what the
                # key runs, which may itself be several words.
                binds.append((number, words[2].split()[0]))
            elif verb in ("set", "seta", "sets", "setu") and len(words) >= 3:
                setas.append((number, words[1], words[2]))
    return binds, setas


def sources(root):
    for base, dirs, names in os.walk(os.path.join(root, "src")):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            if name.endswith((".c", ".h")):
                yield os.path.join(base, name)


def mod_sound_names(library_root):
    """The sounds release/make-cue-sounds.py actually produces.

    Read out of the generator rather than listed here, so a rename in
    one place cannot quietly disagree with the other.
    """
    path = os.path.join(library_root, "release", "make-cue-sounds.py")
    if not os.path.isfile(path):
        return set()
    with open(path, "r", errors="replace") as handle:
        text = handle.read()
    return set(MOD_SOUND_PREFIX + name
               for name in re.findall(r'"([a-z0-9_]+\.wav)"\s*:', text))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout with the patch series applied")
    parser.add_argument("--cfg", default=None, help="config to check")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    cfg = args.cfg or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir,
        "release", "autoexec.cfg")

    if not os.path.isfile(cfg):
        sys.exit("no config at %s" % cfg)

    table_path = os.path.join(root, COMMAND_TABLE)
    if not os.path.isfile(table_path):
        sys.exit("no %s under %s - is this an engine checkout?" % (COMMAND_TABLE, root))

    binds, setas = read_cfg(cfg)

    # An empty parse means the extractor broke, not that the config is
    # clean. Fail loudly rather than reporting nothing to check.
    if not binds:
        sys.exit("found no bind in %s - the config or this parser is wrong" % cfg)
    if not setas:
        sys.exit("found no seta in %s - the config or this parser is wrong" % cfg)

    with open(table_path, "r", errors="replace") as handle:
        commands = set(TABLE_ROW.findall(handle.read()))

    ui_path = os.path.join(root, UI_TABLE)
    if os.path.isfile(ui_path):
        with open(ui_path, "r", errors="replace") as handle:
            commands |= set(TABLE_ROW.findall(handle.read()))

    client_path = os.path.join(root, CLIENT_TABLE)
    if os.path.isfile(client_path):
        with open(client_path, "r", errors="replace") as handle:
            client_commands = set(ADD_COMMAND.findall(handle.read()))
        if not client_commands:
            sys.exit("read no Cmd_AddCommand out of %s - this parser is "
                     "wrong, and a silent pass would let a bind to a "
                     "command nobody registers go out" % CLIENT_TABLE)
        commands |= client_commands

    # The binds the integration installs for itself, read out of the
    # patched tree rather than repeated here.
    code_binds = []
    installer_path = os.path.join(root, BIND_INSTALLER)
    if os.path.isfile(installer_path):
        with open(installer_path, "r", errors="replace") as handle:
            installer = handle.read()
        if "eta_bindsInstalled" in installer:
            code_binds = CODE_BIND_ROW.findall(installer)
            if not code_binds:
                sys.exit("%s installs default binds but none could be read - "
                         "this parser is wrong, and a silent pass here is "
                         "the failure it exists to catch" % BIND_INSTALLER)

    cue_defaults = {}
    plain_defaults = {}
    for path in sources(root):
        with open(path, "r", errors="replace") as handle:
            text = handle.read()
        if "eta_cue" in text:
            for name, default in CUE_ROW.findall(text):
                cue_defaults[name] = default
        for name, default in REGISTER_CALL.findall(text):
            plain_defaults[name] = default
        for name, default in SETTING_ROW.findall(text):
            # The cue tables use the same row shape but are keyed by
            # sound path, and they are handled above; a name that is
            # already known as a cue stays one.
            if name not in cue_defaults:
                plain_defaults[name] = default

    stock_path = os.path.join(root, STOCK_SOUNDS)
    stock_sounds = set()
    # This repository, which is where the generator lives.
    library_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mod_sounds = mod_sound_names(library_root)
    if os.path.isfile(stock_path):
        with open(stock_path, "r", errors="replace") as handle:
            stock_sounds = set(REGISTER_SOUND.findall(handle.read()))

    print("[autoexec] %s" % cfg)
    print("[autoexec] %d bind(s), %d setting(s); engine offers %d command(s), "
          "%d cue cvar(s), %d other cvar(s), %d stock sound(s)"
          % (len(binds), len(setas), len(commands), len(cue_defaults),
             len(plain_defaults), len(stock_sounds)))

    failures = []

    for number, command in binds:
        if command in commands:
            print("[autoexec]   bind %s -> in %s" % (command, COMMAND_TABLE))
        else:
            failures.append("line %d: `%s` is not a command in %s - the key "
                            "would bind and do nothing"
                            % (number, command, COMMAND_TABLE))

    for number, name, value in setas:
        if name in plain_defaults and name not in cue_defaults:
            # Not a sound, so there is no asset to check - only that it is
            # registered and that the config agrees with the built-in
            # default, so the file documents rather than contradicts it.
            if plain_defaults[name] != value:
                failures.append("line %d: %s is set to %r but the built-in "
                                "default is %r; the config says these agree"
                                % (number, name, value, plain_defaults[name]))
            else:
                print("[autoexec]   seta %s -> default matches" % name)
            continue

        if name not in cue_defaults:
            failures.append("line %d: `%s` is not registered by the "
                            "integration - the value would be stored and "
                            "never read" % (number, name))
            continue
        if cue_defaults[name] != value:
            failures.append("line %d: %s is set to %r but the built-in "
                            "default is %r; the config says these agree"
                            % (number, name, value, cue_defaults[name]))
        elif value.startswith(MOD_SOUND_PREFIX):
            # The mod's own sounds, generated and packed into the pk3
            # rather than borrowed from the game. They are legitimately
            # not stock, so the stock-asset rule cannot apply - but they
            # still have to exist, which cue_sounds_test.py proves by
            # running the generator and comparing. Checking it here too
            # would mean two places to keep in step; what matters here is
            # that an unexplained non-stock path is still caught.
            if value not in mod_sounds:
                failures.append(
                    "line %d: %s points at %r, which is under %s but is "
                    "not one of the sounds release/make-cue-sounds.py "
                    "produces - nothing would generate it, so it would be "
                    "absent from the pk3 and play silence"
                    % (number, name, value, MOD_SOUND_PREFIX))
            else:
                print("[autoexec]   seta %s -> default matches, asset is "
                      "the mod's own" % name)
        elif stock_sounds and value not in stock_sounds:
            failures.append("line %d: %s points at %r, which the stock "
                            "engine never registers - it may not be in the "
                            "game's assets, and an absent sound plays "
                            "silence" % (number, name, value))
        else:
            print("[autoexec]   seta %s -> default matches, asset is stock"
                  % name)

    for key, command in code_binds:
        if command in commands:
            print("[autoexec]   %s -> %s, installed by the mod itself"
                  % (key, command))
        else:
            failures.append("%s binds %s to `%s`, which no command table "
                            "offers - the key would bind and do nothing, "
                            "with no config file to inspect"
                            % (BIND_INSTALLER, key, command))

    # Anything the engine offers that the config never mentions is worth
    # seeing: a new cue is useless to a player who is never told it is
    # there.
    registered = set(cue_defaults) | set(plain_defaults)
    unmentioned = sorted(registered - {name for _, name, _ in setas})
    for name in unmentioned:
        print("[autoexec]   note: %s is registered but not in the config" % name)

    if failures:
        print()
        for failure in failures:
            print("[autoexec] FAIL %s" % failure)
        sys.exit(1)

    print("[autoexec] ok")


if __name__ == "__main__":
    main()

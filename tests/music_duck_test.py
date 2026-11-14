#!/usr/bin/env python3
"""Check the music gets out of the way while the narrator is talking.

Why this exists
---------------
A tester turned the music up and found the narrator underneath it. That
is not a bug in either volume setting: the music is mixed by the game and
the speech is mixed by Windows, through NVDA or SAPI, and neither one can
see the other. No slider anywhere balances them, so turning the music up
genuinely does bury the narration and nothing stops it.

The fix is what broadcast has always done - duck the bed while the voice
is on it - using the engine's own music fade, the same call map scripts
use. Three things about that have to stay true, and none of them is a
compile error:

**It has to come back up.** A duck that never lifts leaves the player
with no music at all, and they would reasonably blame the game rather
than this mod. So every path that ducks needs a path that restores.

**It must not override the map.** Map scripts fade the music themselves.
Restoring to full volume after a narration would turn a script's
deliberate hush back into a soundtrack, for everybody, including players
who never asked for any of this. So the duck is a fraction of what the
game last asked for and the restore goes back to that - which means the
places the game moves the music have to keep telling us.

**It must not be behind the speech hold.** The hold exists to keep the
scenery quiet while an answer is being spoken. Ducking is not speech; a
duck that waited for the hold to clear would dip the music exactly when
the talking had stopped.

Usage
-----
    ./music_duck_test.py <engine-root> [--engine etlegacy|id-software]

Run it against an engine checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

DRAW = os.path.join("src", "cgame", "cg_draw.c")
SERVERCMDS = os.path.join("src", "cgame", "cg_servercmds.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")

DUCK = "ETA_DuckMusicForSpeech"
BASELINE = "ETA_MusicFadeRequested"
FADE = "trap_S_FadeBackgroundTrack"
CVAR = "eta_musicDuck"
SERIAL = "ETA_Speech_GetSpokenSerial"
ESTIMATE = "ETA_Speech_EstimateDurationMs"


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


def function_body(text, name):
    match = re.search(r'\b%s\s*\([^;{}]*\)\s*\{' % re.escape(name), text)
    if not match:
        return None
    depth, i = 0, match.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def if_block(text, condition):
    """The braced body of the first `if` whose condition matches.

    Both trees write their conditions differently - (x) here, ( x )
    there - so the caller passes a regex over the whole `if (...)`.
    """
    match = re.search(r'if\s*\([^{;]*?%s[^{;]*?\)\s*\{' % condition, text)
    if not match:
        return None
    depth, i = 0, match.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def guarded_region(draw):
    """The block the passive narration is called from, behind the hold."""
    found = re.search(r'if\s*\(\s*!\s*ETA_HudNarrator_PassiveHeld\s*\(', draw)
    if not found:
        return None
    brace = draw.find("{", found.start())
    depth, i = 0, brace
    while i < len(draw):
        if draw[i] == "{":
            depth += 1
        elif draw[i] == "}":
            depth -= 1
            if depth == 0:
                return draw[brace + 1:i]
        i += 1
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=("etlegacy", "id-software"))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    draw = read(root, DRAW)
    servercmds = read(root, SERVERCMDS)
    main_c = read(root, MAIN)

    failures = []

    body = function_body(draw, DUCK)
    if body is None:
        sys.exit("could not find %s in %s - the ducking this test exists to "
                 "guard is gone" % (DUCK, DRAW))

    tight = re.sub(r'\s+', '', body)

    # 1. It reacts to speech starting, and waits for an estimated end.
    if SERIAL not in body:
        failures.append(
            "%s does not watch %s, so it cannot tell that anything is being "
            "said - a duck that never fires is the same as no duck"
            % (DUCK, SERIAL))

    if ESTIMATE not in body:
        failures.append(
            "%s does not ask %s how long to stay out of the way. Neither "
            "speech backend reports when the words stop, so the length of "
            "the line is the only evidence there is; without it the duck "
            "has no end" % (DUCK, ESTIMATE))

    # 2. It both ducks and restores - and the restore has to be on the
    #    paths that actually end a duck, not merely somewhere in the
    #    function. There are exactly two ways a duck ends: the player
    #    turns the setting off while it is on, and the line finishes.
    #    Each needs its own way back, and a count of fades would be
    #    satisfied by either one of them twice.
    restore = re.escape(FADE) + r'\s*\(\s*gMusicBaseline\s*,'

    off_path = if_block(body, re.escape(CVAR))
    if off_path is None:
        failures.append(
            "%s has no branch testing %s, so the setting cannot turn it off"
            % (DUCK, CVAR))
    elif not re.search(restore, off_path):
        failures.append(
            "turning %s off while the music is ducked leaves it ducked: that "
            "branch of %s never fades back to the baseline. The player would "
            "switch the feature off and be left with the quiet music it "
            "caused" % (CVAR, DUCK))
    else:
        print("[duck] turning the setting off restores the music")

    expiry = if_block(body, "gMusicDuckUntil")
    if expiry is None:
        failures.append(
            "%s has no branch testing the end of the estimate, so a duck "
            "that started has nothing to end it" % DUCK)
    elif not re.search(restore, expiry):
        failures.append(
            "%s never fades back to the baseline when the line has finished. "
            "A duck with no lift leaves the player with no music for the "
            "rest of the map, and nothing to blame but the game" % DUCK)
    else:
        print("[duck] the music comes back when the line ends")

    if not re.search(re.escape(FADE) + r'\s*\(\s*gMusicBaseline\s*\*', body):
        failures.append(
            "%s never fades the music *down* to a fraction of the baseline, "
            "so nothing actually gets out of the narrator's way" % DUCK)

    # 3. The restore goes back to the baseline, never to a hardcoded full
    #    volume. This is the one that silently breaks other people's maps.
    restores_to_one = re.search(r'%s\(1\.0f?,' % re.escape(FADE), tight)
    if restores_to_one:
        failures.append(
            "%s fades the music to a hardcoded 1.0. Map scripts fade the "
            "music themselves, and restoring to full afterwards turns a "
            "script's deliberate hush back into a soundtrack - for "
            "everybody, including players who never turned any of this on. "
            "Restore to the level the game last asked for" % DUCK)

    if "gMusicBaseline" not in body:
        failures.append(
            "%s does not use the game's own music level, so whatever it "
            "restores cannot be what the map wanted" % DUCK)

    # 4. The setting exists, is registered, and 1 means off.
    if CVAR not in body:
        failures.append("%s cannot be turned off - %s is not consulted"
                        % (DUCK, CVAR))
    elif not re.search(r'if\s*\([^{;]*%s' % re.escape(CVAR), body):
        failures.append(
            "%s reads %s but never branches on it, so the setting scales the "
            "duck without being able to switch it off. A player who set it "
            "to the off position would still have their music moved"
            % (DUCK, CVAR))

    if not re.search(r'"%s"\s*,\s*"1"' % re.escape(CVAR), main_c):
        failures.append(
            "%s is not registered with a default of \"1\". Ducking changes "
            "audio the player already had set up, so the shipped default "
            "has to be the off position" % CVAR)

    # 5. Every place the game moves the music tells the duck about it.
    #    Missing one means the duck is applied over a stale baseline and
    #    the restore puts the music somewhere the map never asked for.
    #
    #    Counted per handler rather than per call: "mu_stop" fades the old
    #    track and starts a queued one, which is two calls and one
    #    decision. So each mover is checked against the rest of its own
    #    handler - up to the return that ends it - rather than against a
    #    total, which would have demanded two reports for one event.
    movers = list(re.finditer(
        r'trap_S_(?:FadeBackgroundTrack|StartBackgroundTrack)\s*\(',
        servercmds))
    unreported = []

    for mover in movers:
        end = servercmds.find("return", mover.end())
        if end < 0:
            end = len(servercmds)
        # Far enough past the return to catch a report placed after it in
        # source order but before it in execution - there is none today,
        # and a future one should still count.
        window = servercmds[mover.start():end + 40]
        if BASELINE not in window:
            line = servercmds.count("\n", 0, mover.start()) + 1
            unreported.append(line)

    if not movers:
        sys.exit("found no music calls in %s - this test is out of date with "
                 "the engine, and passing without reading them would defeat "
                 "its purpose" % SERVERCMDS)

    if BASELINE not in servercmds:
        failures.append(
            "%s is never called from %s, so the duck cannot know what level "
            "the map asked for" % (BASELINE, SERVERCMDS))
    elif unreported:
        failures.append(
            "%s moves the music at line(s) %s without telling %s. That "
            "leaves the duck working from a stale level, and the restore "
            "then puts the music somewhere the map never asked for"
            % (SERVERCMDS, ", ".join(str(n) for n in unreported), BASELINE))
    else:
        print("[duck] all %d music moves in %s report the level"
              % (len(movers), SERVERCMDS))

    # 6. And it is called every frame, not from behind the speech hold.
    if not re.search(r'\b%s\s*\(\s*\)\s*;' % re.escape(DUCK), draw):
        failures.append(
            "%s is defined but never called, so none of this reaches a "
            "player" % DUCK)
    else:
        held = guarded_region(draw)
        if held is None:
            failures.append(
                "could not find the passive-hold block in %s, so this cannot "
                "check that the duck is outside it" % DRAW)
        elif DUCK in held:
            failures.append(
                "%s is called from behind ETA_HudNarrator_PassiveHeld. That "
                "hold exists to keep the scenery quiet while an answer is "
                "spoken - ducking from behind it would dip the music exactly "
                "when the talking had stopped" % DUCK)
        else:
            print("[duck] %s runs every frame, outside the speech hold" % DUCK)

    if failures:
        print()
        for failure in failures:
            print("[duck] FAIL %s" % failure)
        sys.exit(1)

    print("music_duck_test: %s - the music steps back while the narrator "
          "talks, returns to the level the map asked for, and ships off"
          % args.engine)


if __name__ == "__main__":
    main()

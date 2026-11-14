#!/usr/bin/env python3
"""Check the game's announcer has a volume of its own, and it is honoured.

The tester found the map's recorded voice - "the bridge has been
destroyed" - louder than the marker, and asked for a volume for it. The
voice reaches the game two ways, and each is checked against the game's
own code:

- most of it is a sound script the map streams, buffered so two never
  overlap. A stream takes no volume of its own, so below full it is
  played as an ordinary sound, which does - at the level that matches a
  stream at full (255 on the game's scale, read from the mixer here),
  from the player's own head, since a sound with no place and no entity
  stops the game;
- the rest is an ordinary sound, which the game plays at 127; it is
  scaled from that;
- at 100 nothing changes: the game's own way, untouched; at 0, silence.

And the setting is everywhere a setting is: registered at 100, a slider
on Accessibility -> Sound, in the shipped config and in the guide.

    ./announcer_volume_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SOUND = os.path.join("src", "cgame", "cg_sound.c")
EVENT = os.path.join("src", "cgame", "cg_event.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
SYSCALLS = os.path.join("src", "cgame", "cg_syscalls.c")
SND_DMA = os.path.join("src", "client", "snd_dma.c")
SND_MIX = os.path.join("src", "client", "snd_mix.c")
SND_AL = os.path.join("src", "client", "snd_openal.c")
MENU = os.path.join(REPO, "release", "ui", "options_accessibility_sound.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")
GUIDE = os.path.join(REPO, "release", "INSTALL.md.in")


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def function_body(text, name):
    match = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return ""
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    sound = strip_comments(read(os.path.join(root, SOUND)))
    event = strip_comments(read(os.path.join(root, EVENT)))
    main_c = strip_comments(read(os.path.join(root, MAIN)))
    syscalls = strip_comments(read(os.path.join(root, SYSCALLS)))
    dma = strip_comments(read(os.path.join(root, SND_DMA)))
    mix = strip_comments(read(os.path.join(root, SND_MIX)))
    openal = strip_comments(read(os.path.join(root, SND_AL)))
    failures = []

    if "CG_AccessibilityAnnouncerVolume" not in main_c:
        sys.exit("no announcer volume in %s - the feature this test measures is gone" % MAIN)

    # --- the game's own scale -----------------------------------------------
    start_sound = function_body(syscalls, "trap_S_StartSound")
    if "CG_S_STARTSOUND, origin, entityNum, entchannel, sfx, 127" not in start_sound:
        failures.append("the game no longer plays an ordinary sound at 127")
    if not ("snd_vol = s_volume->value * s_volCurrent * 255;" in mix
            and "lintVolume = 256 * lvol * s_volume->value;" in dma
            and "curSource->curGain      = volume / 255.0f;" in openal):
        failures.append("the mixer no longer puts a stream at full level with a sound at 255")
    if not re.search(r"if \(!origin && \(entnum < 0 \|\| entnum >= MAX_GENTITIES\)\)\s*\{\s*Com_Error", dma):
        failures.append("the game's rule on a sound with no place has changed")
    if not failures:
        print("[announcer] the game plays a sound at 127, a stream as loud as one at 255, "
              "and stops on a sound with no place or entity")

    # --- the voice, at the volume -------------------------------------------
    # Its definition shares a body with the game's own under #else, so it
    # is cut out by hand: from the definition to the next function.
    begin = sound.rfind("static int CG_SoundPickOldestRandomSoundVolume(")
    pick = sound[begin:sound.find("void CG_AddBufferedSoundScript", begin)] if begin >= 0 else ""
    buffered = function_body(sound, "CG_AddBufferedSoundScript") + function_body(sound, "CG_UpdateBufferedSoundScripts")
    if not re.search(r"if \(volume >= 0 && !sound->looping && cg\.snap\)", pick) \
            or "trap_S_RegisterSound(oldestSound->sounds[pos].filename" not in pick \
            or "((sound->streaming ? 255 : 127) * volume) / 100" not in pick \
            or "org ? entnum : cg.snap->ps.clientNum" not in pick:
        failures.append("a buffered voice below full is not played as an ordinary sound, at its own level, "
                        "from the player's own head")
    elif buffered.count("CG_SoundPickOldestRandomSoundVolume(cg.bufferSoundScripts[0], NULL, -1, "
                        "CG_AccessibilityAnnouncerVolume())") != 2:
        failures.append("the map's voice is not played at the announcer volume")
    else:
        print("[announcer] the map's streamed voice is played at the announcer volume")

    global_sound = function_body(event, "CG_PlayGlobalSound")
    if global_sound.count("trap_S_StartSoundVControl(NULL, cg.snap->ps.clientNum, CHAN_AUTO, sound, (127 * volume) / 100);") != 2 \
            or "CG_SoundPlaySoundScript(s, NULL, -1, qtrue)" not in global_sound:
        failures.append("the map's voice played as an ordinary sound is not scaled from the game's 127")
    else:
        print("[announcer] the map's ordinary voice sounds are scaled from the game's 127")

    volume = function_body(main_c, "CG_AccessibilityAnnouncerVolume")
    if not re.search(r"if \(percent >= 100\)\s*\{\s*return -1;", volume):
        failures.append("at 100 the game's own way is not left alone")
    else:
        print("[announcer] at 100 the game's own way is untouched")

    # --- the setting --------------------------------------------------------
    for ok, what in (
            ('{ &eta_announcerVolume,     "eta_announcerVolume",     "100" }' in read(os.path.join(root, MAIN)),
             "eta_announcerVolume is not registered at 100"),
            ('"eta_announcerVolume" 100 0 100' in read(MENU) and "Announcer volume:" in read(MENU),
             "Accessibility -> Sound has no announcer volume slider"),
            (re.search(r'^seta eta_announcerVolume\s+"100"', read(AUTOEXEC), re.M),
             "the shipped config does not set the announcer volume"),
            ('seta eta_announcerVolume "100"' in read(GUIDE) and "Announcer volume" in read(GUIDE),
             "the guide does not tell where the announcer volume is")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "eta_announcerVolume" in f or "slider" in f or "config" in f or "guide" in f]:
        print("[announcer] registered at 100, on Accessibility -> Sound, in the config and the guide")

    if failures:
        for failure in failures:
            print("[announcer] FAIL %s" % failure)
        sys.exit(1)
    print("announcer_volume_test: the game's announcer has a volume of its own")


if __name__ == "__main__":
    main()

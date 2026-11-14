#!/usr/bin/env python3
"""Check the mod's sounds have a volume each, on a page of their own.

The tester asked for the volumes of the audio cues and the announcer to
be on a page of their own, not mixed in with Speech, where the screen
reader's settings are. So:

- every looping sound the mod plays - the marker, the objective sounds
  and the tank, doors, ladders, the crosshair tick, things to pick up -
  is played at its own setting, on
  the scale the game hands a looping sound (255 full, the level each
  always had), and each kind of sound has its setting;
- the one-shot alerts are played at theirs, at the game's own 127 when
  full;
- the Sound page has a slider for each, from 0 to 100, is opened from
  the Accessibility page and leads back to it, is loaded by the ui and
  packed; Speech no longer holds the announcer;
- each is registered at 100 and in the shipped config.

    ./sound_page_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SOURCES = [os.path.join("src", "cgame", name) for name in ("cg_draw.c", "cg_commandmap.c", "cg_main.c")]
MAIN = os.path.join("src", "cgame", "cg_main.c")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")
UI = os.path.join(REPO, "release", "ui")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")
BUILD = os.path.join(REPO, "release", "build-release.sh")

VOLUMES = {
    "eta_markerVolume": ("ETA_LOOP_MARKER", "ETA_LOOP_MARKER_SIDE", "ETA_LOOP_MARKER_BEHIND"),
    "eta_siteVolume": ("ETA_LOOP_BUILD_SITE", "ETA_LOOP_DEMOLITION_TARGET", "ETA_LOOP_FLAG", "ETA_LOOP_TANK"),
    "eta_pickupVolume": ("ETA_LOOP_HEALTH", "ETA_LOOP_AMMO", "ETA_LOOP_WEAPON"),
    "eta_doorVolume": ("ETA_LOOP_DOOR", "ETA_LOOP_DOOR_LOCKED"),
    "eta_ladderVolume": ("ETA_LOOP_LADDER",),
    "eta_crosshairVolume": ("ETA_LOOP_CROSSHAIR_ENEMY", "ETA_LOOP_CROSSHAIR_TEAMMATE"),
}
ALL = tuple(VOLUMES) + ("eta_cueVolume", "eta_announcerVolume")


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
    main_c = strip_comments(read(os.path.join(root, MAIN)))
    failures = []

    if "CG_AccessibilityLoopVolume" not in main_c:
        sys.exit("no sound volumes in %s - the feature this test measures is gone" % MAIN)

    # --- every looping sound, at its setting --------------------------------
    calls = 0
    for source in SOURCES:
        text = strip_comments(read(os.path.join(root, source)))
        for call in re.findall(r"trap_S_AddLoopingSound\(([^;]*)\);", text):
            if "flameSound" in call:
                continue    # the game's own fire, not the mod's
            calls += 1
            if "CG_AccessibilityLoopVolume(" not in call:
                failures.append("a looping sound in %s plays at a fixed level: %s" % (source, call.strip()))
    volume = function_body(main_c, "CG_AccessibilityLoopVolume")
    for cvar, kinds in VOLUMES.items():
        for kind in kinds:
            if kind not in volume and not (cvar == "eta_markerVolume" and "default:" in volume):
                failures.append("%s has no volume of its own" % kind)
        if "&%s" % cvar not in volume:
            failures.append("%s is never read" % cvar)
    if "return (255 * ETA_VolumePercent(cvar)) / 100;" not in volume:
        failures.append("a looping sound at full is not the 255 it always had")
    if not failures:
        print("[sound] all %d looping sounds play at their own setting, 255 at full" % calls)

    cue = function_body(main_c, "ETA_PlayCueSound")
    if "(127 * ETA_VolumePercent(&eta_cueVolume)) / 100" not in cue or "trap_S_StartSoundVControl(origin, -1, CHAN_AUTO, sfx, volume);" not in cue:
        failures.append("the alerts are not played at their setting")
    else:
        print("[sound] the alerts play at their setting, the game's 127 at full")

    # --- the page -----------------------------------------------------------
    page = read(os.path.join(UI, "options_accessibility_sound.menu"))
    hub = read(os.path.join(UI, "options_accessibility.menu"))
    speech = read(os.path.join(UI, "options_accessibility_speech.menu"))
    for cvar in ALL:
        if not re.search(r'SLIDER\([^\n]*"%s" 100 0 100' % cvar, page):
            failures.append("the Sound page has no slider for %s" % cvar)
        if '{ &%s,' % cvar not in read(os.path.join(root, MAIN)):
            failures.append("%s is not registered" % cvar)
        if not re.search(r'^seta %s\s+"100"' % cvar, read(AUTOEXEC), re.M):
            failures.append("the shipped config does not set %s" % cvar)
    if "eta_announcerVolume" in speech:
        failures.append("the announcer is still on the Speech page")
    if "open options_accessibility_sound" not in hub or "open options_accessibility\n" not in page.replace(" ;", "\n").replace(")", "\n"):
        failures.append("the Sound page is not opened from Accessibility, or does not lead back")
    if 'UI_ParseMenu("ui/options_accessibility_sound.menu");' not in read(os.path.join(root, UI_MAIN)):
        failures.append("the ui does not load the Sound page")
    if "options_accessibility_sound.menu" not in read(BUILD):
        failures.append("the release does not pack the Sound page")
    if not [f for f in failures if "page" in f or "slider" in f or "config" in f or "registered" in f]:
        print("[sound] the Sound page has all %d, reached from Accessibility, loaded and packed; "
              "registered at 100 and in the config" % len(ALL))

    if failures:
        for failure in failures:
            print("[sound] FAIL %s" % failure)
        sys.exit(1)
    print("sound_page_test: each of the mod's sounds has a volume, on the Sound page")


if __name__ == "__main__":
    main()

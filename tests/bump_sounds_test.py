#!/usr/bin/env python3
"""Check walking into a wall thuds, and walking into a thing knocks.

The tester asked for what audio games do: a sound when the way is shut.
ETA_BeaconBump is lifted out of the patched engine unchanged and run
against a world laid out by hand, with the player walking:

- straight into a wall, it thuds once from where they hit, not again for
  a moment, then again while they keep pushing;
- along the wall, or onto a step, or standing still, or in the air, it
  is silent;
- into a thing - an entity, or furniture the map names - it knocks; a
  window the map names is the wall it is in;
- with the setting off, nothing.

And the wiring: the sounds are made, registered, on their pages, and in
the shipped config.

    ./bump_sounds_test.py <engine-root>
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRAW = os.path.join("src", "cgame", "cg_draw.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")
ENVIRONMENT = os.path.join(REPO, "release", "ui", "options_accessibility_environment.menu")
SOUND = os.path.join(REPO, "release", "ui", "options_accessibility_sound.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")
SOUNDS = os.path.join(REPO, "release", "make-cue-sounds.py")

HARNESS = r'''
#include "q_shared.h"
#include "game/bg_public.h"
#include <stdio.h>
#include <math.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

typedef enum { ETA_LOOP_BUMP_WALL = 16, ETA_LOOP_BUMP_OBJECT = 17 } eta_loopSoundType_t;
typedef struct { int numEntities; playerState_t ps; } snapshot_t;
static snapshot_t snapshot;
static struct { snapshot_t *snap; int time; playerState_t predictedPlayerState; } cg;
static struct { int integer; } eta_bumpCues = { 1 };

/* What the player presses, and the world. */
static usercmd_t pressed;
static int       hitEntity = ENTITYNUM_WORLD;
static float     wallNormalZ = 0.0f;
static const char *propHere;

int trap_GetCurrentCmdNumber(void) { return 1; }
qboolean trap_GetUserCmd(int n, usercmd_t *cmd) { (void)n; *cmd = pressed; return qtrue; }

/* A wall across x = 20, facing the player at the origin: the player's
   box, 15 across, is 5 from it. Walking along it, 70 degrees off, the
   box pushed 8 the way they go touches it too. */
static void CG_Trace(trace_t *result, const vec3_t start, const vec3_t mins, const vec3_t maxs, const vec3_t end,
                     int skip, int mask)
{
	(void)mins; (void)maxs; (void)skip; (void)mask;
	memset(result, 0, sizeof(*result));
	result->fraction = 1.0f;
	VectorCopy(end, result->endpos);
	if (end[0] + 15.0f > 17.0f)
	{
		result->fraction  = 0.5f;
		VectorCopy(start, result->endpos);
		result->endpos[0] = 5.0f;
		VectorSet(result->plane.normal, -sqrtf(1.0f - wallNormalZ * wallNormalZ), 0.0f, wallNormalZ);
		result->entityNum = hitEntity;
	}
}

static const char *ETA_PropAt(const vec3_t point) { (void)point; return propHere; }
sfxHandle_t CG_AccessibilityLoopSound(eta_loopSoundType_t which) { return (sfxHandle_t)which; }
int CG_AccessibilityBumpVolume(void) { return 127; }
void trap_S_StartSoundVControl(vec3_t origin, int entityNum, int entchannel, sfxHandle_t sfx, int volume)
{
	(void)entityNum; (void)entchannel; (void)volume;
	printf("  %s at %.0f %.0f\n", sfx == ETA_LOOP_BUMP_WALL ? "thud" : "knock", origin[0], origin[1]);
}

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

static void Walk(const char *name, int forward, int right, float yaw, int frames)
{
	int i;

	printf("%s\n", name);
	pressed.forwardmove = (signed char)forward;
	pressed.rightmove   = (signed char)right;
	cg.predictedPlayerState.viewangles[YAW] = yaw;
	for (i = 0; i < frames; i++)
	{
		ETA_BeaconBump();
		cg.time += 50;
	}
}

int main(void)
{
	cg.snap = &snapshot;
	cg.time = 100000;
	cg.predictedPlayerState.pm_type        = PM_NORMAL;
	cg.predictedPlayerState.groundEntityNum = 0;

	Walk("INTO", 127, 0, 0.0f, 1);
	Walk("PUSHING", 127, 0, 0.0f, 13);      /* 650 ms more */
	Walk("STOPPED", 0, 0, 0.0f, 5);
	Walk("ALONG", 127, 0, 70.0f, 5);        /* walking along it, 70 degrees off */
	Walk("SIDEWAYS", 0, 127, 90.0f, 1);     /* strafing right, facing along the wall */
	Walk("AWAY", 0, 0, 0.0f, 1);
	wallNormalZ = 0.8f;
	Walk("STEP", 127, 0, 0.0f, 3);
	wallNormalZ = 0.0f;
	Walk("AWAY2", 0, 0, 0.0f, 1);
	hitEntity = 7;
	Walk("THING", 127, 0, 0.0f, 1);
	hitEntity = ENTITYNUM_WORLD;
	Walk("AWAY3", 0, 0, 0.0f, 1);
	propHere = "Crate";
	Walk("CRATE", 127, 0, 0.0f, 1);
	Walk("AWAY4", 0, 0, 0.0f, 1);
	propHere = "Window";
	Walk("WINDOW", 127, 0, 0.0f, 1);
	propHere = NULL;
	Walk("AWAY5", 0, 0, 0.0f, 1);
	cg.predictedPlayerState.groundEntityNum = ENTITYNUM_NONE;
	Walk("AIR", 127, 0, 0.0f, 3);
	cg.predictedPlayerState.groundEntityNum = 0;
	Walk("AWAY6", 0, 0, 0.0f, 1);
	eta_bumpCues.integer = 0;
	Walk("OFF", 127, 0, 0.0f, 3);
	printf("END\n");
	return 0;
}
'''

NAMES = ("INTO", "PUSHING", "STOPPED", "ALONG", "SIDEWAYS", "AWAY", "STEP", "AWAY2", "THING", "AWAY3", "CRATE",
         "AWAY4", "WINDOW", "AWAY5", "AIR", "AWAY6", "OFF", "END")


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def section(output, name):
    start = output.find(name + "\n")
    if start < 0:
        return []
    rest = output[start + len(name) + 1:]
    end = min([rest.find(n + "\n") for n in NAMES if rest.find(n + "\n") >= 0] or [len(rest)])
    return re.findall(r"(thud|knock) at (-?\d+) (-?\d+)", rest[:end])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    failures = []

    begin = draw.find("#define ETA_BUMP_REPEAT_MS")
    end = draw.find("/**\n * @brief A sound on each health pack")
    if begin < 0 or end < begin:
        sys.exit("no bump sounds in %s - the feature this test measures is gone" % DRAW)

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "bump.c")
        binary = os.path.join(tmp, "bump")
        with open(source, "w") as handle:
            handle.write(HARNESS.replace("%(LIFTED)s", draw[begin:end]))
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-I", os.path.join(root, "src", "qcommon"), "-I", os.path.join(root, "src"),
             "-o", binary, source, os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted bump sounds do not build:\n%s" % build.stderr[-3000:])
        out = subprocess.run([binary], capture_output=True, text=True, timeout=60).stdout

    def check(ok, good, bad):
        if ok:
            print("[bump] " + good)
        else:
            failures.append(bad)

    into = section(out, "INTO")
    check(into == [("thud", "21", "0")], "walking into a wall: a thud, from where they hit",
          "walking into a wall gave %r" % into)
    pushing = section(out, "PUSHING")
    check(len(pushing) == 1 and pushing[0][0] == "thud", "pushing on: once more after a moment, not every frame",
          "pushing into the wall for 650 ms gave %r" % pushing)
    for name, what in (("STOPPED", "standing still"), ("ALONG", "walking along the wall"),
                       ("STEP", "walking onto a step"), ("AIR", "in the air"), ("OFF", "with the setting off")):
        got = section(out, name)
        check(not got, "%s: silent" % what, "%s gave %r" % (what, got))
    sideways = section(out, "SIDEWAYS")
    check([s[0] for s in sideways] == ["thud"], "strafing into it: a thud too", "strafing into the wall gave %r" % sideways)
    for name, want, what in (("THING", "knock", "a thing - an entity"), ("CRATE", "knock", "furniture the map names"),
                             ("WINDOW", "thud", "a window, which is the wall it is in")):
        got = section(out, name)
        check([s[0] for s in got] == [want], "%s: a %s" % (what, want), "%s gave %r, not a %s" % (what, got, want))

    # --- the wiring ---------------------------------------------------------
    main_c = read(os.path.join(root, MAIN))
    local = read(os.path.join(root, LOCAL))
    sounds = read(SOUNDS)
    for ok, what in (
            ("ETA_BeaconBump();" in draw, "the bump sounds are never played"),
            ("ETA_LOOP_BUMP_WALL" in local and "ETA_LOOP_BUMP_OBJECT" in local
             and '"eta_cueBumpWall",          "sound/accessibility/bump_wall.wav"' in main_c
             and '"eta_cueBumpObject",        "sound/accessibility/bump_object.wav"' in main_c,
             "the bump sounds are not registered"),
            ('"bump_wall.wav":' in sounds and '"bump_object.wav":' in sounds, "the bump sounds are not made"),
            ('{ &eta_bumpCues,            "eta_bumpCues",            "1" }' in main_c
             and '{ &eta_bumpVolume,          "eta_bumpVolume",          "100" }' in main_c,
             "the bump settings are not registered"),
            ('"eta_bumpCues"' in read(ENVIRONMENT), "the Environment page has no switch for the bump sounds"),
            ('"eta_bumpVolume" 100 0 100' in read(SOUND), "the Sound page has no volume for the bump sounds"),
            (re.search(r'^seta eta_bumpCues\s+"1"', read(AUTOEXEC), re.M)
             and re.search(r'^seta eta_bumpVolume\s+"100"', read(AUTOEXEC), re.M),
             "the shipped config does not set the bump sounds")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "registered" in f or "page" in f or "config" in f or "never" in f or "made" in f]:
        print("[bump] made, registered, on the Environment and Sound pages, and in the shipped config")

    if failures:
        for failure in failures:
            print("[bump] FAIL %s" % failure)
        print(out)
        sys.exit(1)
    print("bump_sounds_test: walking into a wall thuds, into a thing knocks")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check landmines the game shows are said, heard and walked round.

The tester kept dying on enemy landmines the narrator never named. The
fix is held to what a sighted player sees, which the game decides in
CG_Missile (cg_ents.c). ETA_NarrateMines is lifted out of the patched
engine unchanged and run on mines laid out by hand:

- an armed enemy mine nobody has spotted is said to nobody, and the way
  does not step round it - it is hidden, as it is from everyone;
- spotted, it is said once as it comes within about ten metres - where
  and how far - beeps within about six, and the way steps round it,
  in sight or not; and said again only after walking well away;
- unspotted, with the battle sense skill that shows traps, it is seen
  within 256 units, as the game draws it, and not beyond;
- the team's own are "Friendly landmine"; several together are said as
  one; a mine not yet armed, or one behind a wall, is not said;
- a spectator hears of none; with the setting off, nothing is said or
  heard, and the way still steps round them.

Then the rule itself against the game's: the same fields CG_Missile
reads, the same 256 units; the way keeps further off a mine than the
distance it goes off at (sEntWillTriggerMine), goes through when there
is no way round, and finds the way again when a mine comes into sight
on it. And the wiring: the setting, its page, the sound, the config.

    ./landmine_warnings_test.py <engine-root>
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRAW = os.path.join("src", "cgame", "cg_draw.c")
ENTS = os.path.join("src", "cgame", "cg_ents.c")
MAP = os.path.join("src", "cgame", "cg_commandmap.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")
MAIN = os.path.join("src", "cgame", "cg_main.c")
MISSILE = os.path.join("src", "game", "g_missile.c")
ENVIRONMENT = os.path.join(REPO, "release", "ui", "options_accessibility_environment.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")
SOUNDS = os.path.join(REPO, "release", "make-cue-sounds.py")

HARNESS = r'''
#include "q_shared.h"
#include "game/bg_public.h"
#include <stdio.h>
#include <math.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

#undef BG_IsSkillAvailable
#define BG_IsSkillAvailable(skill, type, level) ((skill)[type] >= (level))

#define ETA_QU_TO_METERS 0.0254f
typedef enum { ETA_LOOP_MINE = 15 } eta_loopSoundType_t;

typedef struct { entityState_t currentState; vec3_t lerpOrigin; } centity_t;
static centity_t cg_entities[MAX_GENTITIES];
typedef struct { int numEntities; entityState_t entities[64]; playerState_t ps; } snapshot_t;
static snapshot_t snapshot;
static struct
{
	snapshot_t *snap;
	int clientNum;
	playerState_t predictedPlayerState;
	centity_t predictedPlayerEntity;
} cg;
typedef struct { team_t team; int shoutcaster; int skill[SK_NUM_SKILLS]; } clientInfo_t;
static struct { clientInfo_t clientinfo[MAX_CLIENTS]; } cgs;
static struct { int integer; } eta_mineCues = { 1 };

/* A wall at x = 300 and beyond: nothing past it is in sight. */
static qboolean ETA_ClearLine(const vec3_t eye, const vec3_t point) { (void)eye; return point[0] < 300.0f; }

sfxHandle_t CG_AccessibilityLoopSound(eta_loopSoundType_t which) { return (sfxHandle_t)which; }
int CG_AccessibilityLoopVolume(eta_loopSoundType_t which) { (void)which; return 255; }
void trap_S_AddLoopingSound(const vec3_t origin, const vec3_t velocity, sfxHandle_t sfx, int volume, int soundTime)
{
	(void)velocity; (void)volume; (void)soundTime; (void)sfx;
	printf("  beep at %.0f %.0f\n", origin[0], origin[1]);
}
void CG_AccessibilityRouteAvoid(const float (*points)[3], int count)
{
	int i;

	for (i = 0; i < count; i++)
	{
		printf("  avoid %.0f %.0f\n", points[i][0], points[i][1]);
	}
}
float CG_AccessibilityLeftOfView(const vec3_t point) { return point[1] > 0 ? 1.0f : point[1] < 0 ? -1.0f : 0.0f; }
const char *ETA_HudNarrator_RelativeDirection(float left) { return left > 0 ? "left" : left < 0 ? "right" : "ahead"; }
void ETA_Speech_BeginReport(void) { }
void ETA_Speech_EndReport(void) { }
void ETA_Speech_Say(const char *text) { printf("  say %s\n", text); }

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

static void Mine(int number, int team, float x, float y, int spotted, int armed)
{
	entityState_t *es = &snapshot.entities[snapshot.numEntities++];

	memset(es, 0, sizeof(*es));
	es->number      = number;
	es->eType       = ET_MISSILE;
	es->weapon      = WP_LANDMINE;
	es->teamNum     = team;
	es->modelindex2 = spotted;
	es->effect1Time = armed ? 1 : 0;
	es->density     = 30;   /* planted by client 29 */
	cg_entities[number].currentState = *es;
	VectorSet(cg_entities[number].lerpOrigin, x, y, 0);
}

static void At(float x)
{
	VectorSet(cg.predictedPlayerState.origin, x, 0, 0);
	VectorSet(cg.predictedPlayerEntity.lerpOrigin, x, 0, 0);
}

static void Frame(const char *name)
{
	printf("%s\n", name);
	ETA_NarrateMines();
}

int main(void)
{
	cg.snap = &snapshot;
	cg.clientNum = 0;
	snapshot.ps.clientNum = 0;
	cg.predictedPlayerState.pm_type    = PM_NORMAL;
	cg.predictedPlayerState.viewheight = 40;
	cgs.clientinfo[0].team = TEAM_ALLIES;
	At(0);

	Mine(40, TEAM_AXIS, 100, 0, 0, 1);
	Frame("HIDDEN");

	snapshot.numEntities = 0;
	Mine(41, TEAM_AXIS, 200, 0, 1, 1);
	Frame("SPOTTED");
	Frame("AGAIN");
	At(-700);
	Frame("AWAY");
	At(-300);
	Frame("FAR");
	At(0);
	Frame("BACK");

	snapshot.numEntities = 0;
	cgs.clientinfo[0].skill[SK_BATTLE_SENSE] = SK_BATTLE_SENSE_TRAP_AWARENESS;
	Mine(42, TEAM_AXIS, 0, 200, 0, 1);
	Mine(43, TEAM_AXIS, 0, -290, 0, 1);
	Frame("AWARE");
	cgs.clientinfo[0].skill[SK_BATTLE_SENSE] = 0;

	snapshot.numEntities = 0;
	Mine(44, TEAM_ALLIES, 150, 0, 0, 1);
	Frame("FRIENDLY");

	snapshot.numEntities = 0;
	Mine(45, TEAM_AXIS, 220, 0, 1, 1);
	Mine(46, TEAM_AXIS, 220, 60, 1, 1);
	Mine(47, TEAM_AXIS, 220, -60, 1, 1);
	Frame("THREE");

	snapshot.numEntities = 0;
	Mine(48, TEAM_AXIS, 120, 0, 1, 0);
	Mine(49, TEAM_AXIS, 320, 0, 1, 1);
	Frame("UNARMED_WALL");

	snapshot.numEntities = 0;
	Mine(50, TEAM_AXIS, 100, 0, 1, 1);
	Mine(51, TEAM_ALLIES, -100, 0, 1, 1);
	cgs.clientinfo[0].team = TEAM_SPECTATOR;
	snapshot.ps.clientNum = 3;
	cgs.clientinfo[3].team = TEAM_ALLIES;
	Frame("SPECTATOR");
	cgs.clientinfo[0].team = TEAM_ALLIES;
	snapshot.ps.clientNum = 0;

	eta_mineCues.integer = 0;
	Frame("OFF");
	printf("END\n");
	return 0;
}
'''

NAMES = ("HIDDEN", "SPOTTED", "AGAIN", "AWAY", "FAR", "BACK", "AWARE", "FRIENDLY", "THREE", "UNARMED_WALL",
         "SPECTATOR", "OFF", "END")


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


def frame(output, name):
    """What one frame said, beeped and stepped round."""
    start = output.find(name + "\n")
    if start < 0:
        return [], [], []
    rest = output[start + len(name) + 1:]
    end = min([rest.find(n + "\n") for n in NAMES if rest.find(n + "\n") >= 0] or [len(rest)])
    lines = rest[:end]
    return (re.findall(r"say (.*)", lines), re.findall(r"beep at (-?\d+) (-?\d+)", lines),
            re.findall(r"avoid (-?\d+) (-?\d+)", lines))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    failures = []

    begin = draw.find("#define ETA_MINE_SEEN_CLOSE")
    end = draw.find("/**\n * @brief How far a point lies from where the player faces")
    if begin < 0 or end < begin:
        sys.exit("no landmine warnings in %s - the feature this test measures is gone" % DRAW)

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "mines.c")
        binary = os.path.join(tmp, "mines")
        with open(source, "w") as handle:
            handle.write(HARNESS.replace("%(LIFTED)s", draw[begin:end]))
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-DFEATURE_ACCESSIBILITY",
             "-I", os.path.join(root, "src", "qcommon"), "-I", os.path.join(root, "src"),
             "-o", binary, source,
             os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted landmine warnings do not build:\n%s" % build.stderr[-3000:])
        out = subprocess.run([binary], capture_output=True, text=True, timeout=60).stdout

    def check(ok, good, bad):
        if ok:
            print("[mines] " + good)
        else:
            failures.append(bad)

    said, beeps, avoid = frame(out, "HIDDEN")
    check(not said and not beeps and not avoid,
          "an enemy mine nobody has spotted is not said, heard or stepped round - it is hidden from everyone",
          "an unspotted mine was given away: %r %r %r" % (said, beeps, avoid))

    said, beeps, avoid = frame(out, "SPOTTED")
    check(said == ["Enemy landmine, ahead, 5 meters"] and beeps == [("200", "0")] and avoid == [("200", "0")],
          "spotted: \"Enemy landmine, ahead, 5 meters\", a beep from it, and the way steps round it",
          "a spotted mine five metres ahead gave %r %r %r" % (said, beeps, avoid))
    said, beeps, _ = frame(out, "AGAIN")
    check(not said and beeps == [("200", "0")], "said once, and beeps on while near",
          "the next frame gave %r %r" % (said, beeps))
    said, beeps, avoid = frame(out, "AWAY")
    check(not said and not beeps and avoid == [("200", "0")],
          "walked away, it is quiet, and the way still keeps clear of it",
          "walked away, it gave %r %r %r" % (said, beeps, avoid))
    said, _, _ = frame(out, "FAR")
    check(said == [], "beyond about ten metres it is not said", "at thirteen metres it was said: %r" % said)
    said, _, _ = frame(out, "BACK")
    check(said == ["Enemy landmine, ahead, 5 meters"], "come back to it, it is said again",
          "coming back to it gave %r" % said)

    said, _, avoid = frame(out, "AWARE")
    check(said == ["Enemy landmine, left, 5 meters"] and avoid == [("0", "200")],
          "with the skill that shows traps, one within 256 units is seen, and one beyond is not",
          "with trap awareness, mines at 200 and 290 units gave %r %r" % (said, avoid))

    said, _, avoid = frame(out, "FRIENDLY")
    check(said == ["Friendly landmine, ahead, 4 meters"] and avoid == [("150", "0")],
          "the team's own: \"Friendly landmine\"", "a friendly mine gave %r %r" % (said, avoid))

    said, beeps, _ = frame(out, "THREE")
    check(said == ["3 enemy landmines, ahead, 6 meters"] and len(beeps) == 2,
          "three together are said as one, and the nearest two beep",
          "three mines together gave %r and beeps %r" % (said, beeps))

    said, beeps, avoid = frame(out, "UNARMED_WALL")
    check(not said and not beeps and avoid == [("320", "0")],
          "a mine not yet armed is not one; one behind a wall is not said, and the way still keeps clear of it",
          "an unarmed mine and one behind a wall gave %r %r %r" % (said, beeps, avoid))

    said, beeps, avoid = frame(out, "SPECTATOR")
    check(not said and not beeps and not avoid, "a spectator hears of none, as the game shows them none",
          "a spectator was told of %r %r %r" % (said, beeps, avoid))
    said, beeps, avoid = frame(out, "OFF")
    check(not said and not beeps and avoid == [("100", "0"), ("-100", "0")],
          "with the setting off, nothing is said or heard, and the way still keeps clear",
          "with the setting off, it gave %r %r %r" % (said, beeps, avoid))

    # --- the game's own rule ------------------------------------------------
    ents = read(os.path.join(root, ENTS))
    missile = function_body(ents, "CG_Missile")
    rule = function_body(draw, "ETA_MineSeen")
    game = [
        "cent->currentState.weapon == WP_LANDMINE",
        "cgs.clientinfo[cg.clientNum].team == TEAM_SPECTATOR && !cgs.clientinfo[cg.clientNum].shoutcaster",
        "cent->currentState.effect1Time == 1",
        "cgs.clientinfo[cg.snap->ps.clientNum].team != cent->currentState.teamNum",
        "cent->currentState.density - 1 == cg.snap->ps.clientNum",
        "!cent->currentState.modelindex2",
        "BG_IsSkillAvailable(cgs.clientinfo[cg.snap->ps.clientNum].skill, SK_BATTLE_SENSE, SK_BATTLE_SENSE_TRAP_AWARENESS)",
        "distSquared > Square(256)",
    ]
    ours = [
        "es->weapon != WP_LANDMINE", "es->effect1Time != 1",
        "cgs.clientinfo[cg.clientNum].team == TEAM_SPECTATOR && !cgs.clientinfo[cg.clientNum].shoutcaster",
        "team = cgs.clientinfo[cg.snap->ps.clientNum].team;", "es->teamNum == team",
        "es->density - 1 == cg.snap->ps.clientNum", "es->modelindex2",
        "BG_IsSkillAvailable(cgs.clientinfo[cg.snap->ps.clientNum].skill, SK_BATTLE_SENSE, SK_BATTLE_SENSE_TRAP_AWARENESS)",
    ]
    close = re.search(r"#define\s+ETA_MINE_SEEN_CLOSE\s+([\d.]+)f", draw)
    if [g for g in game if g not in missile]:
        failures.append("the game no longer decides which mines are drawn the way this was built on: %r"
                        % [g for g in game if g not in missile])
    elif [o for o in ours if o not in rule] or not close or float(close.group(1)) != 256.0:
        failures.append("which mines are said is not the game's rule for which are drawn")
    else:
        print("[mines] which are said is the game's own rule for which are drawn, to the unit")

    # --- the way round ------------------------------------------------------
    trigger = re.search(r"#define\s+LANDMINE_TRIGGER_DIST\s+([\d.]+)f", read(os.path.join(root, MISSILE)))
    route = read(os.path.join(root, MAP))
    radius = re.search(r"#define\s+ETA_ROUTE_AVOID_RADIUS\s+([\d.]+)f", route)
    move = strip_comments(function_body(route, "ETA_RouteMove"))
    frame_c = strip_comments(function_body(route, "ETA_RouteFrame")) or strip_comments(route)
    if not trigger:
        failures.append("the game's landmine trigger distance is not where this was built on")
    elif not radius or float(radius.group(1)) <= float(trigger.group(1)):
        failures.append("the way keeps nearer a mine than the %s units it goes off at" % trigger.group(1))
    elif "if (ETA_RouteLineAvoided(from, tried))" not in move:
        failures.append("the way's steps do not keep clear of the mines")
    elif "!ETA_RouteLineAvoided(from, to)" not in function_body(route, "ETA_RouteClear"):
        failures.append("following the way cuts its corners over the mines")
    elif "eta_route.throughMines = qtrue;" not in frame_c or "if (eta_route.throughMines)" not in route:
        failures.append("with no way round the mines, there is no way at all")
    elif "eta_routeAvoidNew && !eta_route.throughMines" not in frame_c:
        failures.append("a mine come into sight on the way already found does not change it")
    else:
        print("[mines] the way keeps %s units off a mine, which goes off at %s; goes through when there is no "
              "way round; and is found again when one comes into sight on it" % (radius.group(1), trigger.group(1)))

    # --- the wiring ---------------------------------------------------------
    main_c = read(os.path.join(root, MAIN))
    local = read(os.path.join(root, LOCAL))
    sounds = read(SOUNDS)
    for ok, what in (
            ("ETA_NarrateMines();" in draw, "the warnings are never run"),
            ("ETA_LOOP_MINE" in local and '"eta_cueMine",              "sound/accessibility/landmine.wav"' in main_c,
             "the landmine's sound is not registered"),
            ("case ETA_LOOP_MINE:\n\t\tcvar = &eta_cueVolume;" in main_c, "the landmine's beep has no volume"),
            ('"landmine.wav":' in sounds, "the landmine's sound is not made"),
            ('{ &eta_mineCues,            "eta_mineCues",            "1" }' in main_c, "eta_mineCues is not registered"),
            ('"eta_mineCues"' in read(ENVIRONMENT), "the Environment page has no switch for the landmine warnings"),
            (re.search(r'^seta eta_mineCues\s+"1"', read(AUTOEXEC), re.M)
             and re.search(r'^seta eta_cueMine\s+"sound/accessibility/landmine.wav"', read(AUTOEXEC), re.M),
             "the shipped config does not set the landmine warnings")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "registered" in f or "page" in f or "config" in f or "never run" in f
            or "sound" in f or "volume" in f]:
        print("[mines] registered, made, on the Environment page, and in the shipped config")

    if failures:
        for failure in failures:
            print("[mines] FAIL %s" % failure)
        print(out)
        sys.exit(1)
    print("landmine_warnings_test: the landmines the game shows are said, heard and walked round")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check health packs, ammo packs, weapons and the tank are heard.

The tester asked for sounds on health and ammo packs and on weapons, to
find them and pick them up, and on the tank they have to steal on
Goldrush. ETA_BeaconPickups is lifted out of the patched engine
unchanged and run on items laid out by hand:

- a health pack, an ammo pack and a weapon each play their own sound,
  from where they lie;
- one behind a wall, or further than about ten metres, plays nothing;
- of five in sight, only the nearest three play;
- a dropped objective - the gold - rings the flag's bell;
- a health cabinet plays the health pack's sound, and an ammo cabinet
  the ammo pack's: a cabinet and its own trigger once, and never one
  behind a wall;
- with the setting off, nothing plays.

The kinds are the game's own (bg_misc.c): an ammo pack is a weapon item
whose weapon is WP_AMMO, a health pack a health item. And the tank's
sound follows the hud's own reading of a tank indicator: it rumbles for
both sides, and damaged, taps for the side that escorts it. The settings
are registered, on their pages, and in the shipped config.

    ./pickup_cues_test.py <engine-root>
"""

import glob
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRAW = os.path.join("src", "cgame", "cg_draw.c")
HUD = os.path.join("src", "cgame", "cg_draw_hud.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
BG_MISC = os.path.join("src", "game", "bg_misc.c")
ENVIRONMENT = os.path.join(REPO, "release", "ui", "options_accessibility_environment.menu")
SOUND = os.path.join(REPO, "release", "ui", "options_accessibility_sound.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")

HARNESS = r'''
#include "q_shared.h"
#include "game/bg_public.h"
#include <stdio.h>
#include <math.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

typedef enum
{
	ETA_LOOP_FLAG = 7, ETA_LOOP_HEALTH = 11, ETA_LOOP_AMMO, ETA_LOOP_WEAPON
} eta_loopSoundType_t;

typedef struct { entityState_t currentState; vec3_t lerpOrigin; } centity_t;
static centity_t cg_entities[64];
typedef struct { int numEntities; entityState_t entities[64]; playerState_t ps; } snapshot_t;
static snapshot_t snapshot;
static struct { snapshot_t *snap; playerState_t predictedPlayerState; } cg;
static struct { int integer; } eta_pickupCues = { 1 };

/* The items, by index: what bg_misc.c says each kind is. */
static gitem_t items[6];
gitem_t *BG_GetItem(int index) { return index > 0 && index < 6 ? &items[index] : NULL; }

/* A wall at x = 300 and beyond: nothing past it is in sight. */
static qboolean ETA_ClearLine(const vec3_t eye, const vec3_t point) { (void)eye; return point[0] < 300.0f; }

/* A cabinet is solid: the line to its middle stops on the cabinet. */
static struct { vec3_t inlineModelMidpoints[MAX_MODELS]; } cgs;
static int solidCabinet = -1;
static void CG_Trace(trace_t *result, const vec3_t start, const vec3_t mins, const vec3_t maxs, const vec3_t end,
                     int skipNumber, int mask)
{
	(void)start; (void)mins; (void)maxs; (void)skipNumber; (void)mask;
	memset(result, 0, sizeof(*result));
	result->fraction  = end[0] < 300.0f ? (solidCabinet >= 0 ? 0.9f : 1.0f) : 0.5f;
	result->entityNum = end[0] < 300.0f && solidCabinet >= 0 ? solidCabinet : ENTITYNUM_WORLD;
}

sfxHandle_t CG_AccessibilityLoopSound(eta_loopSoundType_t which) { return (sfxHandle_t)which; }
int CG_AccessibilityLoopVolume(eta_loopSoundType_t which) { (void)which; return 255; }
void trap_S_AddLoopingSound(const vec3_t origin, const vec3_t velocity, sfxHandle_t sfx, int volume, int soundTime)
{
	(void)velocity; (void)volume; (void)soundTime;
	printf("  sound %d at %.0f %.0f\n", (int)sfx, origin[0], origin[1]);
}

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

static void Item(int number, int kind, float x, float y)
{
	entityState_t *es = &snapshot.entities[snapshot.numEntities++];

	memset(es, 0, sizeof(*es));
	es->number    = number;
	es->eType     = ET_ITEM;
	es->modelindex = kind;
	cg_entities[number].lerpOrigin[0] = x;
	cg_entities[number].lerpOrigin[1] = y;
	cg_entities[number].lerpOrigin[2] = 0;
}

int main(void)
{
	items[1].giType = IT_HEALTH;
	items[2].giType = IT_WEAPON; items[2].giWeapon = WP_AMMO;
	items[3].giType = IT_WEAPON; items[3].giWeapon = WP_MP40;
	items[4].giType = IT_TEAM;

	cg.snap = &snapshot;
	cg.predictedPlayerState.pm_type    = PM_NORMAL;
	cg.predictedPlayerState.viewheight = 40;

	printf("KINDS (health %d ammo %d weapon %d flag %d)\n", ETA_LOOP_HEALTH, ETA_LOOP_AMMO, ETA_LOOP_WEAPON, ETA_LOOP_FLAG);
	Item(10, 1, 100, 0);
	Item(11, 2, 0, 100);
	Item(12, 3, -100, 0);
	Item(13, 3, 350, 0);     /* behind the wall */
	Item(14, 1, -100, -390); /* over ten metres */
	printf("THREE\n");
	ETA_BeaconPickups();

	snapshot.numEntities = 0;
	Item(20, 1, 50, 0);
	Item(21, 1, 60, 0);
	Item(22, 1, 70, 0);
	Item(23, 1, 80, 0);
	Item(24, 1, 90, 0);
	printf("FIVE\n");
	ETA_BeaconPickups();

	snapshot.numEntities = 0;
	Item(30, 4, 0, -100);
	printf("GOLD\n");
	ETA_BeaconPickups();

	/* A health cabinet with its trigger in front, and an ammo cabinet
	   behind the wall. */
	snapshot.numEntities = 0;
	Item(40, 0, 100, 100);
	snapshot.entities[0].eType = ET_CABINET_H;
	Item(41, 0, 120, 100);
	snapshot.entities[1].eType = ET_HEALER;
	snapshot.entities[1].solid = SOLID_BMODEL;
	snapshot.entities[1].modelindex = 5;
	VectorSet(cgs.inlineModelMidpoints[5], 0, 0, 30);
	Item(42, 0, 350, -100);
	snapshot.entities[2].eType = ET_CABINET_A;
	solidCabinet = 40;
	printf("CABINETS\n");
	ETA_BeaconPickups();
	solidCabinet = -1;

	eta_pickupCues.integer = 0;
	printf("OFF\n");
	ETA_BeaconPickups();
	printf("END\n");
	return 0;
}
'''


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function_body(text, name):
    match = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return ""
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def section(output, name):
    start = output.find(name + "\n")
    rest = output[start + len(name) + 1:]
    end = min([rest.find(n) for n in ("THREE\n", "FIVE\n", "GOLD\n", "CABINETS\n", "OFF\n", "END\n") if rest.find(n) >= 0] or [len(rest)])
    return re.findall(r"sound (\d+) at (-?\d+) (-?\d+)", rest[:end])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    failures = []

    begin = draw.find("#define ETA_PICKUP_CUE_RANGE")
    end = draw.find("/**\n * @brief The armed landmines this player can see")
    if begin < 0 or end < begin:
        sys.exit("no pickup sounds in %s - the feature this test measures is gone" % DRAW)

    library = sorted(glob.glob(os.path.join(REPO, "src", "accessibility", "**", "*.c"), recursive=True))
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "pickups.c")
        binary = os.path.join(tmp, "pickups")
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
            sys.exit("the lifted pickup sounds do not build:\n%s" % build.stderr[-3000:])
        out = subprocess.run([binary], capture_output=True, text=True, timeout=60).stdout

    kinds = dict(zip(("health", "ammo", "weapon", "flag"), re.search(r"KINDS \(health (\d+) ammo (\d+) weapon (\d+) flag (\d+)\)", out).groups()))
    three = section(out, "THREE")
    want = sorted([(kinds["health"], "100", "0"), (kinds["ammo"], "0", "100"), (kinds["weapon"], "-100", "0")])
    if sorted(three) != want:
        failures.append("a health pack, an ammo pack and a weapon in sight, one behind a wall and one far off, played %r" % three)
    else:
        print("[pickups] a health pack, an ammo pack and a weapon each play their own sound where they lie; "
              "not behind a wall, not ten metres off")
    five = section(out, "FIVE")
    if sorted(x for _, x, _ in five) != ["50", "60", "70"]:
        failures.append("of five in sight, these played: %r" % five)
    else:
        print("[pickups] of five in sight, the nearest three")
    gold = section(out, "GOLD")
    if gold != [(kinds["flag"], "0", "-100")]:
        failures.append("a dropped objective played %r, not the flag's bell" % gold)
    else:
        print("[pickups] a dropped objective rings the flag's bell")
    cabinets = section(out, "CABINETS")
    if len(cabinets) != 1 or cabinets[0][0] != kinds["health"] or cabinets[0][1] not in ("100", "120"):
        failures.append("a health cabinet with its trigger, and an ammo cabinet behind a wall, played %r" % cabinets)
    else:
        print("[pickups] a health cabinet plays the health pack's sound, once with its trigger; "
              "one behind a wall plays nothing")
    if section(out, "OFF"):
        failures.append("with the setting off, something still played")

    # --- the game's own kinds -----------------------------------------------
    misc = read(os.path.join(root, BG_MISC))
    magic = misc[misc.find('"weapon_magicammo"'):misc.find('"weapon_magicammo"') + 900]
    if "IT_WEAPON," not in magic or "WP_AMMO," not in magic:
        failures.append("the game's ammo pack is no longer a weapon item whose weapon is WP_AMMO")
    health = misc[misc.find('"item_health"'):misc.find('"item_health"') + 900]
    if "IT_HEALTH," not in health:
        failures.append("the game's health pack is no longer a health item")

    # --- the tank -----------------------------------------------------------
    hud = read(os.path.join(root, HUD))
    tank = hud[hud.find("case ET_TANK_INDICATOR:"):hud.find("case ET_TANK_INDICATOR_DEAD:")]
    sites = function_body(draw, "ETA_BeaconSites")
    if "ent->teamNum == 1 && cg.predictedPlayerState.persistant[PERS_TEAM] == TEAM_AXIS" not in tank \
            or "escortShader" not in tank:
        failures.append("the hud no longer reads a tank indicator's team as the side that escorts it")
    elif not re.search(r"else if \(es->eType == ET_TANK_INDICATOR\)\s*\{\s*which = ETA_LOOP_TANK;", sites) \
            or not re.search(r"else if \(es->eType == ET_TANK_INDICATOR_DEAD && es->teamNum == team\)\s*\{\s*which = ETA_LOOP_BUILD_SITE;", sites):
        failures.append("the tank does not rumble for both sides, or a damaged one tap for the side that escorts it")
    else:
        print("[pickups] the tank rumbles for both sides; damaged, it taps for the side that escorts it")

    # --- the wiring ---------------------------------------------------------
    main_c = read(os.path.join(root, MAIN))
    for ok, what in (
            ("ETA_BeaconPickups();" in draw, "the pickup sounds are never played"),
            ('{ &eta_pickupCues,          "eta_pickupCues",          "1" }' in main_c, "eta_pickupCues is not registered"),
            ('{ "eta_cueTank",              "sound/accessibility/tank.wav"' in main_c, "the tank's sound is not registered"),
            ('"eta_pickupCues"' in read(ENVIRONMENT), "the Environment page has no switch for the pickup sounds"),
            ('"eta_pickupVolume" 100 0 100' in read(SOUND), "the Sound page has no volume for the pickup sounds"),
            (re.search(r'^seta eta_pickupCues\s+"1"', read(AUTOEXEC), re.M), "the shipped config does not set eta_pickupCues")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "registered" in f or "page" in f or "config" in f or "never played" in f]:
        print("[pickups] registered, on the Environment and Sound pages, and in the shipped config")

    if failures:
        for failure in failures:
            print("[pickups] FAIL %s" % failure)
        print(out)
        sys.exit(1)
    print("pickup_cues_test: health packs, ammo packs, weapons and the tank are heard")


if __name__ == "__main__":
    main()

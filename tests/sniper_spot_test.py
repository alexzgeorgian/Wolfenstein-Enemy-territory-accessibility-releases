#!/usr/bin/env python3
"""Check sniper spots are found the way the game finds them, and offered on a key.

The tester asked for the map to help choose a good spot to use the
sniper rifle from. The game looks over the whole map for floors up off
the ground, and from each looks out in sixteen directions for ground an
enemy could be seen on (ETA_SpotScanPoint in cg_commandmap.c). Lifted
out unchanged, that is run here on a world drawn from boxes:

- a terrace 5 metres up, walled in behind and at the sides, with open
  ground in front, to the south, is a spot, said "Ledge, sees ... meters to the south,
  5 meters up";
- a step half a metre high out in the open is not;
- looked for backwards, a terrace with steps down one side has a way up
  to it, and the top of a pillar has none.

And the rest of the wiring:

- the scan runs every frame within a budget, from the marker's frame,
  and starts again on a new map;
- the key steps through the spots nearest first, puts the marker on
  each with a name that says which way to look, and a spot with no way
  up is told, taken off the list and the marker taken away;
- / is free in both of the game's own layouts, offered by the
  installer, a console command, on the Key Binds page, in the game's
  binding list and bound in the shipped config.

    ./sniper_spot_test.py <engine-root>
"""

import glob
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import marker_route_sim_test as sim  # noqa: E402
import place_probe_test as probe  # noqa: E402

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")
UI_SHARED = os.path.join("src", "ui", "ui_shared.c")
STOCK = (os.path.join("etmain", "default.cfg"), os.path.join("etmain", "default_left.cfg"))
KEYS_MENU = os.path.join(REPO, "release", "ui", "options_accessibility_keys.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")

SCENE = r'''
/* ---- the scene ---- */
static int Scan(const char *name, float x0, float y0, float x1, float y1)
{
	float x, y;
	int   i, column, row = 0;

	ETA_SpotList_Clear(&eta_spots.list);
	for (y = y0 + 64.0f; y < y1; y += ETA_SPOT_SPACING, row++)
	{
		for (x = x0 + 64.0f, column = 0; x < x1; x += ETA_SPOT_SPACING, column++)
		{
			ETA_SpotScanPoint(x, y, column, row);
		}
	}
	for (i = 0; i < eta_spots.list.count; i++)
	{
		char text[128];
		ETA_Spot *spot = &eta_spots.list.spots[i];

		ETA_Spot_Text(spot->kind, &spot->rating, text, sizeof(text));
		printf("SPOT %s at %.0f %.0f %.0f = %s\n", name, spot->origin[0], spot->origin[1], spot->origin[2], text);
	}
	printf("COUNT %s = %d\n", name, eta_spots.list.count);
	return eta_spots.list.count;
}

static void Back(const char *name, const float spot[3], const float goal[3])
{
	ETA_PathState state;
	int           steps = 0;

	ETA_PathFinder_Begin(spot, goal, ETA_ROUTE_CELL, ETA_MARKER_ARRIVE_METERS / ETA_QU_TO_METERS, 0);
	do
	{
		state  = ETA_PathFinder_Step(ETA_ROUTE_BUDGET_STEP, ETA_RouteMoveBack, NULL);
		steps += ETA_ROUTE_BUDGET_STEP;
	}
	while (state == ETA_PATH_SEARCHING && steps < ETA_SPOT_CHECK_STEPS);
	printf("BACK %s = %s\n", name, state == ETA_PATH_FOUND || state == ETA_PATH_SEARCHING ? "reachable" : "shut in");
}

int main(void)
{
	worldCount = 0;
	AddBox(-5000, -5000, 2000, 5000, 5000, 2016);   /* the sky */
	skyLid = worldCount - 1;
	AddBox(-5000, -5000, -64, 5000, 5000, 0);       /* the ground */
	AddBox(-300, 0, 0, 300, 600, 200);              /* a terrace, 5 m up, 15 m long */
	AddBox(-300, 600, 0, 300, 640, 800);            /* the walls behind it */
	AddBox(-340, -200, 0, -300, 640, 800);          /* and either side, out past its edge */
	AddBox(300, -200, 0, 340, 640, 800);
	AddBox(1800, -2400, 0, 2400, -1800, 20);        /* a step out in the open */
	Scan("terrace", -300, 0, 300, 600);
	Scan("step", 1800, -2400, 2400, -1800);

	/* The way down from a spot, looked for backwards: a terrace with
	   steps down one side, and a pillar nobody can climb. */
	{
		float terrace[3] = { 200, 200, 192 + 24 }, pillar[3] = { 1600, 100, 300 + 24 };
		float ground[3] = { -1000, -1000, 24 };
		int   k;

		worldCount = 0;
		AddBox(-5000, -5000, 2000, 5000, 5000, 2016);
		skyLid = worldCount - 1;
		AddBox(-5000, -5000, -64, 5000, 5000, 0);
		AddBox(0, 0, 0, 400, 400, 192);
		for (k = 1; k <= 11; k++)
		{
			AddBox(-32.0f * k, 0, 0, -32.0f * (k - 1), 128, 192 - 16.0f * k);
		}
		AddBox(1500, 0, 0, 1700, 200, 300);
		Back("terrace", terrace, ground);
		Back("pillar", pillar, ground);
	}
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


def run_scene(root, commandmap, scene):
    """Builds the patched engine's map scan - floors, sniper spots, rooms
    and the check for a way up - into the walk's world of boxes with the
    given scene, and runs it. Shared with rooms_test.py."""
    # --- the looking, on a drawn world --------------------------------------
    begin = commandmap.find("/**\n * @brief The floors a player could stand on")
    finish = commandmap.find("/**\n * @brief A little more of the map looked over")
    places_max = re.search(r"#define ETA_MAP_PLACES_MAX +\d+", commandmap)
    if begin < 0 or finish < begin or not places_max or "ETA_SpotScanPoint" not in commandmap:
        sys.exit("no sniper spot scan in %s - the feature this test measures is gone" % sim.COMMANDMAP)
    back_begin = commandmap.find("static int ETA_RouteMoveBackExact(")
    back_end = commandmap.find("static void ETA_SpotCheckFrame(void)")
    check_steps = re.search(r"#define ETA_SPOT_CHECK_STEPS\s+(\d+)", commandmap)
    if back_begin < 0 or back_end < back_begin or not check_steps:
        sys.exit("no check of the way down from a spot in %s - the feature this test measures is gone" % sim.COMMANDMAP)
    lifted = "\n".join([
        places_max.group(0),
        "static struct { int ccLayers; } cgs;",
        "static int CG_CurLayerForZ(int z) { (void)z; return 0; }",
        "static qboolean ETA_MapGrid(vec2_t start, vec2_t step, int *columns, int *rows)",
        "{ start[0] = 0; start[1] = 1200; step[0] = step[1] = 1200; *columns = *rows = 1; return qtrue; }",
        "char *CG_GetLocationMsg(int client, vec3_t origin) { (void)client; (void)origin; return \"Unknown\"; }",
        commandmap[begin:finish],
        "#define ETA_SPOT_CHECK_STEPS " + check_steps.group(1),
        commandmap[back_begin:back_end]])
    harness = probe.world_harness().replace(
        '#include "speech/speech_manager.h"',
        '#include "speech/speech_manager.h"\n#include "navigation/sniper_spots.h"\n#include "navigation/rooms.h"', 1)
    source_text = harness.replace("%(LIFTED)s", sim.lift(commandmap) + "\n" + lifted) + scene

    library = sorted(glob.glob(os.path.join(REPO, "src", "accessibility", "**", "*.c"), recursive=True))
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "spots.c")
        binary = os.path.join(tmp, "spots")
        with open(source, "w") as handle:
            handle.write(source_text)
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-DFEATURE_ACCESSIBILITY",
             "-I", os.path.join(root, "src", "qcommon"), "-I", os.path.join(root, "src"),
             "-I", os.path.join(REPO, "src", "accessibility"),
             "-o", binary, source,
             os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c")] + library + ["-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted sniper spot scan does not build:\n%s" % build.stderr[-3000:])
        run = subprocess.run([binary], capture_output=True, text=True, timeout=300)

    return run


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    commandmap = sim.read(root, sim.COMMANDMAP)
    failures = []

    run = run_scene(root, commandmap, SCENE)

    counts = dict(re.findall(r"COUNT (\w+) = (\d+)", run.stdout))
    spots = re.findall(r"SPOT terrace at (-?\d+) (-?\d+) (-?\d+) = (.*)", run.stdout)
    if counts.get("terrace") is None:
        failures.append("the scan never ran\n%s" % (run.stdout + run.stderr[-1000:]))
    elif not spots:
        failures.append("the terrace looking south over open ground is no sniper spot")
    else:
        x, y, z, said = spots[0]
        if not re.match(r"^Ledge, sees (6\d|7\d) meters to the south, 5 meters up$", said):
            failures.append("the terrace was said %r" % said)
        elif not (0 <= int(y) <= 600 and abs(int(z) - 224) <= 2):
            failures.append("the terrace's spot is not on the terrace: %s %s %s" % (x, y, z))
        elif len(spots) != 1:
            failures.append("the one terrace was offered as %d spots" % len(spots))
        else:
            print("[spot] terrace: %s" % said)
    back = dict(re.findall(r"BACK (\w+) = ([\w ]+)", run.stdout))
    if back.get("terrace") != "reachable":
        failures.append("the terrace with steps down was taken for one with no way up: %r" % back.get("terrace"))
    elif back.get("pillar") != "shut in":
        failures.append("the pillar nobody can climb was taken for one with a way up: %r" % back.get("pillar"))
    else:
        print("[spot] a terrace with steps has a way up; a pillar has none")
    if counts.get("step", "0") != "0":
        failures.append("a step half a metre high was taken for a sniper spot")
    else:
        print("[spot] a step half a metre high is no sniper spot")

    # --- the wiring ---------------------------------------------------------
    frame = function_body(commandmap, "CG_AccessibilityMarkerFrame")
    scan = function_body(commandmap, "ETA_SpotScanFrame")
    if "ETA_SpotScanFrame();" not in frame or "ETA_SpotCheckFrame();" not in frame \
            or "ETA_SpotJudgeWay();" not in frame:
        failures.append("the marker's frame does not scan for spots or judge the way to one")
    if "ETA_SPOT_BUDGET_MS" not in scan or "trap_Milliseconds()" not in scan:
        failures.append("the scan is not held to a budget each frame - a whole map at once is a stall")
    if "memset(&eta_spots, 0, sizeof(eta_spots));" not in function_body(commandmap, "CG_AccessibilityMarkerReset"):
        failures.append("the spots of one map are kept on the next")

    key = function_body(commandmap, "CG_AccessibilitySniperSpot")
    for want, what in (("ETA_SpotList_Nearest(", "the spots are not offered nearest first"),
                       ("ETA_MARKER_CYCLE_MS", "pressing again does not step to the next spot"),
                       ('"sniper spot, look %s"', "arriving does not say which way to look"),
                       ("eta_marker.active = qtrue;", "the marker is not put on the spot"),
                       ("ETA_RouteForget();", "the way to the spot is not looked for afresh")):
        if want not in key:
            failures.append(what)
    judge = function_body(commandmap, "ETA_SpotJudgeWay")
    if not re.search(r"spot->unreachable\s*=\s*1;", judge) or not re.search(r"eta_marker\.active\s*=\s*qfalse;", judge) \
            or "No way up to that sniper spot" not in judge:
        failures.append("a spot with no way up is not told, left off the list and the marker taken away")
    if not [f for f in failures if "spot" in f or "scan" in f or "marker" in f or "way" in f]:
        print("[spot] scanned within a budget, offered nearest first, a spot with no way up dropped")

    console = read(os.path.join(root, CONSOLE))
    ui = read(os.path.join(root, UI_MAIN))
    shared = read(os.path.join(root, UI_SHARED))
    menu = read(KEYS_MENU)
    autoexec = read(AUTOEXEC)
    key_failures = []
    for stock_cfg in STOCK:
        stock = read(os.path.join(root, stock_cfg))
        if re.search(r"^bind\s+\"?/\"?\s", stock, re.M | re.I):
            key_failures.append("/ is bound in %s - the sniper spot key would steal it" % stock_cfg)
    if not re.search(r"\{\s*'/',\s*\"accessibilitySniperSpot\",\s*NULL,\s*\d+\s*\}", ui):
        key_failures.append("the installer does not offer the sniper spot key on /")
    if not re.search(r'\{\s*"accessibilitySniperSpot",\s*CG_AccessibilitySniperSpot_f\s*\}', console):
        key_failures.append("accessibilitySniperSpot is not a console command")
    if '"accessibilitysniperspot"' not in shared:
        key_failures.append("the game's binding list does not know accessibilitySniperSpot")
    if '"accessibilitySniperSpot"' not in menu:
        key_failures.append("the Key Binds page has no row for the sniper spot key")
    if not re.search(r"^bind /\s+accessibilitySniperSpot\s*$", autoexec, re.M):
        key_failures.append("autoexec.cfg does not bind / to accessibilitySniperSpot")
    failures += key_failures
    if not key_failures:
        print("[spot] / is free in the game's layouts, and offered everywhere a key is set")

    if failures:
        for failure in failures:
            print("[spot] FAIL %s" % failure)
        sys.exit(1)
    print("sniper_spot_test: raised places with a long view are found, offered "
          "nearest first, and led to")


if __name__ == "__main__":
    main()

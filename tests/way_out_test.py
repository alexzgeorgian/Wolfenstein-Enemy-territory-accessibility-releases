#!/usr/bin/env python3
"""Check the way out of a building is found, and the way into one.

The tester got lost inside a villa and asked for the way in and out of
buildings to be something the marker can lead to. The search the key
starts is lifted out of the patched engine unchanged and run, with the
marker's own steps, on a world drawn from boxes:

- inside a house with one door, the way out ends under the open sky,
  through the door - not at the nearer outside through a wall, and not
  under a hole in the roof (a skylight), which is not outside;
- pressed again, the door already given is shut to the search, so it
  looks for another door: with only one door there is none;
- outside, the way in ends inside a room the map look-over found.

And the wiring: the key puts the marker there, said as "Way out" with
the distance and the way; the spot check stands down while it searches
(they share the one way-finder); it is forgotten on a new map; and ;
is free in both of the game's layouts and offered everywhere a key is
set.

    ./way_out_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import marker_route_sim_test as sim  # noqa: E402
import sniper_spot_test as spots  # noqa: E402

SCENE = r'''
/* ---- lifted: the way out's question ---- */
%(PLACE_SKY)s
%(STATE)s
%(GOAL)s

/* ---- the scene ---- */
static void House(float x0, float y0, float x1, float y1, float doorFrom, float doorTo)
{
	/* Walls 16 thick and a roof 200 up, a door in the south wall. */
	AddBox(x0, y1 - 16, 0, x1, y1, 200);
	AddBox(x0, y0, 0, x0 + 16, y1, 200);
	AddBox(x1 - 16, y0, 0, x1, y1, 200);
	AddBox(x0, y0, 0, doorFrom, y0 + 16, 200);
	AddBox(doorTo, y0, 0, x1, y0 + 16, 200);
}

static int Search(float x, float y, int in, float end[3], int *passedDoor)
{
	float         start[3] = { x, y, 24 };
	ETA_PathState state;
	int           steps = 0, i;

	eta_wayOut.in = in;
	ETA_PathFinder_BeginSearch(start, ETA_ROUTE_CELL, ETA_WayOutGoal, NULL);
	do
	{
		state  = ETA_PathFinder_Step(ETA_ROUTE_BUDGET_STEP, ETA_WayOutMove, NULL);
		steps += ETA_ROUTE_BUDGET_STEP;
	}
	while (state == ETA_PATH_SEARCHING && steps < ETA_WAYOUT_STEPS);

	*passedDoor = 0;
	if (state != ETA_PATH_FOUND || ETA_PathFinder_PointCount() <= 0)
	{
		return 0;
	}
	for (i = 0; i < ETA_PathFinder_PointCount(); i++)
	{
		float p[3];

		ETA_PathFinder_Point(i, p);
		if (p[0] > 600 && p[0] < 800 && p[1] > -40 && p[1] < 60)
		{
			*passedDoor = 1;
		}
	}
	ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, end);
	return 1;
}

int main(void)
{
	float x, y, end[3];
	int   column, row = 0, door;

	worldCount = 0;
	AddBox(-5000, -5000, 2000, 5000, 5000, 2016);   /* the sky */
	skyLid = worldCount - 1;
	AddBox(-5000, -5000, -64, 5000, 5000, 0);       /* the ground */

	/* A house 1400 by 800 with one door in the middle of the south
	   wall; the roof has a skylight near the west end, where the player
	   starts, 120 from the west wall - the outside through that wall is
	   far nearer than the door. */
	House(0, 0, 1400, 800, 650, 750);
	AddBox(0, 0, 200, 1400, 300, 216);
	AddBox(0, 500, 200, 1400, 800, 216);
	AddBox(0, 300, 200, 100, 500, 216);
	AddBox(260, 300, 200, 1400, 500, 216);           /* the skylight: 100 to 260 */

	eta_rooms.sampleCount = 0;
	for (y = 800 - 64.0f; y > -300.0f; y -= ETA_SPOT_SPACING, row++)
	{
		for (x = -300 + 64.0f, column = 0; x < 1700.0f; x += ETA_SPOT_SPACING, column++)
		{
			ETA_SpotScanPoint(x, y, column, row);
		}
	}
	ETA_RoomsBuild();

	eta_wayOut.found = 0;
	if (Search(120, 650, 0, end, &door))
	{
		printf("OUT %.0f %.0f door %d sky %d\n", end[0], end[1], door, ETA_SkyOver(end) ? 1 : 0);
		VectorCopy(end, eta_wayOut.ways[0]);
		eta_wayOut.found = 1;
		printf("AGAIN %d\n", Search(120, 650, 0, end, &door));
	}
	else
	{
		printf("OUT none\n");
	}

	eta_wayOut.found = 0;
	if (Search(700, -250, 1, end, &door))
	{
		printf("IN %.0f %.0f room %d\n", end[0], end[1], ETA_RoomAt(end));
	}
	else
	{
		printf("IN none\n");
	}
	return 0;
}
'''


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    commandmap = sim.read(root, sim.COMMANDMAP)
    failures = []

    state = re.search(r"#define ETA_WAYOUT_MAX \d+\s*\n.*?\} eta_wayOut;", commandmap, re.S)
    begin = commandmap.find("#define ETA_WAYOUT_STEPS")
    end = commandmap.find("void CG_AccessibilityWayOut(void)\n{")
    sky = re.search(r"#define ETA_PLACE_SKY [^\n]+", commandmap)
    if not state or begin < 0 or end < begin or not sky:
        sys.exit("no way out in %s - the feature this test measures is gone" % sim.COMMANDMAP)
    scene = SCENE.replace("%(PLACE_SKY)s", sky.group(0)).replace("%(STATE)s", state.group(0)) \
                 .replace("%(GOAL)s", commandmap[begin:end])

    # --- the search, on a drawn world ---------------------------------------
    run = spots.run_scene(root, commandmap, scene)
    out = re.search(r"OUT (-?\d+) (-?\d+) door (\d) sky (\d)", run.stdout)
    again = re.search(r"AGAIN (\d)", run.stdout)
    inside = re.search(r"IN (-?\d+) (-?\d+) room (-?\d+)", run.stdout)
    if not out:
        failures.append("no way out of the house was found\n%s" % (run.stdout + run.stderr[-2000:]))
    else:
        x, y, door, sky_over = (int(v) for v in out.groups())
        if not door or y > 0 or sky_over != 1:
            failures.append("the way out ends at %d %d, not outside through the door (door %d, sky %d)"
                            % (x, y, door, sky_over))
        else:
            print("[way out] from the far end of the house: out through the door, under the sky at %d %d" % (x, y))
        if not again or again.group(1) != "0":
            failures.append("asked again with only one door, another way out was found")
        else:
            print("[way out] asked again with only one door: no other way, and not the skylight")
    if not inside:
        failures.append("no way into the house was found from outside\n%s" % run.stdout)
    elif int(inside.group(3)) < 0:
        failures.append("the way in ends at %s %s, not inside a room" % inside.groups()[:2])
    else:
        print("[way out] from outside: the way in ends inside the room")

    # --- the wiring ---------------------------------------------------------
    key = spots.function_body(commandmap, "CG_AccessibilityWayOut")
    frame = spots.function_body(commandmap, "ETA_WayOutFrame")
    check = spots.function_body(commandmap, "ETA_SpotCheckFrame")
    marker_frame = spots.function_body(commandmap, "CG_AccessibilityMarkerFrame")
    reset = spots.function_body(commandmap, "CG_AccessibilityMarkerReset")
    for ok, what in (
            ("ETA_PathFinder_BeginSearch(origin, ETA_ROUTE_CELL, ETA_WayOutGoal, NULL);" in key,
             "the key does not look for the way out"),
            ("ETA_MARKER_CYCLE_MS" in key and "eta_wayOut.found = 0;" in key,
             "pressing again does not look for another way"),
            ("eta_marker.active = qtrue;" in frame and '"Way out"' in frame
             and "ETA_NavigationSystem_AnnounceMarkerDistance(distance);" in frame and "ETA_MarkerSpeakWay();" in frame,
             "the way found is not put on the marker and said with the distance and the way"),
            ("No way out found from here" in frame, "no way out is not said"),
            ("eta_wayOut.searching" in check, "the spot check does not stand down while the way out is looked for"),
            ("ETA_WayOutFrame();" in marker_frame, "the search is never carried on"),
            ("memset(&eta_wayOut, 0, sizeof(eta_wayOut));" in reset, "the way out of one map is kept on the next")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "key" in f or "marker" in f or "said" in f or "spot check" in f or "map" in f]:
        print("[way out] put on the marker and said; the spot check waits for it; forgotten on a new map")

    console = spots.read(os.path.join(root, spots.CONSOLE))
    ui = spots.read(os.path.join(root, spots.UI_MAIN))
    shared = spots.read(os.path.join(root, spots.UI_SHARED))
    menu = spots.read(spots.KEYS_MENU)
    autoexec = spots.read(spots.AUTOEXEC)
    key_failures = []
    for stock in spots.STOCK:
        if re.search(r"^bind\s+\"?;\"?\s", spots.read(os.path.join(root, stock)), re.M | re.I):
            key_failures.append("; is bound in the game's own %s" % stock)
    if not re.search(r"\{\s*';',\s*\"accessibilityWayOut\",\s*NULL,\s*\d+\s*\}", ui):
        key_failures.append("the installer does not offer the way out on ;")
    if not re.search(r'\{\s*"accessibilityWayOut",\s*CG_AccessibilityWayOut_f\s*\}', console):
        key_failures.append("accessibilityWayOut is not a console command")
    if '"accessibilitywayout"' not in shared:
        key_failures.append("the game's binding list does not know accessibilityWayOut")
    if '"accessibilityWayOut"' not in menu:
        key_failures.append("the Key Binds page has no row for the way out")
    if not re.search(r"^bind ;\s+accessibilityWayOut\s*$", autoexec, re.M):
        key_failures.append("autoexec.cfg does not bind ; to accessibilityWayOut")
    failures += key_failures
    if not key_failures:
        print("[way out] ; is free in both of the game's layouts, and offered everywhere a key is set")

    if failures:
        for failure in failures:
            print("[way out] FAIL %s" % failure)
        sys.exit(1)
    print("way_out_test: the way out of a building is found, and the way in")


if __name__ == "__main__":
    main()

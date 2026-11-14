#!/usr/bin/env python3
"""Check the way goes under a ceiling too low to stand, crouched, and says so.

Asked whether the way out works in tunnels, the way was found to refuse
any passage lower than a player standing - the game's own crouch fits
under a ceiling a standing player does not. The marker's steps are lifted
out of the patched engine unchanged and run on a world drawn from boxes:

- under a ceiling as high as a room, a step is a walk;
- under one lower than a player standing but higher than one crouched -
  the game's own crouchMaxZ, read from g_client.c and bg_public.h - it
  is a crouch;
- lower than that, there is no way; nor is there a jump under a ceiling
  too low to stand;
- the way out of a low tunnel is found, crouched, to the sky beyond;

and the wiring: a crouch is no stop on the way, as a jump or a ladder
is; within a couple of metres of where it starts the player is told to
crouch, with the key, and once out from under, that they can stand; a
crouch is taken over a jump, and costs more than a walk.

    ./crouch_way_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import marker_route_sim_test as sim  # noqa: E402
import sniper_spot_test as spots  # noqa: E402

G_CLIENT = os.path.join("src", "game", "g_client.c")
BG_PUBLIC = os.path.join("src", "game", "bg_public.h")
NAV = os.path.join(REPO, "src", "accessibility", "navigation", "navigation_system.c")

SCENE = r'''
%(PLACE_SKY)s
%(STATE)s
%(GOAL)s

static void Step(const char *label, float x, float y)
{
	float from[3] = { x, y, 24 }, to[3] = { x + 32, y, 24 };
	printf("STEP %s %d\n", label, ETA_RouteMoveExact(NULL, from, to));
}

int main(void)
{
	float         start[3] = { -200, 1000, 24 };
	ETA_PathState state;
	int           steps = 0, i, crouched = 0;

	worldCount = 0;
	AddBox(-5000, -5000, 2000, 5000, 5000, 2016);   /* the sky */
	skyLid = worldCount - 1;
	AddBox(-5000, -5000, -64, 5000, 5000, 0);       /* the ground */

	/* Three passages along x, 128 wide, each with its own ceiling. */
	AddBox(0, -100, 200, 400, 100, 216);            /* a room's height */
	AddBox(0, 200, 66, 400, 400, 300);              /* 66: lower than standing, 72 */
	AddBox(0, 500, 40, 400, 700, 300);              /* 40: lower than crouched, 48 */
	Step("room", 100, 0);
	Step("low", 100, 300);
	Step("lower", 100, 600);

	/* A low tunnel, 64 high, from inside a roofed hall out to the sky. */
	AddBox(-400, 900, 200, 0, 1100, 216);           /* the hall's roof */
	AddBox(-400, 880, 0, 400, 900, 200);            /* its walls, and the tunnel's */
	AddBox(-400, 1100, 0, 400, 1120, 200);
	AddBox(-420, 880, 0, -400, 1120, 200);
	AddBox(0, 900, 0, 400, 960, 200);               /* the tunnel: 80 wide, 64 high */
	AddBox(0, 1040, 0, 400, 1100, 200);
	AddBox(0, 960, 64, 400, 1040, 200);

	eta_wayOut.in = 0;
	eta_wayOut.found = 0;
	ETA_PathFinder_BeginSearch(start, ETA_ROUTE_CELL, ETA_WayOutGoal, NULL);
	do
	{
		state  = ETA_PathFinder_Step(ETA_ROUTE_BUDGET_STEP, ETA_WayOutMove, NULL);
		steps += ETA_ROUTE_BUDGET_STEP;
	}
	while (state == ETA_PATH_SEARCHING && steps < ETA_WAYOUT_STEPS);
	for (i = 0; i < ETA_PathFinder_PointCount(); i++)
	{
		crouched += ETA_PathFinder_PointKind(i) == ETA_PATH_CROUCH;
	}
	if (state == ETA_PATH_FOUND)
	{
		float end[3];

		ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, end);
		printf("OUT found %.0f %.0f crouched %d\n", end[0], end[1], crouched);
	}
	else
	{
		printf("OUT none %d\n", state);
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

    top = re.search(r"#define ETA_ROUTE_CROUCH_TOP \(ETA_ROUTE_BODY_TOP - \(40\.0f - 16\.0f\)\)", commandmap)
    client = spots.read(os.path.join(root, G_CLIENT))
    public = spots.read(os.path.join(root, BG_PUBLIC))
    if not top:
        sys.exit("no crouch on the way in %s - the feature this test measures is gone" % sim.COMMANDMAP)
    if "client->ps.crouchMaxZ = client->ps.maxs[2] - (client->ps.standViewHeight - client->ps.crouchViewHeight);" not in client \
            or not re.search(r"#define DEFAULT_VIEWHEIGHT\s+40\b", public) or not re.search(r"#define CROUCH_VIEWHEIGHT\s+16\b", public):
        failures.append("the game's own crouch height is not the standing height less 40 - 16, which the way was built on")
    else:
        print("[crouch] the game crouches to its standing height less 40 - 16, as the way does")

    state = re.search(r"#define ETA_WAYOUT_MAX \d+\s*\n.*?\} eta_wayOut;", commandmap, re.S)
    begin = commandmap.find("#define ETA_WAYOUT_STEPS")
    end = commandmap.find("void CG_AccessibilityWayOut(void)\n{")
    sky = re.search(r"#define ETA_PLACE_SKY [^\n]+", commandmap)
    scene = SCENE.replace("%(PLACE_SKY)s", sky.group(0)).replace("%(STATE)s", state.group(0)) \
                 .replace("%(GOAL)s", commandmap[begin:end])
    run = spots.run_scene(root, commandmap, scene)
    kinds = dict(re.findall(r"STEP (\w+) (\d+)", run.stdout))
    out = re.search(r"OUT (found (-?\d+) (-?\d+) crouched (\d+)|none \d+)", run.stdout)

    if kinds.get("room") != "1" or kinds.get("low") != "5" or kinds.get("lower") != "0":
        failures.append("under a room's ceiling, a low one and one lower still, the steps were %r, not walk, crouch, none\n%s"
                        % (kinds, run.stdout + run.stderr[-1500:]))
    else:
        print("[crouch] under a room's ceiling a walk; under one lower than standing a crouch; lower still, no way")
    if not out or not out.group(2) or int(out.group(4)) < 3 or int(out.group(2)) < 400:
        failures.append("the way out of a low tunnel was not found crouched: %r" % (out.group(0) if out else run.stdout))
    else:
        print("[crouch] the way out of a low tunnel: through it crouched, %s squares, to the sky at %s %s"
              % (out.group(4), out.group(2), out.group(3)))

    follow = spots.function_body(commandmap, "ETA_RouteFollow")
    say = spots.function_body(commandmap, "ETA_RouteSayCrouch")
    move = spots.function_body(commandmap, "ETA_RouteMove")
    exact = spots.function_body(commandmap, "ETA_RouteMoveExact")
    nav = spots.read(NAV)
    for ok, what in (
            ("ETA_PathFinder_PointKind(i) != ETA_PATH_CROUCH" in follow, "a crouch stops the way as a jump or a ladder does"),
            ("ETA_RouteSayCrouch(nearest, count, here);" in follow, "the crouch is never said"),
            ('"Crouch, low ceiling ahead%s", ETA_RouteKey("+movedown")' in say and "Stand up" in say,
             "the player is not told to crouch with the key, or to stand once out"),
            ("kind == ETA_PATH_CROUCH && found == ETA_PATH_JUMP" in move, "a jump is taken over a crouch"),
            ("if (ledge || !ETA_RouteRoom(from, to, lift, ETA_ROUTE_CROUCH_TOP))" in exact,
             "a jump is offered under a ceiling too low to stand"),
            ("if (kind == ETA_PATH_CROUCH)" in nav and "cost += flat;" in nav, "a crouch costs no more than a walk")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "said" in f or "told" in f or "stops" in f or "taken" in f or "offered" in f or "costs" in f]:
        print("[crouch] no stop on the way; told with the key, and to stand; over a jump, and slower than a walk")

    if failures:
        for failure in failures:
            print("[crouch] FAIL %s" % failure)
        sys.exit(1)
    print("crouch_way_test: the way goes under a low ceiling crouched, and says so")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check rooms are found the way the game finds them, and offered on a key.

The tester asked for the rooms to be trackable on the map. On the same
look over the map as the sniper spots, every floor with a roof over it
is kept, and the floors next to each other with no wall between make a
room (navigation/rooms.c). Lifted out of the patched engine unchanged,
that is run on a world drawn from boxes:

- two rooms side by side, a wall between them and a door into each, are
  two rooms, each with a way in;
- a courtyard walled round but open to the sky is no room;
- a room sealed on every side has no way in.

And the rest of the wiring:

- the rooms are grouped once the map has been looked over, checked for a
  way in, and forgotten on a new map;
- the key steps through them nearest first, puts the marker on each with
  a name that says "inside", and a room with no way in is told, taken
  off the list and the marker taken away;
- the map survey says how many rooms a square has;
- ' is free in the game's own right-handed layout, offered by the
  installer, a console command, on the Key Binds page, in the game's
  binding list and bound in the shipped config.

    ./rooms_test.py <engine-root>
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
/* ---- the scene ---- */
static void Walls(float x0, float y0, float x1, float y1, float doorFrom, float doorTo)
{
	/* Four walls 16 thick and a roof 200 up; a door in the south wall
	   from doorFrom to doorTo, none when they are equal. */
	AddBox(x0, y1 - 16, 0, x1, y1, 200);
	AddBox(x0, y0, 0, x0 + 16, y1, 200);
	AddBox(x1 - 16, y0, 0, x1, y1, 200);
	if (doorFrom < doorTo)
	{
		AddBox(x0, y0, 0, doorFrom, y0 + 16, 200);
		AddBox(doorTo, y0, 0, x1, y0 + 16, 200);
	}
	else
	{
		AddBox(x0, y0, 0, x1, y0 + 16, 200);
	}
}

int main(void)
{
	float x, y, ground[3] = { -2000, -2000, 24 };
	int   column, row = 0, i;

	worldCount = 0;
	AddBox(-5000, -5000, 2000, 5000, 5000, 2016);   /* the sky */
	skyLid = worldCount - 1;
	AddBox(-5000, -5000, -64, 5000, 5000, 0);       /* the ground */

	Walls(0, 0, 400, 400, 150, 250);                /* room A */
	AddBox(0, 0, 200, 400, 400, 216);
	Walls(400, 0, 800, 400, 550, 650);              /* room B, sharing A's east wall */
	AddBox(400, 0, 200, 800, 400, 216);
	Walls(-800, 0, -400, 400, -650, -550);          /* a courtyard: no roof */
	Walls(1500, 0, 1900, 400, 0, 0);                /* a room sealed on every side */
	AddBox(1500, 0, 200, 1900, 400, 216);

	eta_rooms.sampleCount = 0;
	for (y = 400 - 64.0f; y > -100.0f; y -= ETA_SPOT_SPACING, row++)
	{
		for (x = -900 + 64.0f, column = 0; x < 2000.0f; x += ETA_SPOT_SPACING, column++)
		{
			ETA_SpotScanPoint(x, y, column, row);
		}
	}
	ETA_RoomsBuild();

	for (i = 0; i < eta_rooms.list.count; i++)
	{
		ETA_Room     *room = &eta_rooms.list.rooms[i];
		ETA_PathState state;
		int           steps = 0;
		char          text[128];

		ETA_PathFinder_Begin(room->origin, ground, ETA_ROUTE_CELL, ETA_MARKER_ARRIVE_METERS / ETA_QU_TO_METERS, 0);
		do
		{
			state  = ETA_PathFinder_Step(ETA_ROUTE_BUDGET_STEP, ETA_RouteMoveBack, NULL);
			steps += ETA_ROUTE_BUDGET_STEP;
		}
		while (state == ETA_PATH_SEARCHING && steps < ETA_SPOT_CHECK_STEPS);

		ETA_Room_Text(room, ETA_SPOT_SPACING, text, sizeof(text));
		printf("ROOM %.0f %.0f %s = %s\n", room->origin[0], room->origin[1],
		       state == ETA_PATH_FOUND || state == ETA_PATH_SEARCHING ? "in" : "shut", text);
	}
	printf("ROOMS = %d\n", eta_rooms.list.count);
	return 0;
}
'''


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    commandmap = sim.read(root, sim.COMMANDMAP)
    if "ETA_RoomsBuild" not in commandmap:
        sys.exit("no rooms in %s - the feature this test measures is gone" % sim.COMMANDMAP)
    failures = []

    # --- the finding, on a drawn world --------------------------------------
    run = spots.run_scene(root, commandmap, SCENE)
    rooms = re.findall(r"ROOM (-?\d+) (-?\d+) (\w+) = (.*)", run.stdout)
    total = re.search(r"ROOMS = (\d+)", run.stdout)
    if not total:
        failures.append("the rooms were never looked for\n%s" % (run.stdout + run.stderr[-1000:]))
    else:
        def room_at(x0, x1):
            return [r for r in rooms if x0 < int(r[0]) < x1]
        a, b, court, sealed = room_at(0, 400), room_at(400, 800), room_at(-800, -400), room_at(1500, 1900)
        if len(a) != 1 or len(b) != 1:
            failures.append("two rooms with a wall between them were found as %d and %d" % (len(a), len(b)))
        elif a[0][2] != "in" or b[0][2] != "in":
            failures.append("a room with a door was taken for one with no way in")
        elif not re.match(r"^Room, ground floor, 10 by 10 meters$", a[0][3]):
            failures.append("room A was said %r" % a[0][3])
        else:
            print("[rooms] two rooms with a wall between: two rooms, each with a way in: %s" % a[0][3])
        if court:
            failures.append("a courtyard open to the sky was taken for a room")
        else:
            print("[rooms] a courtyard open to the sky is no room")
        if len(sealed) != 1 or sealed[0][2] != "shut":
            failures.append("the sealed room was not found, or was taken for one with a way in: %r" % sealed)
        else:
            print("[rooms] a room sealed on every side has no way in")

    # --- the wiring ---------------------------------------------------------
    scan = spots.function_body(commandmap, "ETA_SpotScanFrame")
    check = spots.function_body(commandmap, "ETA_SpotCheckFrame")
    reset = spots.function_body(commandmap, "CG_AccessibilityMarkerReset")
    key = spots.function_body(commandmap, "CG_AccessibilityRoom")
    judge = spots.function_body(commandmap, "ETA_SpotJudgeWay")
    speak = spots.function_body(commandmap, "ETA_MapSpeakCell")
    for ok, what in (
            ("ETA_RoomsBuild();" in scan, "the rooms are not grouped once the map has been looked over"),
            ("eta_rooms.list.rooms[" in check, "the rooms are not checked for a way in"),
            ("memset(&eta_rooms, 0, sizeof(eta_rooms));" in reset, "the rooms of one map are kept on the next"),
            ("ETA_RoomList_Nearest(" in key, "the rooms are not offered nearest first"),
            ("ETA_MARKER_CYCLE_MS" in key, "pressing again does not step to the next room"),
            ('"inside %s"' in key and '"inside the room"' in key, "arriving does not say inside the room"),
            ("eta_marker.active = qtrue;" in key, "the marker is not put on the room"),
            (re.search(r"room->unreachable\s*=\s*1;", judge) and "No way into that room" in judge,
             "a room with no way in is not told and left off the list"),
            ("ETA_RoomsInCell(" in speak, "the map survey does not say how many rooms a square has")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "room" in f and "two rooms" not in f and "courtyard" not in f and "sealed" not in f]:
        print("[rooms] grouped after the scan, checked for a way in, offered nearest first, counted by square")

    console = spots.read(os.path.join(root, spots.CONSOLE))
    ui = spots.read(os.path.join(root, spots.UI_MAIN))
    shared = spots.read(os.path.join(root, spots.UI_SHARED))
    menu = spots.read(spots.KEYS_MENU)
    autoexec = spots.read(spots.AUTOEXEC)
    stock = spots.read(os.path.join(root, spots.STOCK[0]))
    key_failures = []
    if re.search(r"^bind\s+\"?'\"?\s", stock, re.M | re.I):
        key_failures.append("' is bound in the game's own layout - the room key would steal it")
    if not re.search(r"\{\s*'\\'',\s*\"accessibilityRoom\",\s*NULL,\s*\d+\s*\}", ui):
        key_failures.append("the installer does not offer the room key on '")
    if not re.search(r'\{\s*"accessibilityRoom",\s*CG_AccessibilityRoom_f\s*\}', console):
        key_failures.append("accessibilityRoom is not a console command")
    if '"accessibilityroom"' not in shared:
        key_failures.append("the game's binding list does not know accessibilityRoom")
    if '"accessibilityRoom"' not in menu:
        key_failures.append("the Key Binds page has no row for the room key")
    if not re.search(r"^bind '\s+accessibilityRoom\s*$", autoexec, re.M):
        key_failures.append("autoexec.cfg does not bind ' to accessibilityRoom")
    failures += key_failures
    if not key_failures:
        print("[rooms] ' is free in the game's layout, and offered everywhere a key is set")

    if failures:
        for failure in failures:
            print("[rooms] FAIL %s" % failure)
        sys.exit(1)
    print("rooms_test: rooms are found, checked for a way in, and offered on a key")


if __name__ == "__main__":
    main()

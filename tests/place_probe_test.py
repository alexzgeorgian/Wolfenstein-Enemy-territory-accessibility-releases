#!/usr/bin/env python3
"""Measure places the way the game does, in worlds drawn from boxes.

The tester asked to follow streets and alleys and tell the parts of a
building apart. The words come from navigation/place_classifier.c, which
its own smoke test pins; this checks the other half - the measuring in
the patched engine (ETA_PlaceProbeAt in cg_commandmap.c), lifted out
unchanged and run against walls and floors the way marker_route_sim_test
runs the route: a street each way round, an alley, a square, open ground,
a building with a floor above it, a balcony, a rooftop and a ledge.

Two traps it was built against on the real Oasis map:

- every street there sits on the sealed space under the map, which is
  lined with surfaces nobody sees; counted as a room below, every street
  became "upper floor" or "balcony";
- a drop beside solid ground is a ledge, not a balcony - there is no
  building under it.

    ./place_probe_test.py <engine-root>
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

SCENES = r'''
/* ---- the places ---- */
static int nodrawBelow;   /* the world's underside is the sealed kind */

static void Ground(void)
{
	worldCount = 0;
	AddBox(-4096, -4096, -64, 4096, 4096, 0);
}

static const char *Measure(const char *name, float x, float y, float z)
{
	static char text[160];
	vec3_t      at = { x, y, z + 24.0f };
	ETA_Place   place;

	CG_AccessibilityPlace(at, &place);
	ETA_Place_Text(&place, text, sizeof(text));
	printf("PLACE %s = %s\n", name, text);
	return text;
}

int main(void)
{
	/* A street running north to south: two rows of houses 320 apart. */
	Ground();
	AddBox(-2000, -2000, 0, -160, 2000, 400);
	AddBox(160, -2000, 0, 2000, 2000, 400);
	Measure("street north to south", 0, 0, 0);

	/* The same street east to west. */
	Ground();
	AddBox(-2000, -2000, 0, 2000, -160, 400);
	AddBox(-2000, 160, 0, 2000, 2000, 400);
	Measure("street east to west", 0, 0, 0);

	/* An alley, 120 across. */
	Ground();
	AddBox(-2000, -2000, 0, -60, 2000, 400);
	AddBox(60, -2000, 0, 2000, 2000, 400);
	Measure("alley north to south", 0, 0, 0);

	/* A square: walls all round, 640 across. */
	Ground();
	AddBox(-2000, -2000, 0, 2000, -320, 400);
	AddBox(-2000, 320, 0, 2000, 2000, 400);
	AddBox(-2000, -320, 0, -320, 320, 400);
	AddBox(320, -320, 0, 2000, 320, 400);
	Measure("square", 0, 0, 0);

	/* Open ground. */
	Ground();
	Measure("open ground", 0, 0, 0);

	/* A building: a roof over a hall. */
	Ground();
	AddBox(-600, -600, 200, 600, 600, 232);
	Measure("indoors", 0, 0, 0);

	/* Its upper floor: a floor slab at 160 with a room under it, and the
	   roof above. */
	AddBox(-600, -600, 160, 600, 600, 176);
	worldBoxes[worldCount - 2].mn[2] = 400;   /* raise the roof */
	worldBoxes[worldCount - 2].mx[2] = 432;
	Measure("upper floor", 0, 0, 176);

	/* A balcony: a narrow slab 160 up along a wall, open to the sky,
	   the street under it. */
	Ground();
	AddBox(-2000, 60, 0, 2000, 2000, 600);         /* the house front */
	AddBox(-2000, -60, 160, 2000, 60, 176);        /* the balcony slab */
	Measure("balcony", 0, 0, 176);

	/* A rooftop: a broad slab 300 up with rooms under it. */
	Ground();
	AddBox(-800, -800, 300, 800, 800, 316);
	Measure("rooftop", 0, 0, 316);

	/* A ledge: solid ground 200 up - a terrace - falling away to the
	   south a step from the player. */
	Ground();
	AddBox(-2000, -48, 0, 2000, 2000, 200);
	Measure("ledge", 0, 0, 200);

	/* The street again, standing on the sealed space under the map: the
	   ground is a thin slab with emptiness under it, lined with surfaces
	   nobody sees. Still a street. */
	worldCount = 0;
	AddBox(-4096, -4096, -24, 4096, 4096, 0);
	AddBox(-4096, -4096, -600, 4096, 4096, -560);
	AddBox(-2000, -2000, 0, -160, 2000, 400);
	AddBox(160, -2000, 0, 2000, 2000, 400);
	nodrawBelow = 1;
	Measure("street over the sealed space", 0, 0, 0);
	nodrawBelow = 0;

	/* A square of the command map, 1200 across, under a sky like a real
	   map's: a street running north to south through it, the houses to
	   the west a solid block up to the sky the way Oasis builds the
	   houses nobody enters, and to the east a building you can go into,
	   with a flat roof. */
	worldCount = 0;
	AddBox(-100, -100, 1000, 1300, 1300, 1016);    /* the sky */
	skyLid = worldCount - 1;
	AddBox(0, 0, -64, 1200, 1200, 0);              /* the ground */
	AddBox(0, 0, 0, 500, 1200, 1000);              /* houses to the west */
	AddBox(800, 0, 0, 816, 1200, 300);             /* the building: walls */
	AddBox(1184, 0, 0, 1200, 1200, 300);
	AddBox(816, 0, 0, 1184, 16, 300);
	AddBox(816, 1184, 0, 1184, 1200, 300);
	AddBox(800, 0, 300, 1200, 1200, 316);          /* and its roof */
	{
		char text[ETA_MAP_PLACES_MAX];

		ETA_MapCellPlaces(0, 0, 0, text, sizeof(text));
		printf("SURVEY square = %s\n", text);
	}
	skyLid = -1;
	return 0;
}
'''


def world_harness():
    """The walk's world of boxes, fitted for looking down through floors:
    traces start inside a box and leave it the way the engine's do, the
    world's underside can be the sealed kind, and the sky is sky. Shared
    with sniper_spot_test.py."""
    harness = sim.HARNESS[:sim.HARNESS.index("/* ---- the walker ---- */")]
    # The sealed space under a map is lined with surfaces nobody sees:
    # in these worlds, every surface below the ground when asked.
    harness = harness.replace("	results->entityNum = best < 1.0f ? ENTITYNUM_WORLD : ENTITYNUM_NONE;",
                              "	results->entityNum = best < 1.0f ? ENTITYNUM_WORLD : ENTITYNUM_NONE;\n"
                              "	if (best < 1.0f && nodrawBelowWorld && results->endpos[2] < -1.0f) results->surfaceFlags |= SURF_NODRAW;")
    harness = harness.replace("static long  traceCount;", "static long  traceCount;\nstatic int   nodrawBelowWorld;\nstatic int   skyLid = -1;")
    # The survey drops through floors the way the engine's traces do: a
    # trace that starts inside a box and leaves it is not stopped by it.
    # And the sky over the map is sky.
    harness = harness.replace("""		if (inside)
		{
			results->startsolid = qtrue;
			best                = 0.0f;
			continue;
		}""", """		if (inside)
		{
			int endInside = 1;
			results->startsolid = qtrue;
			for (a = 0; a < 3; a++)
			{
				if (!(end[a] > lo[a] + 0.01f && end[a] < hi[a] - 0.01f))
				{
					endInside = 0;
				}
			}
			if (skyLid >= 0 && !endInside)
			{
				continue;
			}
			best = 0.0f;
			continue;
		}""")
    harness = harness.replace("int   i, a, hitAxis = -1;", "int   i, a, hitAxis = -1, hitBox = -1;")
    harness = harness.replace("		hitSign = sign;\n", "		hitSign = sign;\n		hitBox  = i;\n")
    harness = harness.replace("	results->entityNum = best < 1.0f ? ENTITYNUM_WORLD : ENTITYNUM_NONE;\n",
                              "	results->entityNum = best < 1.0f ? ENTITYNUM_WORLD : ENTITYNUM_NONE;\n"
                              "	if (best < 1.0f && hitBox >= 0 && hitBox == skyLid) results->surfaceFlags |= SURF_SKY;\n", 1)
    if "hitBox  = i;" not in harness or "endInside" not in harness or "SURF_SKY;" not in harness:
        sys.exit("could not fit the survey's traces to the walk's world - has marker_route_sim_test changed?")

    return harness


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    commandmap = sim.read(root, sim.COMMANDMAP)
    if "static void ETA_PlaceProbeAt(" not in commandmap:
        sys.exit("no place probe in %s - the feature this test measures is gone" % sim.COMMANDMAP)

    harness = world_harness()

    # The map survey's reading of a square, lifted on its own: it needs
    # the map's grid, here one square 1200 across.
    begin = commandmap.find("/**\n * @brief The floors a player could stand on")
    finish_mark = "\tETA_PlaceSurvey_Describe(&survey, out, outSize);\n}\n"
    finish = commandmap.find(finish_mark, begin)
    places_max = re.search(r"#define ETA_MAP_PLACES_MAX +\d+", commandmap)
    if begin < 0 or finish < 0 or not places_max:
        sys.exit("no map survey places in %s - the feature this test measures is gone" % sim.COMMANDMAP)
    survey = "\n".join([
        places_max.group(0),
        "static struct { int ccLayers; } cgs;",
        "static int CG_CurLayerForZ(int z) { (void)z; return 0; }",
        "static qboolean ETA_MapGrid(vec2_t start, vec2_t step, int *columns, int *rows)",
        "{ start[0] = 0; start[1] = 1200; step[0] = step[1] = 1200; *columns = *rows = 1; return qtrue; }",
        commandmap[begin:finish + len(finish_mark)]])

    source_text = harness.replace("%(LIFTED)s", sim.lift(commandmap) + "\n" + survey) \
        + SCENES.replace("static int nodrawBelow;", "#define nodrawBelow nodrawBelowWorld")

    library = sorted(glob.glob(os.path.join(REPO, "src", "accessibility", "**", "*.c"), recursive=True))
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "place.c")
        binary = os.path.join(tmp, "place")
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
            sys.exit("the lifted place probe does not build:\n%s" % build.stderr[-3000:])
        run = subprocess.run([binary], capture_output=True, text=True, timeout=120)

    got = dict(re.findall(r"PLACE (.*?) = (.*)", run.stdout))
    surveyed = dict(re.findall(r"SURVEY (.*?) = (.*)", run.stdout))
    want = {
        "street north to south": r"^Street, north to south, 8 meters wide$",
        "street east to west": r"^Street, east to west, 8 meters wide$",
        "alley north to south": r"^Alley, north to south$",
        "square": r"^Square$",
        "open ground": r"^Open ground$",
        "indoors": r"^Indoors$",
        "upper floor": r"^Indoors, upper floor$",
        "balcony": r"^Balcony$",
        "rooftop": r"^Rooftop$",
        "ledge": r"^Ledge, 5 meter drop beside$",
        "street over the sealed space": r"^Street, north to south, 8 meters wide$",
    }
    failures = []
    for name, pattern in want.items():
        said = got.get(name)
        if said is None:
            failures.append("%s: never measured\n%s" % (name, run.stdout + run.stderr[-1000:]))
        elif not re.match(pattern, said):
            failures.append("%s: said %r" % (name, said))
        else:
            print("[place] %-30s %s" % (name, said))

    said = surveyed.get("square")
    want_survey = r"^a street running north to south, a building to the east with a rooftop$"
    if said is None:
        failures.append("the map square: never surveyed\n%s" % (run.stdout + run.stderr[-1000:]))
    elif not re.match(want_survey, said):
        failures.append("the map square: said %r" % said)
    else:
        print("[place] %-30s %s" % ("map square", said))

    # And the measuring is used: said as you walk, unless turned off, and
    # by F9; the setting is on the Environment page and in the config.
    draw = sim.read(root, "src/cgame/cg_draw.c")
    main_c = sim.read(root, "src/cgame/cg_main.c")
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    menu = sim.read(here, "release/ui/options_accessibility_environment.menu")
    autoexec = sim.read(here, "release/autoexec.cfg")
    wiring = {
        "walking callouts are made": "ETA_NarratePlace();" in draw,
        "walking callouts can be turned off": "!eta_placeCallouts.integer" in draw,
        "walking callouts say the voted place":
            "ETA_Place_Update(&place, cg.time) && ETA_Place_Spoken(&place)" in draw,
        "F9 measures the place": draw.count("CG_AccessibilityPlace(") >= 2,
        "the setting is registered, on by default":
            '"eta_placeCallouts",       "1"' in main_c,
        "the setting is on the Environment page": '"eta_placeCallouts"' in menu,
        "the setting is in the config": re.search(r'seta eta_placeCallouts\s+"1"', autoexec),
    }
    for name, ok in wiring.items():
        if not ok:
            failures.append(name + ": no")
        else:
            print("[place] %s" % name)

    if failures:
        for failure in failures:
            print("[place] FAIL %s" % failure)
        sys.exit(1)
    print("place_probe_test: streets, alleys, squares, buildings, balconies, "
          "rooftops and ledges are measured as the game will")


if __name__ == "__main__":
    main()

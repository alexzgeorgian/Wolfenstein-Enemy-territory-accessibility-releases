#!/usr/bin/env python3
"""Check flights of stairs are on the F list, and F turns up or down them.

The tester found the stairs to the Allied command post on Oasis and
could not get onto them: stairs were not on the list of things F turns
to, the way ladders are, and facing straight up a flight by ear is
guesswork. The map has nothing that marks stairs, so the patched engine
looks for them (ETA_StairsNear in cg_draw.c). Lifted out unchanged, that
is run on a world drawn from boxes:

- a flight of eight steps, 16 high, going north from in front of the
  player, is "Stairs up, 3 meters", its foot where the first step starts
  and facing north;
- the same flight from its top is "Stairs down", facing south;
- flat ground, and a single high step, are no stairs.

And the wiring: the stairs are added to the F list after the ladders;
F, and the bracket keys' choice, turn to a flight's foot, and at the foot
straight along it, saying so, and never press use at it.

    ./stairs_on_f_test.py <engine-root>
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

DRAW = os.path.join("src", "cgame", "cg_draw.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")

SCENE = r'''
typedef struct
{
	int      entityNum;
	vec3_t   point;
	float    meters;
	char     name[64];
	qboolean ladder;
	qboolean locked;
	qboolean stairs;
	vec3_t   along;
} etaAimTarget_t;

%(STAIRS)s

static void Look(const char *name, float x, float y, float z)
{
	etaAimTarget_t found[4];
	vec3_t         at = { x, y, z + 24.0f };
	int            n = ETA_StairsNear(at, found, 4), i;

	printf("LOOK %s %d\n", name, n);
	for (i = 0; i < n; i++)
	{
		printf("FLIGHT %s = %s | foot %.0f %.0f | faces %.0f %.0f %s\n", name, found[i].name,
		       found[i].point[0], found[i].point[1],
		       found[i].along[0] - found[i].point[0], found[i].along[1] - found[i].point[1],
		       found[i].along[2] > found[i].point[2] ? "up" : "down");
	}
}

int main(void)
{
	int k;

	/* A flight north: eight steps 16 high and 32 deep from y = 200,
	   then a landing at 128. */
	worldCount = 0;
	AddBox(-4096, -4096, -64, 4096, 4096, 0);
	for (k = 1; k <= 8; k++)
	{
		AddBox(-64, 200 + 32 * (k - 1), 0, 64, 200 + 32 * k, 16.0f * k);
	}
	AddBox(-64, 456, 0, 64, 800, 128);
	Look("bottom", 0, 0, 0);
	Look("top", 0, 600, 128);

	/* Flat ground; and one step a third of a metre high. */
	worldCount = 0;
	AddBox(-4096, -4096, -64, 4096, 4096, 0);
	Look("flat", 0, 0, 0);
	AddBox(-2000, 200, 0, 2000, 2000, 14);
	Look("one step", 0, 0, 0);
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


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    console = read(os.path.join(root, CONSOLE))
    failures = []

    begin = draw.find("#define ETA_STAIRS_STEP")
    end = draw.find("/**\n * @brief The things close by the player could use, nearest first.")
    if begin < 0 or end < begin or "static int ETA_StairsNear(" not in draw:
        sys.exit("no stairs finder in %s - the feature this test measures is gone" % DRAW)

    harness = sim.HARNESS[:sim.HARNESS.index("/* ---- lifted from the patched engine ---- */")]
    source_text = harness + SCENE.replace("%(STAIRS)s", draw[begin:end])

    library = sorted(glob.glob(os.path.join(REPO, "src", "accessibility", "**", "*.c"), recursive=True))
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "stairs.c")
        binary = os.path.join(tmp, "stairs")
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
            sys.exit("the lifted stairs finder does not build:\n%s" % build.stderr[-3000:])
        run = subprocess.run([binary], capture_output=True, text=True, timeout=120)

    looks = dict(re.findall(r"LOOK (.+?) (\d+)", run.stdout))
    flights = {}
    for name, said, fx, fy, ax, ay, way in re.findall(
            r"FLIGHT (.+?) = (.*?) \| foot (-?\d+) (-?\d+) \| faces (-?\d+) (-?\d+) (\w+)", run.stdout):
        flights.setdefault(name, []).append((said, int(fx), int(fy), int(ax), int(ay), way))

    bottom = flights.get("bottom", [])
    if len(bottom) != 1:
        failures.append("from the bottom, the flight was found %d times\n%s" % (len(bottom), run.stdout))
    else:
        said, fx, fy, ax, ay, way = bottom[0]
        if not re.match(r"^Stairs up, 3 meters$", said):
            failures.append("from the bottom, the flight was said %r" % said)
        elif not (abs(fx) <= 16 and 168 <= fy <= 208):
            failures.append("from the bottom, the foot is at %d %d, not where the first step starts" % (fx, fy))
        elif not (abs(ax) <= 8 and ay > 200 and way == "up"):
            failures.append("at the foot, F would face %d %d %s, not straight up the flight" % (ax, ay, way))
        else:
            print("[stairs] from the bottom: %s, facing straight up it" % said)

    top = flights.get("top", [])
    if len(top) != 1:
        failures.append("from the top, the flight was found %d times\n%s" % (len(top), run.stdout))
    else:
        said, fx, fy, ax, ay, way = top[0]
        if not said.startswith("Stairs down") or not (abs(ax) <= 8 and ay < -200 and way == "down"):
            failures.append("from the top, the flight was said %r facing %d %d %s" % (said, ax, ay, way))
        else:
            print("[stairs] from the top: %s, facing straight down it" % said)

    if looks.get("flat") != "0" or looks.get("one step") != "0":
        failures.append("flat ground or a single step was taken for stairs: %r" % looks)
    else:
        print("[stairs] flat ground and a single step are no stairs")

    targets = function_body(draw, "CG_AccessibilityUseTargets")
    turn = function_body(console, "ETA_StairsTurn")
    activate = function_body(console, "CG_AccessibilityActivateDown_f")
    for ok, what in (
            ("ETA_StairsNear(ps->origin" in targets and "ETA_AimInsert(list, &count, max, &flights[i]);" in targets,
             "the stairs close by are not on the F list"),
            ("target->along" in turn and "Facing %s the stairs. Walk forward" in turn
             and "ETA_STAIRS_AT_FOOT_METERS" in turn, "at the foot, F does not turn along the flight and say so"),
            ("eta_use.pending" not in turn, "F presses use at stairs"),
            (activate.count("ETA_StairsTurn(") >= 2,
             "F, or the bracket keys' choice, does not turn to stairs the way it should")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "F " in f or "F list" in f]:
        print("[stairs] on the F list; F turns to the foot, then along the flight, and presses nothing")

    if failures:
        for failure in failures:
            print("[stairs] FAIL %s" % failure)
        sys.exit(1)
    print("stairs_on_f_test: flights of stairs are found, on the F list, and faced up or down")


if __name__ == "__main__":
    main()

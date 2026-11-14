#!/usr/bin/env python3
"""Check the things in a room are said as the player comes up to them.

The tester asked to hear the table, the chair, the bookcase when getting
close to one. The things are read from the map file (map/bsp_props.c,
checked by its own smoke test); saying them is the patched engine's
ETA_NarrateFurniture, lifted out unchanged and run in a room drawn from
boxes, frame by frame:

- an armchair a metre ahead is said, by name and direction, once;
  walked away from and back to, it is said again;
- two chairs side by side are said once, not twice;
- a crate behind a wall, and a bed on the floor above, are not said;
- a window is said from inside, not walking past a house outside;
- what a trace ends on is said by its name: the look-ahead and the
  scope say "Crate", not the wood it is made of.

And the wiring: the things are read while the map loads, said with the
other scenery behind an answer the player asked for, and the setting
is registered, on the Environment page and in the shipped config.

    ./furniture_test.py <engine-root>
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
MAIN = os.path.join("src", "cgame", "cg_main.c")
ENVIRONMENT = os.path.join(REPO, "release", "ui", "options_accessibility_environment.menu")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")

HARNESS = r'''
#include "q_shared.h"
#include "game/surfaceflags.h"
#include "game/bg_public.h"
#include "hud/hud_narrator.h"
#include "map/bsp_props.h"
#include <stdio.h>
#include <math.h>

#ifndef MASK_SOLID
#define MASK_SOLID CONTENTS_SOLID
#endif

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

static struct { int ps_clientNum; } snapshot;
static struct
{
	int           time;
	struct { struct { int clientNum; } ps; } *snap;
	playerState_t predictedPlayerState;
} cg;
static struct { char mapname[64]; } cgs;
static struct { int integer; } eta_furnitureCallouts = { 1 };

/* What was said, frame by frame. */
static char said[64][96];
static int  saidCount;
#define ETA_Speech_BeginReport()
#define ETA_Speech_EndReport()
#define ETA_Speech_Say(text) (saidCount < 64 ? (Q_strncpyz(said[saidCount++], (text), 96), 0) : 0)

/* Boxes; the one marked sky is sky. */
typedef struct { float mn[3], mx[3]; int sky; } box_t;
static box_t boxes[32];
static int   boxCount;

static void AddBox(float x0, float y0, float z0, float x1, float y1, float z1, int sky)
{
	box_t *b = &boxes[boxCount++];
	b->mn[0] = x0; b->mn[1] = y0; b->mn[2] = z0; b->mx[0] = x1; b->mx[1] = y1; b->mx[2] = z1; b->sky = sky;
}

void CG_Trace(trace_t *result, const vec3_t start, const vec3_t mins, const vec3_t maxs, const vec3_t end, int skip, int mask)
{
	int i, a;

	(void)mins; (void)maxs; (void)skip; (void)mask;
	memset(result, 0, sizeof(*result));
	result->fraction = 1.0f;
	VectorCopy(end, result->endpos);

	for (i = 0; i < boxCount; i++)
	{
		float enter = 0.0f, leave = 1.0f;

		for (a = 0; a < 3; a++)
		{
			float d = end[a] - start[a], t0, t1;

			if (fabs(d) < 1e-6f)
			{
				if (start[a] < boxes[i].mn[a] || start[a] > boxes[i].mx[a])
				{
					enter = 2.0f;
				}
				continue;
			}
			t0 = (boxes[i].mn[a] - start[a]) / d;
			t1 = (boxes[i].mx[a] - start[a]) / d;
			if (t0 > t1) { float s = t0; t0 = t1; t1 = s; }
			if (t0 > enter) enter = t0;
			if (t1 < leave) leave = t1;
		}
		if (enter <= leave && enter < result->fraction && enter >= 0.0f)
		{
			result->fraction     = enter;
			result->surfaceFlags = boxes[i].sky ? SURF_SKY : 0;
			for (a = 0; a < 3; a++)
			{
				result->endpos[a] = start[a] + (end[a] - start[a]) * enter;
			}
		}
	}
}

/* The player faces east: left of view is the angle from east. */
float CG_AccessibilityLeftOfView(const vec3_t point)
{
	return (float)(atan2(point[1] - cg.predictedPlayerState.origin[1], point[0] - cg.predictedPlayerState.origin[0]) * 180.0 / M_PI);
}

typedef struct { int handle; } etaMapFile_t;
static int ETA_MapFileRead(void *c, void *b, int l) { (void)c; (void)b; (void)l; return 0; }
static int ETA_MapFileRestart(void *c) { (void)c; return 0; }
static void trap_FS_FCloseFile(int h) { (void)h; }
static void CG_DPrintf(const char *fmt, ...) { (void)fmt; }

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

/* ---- the scene ---- */
static void Prop(const char *name, float x0, float y0, float z0, float x1, float y1, float z1)
{
	float mn[3] = { x0, y0, z0 }, mx[3] = { x1, y1, z1 };
	eta_mapPropCount = ETA_BspProps_Add(eta_mapProps, eta_mapPropCount, ETA_MAP_PROPS, name, mn, mx, 0.0f);
}

/* Walks the player to x, y a frame at a time, and prints what was said. */
static void Stand(const char *label, float x, float y)
{
	int f;

	saidCount = 0;
	cg.predictedPlayerState.origin[0] = x;
	cg.predictedPlayerState.origin[1] = y;
	for (f = 0; f < 40; f++)
	{
		cg.time += 100;
		ETA_NarrateFurniture();
	}
	printf("AT %s %d", label, saidCount);
	for (f = 0; f < saidCount; f++)
	{
		printf(" | %s", said[f]);
	}
	printf("\n");
}

int main(void)
{
	static struct { struct { int clientNum; } ps; } snap;

	cg.snap = (void *)&snap;
	cg.predictedPlayerState.pm_type    = PM_NORMAL;
	cg.predictedPlayerState.viewheight = 40;
	cg.predictedPlayerState.origin[2]  = 24;

	/* A room with a roof, a wall across it at x = 300; the sky over all. */
	AddBox(-2000, -2000, 2000, 4000, 2000, 2016, 1);
	AddBox(-400, -400, 200, 1000, 400, 216, 0);
	AddBox(300, -400, 0, 316, 400, 200, 0);

	Prop("Armchair", 50, -20, 0, 100, 20, 50);
	Prop("Chair", -60, 150, 0, -40, 170, 40);
	Prop("Chair", -20, 150, 0, 0, 170, 40);
	Prop("Crate", 330, -20, 0, 380, 20, 48);
	Prop("Bed", -40, -200, 220, 40, -150, 260);
	Prop("Window", -80, 395, 60, -20, 400, 120);
	Prop("Window", 2000, -10, 60, 2060, -5, 120);

	Stand("armchair", 0, 0);
	Stand("away", -300, 0);
	Stand("back", 0, 0);
	Stand("chairs", -30, 110);
	Stand("wall", 280, 0);
	Stand("below the bed", 0, -170);
	Stand("inside the window", -50, 360);
	Stand("outside the window", 2030, -60);

	{
		vec3_t onCrate = { 331, 0, 30 }, inAir = { 200, 0, 30 };
		const char *name = ETA_PropAt(onCrate);
		printf("HIT %s %s\n", name ? name : "-", ETA_PropAt(inAir) ? "something" : "-");
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


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    draw = read(os.path.join(root, DRAW))
    failures = []

    begin = draw.find("#define ETA_MAP_PROPS")
    end = draw.find("/**\n * @brief How far a ladder is heard")
    if begin < 0 or end < begin or "static void ETA_NarrateFurniture(void)" not in draw:
        sys.exit("no furniture callouts in %s - the feature this test measures is gone" % DRAW)

    source_text = HARNESS.replace("%(LIFTED)s", draw[begin:end])
    library = sorted(glob.glob(os.path.join(REPO, "src", "accessibility", "**", "*.c"), recursive=True))
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "furniture.c")
        binary = os.path.join(tmp, "furniture")
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
            sys.exit("the lifted furniture callouts do not build:\n%s" % build.stderr[-3000:])
        run = subprocess.run([binary], capture_output=True, text=True, timeout=120)

    at = {}
    for label, count, rest in re.findall(r"AT (.+?) (\d+)((?: \| [^|\n]*)*)\n", run.stdout):
        at[label] = [s.strip() for s in rest.split("|")[1:]]
    hit = re.search(r"HIT (\S+) (\S+)", run.stdout)

    def said(label):
        return at.get(label, ["(never run)"])

    if said("armchair") != [s for s in said("armchair") if s.startswith("Armchair, ")] or len(said("armchair")) != 1:
        failures.append("an armchair a metre ahead was said %r, not once by name and direction" % said("armchair"))
    elif said("back") != said("armchair") or said("away"):
        failures.append("walked away and back, the armchair was said %r then %r" % (said("away"), said("back")))
    else:
        print("[furniture] an armchair a metre ahead: %r, once; and again after walking off and back" % said("armchair")[0])
    if [s for s in said("chairs") if s.startswith("Chair")] != [s for s in said("chairs") if s.startswith("Chair")][:1] \
            or not [s for s in said("chairs") if s.startswith("Chair")]:
        failures.append("two chairs side by side were said %r" % said("chairs"))
    else:
        print("[furniture] two chairs side by side: said once")
    if [s for s in said("wall") if s.startswith("Crate")]:
        failures.append("a crate behind a wall was said")
    elif [s for s in said("below the bed") if s.startswith("Bed")]:
        failures.append("a bed on the floor above was said")
    else:
        print("[furniture] a crate behind a wall, a bed on the floor above: not said")
    if not [s for s in said("inside the window") if s.startswith("Window")]:
        failures.append("a window was not said from inside: %r" % said("inside the window"))
    elif [s for s in said("outside the window") if s.startswith("Window")]:
        failures.append("a window was said walking past a house outside")
    else:
        print("[furniture] a window is said from inside, not from the street")
    if not hit or hit.group(1) != "Crate" or hit.group(2) != "-":
        failures.append("what a trace ends on is not said by its name: %r" % (hit.groups() if hit else run.stdout))
    else:
        print("[furniture] a trace ending on a crate says \"Crate\"")

    # --- the wiring ---------------------------------------------------------
    hit_text = function_body(draw, "ETA_DescribeTraceHit")
    load = function_body(read(os.path.join(root, MAIN)), "CG_LoadMap") or read(os.path.join(root, MAIN))
    passive = draw[draw.find("if (!ETA_HudNarrator_PassiveHeld(cg.time))"):]
    for ok, what in (
            ("ETA_PropAt(trace->endpos)" in hit_text, "the look-ahead does not name the thing it ends on"),
            ("CG_AccessibilityLoadLadders();\n\tCG_AccessibilityLoadProps();" in load,
             "the things are not read while the map loads"),
            ("ETA_NarrateFurniture();" in passive[:passive.find("\n\t}") if passive else 0] or
             "ETA_NarrateFurniture();" in passive[:4000],
             "the things are not said with the scenery, behind an answer the player asked for"),
            ('{ &eta_furnitureCallouts,   "eta_furnitureCallouts",   "1" }' in read(os.path.join(root, MAIN)),
             "eta_furnitureCallouts is not registered"),
            ('"eta_furnitureCallouts"' in read(ENVIRONMENT), "the Environment page has no row for the furniture"),
            (re.search(r'^seta eta_furnitureCallouts\s+"1"', read(AUTOEXEC), re.M),
             "the shipped config does not set eta_furnitureCallouts")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "loads" in f or "scenery" in f or "registered" in f or "page" in f or "config" in f or "look-ahead" in f]:
        print("[furniture] read as the map loads, said with the scenery, on the Environment page")

    if failures:
        for failure in failures:
            print("[furniture] FAIL %s" % failure)
        if run.stdout:
            print(run.stdout)
        sys.exit(1)
    print("furniture_test: the things in a room are said as the player comes up to them")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check F never picks up a weapon lying in front of what was chosen.

The tester chose a mounted gun with the bracket keys, pressed F, and
picked up an enemy's weapon lying by it instead. The game's use key takes
the first thing its line from the eyes meets (Cmd_Activate_f traces
triggers, and an item is one), and using an item picks it up
(Do_Activate_f) - a weapon in place of the player's own. The cgame's
traces pass through items, so F could not see it was in the way.

ETA_UseLineBlocked is lifted out of the patched engine unchanged and run
on items laid out by hand: an item across the line short of the target
is found; one beside the line, behind the target, the target itself, or
hidden, is not. Then the game's own rules it rests on, and the wiring:
on arriving with something in the way, F aims a little higher to clear
it, and failing that says so rather than press use.

    ./use_line_test.py <engine-root>
"""

import os
import re
import subprocess
import sys
import tempfile

CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
G_CMDS = os.path.join("src", "game", "g_cmds.c")
G_ITEMS = os.path.join("src", "game", "g_items.c")
BG_PUBLIC = os.path.join("src", "game", "bg_public.h")

HARNESS = r'''
#include "q_shared.h"
#include "game/bg_public.h"
#include <stdio.h>
#include <math.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

typedef struct { entityState_t currentState; vec3_t lerpOrigin; } centity_t;
static centity_t cg_entities[64];
typedef struct { int numEntities; entityState_t entities[64]; } snapshot_t;
static snapshot_t snapshot;
static struct { snapshot_t *snap; } cg;

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

static void Item(int number, float x, float y, float z, int flags)
{
	entityState_t *es = &snapshot.entities[snapshot.numEntities++];

	memset(es, 0, sizeof(*es));
	es->number = number;
	es->eType  = ET_ITEM;
	es->eFlags = flags;
	VectorSet(cg_entities[number].lerpOrigin, x, y, z);
}

static void Case(const char *name, float tx, float ty, float tz, int target)
{
	vec3_t eye = { 0, 0, 64 }, end;

	VectorSet(end, tx, ty, tz);
	printf("%s %d\n", name, ETA_UseLineBlocked(eye, end, target));
}

int main(void)
{
	cg.snap = &snapshot;

	/* The gun 80 units ahead at waist height, a weapon on the floor half way. */
	Item(10, 40, 0, 20, 0);
	Case("ACROSS", 80, 0, 24, 30);
	Case("LIFTED", 80, 0, 48, 30);
	snapshot.numEntities = 0;

	Item(11, 40, 40, 0, 0);
	Case("BESIDE", 80, 0, 24, 30);
	snapshot.numEntities = 0;

	Item(12, 120, 0, 0, 0);
	Case("BEHIND", 80, 0, 24, 30);
	snapshot.numEntities = 0;

	Item(13, 80, 0, 16, 0);
	Case("ITSELF", 80, 0, 24, 13);
	snapshot.numEntities = 0;

	Item(14, 40, 0, 20, EF_NODRAW);
	Case("HIDDEN", 80, 0, 24, 30);

	/* A weapon on the floor chosen, an ammo pack lying just in front of
	   it: the middle of the weapon is covered, a part of it is not. */
	snapshot.numEntities = 0;
	Item(15, 62, 0, 0, 0);
	Item(16, 86, 0, 0, 0);
	{
		vec3_t eye = { 0, 0, 64 }, middle, at;
		int    k, clear = -1;

		VectorSet(middle, 86, 0, 8);
		printf("MIDDLE %d\n", ETA_UseLineBlocked(eye, middle, 16));
		for (k = 0; k < ETA_USE_ITEM_AIMS && clear < 0; k++)
		{
			VectorAdd(cg_entities[16].lerpOrigin, eta_useItemAims[k], at);
			if (ETA_UseLineBlocked(eye, at, 16) < 0)
			{
				clear = k;
			}
		}
		printf("PART %d\n", clear);
	}
	return 0;
}
'''


def read(root, relative):
    path = os.path.join(root, relative)
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


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    console = read(root, CONSOLE)
    failures = []

    begin = console.find("#define ETA_USE_LIFT_MAX")
    end = console.find("/* Where the use key's line ends now")
    if begin < 0 or end < begin:
        sys.exit("no check of the use key's line in %s - the feature this test measures is gone" % CONSOLE)

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "line.c")
        binary = os.path.join(tmp, "line")
        with open(source, "w") as handle:
            handle.write(HARNESS.replace("%(LIFTED)s", console[begin:end]))
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-I", os.path.join(root, "src", "qcommon"), "-I", os.path.join(root, "src"),
             "-o", binary, source, os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted use line check does not build:\n%s" % build.stderr[-3000:])
        out = dict(line.split() for line in
                   subprocess.run([binary], capture_output=True, text=True, timeout=60).stdout.splitlines())

    for name, want, good, bad in (
            ("ACROSS", "10", "a weapon on the floor across the line, short of the gun, is found",
             "a weapon across the line was not found"),
            ("LIFTED", "-1", "aimed a little higher, the line clears it",
             "aimed higher over it, the weapon was still in the way"),
            ("BESIDE", "-1", "one beside the line is not in the way", "a weapon beside the line was taken as in the way"),
            ("BEHIND", "-1", "nor one behind the gun", "a weapon behind the gun was taken as in the way"),
            ("ITSELF", "-1", "nor the thing chosen itself", "the chosen thing was taken as in its own way"),
            ("HIDDEN", "-1", "nor one the game is not showing", "a hidden item was taken as in the way"),
            ("MIDDLE", "15", "a weapon on the floor with a pack in front: its middle is covered",
             "a pack in front of a weapon on the floor was not found in the way")):
        if out.get(name) != want:
            failures.append("%s (got %s)" % (bad, out.get(name)))
        else:
            print("[use line] " + good)

    if out.get("PART", "-1") == "-1":
        failures.append("a weapon on the floor with a pack in front has no part F can aim at")
    else:
        print("[use line] and F aims at a part of it the pack does not cover (aim %s)" % out["PART"])

    # --- the game's own rules -----------------------------------------------
    cmds = strip_comments(read(root, G_CMDS))
    activate = function_body(cmds, "Cmd_Activate_f")
    do_activate = function_body(cmds, "Do_Activate_f")
    items = read(root, G_ITEMS)
    radius = re.search(r"#define\s+ITEM_RADIUS\s+(\d+)", read(root, BG_PUBLIC))
    if "CONTENTS_TRIGGER" not in activate or "VectorDistance(offset, tr.endpos) <= CH_ACTIVATE_DIST" not in activate:
        failures.append("the game's use no longer takes the first trigger along its line")
    elif not re.search(r"traceEnt->s\.eType == ET_ITEM\)\s*\{.*?traceEnt->touch\(traceEnt, ent, &trace\);", do_activate, re.S):
        failures.append("the game's use no longer picks up an item it meets")
    elif "VectorSet(dropped->r.mins, -ITEM_RADIUS, -ITEM_RADIUS, 0);" not in items \
            or "VectorSet(dropped->r.maxs, ITEM_RADIUS, ITEM_RADIUS, 2 * ITEM_RADIUS);" not in items or not radius:
        failures.append("a dropped weapon's box is no longer the one this test was built on")
    else:
        print("[use line] the game's use takes the first trigger on its line and picks up an item, "
              "whose box is %s units round" % radius.group(1))

    # --- the wiring ---------------------------------------------------------
    frame = strip_comments(function_body(console, "CG_AccessibilityAimFrame"))
    for ok, what in (
            ("blocker = ETA_UseLineBlocked(eye, end, body);" in frame and "ETA_UseLineEnd(eye, eta_aim.point, end);" in frame,
             "arriving at what was chosen, the line to it is not checked"),
            ("eta_aim.lift    = lift;" in frame and "ETA_UseLineBlocked(eye, higher, body) < 0" in frame,
             "with something in the way, F does not aim higher to clear it"),
            ("is in the way, and would be picked up" in frame,
             "with no way to clear it, F does not say what is in the way"),
            (frame.find("blocker = ETA_UseLineBlocked") < frame.find("ETA_UseKey(qtrue);"),
             "use is pressed before the line is checked")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "F " in f or "line to it" in f or "pressed" in f]:
        print("[use line] on arrival F checks the line, aims higher to clear it, or says what is in the way")

    if failures:
        for failure in failures:
            print("[use line] FAIL %s" % failure)
        sys.exit(1)
    print("use_line_test: F uses what was chosen, never a weapon lying in front of it")


if __name__ == "__main__":
    main()

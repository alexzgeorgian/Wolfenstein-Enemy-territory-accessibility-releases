#!/usr/bin/env python3
"""Check F keeps an objective on its list however crowded the spot.

F lists the sixteen nearest things to use. The tester found F miss the
construction they were sent to build in a spot littered with dropped
weapons and packs: every one of them was nearer, so the objective was
the one left off the list. ETA_AimInsert is lifted out of the patched
engine unchanged and fed by hand:

- sixteen nearer things, then an objective farther off: the objective is
  on the list, and the farthest of the others is not;
- more nearer things after it: the objective stays;
- a list of objectives only: a farther objective does not push off a
  nearer one;
- the list stays nearest first, and the two halves of one thing are one.

    ./use_list_full_test.py <engine-root>
"""

import os
import subprocess
import sys
import tempfile

DRAW = os.path.join("src", "cgame", "cg_draw.c")

HARNESS = r'''
#include "q_shared.h"
#include <stdio.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

typedef struct
{
	int      entityNum;
	vec3_t   point;
	float    meters;
	char     name[64];
	qboolean ladder, locked, stairs, objective;
	vec3_t   along;
	qboolean uniform;
} etaAimTarget_t;

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

static etaAimTarget_t list[16];
static int            count;

static void Add(const char *name, float meters, qboolean objective)
{
	etaAimTarget_t t;

	memset(&t, 0, sizeof(t));
	Q_strncpyz(t.name, name, sizeof(t.name));
	t.meters    = meters;
	t.point[0]  = meters * 1000.0f;
	t.objective = objective;
	ETA_AimInsert(list, &count, 16, &t);
}

static void Show(const char *label)
{
	int i;

	printf("%s", label);
	for (i = 0; i < count; i++)
	{
		printf(" %s@%.0f", list[i].name, list[i].meters);
	}
	printf("\n");
}

int main(void)
{
	int i;

	for (i = 0; i < 16; i++)
	{
		Add(va("pack%d", i), 1.0f + i * 0.5f, qfalse);
	}
	Add("bridge", 14.0f, qtrue);
	Show("CROWDED");
	for (i = 0; i < 5; i++)
	{
		Add(va("near%d", i), 0.5f + i * 0.1f, qfalse);
	}
	Show("MORE");

	count = 0;
	for (i = 0; i < 16; i++)
	{
		Add(va("obj%d", i), 1.0f + i, qtrue);
	}
	Add("farobj", 30.0f, qtrue);
	Add("nearobj", 0.2f, qtrue);
	Show("OBJECTIVES");

	count = 0;
	Add("door", 3.0f, qfalse);
	Add("door", 3.0f, qfalse);
	Show("SAME");
	return 0;
}
'''


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    path = os.path.join(root, DRAW)
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    draw = open(path, errors="replace").read()
    begin = draw.find("static void ETA_AimInsert(etaAimTarget_t *list")
    end = draw.find("/* Where to aim at a player", begin)
    if begin < 0 or end < 0 or "objective" not in draw[begin:end]:
        sys.exit("no objective-keeping list in %s - the feature this test measures is gone" % DRAW)

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "list.c")
        binary = os.path.join(tmp, "list")
        with open(source, "w") as handle:
            handle.write(HARNESS.replace("%(LIFTED)s", draw[begin:end]))
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-I", os.path.join(root, "src", "qcommon"), "-I", os.path.join(root, "src"),
             "-o", binary, source, os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted list does not build:\n%s" % build.stderr[-3000:])
        out = dict(line.split(" ", 1) for line in
                   subprocess.run([binary], capture_output=True, text=True, timeout=60).stdout.splitlines())

    failures = []

    def names(key):
        return [e.split("@")[0] for e in out.get(key, "").split()]

    def meters(key):
        return [float(e.split("@")[1]) for e in out.get(key, "").split()]

    crowded = names("CROWDED")
    if "bridge" not in crowded or "pack15" in crowded or len(crowded) != 16:
        failures.append("with sixteen nearer things, the objective was left off F's list: %s" % crowded)
    else:
        print("[list] with sixteen nearer things, the objective is on F's list and the farthest other is not")
    more = names("MORE")
    if "bridge" not in more or len(more) != 16:
        failures.append("more nearer things pushed the objective off: %s" % more)
    else:
        print("[list] more nearer things after it do not push the objective off")
    objs = names("OBJECTIVES")
    if "farobj" in objs or "nearobj" not in objs or "obj15" in objs:
        failures.append("among objectives only, the nearest were not kept: %s" % objs)
    else:
        print("[list] among objectives only, the nearest are kept")
    for key in ("CROWDED", "MORE", "OBJECTIVES"):
        if meters(key) != sorted(meters(key)):
            failures.append("%s: the list is not nearest first: %s" % (key, out.get(key)))
    if names("SAME") != ["door"]:
        failures.append("the two halves of one door are listed twice: %s" % names("SAME"))

    if failures:
        for failure in failures:
            print("[list] FAIL %s" % failure)
        sys.exit(1)
    print("use_list_full_test: F keeps the objective on its list however crowded the spot")


if __name__ == "__main__":
    main()

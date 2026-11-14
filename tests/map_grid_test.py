"""Check the map survey's squares are the engine's own squares.

Why this exists
---------------
The whole value of the survey speaking "C,3" is that it is the same C,3
a sighted teammate reads off their screen and types into team chat. A
blind player calling out a square has to be describing the map everyone
else is looking at, or they are worse off than saying nothing - fluent,
confident, and pointing at a place that does not exist.

So the grid may not be the mod's own. It is read out of the engine
through BG_GetLocationGrid, and this fails if that ever turns back into
a second copy of the density arithmetic - which would agree on the day
it was written and drift the first time the engine's rule changed.

The dangerous half is the rows, and it is dangerous in a way that is
invisible from the code. ET derives a row as (gridStart - y), not
(y - gridStart), because its y axis runs the opposite way from its x
axis: cg.mapcoordsMins[1] is the *north* edge. Written the natural way
round it compiles, runs, and mirrors the entire battlefield north for
south. This project has shipped exactly that shape of defect once
already - bearings reversed left for right, in both integrations - and
nothing but a test like this one caught it.

So rather than read the mod's expression and hope, this compiles it.
The mod's cell lookup and the engine's own BG_GetLocationString are
lifted out of the tree, built into one harness against a shared grid,
and asked about a few thousand positions across the map. Every one has
to land in the same square by both routes. A test carrying its own copy
of the formula would pass happily while the shipped one is backwards,
which is the failure being guarded against.

What it does NOT check
----------------------
Whether the squares are a useful size to survey, or whether the reading
order for "next thing on the map" is the one a player expects. Those
need ears.

Usage
-----
    ./map_grid_test.py <engine-root>

ET: Legacy only - the 2010 tree has no location grid.
Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
MISC = os.path.join("src", "game", "bg_misc.c")
PUBLIC = os.path.join("src", "game", "bg_public.h")


def read(root, relative, what):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - %s" % (relative, root, what))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    out, i, n = [], 0, len(text)
    while i < n:
        two = text[i:i + 2]
        if two == "/*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif two == "//":
            end = text.find("\n", i)
            i = n if end < 0 else end
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def body_of(text, signature, where):
    start = text.find(signature)
    if start < 0:
        sys.exit("could not find %s in %s - the survey this test guards is "
                 "gone, and passing without it would mean nothing"
                 % (signature.split("(")[0], where))
    brace = text.find("{", start)
    depth, i, n = 0, brace, len(text)
    while i < n:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1:i]
        i += 1
    sys.exit("could not find the end of %s in %s" % (signature, where))


HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

typedef float vec2_t[2];
typedef int qboolean;
#define qtrue 1
#define qfalse 0

/* The grid, shared by both routes. Values from a real stock map's
   bounds, run through the engine's own density rule. */
static struct { vec2_t gridStartCoord; vec2_t gridStep; } locInfo;

static struct { vec2_t mapcoordsMins; vec2_t mapcoordsMaxs; } cg;

static char coord[8];

/* The engine's own wrapper, so its expression is lifted unaltered. */
static void Com_sprintf(char *dest, int size, const char *fmt, ...)
{
    va_list argptr;

    va_start(argptr, fmt);
    vsnprintf(dest, (size_t)size, fmt, argptr);
    va_end(argptr);
}

/* ---- the engine's own, lifted from bg_misc.c ---- */
char *BG_GetLocationString(float xpos, float ypos)
{
@@ENGINE@@
}

void BG_GetLocationGrid(vec2_t gridStartCoord, vec2_t gridStep)
{
    gridStartCoord[0] = locInfo.gridStartCoord[0];
    gridStartCoord[1] = locInfo.gridStartCoord[1];
    gridStep[0]       = locInfo.gridStep[0];
    gridStep[1]       = locInfo.gridStep[1];
}

/* ---- the mod's, lifted from cg_commandmap.c ---- */
static qboolean ETA_MapGrid(vec2_t start, vec2_t step, int *columns, int *rows)
{
@@GRID@@
}

static void ETA_MapCellFor(float x, float y, int *column, int *row)
{
@@CELL@@
}

int main(void)
{
    float x, y;
    int   mismatches = 0, checked = 0, clamped = 0;
    vec2_t start, step;
    int    columns, rows;

    /* Braundorf-sized bounds, and the engine's own density rule. */
    cg.mapcoordsMins[0] = -12000.0f;  cg.mapcoordsMaxs[0] =  8000.0f;
    cg.mapcoordsMins[1] =  10000.0f;  cg.mapcoordsMaxs[1] = -9000.0f;

    locInfo.gridStep[0] = 1200.0f;
    locInfo.gridStep[1] = 1200.0f;
    while ((cg.mapcoordsMaxs[0] - cg.mapcoordsMins[0]) / locInfo.gridStep[0] < 7)
        locInfo.gridStep[0] -= 50.0f;
    while ((cg.mapcoordsMins[1] - cg.mapcoordsMaxs[1]) / locInfo.gridStep[1] < 7)
        locInfo.gridStep[1] -= 50.0f;
    locInfo.gridStartCoord[0] = cg.mapcoordsMins[0] + .5f *
        ((((cg.mapcoordsMaxs[0] - cg.mapcoordsMins[0]) / locInfo.gridStep[0]) -
          ((int)((cg.mapcoordsMaxs[0] - cg.mapcoordsMins[0]) / locInfo.gridStep[0]))) * locInfo.gridStep[0]);
    locInfo.gridStartCoord[1] = cg.mapcoordsMins[1] - .5f *
        ((((cg.mapcoordsMins[1] - cg.mapcoordsMaxs[1]) / locInfo.gridStep[1]) -
          ((int)((cg.mapcoordsMins[1] - cg.mapcoordsMaxs[1]) / locInfo.gridStep[1]))) * locInfo.gridStep[1]);

    if (!ETA_MapGrid(start, step, &columns, &rows))
    {
        printf("FAIL the mod could not read the engine's grid at all\n");
        return 1;
    }

    printf("grid %d columns x %d rows, step %.0f x %.0f\n",
           columns, rows, step[0], step[1]);

    if (columns < 7 || rows < 7)
    {
        printf("FAIL the engine guarantees at least 7 divisions each way, "
               "the mod counted %dx%d\n", columns, rows);
        return 1;
    }

    /* Deliberately starting a full square OUTSIDE the west and north
       edges. Inside the map the partial square before the first grid
       line is never wider than half a step, so truncation toward zero
       swallows it and the negative clamp is never reached - a sweep of
       in-bounds positions alone passes with the clamp deleted. But this
       is also asked about entity positions, and a mine on a ledge or a
       body past the edge really can sit outside the bounds. Without the
       clamp that becomes column -1, and the survey announces square
       "@,3". */
    for (y = cg.mapcoordsMaxs[1]; y <= cg.mapcoordsMins[1] + step[1]; y += 97.0f)
    {
        for (x = cg.mapcoordsMins[0] - step[0]; x <= cg.mapcoordsMaxs[0]; x += 97.0f)
        {
            char expected[8];
            char actual[8];
            int  column, row;

            snprintf(expected, sizeof(expected), "%s", BG_GetLocationString(x, y));

            ETA_MapCellFor(x, y, &column, &row);
            snprintf(actual, sizeof(actual), "%c,%d", 'A' + column, row);

            checked++;

            /* The mod clamps to the grid it counted; the engine clamps
               only negatives. Where the engine runs past the last
               square the two legitimately differ, and the mod is the
               one being conservative. Counted, not ignored. */
            if (column == columns - 1 || row == rows - 1)
            {
                clamped++;
                continue;
            }

            /* A square name is only speakable if it is a letter. */
            if (column < 0 || row < 0)
            {
                printf("FAIL at %.0f,%.0f: the mod produced column %d row %d, "
                       "which is spoken as a square that does not exist\n",
                       x, y, column, row);
                mismatches++;
                continue;
            }

            if (strcmp(expected, actual) != 0)
            {
                if (mismatches < 8)
                {
                    printf("FAIL at %.0f,%.0f: engine says %s, mod says %s\n",
                           x, y, expected, actual);
                }
                mismatches++;
            }
        }
    }

    printf("%d position(s) checked, %d in the clamped outer squares\n",
           checked, clamped);

    if (mismatches)
    {
        printf("FAIL %d position(s) land in a different square\n", mismatches);
        return 1;
    }

    if (checked - clamped < 1000)
    {
        printf("FAIL only %d position(s) were actually compared - this test "
               "would pass by checking almost nothing\n", checked - clamped);
        return 1;
    }

    printf("ok\n");
    return 0;
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy", choices=("etlegacy",),
                        help="ET: Legacy only; the 2010 tree has no grid")
    args = parser.parse_args()

    commandmap = strip_comments(read(args.root, COMMANDMAP,
                                     "is the patch series applied?"))
    misc = strip_comments(read(args.root, MISC, "is this an engine checkout?"))
    public = read(args.root, PUBLIC, "is this an engine checkout?")

    failures = []

    # --- the grid must be the engine's, not a second copy ------------
    grid_body = body_of(commandmap, "static qboolean ETA_MapGrid(", COMMANDMAP)

    if "BG_GetLocationGrid" not in grid_body:
        failures.append(
            "ETA_MapGrid does not read the engine's grid through "
            "BG_GetLocationGrid. Whatever it is using instead is a second "
            "copy of the density rule, which agrees today and drifts the "
            "day the engine changes it - at which point the survey names "
            "squares no teammate can find")

    if re.search(r'\b1200\b', grid_body) or re.search(r'\b50\b', grid_body):
        failures.append(
            "ETA_MapGrid carries the engine's grid constants (1200 / 50) "
            "itself, which is the second copy this is meant to prevent")

    if "BG_GetLocationGrid" not in public:
        failures.append(
            "BG_GetLocationGrid is not declared in %s, so the accessor the "
            "mod relies on is not part of the engine's interface" % PUBLIC)

    if not re.search(r'BG_GetLocationGrid\s*\(', misc):
        failures.append("BG_GetLocationGrid is gone from %s" % MISC)

    # --- the engine's own formula must still be what we compare to ---
    if "char *BG_GetLocationString" not in misc:
        failures.append(
            "BG_GetLocationString is gone from %s - this test reads the "
            "mod against it and can no longer tell whether the squares "
            "agree" % MISC)

    if failures:
        print("map_grid_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    # --- and now the behaviour, compiled ------------------------------
    engine_body = body_of(misc, "char *BG_GetLocationString(", MISC)
    cell_body = body_of(commandmap, "static void ETA_MapCellFor(", COMMANDMAP)

    source = (HARNESS
              .replace("@@ENGINE@@", engine_body)
              .replace("@@GRID@@", grid_body)
              .replace("@@CELL@@", cell_body))

    with tempfile.TemporaryDirectory() as workdir:
        path = os.path.join(workdir, "map_grid.c")
        binary = os.path.join(workdir, "map_grid")

        with open(path, "w") as handle:
            handle.write(source)

        compiled = subprocess.run(
            ["cc", "-std=c99", "-Wall", "-o", binary, path, "-lm"],
            capture_output=True, text=True)

        if compiled.returncode != 0:
            print("map_grid_test: FAIL (%s) - the lifted expressions do not "
                  "compile" % args.engine)
            print(compiled.stderr.strip()[:2000])
            return 1

        result = subprocess.run([binary], capture_output=True, text=True)

    for line in result.stdout.strip().splitlines():
        print("  %s" % line)

    if result.returncode != 0:
        print("map_grid_test: FAIL (%s) - the survey's squares are not the "
              "engine's squares" % args.engine)
        return 1

    print("map_grid_test: %s - the survey reads the engine's own grid and "
          "lands in the same square as BG_GetLocationString everywhere it "
          "was asked" % args.engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())

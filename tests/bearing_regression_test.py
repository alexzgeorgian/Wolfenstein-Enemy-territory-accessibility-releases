#!/usr/bin/env python3
"""Check that the navigation bearings point where they claim to.

Why this exists
---------------
Both engine integrations once told the player to turn *left* when the
objective was on their right, and both shipped a directional audio cue
mirrored end for end. Neither defect was catchable by anything else in
this repository: the code compiled without a warning, linked, and passed
every smoke test, because the bug was in the *meaning* of a number that
was otherwise perfectly well-formed. It is only wrong to the person
relying on it.

So this test compiles the real bearing expressions - lifted out of the
patched engine tree, not copied into this file - against that engine's
own q_math.c, puts a target at a known position, and checks which way
the player is told to go.

Reading the expressions out of the engine source is the point. A test
carrying its own copy of the formula passes happily while the shipped
formula is backwards, which is exactly the failure being guarded
against.

The convention under test is the engine's own, not an invention of this
project: ET: Legacy's damage indicator in cg_draw.c brackets
cg.v_dmg_angle as `>= 60 && < 120` for "right" and `>= 240 && < 300` for
"left", in its own comments. So 0 = ahead, 90 = right, 180 = behind,
270 = left.

In id Tech 3, +X is forward and +Y is left, and yaw increases
counter-clockwise - so a target on the player's right sits at a *lower*
yaw than the view. That is the trap: `targetYaw - viewYaw` reads like
the natural way round and is mirrored.

Usage
-----
    ./bearing_regression_test.py <engine-root> --engine etlegacy|id-software

Run it against a tree with the integration's patch series already
applied. It exits non-zero on any mismatch.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

ENGINES = {
    "etlegacy": {
        "math": os.path.join("src", "qcommon", "q_math.c"),
        "includes": [os.path.join("src", "qcommon"), "src"],
        "std": "gnu99",
        "scan": [os.path.join("src", "cgame"), os.path.join("src", "ui")],
    },
    "id-software": {
        "math": os.path.join("src", "game", "q_math.c"),
        "includes": [os.path.join("src", "game")],
        "std": "gnu90",
        "scan": [os.path.join("src", "cgame"), os.path.join("src", "ui")],
    },
}

CUE_CALL = "ETA_AudioCueSystem_PlayObjectiveDirectionCue"
ROUTE_CALL = "ETA_NavigationSystem_AnnounceRouteCorrection"


class ExtractionError(Exception):
    """The source no longer has the shape this test knows how to read.

    Raised rather than skipped on purpose: silently testing nothing is
    how the mirrored bearings survived review in the first place.
    """


def source_files(root, engine):
    found = []
    for rel in ENGINES[engine]["scan"]:
        directory = os.path.join(root, rel)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith(".c"):
                found.append(os.path.join(directory, name))
    return found


def balanced_argument(text, open_index):
    """Return the text between the parens starting at open_index."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i]
    raise ExtractionError("unbalanced parentheses after column %d" % open_index)


def normalize(expression):
    return " ".join(expression.split())


def extract_cue_expressions(text):
    """Every argument passed to the objective-direction cue."""
    results = []
    for match in re.finditer(re.escape(CUE_CALL) + r"\s*\(", text):
        open_index = match.end() - 1
        results.append(normalize(balanced_argument(text, open_index)))
    return results


# The cue backend turns a bearing back into a world position for the engine
# to spatialise. That inverse is the same trap as the forward direction and
# lives in a different file, so it is lifted and checked too: a mirrored
# placement would put every directional cue on the wrong side while every
# other check here stayed green.
CUE_YAW = re.compile(r"angles\[YAW\]\s*=\s*(?P<rhs>[^;]+);")


def extract_cue_placements(text):
    if "ETA_AudioCueSystem_SetBackend" not in text:
        return []
    return [normalize(m.group("rhs")) for m in CUE_YAW.finditer(text)]


BRANCH = re.compile(
    r"(?P<kind>else\s+if|if|else)\s*(?:\(\s*(?P<cond>.*?)\s*\)\s*)?\{?\s*"
    + re.escape(ROUTE_CALL)
    + r"\s*\(\s*\"(?P<text>[^\"]*)\"\s*\)\s*;",
    re.S,
)


def extract_route_chains(text):
    """Each `relativeYaw = ...` and the if/else chain that reads it."""
    chains = []
    for match in re.finditer(r"relativeYaw\s*=\s*(?P<rhs>[^;]+);", text):
        rhs = normalize(match.group("rhs"))
        block = text[match.end():match.end() + 1200]

        branches = []
        fallback = None
        for branch in BRANCH.finditer(block):
            kind = " ".join(branch.group("kind").split())
            if kind == "else":
                fallback = branch.group("text")
                break
            branches.append((normalize(branch.group("cond")), branch.group("text")))

        if not branches or fallback is None:
            raise ExtractionError(
                "found `relativeYaw = %s` but not the if/else chain that reads it" % rhs
            )
        chains.append((rhs, branches, fallback))
    return chains


# The players-near-you callouts measure a thing's angle from the view,
# positive to the left, and say "left" for positive. The library's words
# for a sign are checked in its own smoke test; the sign itself comes
# from here, so it is lifted and checked like the rest.
LEFT_OF_VIEW = re.compile(r"\bleftOfView\s*=\s*(?P<rhs>[^;]+);")


def extract_left_of_view(text):
    return [normalize(m.group("rhs")) for m in LEFT_OF_VIEW.finditer(text)]


SETUP = """
    eta_test_ps_t storage;
    eta_test_ps_t *ps = &storage;
    vec3_t delta, angles;
    float relativeYaw;

    (void)relativeYaw;
    storage.viewangles[PITCH] = 0.0f;
    storage.viewangles[YAW]   = viewYaw;
    storage.viewangles[ROLL]  = 0.0f;

    VectorSubtract(target, origin, delta);
    vectoangles(delta, angles);
"""


def generate_harness(cues, chains, placements, lefts=()):
    out = []
    out.append("#include <math.h>")
    out.append("#include <stdio.h>")
    out.append("#include <string.h>")
    out.append('#include "q_shared.h"')
    out.append("")
    out.append("/* Just enough of playerState_t for the lifted expressions to")
    out.append("   compile verbatim: they read ps->viewangles[YAW]. */")
    out.append("typedef struct { vec3_t viewangles; vec3_t origin; } eta_test_ps_t;")
    out.append("typedef struct { eta_test_ps_t ps; } eta_test_snap_t;")
    out.append("typedef struct { eta_test_snap_t *snap; } eta_test_cg_t;")
    out.append("static eta_test_snap_t eta_test_snap;")
    out.append("static eta_test_cg_t cg;")
    out.append("")

    for index, expression in enumerate(cues):
        out.append("static int Cue_%d(const vec3_t target, const vec3_t origin, float viewYaw)" % index)
        out.append("{")
        out.append(SETUP.rstrip())
        out.append("")
        out.append("    return %s;" % expression)
        out.append("}")
        out.append("")

    for index, (rhs, branches, fallback) in enumerate(chains):
        out.append("static const char *Turn_%d(const vec3_t target, const vec3_t origin, float viewYaw)" % index)
        out.append("{")
        out.append(SETUP.rstrip())
        out.append("")
        out.append("    relativeYaw = %s;" % rhs)
        out.append("")
        first = True
        for condition, text in branches:
            keyword = "if" if first else "else if"
            out.append('    %s (%s) { return "%s"; }' % (keyword, condition, text))
            first = False
        out.append('    return "%s";' % fallback)
        out.append("}")
        out.append("")

    for index, expression in enumerate(placements):
        out.append("/* Lifted from the cue backend: a view-relative bearing back to a")
        out.append("   world yaw. Checked by which side of the listener the resulting")
        out.append("   sound lands on, the way the engine renders it - judging the raw")
        out.append("   world position instead makes a correct backend look broken. */")
        out.append("static const char *Placement_%d(float viewYaw, int directionDegrees)" % index)
        out.append("{")
        out.append("    vec3_t angles, forward, position, delta, back;")
        out.append("    float bearing;")
        out.append("")
        out.append("    eta_test_snap.ps.viewangles[PITCH] = 0.0f;")
        out.append("    eta_test_snap.ps.viewangles[YAW]   = viewYaw;")
        out.append("    eta_test_snap.ps.viewangles[ROLL]  = 0.0f;")
        out.append("    VectorClear(eta_test_snap.ps.origin);")
        out.append("    cg.snap = &eta_test_snap;")
        out.append("")
        out.append("    VectorClear(angles);")
        out.append("    angles[YAW] = " + expression + ";")
        out.append("    AngleVectors(angles, forward, NULL, NULL);")
        out.append("    VectorMA(eta_test_snap.ps.origin, 128.0f, forward, position);")
        out.append("")
        out.append("    VectorSubtract(position, eta_test_snap.ps.origin, delta);")
        out.append("    vectoangles(delta, back);")
        out.append("    bearing = AngleNormalize360(viewYaw - back[YAW]);")
        out.append("")
        out.append("    if (bearing < 45.0f || bearing >= 315.0f) { return \"ahead\"; }")
        out.append("    if (bearing < 135.0f) { return \"right\"; }")
        out.append("    if (bearing < 225.0f) { return \"behind\"; }")
        out.append("    return \"left\";")
        out.append("}")
        out.append("")

    for index, expression in enumerate(lefts):
        out.append("static float Left_%d(const vec3_t target, const vec3_t origin, float viewYaw)" % index)
        out.append("{")
        out.append(SETUP.rstrip())
        out.append("")
        out.append("    return %s;" % expression)
        out.append("}")
        out.append("")

    out.append("int main(void)")
    out.append("{")
    out.append("    static const vec3_t origin = { 0.0f, 0.0f, 0.0f };")
    out.append("    vec3_t target;")
    out.append("    int i;")
    out.append("    int failures = 0;")
    out.append("")
    out.append("    struct { float x; float y; float viewYaw; int bearing; const char *turn; const char *side; const char *label; } cases[] = {")
    out.append('        {  100.0f,    0.0f,   0.0f,   0, "ahead", "ahead", "target straight ahead" },')
    out.append('        {    0.0f, -100.0f,   0.0f,  90, "right", "right", "target on the right" },')
    out.append('        { -100.0f,    0.0f,   0.0f, 180, NULL,    "behind", "target directly behind" },')
    out.append('        {    0.0f,  100.0f,   0.0f, 270, "left",  "left", "target on the left" },')
    out.append('        {  100.0f,    0.0f,  90.0f,  90, "right", "right", "ahead, but facing 90 degrees left" },')
    out.append('        {  100.0f,    0.0f, 270.0f, 270, "left",  "left", "ahead, but facing 90 degrees right" },')
    out.append('        {  100.0f,  -10.0f,   0.0f,   5, "ahead", "ahead", "just off-centre, inside the ahead band" },')
    out.append("    };")
    out.append("")
    out.append("    for (i = 0; i < (int)(sizeof(cases) / sizeof(cases[0])); i++) {")
    out.append("        target[0] = cases[i].x;")
    out.append("        target[1] = cases[i].y;")
    out.append("        target[2] = 0.0f;")
    out.append("")

    for index in range(len(cues)):
        out.append("        {")
        out.append("            int bearing = Cue_%d(target, origin, cases[i].viewYaw);" % index)
        out.append("            if (bearing != cases[i].bearing) {")
        out.append('                printf("FAIL cue #%d: %s - bearing %d, expected %d\\n",')
        out.append("                       %d, cases[i].label, bearing, cases[i].bearing);" % index)
        out.append("                failures++;")
        out.append("            }")
        out.append("        }")

    for index in range(len(placements)):
        out.append("        {")
        out.append("            const char *side = Placement_%d(cases[i].viewYaw, cases[i].bearing);" % index)
        out.append("            if (strcmp(side, cases[i].side) != 0) {")
        out.append('                printf("FAIL placement #%d: %s - cue placed %s, expected %s\\n",')
        out.append("                       %d, cases[i].label, side, cases[i].side);" % index)
        out.append("                failures++;")
        out.append("            }")
        out.append("        }")

    for index in range(len(lefts)):
        out.append("        {")
        out.append("            float left = Left_%d(target, origin, cases[i].viewYaw);" % index)
        out.append("            float expected = (float)(-cases[i].bearing);")
        out.append("            float off;")
        out.append("            if (expected <= -180.0f) { expected += 360.0f; }")
        out.append("            off = (float)fabs(AngleNormalize180(left - expected));")
        out.append("            if (off > 1.0f) {")
        out.append('                printf("FAIL left-of-view #%d: %s - %.1f degrees, expected %.1f (positive is left)\\n",')
        out.append("                       %d, cases[i].label, left, expected);" % index)
        out.append("                failures++;")
        out.append("            }")
        out.append("        }")

    for index in range(len(chains)):
        out.append("        if (cases[i].turn != NULL) {")
        out.append("            const char *turn = Turn_%d(target, origin, cases[i].viewYaw);" % index)
        out.append("            if (strstr(turn, cases[i].turn) == NULL) {")
        out.append('                printf("FAIL route #%d: %s - said \\"%s\\", expected it to mention \\"%s\\"\\n",')
        out.append("                       %d, cases[i].label, turn, cases[i].turn);" % index)
        out.append("                failures++;")
        out.append("            }")
        out.append("        }")

    out.append("    }")
    out.append("")
    out.append("    if (failures != 0) {")
    out.append('        printf("[bearing] %d check(s) FAILED\\n", failures);')
    out.append("        return 1;")
    out.append("    }")
    out.append('    printf("[bearing] all checks passed\\n");')
    out.append("    return 0;")
    out.append("}")
    out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout with the patch series applied")
    parser.add_argument("--engine", required=True, choices=sorted(ENGINES))
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--keep", action="store_true", help="print the generated harness")
    args = parser.parse_args()

    config = ENGINES[args.engine]
    root = os.path.abspath(args.root)

    math_source = os.path.join(root, config["math"])
    if not os.path.isfile(math_source):
        sys.exit("no %s under %s - is this an %s checkout?" % (config["math"], root, args.engine))

    cues = []
    chains = []
    placements = []
    lefts = []
    for path in source_files(root, args.engine):
        with open(path, "r", errors="replace") as handle:
            text = handle.read()
        if CUE_CALL in text:
            cues.extend(extract_cue_expressions(text))
        if "relativeYaw" in text:
            chains.extend(extract_route_chains(text))
        placements.extend(extract_cue_placements(text))
        lefts.extend(extract_left_of_view(text))

    # Finding nothing means the patches are not applied, or the wiring
    # moved and this extractor no longer reads it. Either way the test
    # has stopped testing, which must be loud, not green.
    if not cues:
        sys.exit("found no %s call under %s - apply the patch series first" % (CUE_CALL, root))
    if not chains:
        sys.exit("found no route-correction chain under %s - apply the patch series first" % root)

    if args.engine == "etlegacy" and not lefts:
        sys.exit("found no leftOfView measurement under %s - the players-near-you "
                 "callouts moved, and their sign is no longer checked" % root)

    print("[bearing] %s: %d cue expression(s), %d route chain(s), %d cue placement(s), "
          "%d left-of-view measurement(s)"
          % (args.engine, len(cues), len(chains), len(placements), len(lefts)))
    for expression in cues:
        print("[bearing]   cue:   %s" % expression)
    for rhs, _, _ in chains:
        print("[bearing]   route: relativeYaw = %s" % rhs)
    for expression in placements:
        print("[bearing]   place: angles[YAW] = %s" % expression)
    for expression in lefts:
        print("[bearing]   left:  leftOfView = %s" % expression)

    harness = generate_harness(cues, chains, placements, lefts)
    if args.keep:
        print(harness)

    workdir = tempfile.mkdtemp(prefix="bearing-")
    source = os.path.join(workdir, "bearing_harness.c")
    binary = os.path.join(workdir, "bearing_harness")
    with open(source, "w") as handle:
        handle.write(harness)

    command = [args.cc, "-std=%s" % config["std"], "-w", "-o", binary, source, math_source]
    for include in config["includes"]:
        command.append("-I" + os.path.join(root, include))
    command.append("-lm")

    compile_result = subprocess.run(command, capture_output=True, text=True)
    if compile_result.returncode != 0:
        sys.stderr.write(compile_result.stdout + compile_result.stderr)
        sys.exit("could not compile the lifted expressions")

    run_result = subprocess.run([binary], capture_output=True, text=True)
    sys.stdout.write(run_result.stdout)
    sys.stderr.write(run_result.stderr)
    return run_result.returncode


if __name__ == "__main__":
    sys.exit(main())

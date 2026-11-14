#!/usr/bin/env python3
"""Check objective text is spoken as sentences, not with its stars.

Why this exists
---------------
ET's objective and map descriptions break their lines with '*': the
panel draws each piece on a line of its own. Passed to a screen reader
as it is, each break is read out as "star", which a tester heard on the
objectives key. The mod turns each break into the end of a sentence.

The cleanup is lifted out of the patched engine, compiled against the
engine's own headers, and given real-looking descriptions. Then the two
places that speak objective text are checked to go through it - the
running order ("Objective 2 of 4, ...") and the map's description.

Usage
-----
    ./objective_text_test.py <engine-root>

Run it against an ET: Legacy checkout with the patch series applied.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")

CASES = (
    ("Destroy the Old City Wall*Build the Pump",
     "Destroy the Old City Wall. Build the Pump"),
    ("*Allied Objectives:**Capture the gold*",
     "Allied Objectives: Capture the gold"),
    ("Escort the tank.*  Destroy   the bridge",
     "Escort the tank. Destroy the bridge"),
    ("Line one\nLine two", "Line one. Line two"),
    ("No breaks at all", "No breaks at all"),
    ("***", ""),
    ("", ""),
)


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function(text, signature, where):
    found = re.search(signature, text)
    if not found:
        sys.exit("could not find %s in %s - the feature this test guards is "
                 "gone" % (signature, where))
    depth, i = 0, text.index("{", found.end() - 1)
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[found.start():i + 1]
        i += 1
    sys.exit("could not find the end of %s" % signature)


def c_string(value):
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    commandmap = read(root, COMMANDMAP)
    console = read(root, CONSOLE)
    failures = []

    cleaner = function(commandmap,
                       r"void CG_AccessibilitySpeakableText\s*\([^)]*\)\s*\{",
                       COMMANDMAP)

    harness = ['#include "q_shared.h"', '#include <stdio.h>', '#include <stdlib.h>',
               "void QDECL Com_Error(int code, const char *fmt, ...) { exit(2); }",
               "void QDECL Com_Printf(const char *fmt, ...) { }",
               cleaner, "int main(void)", "{", "    char out[128];",
               "    char tiny[8];", "    int failures = 0;"]
    for given, expected in CASES:
        harness.append(
            '    CG_AccessibilitySpeakableText(%s, out, sizeof(out));'
            ' if (strcmp(out, %s) != 0) { printf("FAIL %%s -> \\"%%s\\"\\n", %s, out); failures++; }'
            % (c_string(given), c_string(expected), c_string(given)))
    # A buffer too small for the text is filled and ended, not overrun.
    harness.append(
        '    CG_AccessibilitySpeakableText("Destroy*the*wall*now", tiny, sizeof(tiny));'
        ' if (strlen(tiny) >= sizeof(tiny)) { printf("FAIL overran a small buffer\\n"); failures++; }')
    harness += ["    return failures ? 1 : 0;", "}"]

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "text.c")
        binary = os.path.join(tmp, "text")
        with open(source, "w") as handle:
            handle.write("\n".join(harness) + "\n")
        build = subprocess.run(
            ["cc", "-std=gnu99", "-w", "-fsanitize=address,undefined",
             "-I", os.path.join(root, "src", "qcommon"),
             "-I", os.path.join(root, "src"), "-o", binary, source,
             os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted cleanup does not compile against the "
                     "engine:\n%s" % build.stderr[-2000:])
        run = subprocess.run([binary], capture_output=True, text=True)
        if run.returncode != 0:
            failures.append("objective text is not turned into sentences:\n  %s"
                            % (run.stdout + run.stderr).strip().replace("\n", "\n  "))
        else:
            print("[objectives] %d descriptions come out as sentences, "
                  "without their stars" % len(CASES))

    # --- both places that speak objective text use it -----------------
    describe = function(commandmap,
                        r"const char \*CG_AccessibilityObjectiveDescription\s*\([^)]*\)\s*\{",
                        COMMANDMAP)
    if "CG_AccessibilitySpeakableText" not in describe:
        failures.append(
            "CG_AccessibilityObjectiveDescription hands out the raw text, so "
            "\"Objective 2 of 4\" and the finished-objective callout read "
            "the stars out")
    narrate = function(console,
                       r"static void CG_AccessibilityNarrateObjectiveText\s*\([^)]*\)\s*\{",
                       CONSOLE)
    if "CG_AccessibilitySpeakableText" not in narrate:
        failures.append(
            "the objectives key reads the map description without the "
            "cleanup")
    if not failures:
        print("[objectives] the running order and the map description both "
              "go through it")

    if failures:
        print()
        for failure in failures:
            print("[objectives] FAIL %s" % failure)
        return 1

    print("objective_text_test: objective text is spoken as sentences")
    return 0


if __name__ == "__main__":
    sys.exit(main())

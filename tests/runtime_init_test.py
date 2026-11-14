#!/usr/bin/env python3
"""Check the engine actually brings the accessibility runtime up.

Why this exists
---------------
This is the one defect class that has shipped from this repository, and
it shipped twice.

ET: Legacy's patch series narrated for thirteen patches without calling
any `_Init`. So did the id Software series, independently, for fourteen.
Both speech backends check a handle their Init creates - the NVDA
controller client's speakText entry point, and the SAPI voice - and
return immediately while it is NULL. Every narration call in both trees
was reaching a backend that discarded it in silence. alpha-0.1.0 was
released that way and could not speak at all.

Nothing caught it. The code compiled, linked, passed every smoke test
and read correctly to review, because a call to a function that does
nothing is indistinguishable from a call to a function that works until
someone listens.

What is checked
---------------
For each engine module that uses the library, every library subsystem it
calls into must have its Init reached - directly, or through another
Init that module calls. The init graph is read out of the library's own
sources rather than listed here, so a new subsystem, or one Init
starting to call another, is picked up without editing this file.

Shutdown is checked the same way. A missing one leaks the SAPI voice and
the NVDA DLL handle across a map change.

What is NOT checked
-------------------
That a narration call reaches a real backend at runtime. Both backends
are Windows-only and compile to stubs on the platform CI runs on, so
there is nothing to observe here; the library's own lifecycle is covered
by tests/speech_smoke_test.c. This test covers the wiring between the
engine and the library, which is precisely where both failures were.

Usage
-----
    ./runtime_init_test.py <engine-root> [--library <path>]

Run it against a tree with a patch series applied.
"""

import argparse
import os
import re
import sys

MODULES = (
    ("cgame", os.path.join("src", "cgame")),
    ("ui", os.path.join("src", "ui")),
)

CALL = re.compile(r'\b(ETA_[A-Za-z0-9_]+)\s*\(')
DECL = re.compile(r'\b(ETA_[A-Za-z0-9_]+)\s*\(')
INIT_DEF = re.compile(r'^\s*void\s+(ETA_[A-Za-z0-9_]+_(?:Init|Shutdown))\s*\(\s*void\s*\)')

# A definition at the start of a line, which is how this codebase writes
# them: `void ETA_Speech_Say(const char *message)`.
DEFINITION = re.compile(r'^[A-Za-z_][A-Za-z0-9_ *]*\s\*?(ETA_[A-Za-z0-9_]+)\s*\(', re.MULTILINE)


def sources(root, extensions=(".c", ".h")):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            if name.endswith(extensions):
                yield os.path.join(base, name)


def library_api(library_root):
    """Every ETA_ name the library's headers declare.

    Anything else beginning with ETA_ in an engine tree is a helper the
    patches define for themselves, and is not this test's business.
    """
    names = set()
    for path in sources(library_root, (".h",)):
        with open(path, "r", errors="replace") as handle:
            names.update(DECL.findall(handle.read()))
    return names


def lifecycle_graph(library_root):
    """Which Init/Shutdown functions call which others.

    Read from the library source: ETA_AccessibilityRuntime_Init calls
    ETA_Speech_Init, so an engine module that calls the former has the
    latter covered without naming it.
    """
    graph = {}
    for path in sources(library_root, (".c",)):
        with open(path, "r", errors="replace") as handle:
            lines = handle.read().splitlines()

        current = None
        for line in lines:
            match = INIT_DEF.match(line)
            if match:
                current = match.group(1)
                graph.setdefault(current, set())
                continue
            if current is None:
                continue
            if line.startswith("}"):
                current = None
                continue
            for callee in CALL.findall(line):
                if callee != current and callee.endswith(("_Init", "_Shutdown")):
                    graph.setdefault(current, set()).add(callee)
    return graph


def usage_graph(library_root, api):
    """Which subsystems each subsystem calls into.

    ETA_HudNarrator_SpeakHealth calls ETA_Speech_Say, so a module that
    narrates health depends on Speech being initialised even though it
    never names Speech. Following that here is what makes the report
    point at the missing Init rather than at a symptom three layers up.
    """
    graph = {}
    for path in sources(library_root, (".c",)):
        with open(path, "r", errors="replace") as handle:
            text = handle.read()

        # The file's own subsystem, from the symbols it defines.
        defined = {subsystem_of(n) for n in DEFINITION.findall(text)}
        called = {subsystem_of(n) for n in CALL.findall(text) if n in api}
        for owner in defined:
            graph.setdefault(owner, set()).update(called - {owner})
    return graph


def reached(entry_points, graph):
    """Everything those entry points bring up, transitively."""
    seen = set()
    pending = list(entry_points)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(graph.get(name, ()))
    return seen


def subsystem_of(symbol):
    """ETA_Speech_Say -> ETA_Speech. ETA_MenuNarrator_Stop -> ETA_MenuNarrator."""
    return symbol.rsplit("_", 1)[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout with a patch series applied")
    parser.add_argument("--library", default=None,
                        help="path to src/accessibility (default: alongside this test)")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    library_root = args.library or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, "src", "accessibility")
    library_root = os.path.abspath(library_root)

    if not os.path.isdir(library_root):
        sys.exit("no accessibility library at %s" % library_root)

    api = library_api(library_root)
    graph = lifecycle_graph(library_root)
    uses = usage_graph(library_root, api)

    # Subsystems that have a lifecycle at all.
    has_init = {subsystem_of(n): n for n in api if n.endswith("_Init")}
    has_shutdown = {subsystem_of(n): n for n in api if n.endswith("_Shutdown")}

    if not api or not has_init:
        sys.exit("read no library API from %s - this test has stopped testing"
                 % library_root)

    print("[init] library exposes %d symbols, %d with an Init"
          % (len(api), len(has_init)))

    failures = []
    total_calls = 0

    for label, relative in MODULES:
        module_root = os.path.join(root, relative)
        if not os.path.isdir(module_root):
            sys.exit("no %s under %s - is this an engine checkout?" % (relative, root))

        used = set()
        for path in sources(module_root):
            with open(path, "r", errors="replace") as handle:
                for name in CALL.findall(handle.read()):
                    if name in api:
                        used.add(name)

        total_calls += len(used)
        if not used:
            print("[init] %-5s uses no library calls" % label)
            continue

        entry_points = {n for n in used if n.endswith(("_Init", "_Shutdown"))}
        covered = reached(entry_points, graph)

        # A module depends on everything its calls reach inside the
        # library, not only on what it names.
        direct = {subsystem_of(n) for n in used}
        subsystems = sorted(reached(direct, uses))

        print("[init] %-5s uses %d call(s) across %d subsystem(s); calls %s"
              % (label, len(used), len(subsystems),
                 ", ".join(sorted(entry_points)) or "no lifecycle function at all"))

        for subsystem in subsystems:
            init = has_init.get(subsystem)
            if init and init not in covered:
                named = sorted(n for n in used if subsystem_of(n) == subsystem)
                via = ("calls %s but" % ", ".join(named[:3])) if named else (
                    "reaches %s through the library but" % subsystem)
                failures.append(
                    "%s %s nothing reaches %s. Anything that narrates then "
                    "hands its text to a backend that has no voice and no "
                    "controller client, and is discarded without a word"
                    % (label, via, init))

            shutdown = has_shutdown.get(subsystem)
            if shutdown and shutdown not in covered:
                failures.append(
                    "%s uses %s but nothing reaches %s, so whatever it holds "
                    "outlives the module across a map change"
                    % (label, subsystem, shutdown))

    # No calls anywhere means the patches are not applied, not that the
    # wiring is sound.
    if not total_calls:
        sys.exit("found no library calls anywhere under %s - apply the patch "
                 "series first" % root)

    if failures:
        print()
        for failure in failures:
            print("[init] FAIL %s" % failure)
        sys.exit(1)

    print("[init] ok")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build (and verify) the Enemy Territory cgame/ui modules with the
accessibility layer, without SCons.

Why this exists
---------------
The 2010 GPL release builds with SCons under Python 2 (its SConstruct
imports `commands`, `StringIO` and `popen2`, and asks for SCons 0.96), and
with Visual C++ 2008 on Windows. Patch 0010 wires an ACCESSIBILITY=1
option into those SCons scripts, but Python 2 has been end-of-life since
2020 and was not available to run them where this integration was
developed - so the SCons scripts themselves have never been executed.

This script covers that gap. It reads the real source lists straight out
of SConscript.cgame / SConscript.ui - including the accessibility_string
list that patch 0010 adds - and compiles and links them with the same
flags SConstruct's Linux 'release' path uses. So it builds exactly the
inputs the SCons wiring specifies, and it fails if that wiring names a
file that doesn't exist or doesn't compile.

It is a verification harness and a working fallback, not a replacement
build system: it does not build the engine, the game module, bspc or curl,
and it has no dependency tracking.

Usage
-----
    ./build-modules.py <path-to-enemy-territory/src> [--outdir DIR] [--m32]

Expects the accessibility-mode sources at
<src>/../accessibility-mode/src/accessibility, which is where the
README's `git submodule add` instructions put them.

By default it builds each module twice, with the feature off and on, and
checks three things that matter for this integration:

  * both configurations compile and link,
  * linking with --no-undefined succeeds, so nothing the accessibility
    layer calls is left unresolved,
  * the compiler warning set is *identical* with the feature off and on,
    which is what makes "FEATURE_ACCESSIBILITY is a true no-op when
    undefined" a checked claim rather than an assumed one.

Deviations from what SCons would do, both deliberate:

  * 64-bit by default. SConstruct uses `gcc -m32`; pass --m32 to match it
    if you have 32-bit libc/libgcc installed. `-march=i686` is dropped on
    64-bit builds since it is not a valid target there.
  * Objects and libraries land in one flat output directory rather than
    SCons's build/<config>/<module>/ tree.
"""

import argparse
import os
import re
import subprocess
import sys

ACCESS_REL = os.path.join("..", "accessibility-mode", "src", "accessibility")

# SConstruct: BASECPPFLAGS + release OPTCPPFLAGS + the -fno-strict-aliasing
# it appends unconditionally. -fPIC comes from SCons's own Linux SHCCFLAGS
# default (SConstruct only overrides SHCCFLAGS on the win32 cross path).
BASE_CFLAGS = [
    "-pipe", "-Wall", "-fmessage-length=0", "-DNDEBUG",
    "-O3", "-Winline", "-ffast-math", "-fomit-frame-pointer",
    "-finline-functions", "-fschedule-insns2",
    "-fno-strict-aliasing", "-fPIC", "-std=gnu90",
]


def source_list(src, module, name):
    """Pull a `<name> = \"\"\"...\"\"\"` list out of a module SConscript.

    Mirrors scons_utils.BuildList(): whitespace-split, then prefixed.
    """
    path = os.path.join(src, "SConscript.%s" % module)
    with open(path) as f:
        text = f.read()
    m = re.search(r'%s\s*=\s*"""(.*?)"""' % re.escape(name), text, re.S)
    if not m:
        return None
    return m.group(1).split()


def build(src, module, accessibility, outdir, m32):
    define = "CGAMEDLL" if module == "cgame" else "UIDLL"
    cflags = list(BASE_CFLAGS)
    if m32:
        cflags += ["-m32", "-march=i686"]

    sources = [os.path.join(src, module, e)
               for e in source_list(src, module, "%s_string" % module)]

    access_root = os.path.abspath(os.path.join(src, ACCESS_REL))
    args = ["-D" + define]
    if accessibility:
        entries = source_list(src, module, "accessibility_string")
        if entries is None:
            sys.exit("SConscript.%s has no accessibility_string: is patch "
                     "0010 applied?" % module)
        if not os.path.isdir(access_root):
            sys.exit("accessibility sources not found at %s" % access_root)
        sources += [os.path.join(access_root, e) for e in entries]
        args += ["-DFEATURE_ACCESSIBILITY", "-I" + access_root]

    os.makedirs(outdir, exist_ok=True)
    objs, warnings = [], []

    for s in sources:
        obj = os.path.join(outdir, re.sub(r"[^\w]", "_", os.path.relpath(s, src)) + ".o")
        p = subprocess.run(["gcc", "-c"] + cflags + args + [s, "-o", obj],
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(p.stderr[:3000])
            sys.exit("compile failed: %s" % s)
        objs.append(obj)
        warnings += [ln for ln in p.stderr.splitlines() if " warning:" in ln]

    so = os.path.join(outdir, "%s.mp.so" % module)
    link = ["gcc", "-shared", "-Wl,--no-undefined", "-o", so] + objs + ["-lm"]
    if m32:
        link.insert(1, "-m32")
    p = subprocess.run(link, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[:3000])
        sys.exit("link failed: %s (strict --no-undefined)" % module)

    return {"objects": len(objs), "warnings": sorted(warnings), "so": so}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="path to enemy-territory/src")
    ap.add_argument("--outdir", default="build-accessibility")
    ap.add_argument("--m32", action="store_true",
                    help="build 32-bit, as SConstruct's 'gcc -m32' does")
    a = ap.parse_args()

    src = os.path.abspath(a.src)
    failures = 0

    for module in ("cgame", "ui"):
        results = {}
        for accessibility in (False, True):
            tag = "on" if accessibility else "off"
            r = build(src, module, accessibility,
                      os.path.join(a.outdir, "%s-%s" % (module, tag)), a.m32)
            results[tag] = r
            print("%-5s accessibility=%-3s objects=%3d warnings=%3d  %s"
                  % (module, tag, r["objects"], len(r["warnings"]),
                     os.path.basename(r["so"])))

        added = results["on"]["objects"] - results["off"]["objects"]
        if results["off"]["warnings"] == results["on"]["warnings"]:
            print("      warning sets identical with the feature off and on "
                  "(+%d accessibility objects)" % added)
        else:
            failures += 1
            print("      WARNING SETS DIFFER - FEATURE_ACCESSIBILITY is not a "
                  "clean no-op here:")
            off = set(results["off"]["warnings"])
            for w in results["on"]["warnings"]:
                if w not in off:
                    print("        + %s" % w)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

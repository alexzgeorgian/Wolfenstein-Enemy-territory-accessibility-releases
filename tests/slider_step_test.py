#!/usr/bin/env python3
"""Check a slider can be driven, and driven sensibly, from the keyboard.

Why this exists
---------------
A slider was the last control in ET that only a mouse could work. It
takes its value from *where in the bar* the pointer sits when you click,
so unlike the checkboxes and the multi fields there was no key press to
un-break: the behaviour had to be invented. Inventions need checking
harder than transcriptions do, because there is no upstream truth to
compare them against - only whether the result is usable by somebody who
can hear the number and not see the bar.

Sixty-six sliders ship in the stock menus and their ranges are nothing
alike: 0 to 1 for a volume, 1 to 30 for mouse sensitivity, 0 to 10000
for a banner timeout. A flat twentieth of each would give ladders like
1, 2.45, 3.9 - correct, and miserable to listen to. So the step is
snapped to a round 1, 2 or 5, and this reads the real function out of
the patched engine, compiles it, and walks every one of those sliders
end to end.

What it requires
----------------
  * the ladder reaches both ends, from either end
  * pressing past an end stays at the end, rather than drifting or
    wrapping to the other side
  * every value on the way is inside the slider's own range
  * the number of presses end to end is humane - enough to be precise,
    few enough to be usable
  * every value the narrator would read out is a round number

Usage
-----
    ./slider_step_test.py <engine-root>

Run it against a checkout with the patch series applied.
"""

import os
import re
import subprocess
import sys
import tempfile

UI_ITEM = os.path.join("src", "ui", "ui_menuitem.c")
MENUS = os.path.join("etmain", "ui")

# A press count outside this band is a usable slider only in theory: too
# few and a volume cannot be set finely, too many and reaching the end
# is a chore nobody will sit through.
MIN_PRESSES = 8
MAX_PRESSES = 60


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def lift(text, name):
    """Take a function out of the engine source, whole and unaltered."""
    match = re.search(r'^static float %s\([^)]*\)\n\{' % re.escape(name),
                      text, re.M)
    if not match:
        sys.exit("could not find %s in %s - the stepping this test guards "
                 "is gone, and passing without it would mean nothing"
                 % (name, UI_ITEM))

    depth, start = 0, match.end() - 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[match.start():index + 1]
    sys.exit("could not find the end of %s" % name)


def sliders(root):
    """Every slider the stock menus define, with its real range."""
    found = {}
    directory = os.path.join(root, MENUS)
    if not os.path.isdir(directory):
        sys.exit("no %s under %s" % (MENUS, root))

    pattern = re.compile(
        r'SLIDER\w*\(.*?_\("([^"]+)"\).*?"([A-Za-z_0-9]+)"'
        r'\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)')

    for name in sorted(os.listdir(directory)):
        if not name.endswith(".menu"):
            continue
        with open(os.path.join(directory, name), "r", errors="replace") as fh:
            for line in fh:
                match = pattern.search(line)
                if match:
                    label, cvar, _default, low, high = match.groups()
                    found[cvar] = (label.strip(), float(low), float(high))

    if not found:
        sys.exit("found no sliders in %s. This test cannot pass "
                 "vacuously: if the menus stopped defining sliders, or "
                 "the macro was renamed, it has nothing to check and "
                 "says so" % MENUS)
    return found


HARNESS = r"""
#include <stdio.h>
#include <math.h>

typedef struct { float minVal, maxVal, defVal, range; int a, b, c; } editFieldDef_t;

@@STEP@@

@@NUDGE@@

int main(int argc, char **argv)
{
    editFieldDef_t def;
    float value;
    int   i;

    (void)argc;
    def.minVal = (float)atof(argv[1]);
    def.maxVal = (float)atof(argv[2]);

    printf("step %.10g\n", ETA_SliderStep(def.minVal, def.maxVal));

    /* Up from the bottom, then keep pressing past the top. */
    value = def.minVal;
    for (i = 0; i < 4096; i++)
    {
        float next = ETA_SliderNudge(&def, value, 1);
        printf("up %.10g\n", next);
        if (next == value) { break; }
        value = next;
    }

    /* Down from the top, then keep pressing past the bottom. */
    value = def.maxVal;
    for (i = 0; i < 4096; i++)
    {
        float next = ETA_SliderNudge(&def, value, -1);
        printf("down %.10g\n", next);
        if (next == value) { break; }
        value = next;
    }

    /* A value the mouse could have left behind, nowhere near a rung. */
    value = def.minVal + (def.maxVal - def.minVal) * 0.3712f;
    printf("offgrid %.10g\n", ETA_SliderNudge(&def, value, 1));
    printf("offgridback %.10g\n", ETA_SliderNudge(&def, value, -1));
    return 0;
}
"""


def same(a, b):
    """Equal at the precision the engine actually keeps.

    The stepping is float maths and these ranges are read out of the
    menus as text, so a max written 7.43 arrives in the engine as
    7.4299998. Comparing those as doubles would fail a slider that is
    behaving perfectly.
    """
    return abs(a - b) <= max(1e-6, abs(b) * 1e-6)


def tidy(value, step):
    """Is this a number a person would have chosen?

    Judged against the step rather than in the abstract: a ladder of
    0.05 may say 0.35, and one of 500 may say 3500, but neither should
    ever produce 0.35000001 or 3499.9998 for a narrator to read out.
    """
    if step <= 0:
        return False
    rungs = value / step
    return abs(rungs - round(rungs)) < 1e-3


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: slider_step_test.py <engine-root>")
    root = os.path.abspath(sys.argv[1])

    source = read(root, UI_ITEM)
    harness = (HARNESS
               .replace("@@STEP@@", lift(source, "ETA_SliderStep"))
               .replace("@@NUDGE@@", lift(source, "ETA_SliderNudge")))
    harness = harness.replace("#include <math.h>",
                              "#include <math.h>\n#include <stdlib.h>")

    work = tempfile.mkdtemp()
    csrc = os.path.join(work, "slider.c")
    exe = os.path.join(work, "slider")
    with open(csrc, "w") as handle:
        handle.write(harness)

    build = subprocess.run(["cc", "-std=c99", "-O1", "-o", exe, csrc, "-lm"],
                           capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr)
        sys.exit("the stepping code lifted out of %s does not compile "
                 "on its own" % UI_ITEM)

    failures = []
    checked = 0

    for cvar, (label, low, high) in sorted(sliders(root).items()):
        run = subprocess.run([exe, repr(low), repr(high)],
                             capture_output=True, text=True)
        if run.returncode != 0:
            failures.append("%s: the stepping crashed on %g..%g"
                            % (cvar, low, high))
            continue

        step = None
        ups, downs, offgrid, offgridback = [], [], None, None
        for line in run.stdout.split("\n"):
            if not line:
                continue
            what, _, number = line.partition(" ")
            number = float(number)
            if what == "step":
                step = number
            elif what == "up":
                ups.append(number)
            elif what == "down":
                downs.append(number)
            elif what == "offgrid":
                offgrid = number
            elif what == "offgridback":
                offgridback = number

        checked += 1

        if step is None or step <= 0:
            failures.append("%s (%g..%g): no usable step" % (cvar, low, high))
            continue

        # Reaches the top, and stops there.
        if not same(ups[-1], high):
            failures.append(
                "%s (%g..%g): pressing right from the bottom settles at %g, "
                "not the slider's own maximum - a player cannot reach the "
                "end of their own setting" % (cvar, low, high, ups[-1]))

        if not same(downs[-1], low):
            failures.append(
                "%s (%g..%g): pressing left from the top settles at %g, not "
                "the minimum" % (cvar, low, high, downs[-1]))

        # Never outside the slider's own range, in either direction.
        for value in ups + downs + [offgrid, offgridback]:
            if value < low - 1e-6 or value > high + 1e-6:
                failures.append(
                    "%s (%g..%g): produced %g, outside the range the menu "
                    "declares - the cvar would be set to something the "
                    "slider cannot represent" % (cvar, low, high, value))
                break

        # Humane to drive.
        presses = len(ups) - 1
        if presses < MIN_PRESSES or presses > MAX_PRESSES:
            failures.append(
                "%s (%g..%g): %d presses from end to end. Outside %d-%d is "
                "either too coarse to set or too long to sit through"
                % (cvar, low, high, presses, MIN_PRESSES, MAX_PRESSES))

        # Every spoken value a round one - except the two ends, which
        # are whatever the menu author wrote. cg_automapZoom stops at
        # 7.43; that is the setting's real limit and reaching it exactly
        # matters more than reaching a tidy number near it.
        for value in ups:
            if same(value, low) or same(value, high):
                continue
            if not tidy(value, step):
                failures.append(
                    "%s (%g..%g): step %g produces %.10g, which is not a "
                    "number anybody would choose and is what the narrator "
                    "has to read out" % (cvar, low, high, step, value))
                break

        # Two rungs must not sound the same. The narration speaks a
        # slider as "%.2f", so a step finer than 0.01 would give a
        # player two different settings they cannot tell apart by ear -
        # pressing the key, hearing the same number, and concluding the
        # control is broken.
        if step < 0.01 - 1e-9:
            failures.append(
                "%s (%g..%g): step %g is finer than the two decimals the "
                "narration speaks, so consecutive values would be read out "
                "identically" % (cvar, low, high, step))

        # An off-grid value must move, and move onto the ladder.
        if offgrid is None or offgridback is None:
            failures.append("%s: the off-grid case produced nothing" % cvar)
        elif offgrid <= offgridback:
            failures.append(
                "%s (%g..%g): right gave %g and left gave %g from the same "
                "starting point - the two directions have to disagree, or "
                "one of them does nothing" % (cvar, low, high,
                                              offgrid, offgridback))

    if failures:
        print("slider_step_test: FAIL")
        for failure in failures:
            print("  - %s" % failure)
        sys.exit(1)

    print("slider_step_test: %d slider(s) in the stock menus can all be "
          "driven end to end from the keyboard, on a ladder of round "
          "numbers" % checked)


if __name__ == "__main__":
    main()

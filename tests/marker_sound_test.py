#!/usr/bin/env python3
"""Check the marker sounds different ahead, to the side and behind.

The tester could not tell a marker behind them from one ahead: the
game's stereo says left and right, not front and back, and there was
gunfire ahead as well. So the marker has three sounds - the high ping
ahead, a lower one off to either side, a low double ping behind - and
this checks the whole chain:

- the three are different sounds, each its own cvar and loop-table row,
  made by the generator and set in the shipped config;
- the side and behind pings are lower than the one ahead, and the one
  behind pings twice;
- the choice, lifted out of the patched engine and compiled, picks the
  right one all the way round, both sides alike, and holds its choice a
  few degrees past each change so walking along the edge does not swap
  them back and forth.

    ./marker_sound_test.py <engine-root>
"""

import os
import re
import subprocess
import sys
import tempfile
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")
GENERATOR = os.path.join(REPO, "release", "make-cue-sounds.py")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")

SOUNDS = {
    "ETA_LOOP_MARKER": ("eta_cueMarker", "marker_beacon.wav"),
    "ETA_LOOP_MARKER_SIDE": ("eta_cueMarkerSide", "marker_side.wav"),
    "ETA_LOOP_MARKER_BEHIND": ("eta_cueMarkerBehind", "marker_behind.wav"),
}


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def function_text(text, name):
    match = re.search(r"\n(static [^\n]*\b%s\s*\([^;{)]*\)\s*\{)" % re.escape(name), text)
    if not match:
        return None
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.start(1):i]


def pings(path):
    """How many separate pings a loop has, and the pitch of the first."""
    with wave.open(path, "rb") as handle:
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    samples = [int.from_bytes(raw[i:i + 2], "little", signed=True) for i in range(0, len(raw), 2)]
    loud = max(abs(v) for v in samples) * 0.05
    count, inside, quiet, first = 0, False, 0, None
    for i, v in enumerate(samples):
        if abs(v) > loud:
            if not inside:
                count += 1
                if first is None:
                    first = i
            inside, quiet = True, 0
        else:
            quiet += 1
            if quiet > rate * 0.03:
                inside = False
    # The pitch of the first ping by counting upward zero crossings over
    # its loudest part, against the fundamental the overtones sit on.
    seg = samples[first + int(rate * 0.02):first + int(rate * 0.10)]
    ups = sum(1 for a, b in zip(seg, seg[1:]) if a < 0 <= b)
    return count, ups / (len(seg) / rate)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    failures = []

    commandmap = read(os.path.join(root, COMMANDMAP))
    main_c = read(os.path.join(root, MAIN))
    local = read(os.path.join(root, LOCAL))

    # --- the chain: enum row, cvar, file, generator, config -------------
    enum = re.search(r"typedef enum\s*\{(.*?)\}\s*eta_loopSoundType_t;", local, re.S)
    table = re.search(r"eta_cueSound_t eta_loopSounds\[\]\s*=\s*\{(.*?)\n\};", main_c, re.S)
    if not enum or not table:
        sys.exit("could not read the loop sounds' enum or table")
    names = re.findall(r"\b(ETA_LOOP_[A-Z_]+)\b", enum.group(1))
    rows = re.findall(r'\{\s*"(\w+)",\s*"sound/accessibility/([\w.]+)"', table.group(1))
    generator = read(GENERATOR)
    autoexec = read(AUTOEXEC)
    for name, (cvar, wav) in sorted(SOUNDS.items()):
        at = names.index(name) if name in names else -1
        if at < 0 or at >= len(rows) or rows[at] != (cvar, wav):
            failures.append("%s does not play %s as %s" % (name, wav, cvar))
        if '"%s"' % wav not in generator:
            failures.append("make-cue-sounds.py does not make %s" % wav)
        if not re.search(r'^seta %s\s+"sound/accessibility/%s"' % (cvar, re.escape(wav)), autoexec, re.M):
            failures.append("autoexec.cfg does not set %s" % cvar)
    if not failures:
        print("[marker] three marker sounds, each its own cvar, made and shipped")

    # --- the sounds themselves --------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, GENERATOR, tmp], check=True, capture_output=True)
        ahead = pings(os.path.join(tmp, "marker_beacon.wav"))
        side = pings(os.path.join(tmp, "marker_side.wav"))
        behind = pings(os.path.join(tmp, "marker_behind.wav"))
    if not (behind[1] < side[1] < ahead[1]):
        failures.append("the marker does not drop in pitch as it goes round: "
                        "ahead %.0f Hz, side %.0f, behind %.0f" % (ahead[1], side[1], behind[1]))
    elif ahead[0] != 1 or side[0] != 1 or behind[0] != 2:
        failures.append("the pings are not one ahead, one to the side and two "
                        "behind (%d, %d, %d)" % (ahead[0], side[0], behind[0]))
    else:
        print("[marker] ahead %.0f Hz once, side %.0f Hz once, behind %.0f Hz twice"
              % (ahead[1], side[1], behind[1]))

    # --- the choice, compiled ----------------------------------------------
    chooser = function_text(commandmap, "ETA_MarkerSoundFor")
    defines = "\n".join(re.findall(r"#define ETA_MARKER_(?:AHEAD|BEHIND|HOLD)_DEGREES[^\n]*", commandmap))
    frame = commandmap[commandmap.find("if (eta_markerCues.integer)"):]
    if not chooser or defines.count("#define") != 3:
        failures.append("there is no choosing between the marker's sounds")
    elif "CG_AccessibilityLoopSound(ETA_MarkerSoundFor(direction))" not in frame[:800]:
        failures.append("the marker's sound is not chosen by where it is")
    else:
        harness = r'''
#include <math.h>
#include <stdio.h>
typedef float vec3_t[3];
typedef enum { ETA_LOOP_MARKER = 4, ETA_LOOP_LADDER = 8, ETA_LOOP_MARKER_SIDE, ETA_LOOP_MARKER_BEHIND } eta_loopSoundType_t;
#define YAW 1
static struct { struct { vec3_t viewangles; } predictedPlayerState; } cg;
static float AngleNormalize180(float a) { a = fmodf(a, 360.0f); if (a > 180) a -= 360; if (a < -180) a += 360; return a; }
static float AngleSubtract(float a, float b) { return AngleNormalize180(a - b); }
static float vectoyaw(const vec3_t v) { return atan2f(v[1], v[0]) * 180.0f / 3.14159265f; }
%s
%s
int main(void)
{
	int a, i;
	/* Round once each way, then back, a degree at a time. */
	for (i = 0; i < 2; i++)
	{
		for (a = 0; a <= 180; a++) { vec3_t d = { cosf(a * 3.14159265f / 180), sinf(a * 3.14159265f / 180), 0 }; printf("%%d %%d %%d\n", i, a, ETA_MarkerSoundFor(d)); }
		for (a = 180; a >= 0; a--) { vec3_t d = { cosf(a * 3.14159265f / 180), sinf(a * 3.14159265f / 180), 0 }; printf("%%d %%d %%d\n", i, a, ETA_MarkerSoundFor(d)); }
		cg.predictedPlayerState.viewangles[YAW] = 90.0f;   /* and facing elsewhere */
	}
	for (a = 0; a <= 180; a++) { vec3_t d = { cosf(-a * 3.14159265f / 180), sinf(-a * 3.14159265f / 180), 0 }; cg.predictedPlayerState.viewangles[YAW] = 0; printf("2 %%d %%d\n", a, ETA_MarkerSoundFor(d)); }
	return 0;
}
''' % (defines, chooser.replace("fabsf(AngleSubtract", "fabsf(AngleSubtract"))
        with tempfile.TemporaryDirectory() as tmp:
            src, binary = os.path.join(tmp, "m.c"), os.path.join(tmp, "m")
            with open(src, "w") as handle:
                handle.write(harness)
            build = subprocess.run(["cc", "-std=gnu99", "-o", binary, src, "-lm"], capture_output=True, text=True)
            if build.returncode:
                sys.exit("the marker's sound choice does not build on its own:\n" + build.stderr[-2000:])
            out = subprocess.run([binary], capture_output=True, text=True).stdout.split("\n")
        ahead, side, behind = 4, 9, 10
        picks = [tuple(int(x) for x in line.split()) for line in out if line.strip()]
        # Facing yaw 0 on the first pass; the second pass is facing 90, so
        # its "a" is not an angle off the view and only the first and the
        # mirrored third are checked for where the changes fall.
        def first(seq, value):
            return next((a for a, s in seq if s == value), None)
        outward = [(a, s) for p, a, s in picks[:181] if p == 0]
        back = [(a, s) for p, a, s in picks[181:362] if p == 0]
        mirror = [(a, s) for p, a, s in picks if p == 2]
        to_side, to_behind = first(outward, side), first(outward, behind)
        back_side = next((a for a, s in back if s == side), None)
        back_ahead = next((a for a, s in back if s == ahead), None)
        if outward[0][1] != ahead or outward[-1][1] != behind:
            failures.append("straight ahead is not the high ping, or straight "
                            "behind not the low one")
        elif not (50 < to_side <= 62 and 130 < to_behind <= 142):
            failures.append("turning away, the sound changes at %s and %s degrees "
                            "rather than past 50 and 130" % (to_side, to_behind))
        elif not (118 <= back_side < 130 and 38 <= back_ahead < 50):
            failures.append("turning back, the sound changes at %s and %s degrees: "
                            "a change is not held a few degrees past it"
                            % (back_side, back_ahead))
        elif [s for a, s in mirror] != [s for a, s in outward]:
            failures.append("the marker on the left does not sound as it does "
                            "on the right")
        else:
            print("[marker] the high ping to %d degrees off, the lower one to %d, "
                  "then the double; each held about 10 degrees on the way back"
                  % (to_side - 1, to_behind - 1))

    if failures:
        for failure in failures:
            print("[marker] FAIL %s" % failure)
        sys.exit(1)
    print("marker_sound_test: the marker sounds different ahead, to the side "
          "and behind")


if __name__ == "__main__":
    main()

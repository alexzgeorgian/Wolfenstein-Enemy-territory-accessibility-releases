#!/usr/bin/env python3
"""Check a Mac says the map, its briefing and the team key one at a time.

On a Mac a line said cuts off the one still being said. In 1.3.5 the
end of a load said three lines in the same frame - "Loaded", the map and
its type; the briefing; the key for the team and class menu - and the
tester heard only the last. The Mac's end-of-load code is lifted out of
the patched engine unchanged, with its Mac branch switched on, and run
frame by frame on a made-up clock:

- nothing is said for a second after the load;
- then "Loaded", the map and its type;
- the briefing only once that line has had time to be said;
- the team and class key only once the briefing has;
- never two lines in one frame;
- a player already on a team hears no team key; a map with no briefing
  goes straight from the map to the key.

    ./mac_loading_order_test.py <engine-root>
"""

import os
import subprocess
import sys
import tempfile

PANEL = os.path.join("src", "cgame", "cg_loadpanel.c")

HARNESS = r'''
#include "q_shared.h"
#include <stdio.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

#define ETA_MAX_SPEECH_TEXT_LENGTH 512
#define PERS_TEAM      3
#define TEAM_SPECTATOR 3
#define MS_PER_CHAR    70

typedef struct { playerState_t ps; } fakeSnap_t;
static fakeSnap_t                    snap;
static struct { fakeSnap_t *snap; } cg = { &snap };
static int                           now;

static int trap_Milliseconds(void) { return now; }
static int ETA_Speech_EstimateDurationMs(const char *m) { return m && *m ? (int)strlen(m) * MS_PER_CHAR : 0; }
static void ETA_Speech_Say(const char *m) { printf("SAY %d %s\n", now, m); }
static void trap_Key_KeysForBinding(const char *b, int *k1, int *k2) { (void)b; *k1 = 'l'; *k2 = -1; }
static void trap_Key_KeynumToStringBuf(int k, char *buf, int size) { (void)k; Q_strncpyz(buf, "l", size); }

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

static void Run(const char *label, const char *briefing, int team)
{
	int end;

	printf("RUN %s\n", label);
	Q_strncpyz(eta_loadingTitle, "Loaded. Goldrush. Stopwatch.", sizeof(eta_loadingTitle));
	Q_strncpyz(eta_loadingBriefing, briefing, sizeof(eta_loadingBriefing));
	eta_loadingBriefingUntil   = 0;
	eta_loadedAt               = 0;
	eta_loadingReadySaid       = qfalse;
	snap.ps.persistant[PERS_TEAM] = team;

	now = 5000;
	printf("FIRST %d\n", now);
	for (end = now + 120000; now < end; now += 16)
	{
		CG_AccessibilityLoadingFrame();
	}
}

int main(void)
{
	Run("spectator", "The Allies must steal the gold from the Axis bank and escape with it in the truck.", TEAM_SPECTATOR);
	Run("onteam", "The Allies must steal the gold.", 1);
	Run("nobriefing", "", TEAM_SPECTATOR);
	return 0;
}
'''


def lift(panel):
    statics_at = panel.find("static int      eta_loadingBriefingUntil;")
    statics_end = panel.find("void CG_AccessibilityLoadingBegin(void)", statics_at)
    frame_at = panel.find("void CG_AccessibilityLoadingFrame(void)")
    if statics_at < 0 or statics_end < 0 or frame_at < 0:
        sys.exit("no end-of-load speech in %s - the feature this test measures is gone" % PANEL)
    depth, i = 0, panel.index("{", frame_at)
    while True:
        if panel[i] == "{":
            depth += 1
        elif panel[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    lifted = panel[statics_at:statics_end] + panel[frame_at:i + 1]
    if "#ifdef __APPLE__" not in lifted:
        sys.exit("no Mac branch in the end-of-load speech in %s" % PANEL)
    return lifted.replace("#ifdef __APPLE__", "#if 1")


def estimate(text):
    return len(text) * 70


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    path = os.path.join(root, PANEL)
    if not os.path.isfile(path):
        sys.exit("no %s - is the patch series applied?" % path)
    lifted = lift(open(path, errors="replace").read())

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "loaded.c")
        binary = os.path.join(tmp, "loaded")
        with open(source, "w") as handle:
            handle.write(HARNESS.replace("%(LIFTED)s", lifted))
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-I", os.path.join(root, "src", "qcommon"),
             "-I", os.path.join(root, "src"), "-o", binary, source,
             os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted end-of-load speech does not build:\n%s" % build.stderr[-3000:])
        output = subprocess.run([binary], capture_output=True, text=True, timeout=60).stdout

    runs, current = {}, None
    for line in output.splitlines():
        kind, _, rest = line.partition(" ")
        if kind == "RUN":
            current = runs.setdefault(rest, {"said": []})
        elif kind == "FIRST":
            current["first"] = int(rest)
        elif kind == "SAY":
            when, _, text = rest.partition(" ")
            current["said"].append((int(when), text))

    failures = []
    title = "Loaded. Goldrush. Stopwatch."
    key = "Press L to choose your team and class"

    def check(label, expected):
        run = runs.get(label)
        if not run:
            failures.append("%s: the lifted code was not run" % label)
            return
        said = run["said"]
        texts = [text for _, text in said]
        if texts != expected:
            failures.append("%s: said %s, not %s, in that order" % (label, texts, expected))
            return
        if said[0][0] - run["first"] < 1000:
            failures.append("%s: the map was said %d ms after the load, not a second"
                            % (label, said[0][0] - run["first"]))
        for (before, text), (after, _) in zip(said, said[1:]):
            if after - before < estimate(text):
                failures.append("%s: a line came %d ms after %r, which takes %d ms to say"
                                % (label, after - before, text, estimate(text)))

    briefing = "The Allies must steal the gold from the Axis bank and escape with it in the truck."
    check("spectator", [title, briefing, key])
    check("onteam", [title, "The Allies must steal the gold."])
    check("nobriefing", [title, key])

    if failures:
        for failure in failures:
            print("[mac loading] FAIL %s" % failure)
        sys.exit(1)
    print("[mac loading] a second after the load: the map, then the briefing once it has been "
          "said, then the team key once that has")
    print("[mac loading] on a team, no team key; with no briefing, the map then the key")
    print("mac_loading_order_test: a Mac says the map, its briefing and the team key one at a time")


if __name__ == "__main__":
    main()

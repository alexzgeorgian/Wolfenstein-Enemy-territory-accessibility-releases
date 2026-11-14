#!/usr/bin/env python3
"""Check deaths and kills are said, the one watched is described, and
the console says when it opens.

The tester kept dying without hearing what killed them, wanted to know
what other players were doing while spectating without being buried in
it, and opened the console by mistake three times without knowing.

- A death or a kill is said in the game's own words, from its own table
  (bg_misc.c) - "You failed to spot Hans's Landmine" - only for the
  player, or the one they are watching; the player's own in one line
  with the "Down, a medic can revive you" that follows, so neither cuts
  the other off. ETA_ObituaryForYou is lifted out
  of the patched engine and run on every one of the game's death
  messages said of "You": none is left "You was", "himself" or "his".
- Watching someone says who, which side and class, and how they are;
  a change of health does not say it all again; their getting up again
  where they fell is said.
- The console says when it opens and when it closes, in a match and in
  the menus, and only once each.

    ./deaths_watching_console_test.py <engine-root>
"""

import os
import re
import subprocess
import sys
import tempfile

EVENT = os.path.join("src", "cgame", "cg_event.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
UI = os.path.join("src", "ui", "ui_main.c")
BG_MISC = os.path.join("src", "game", "bg_misc.c")

HARNESS = r'''
#include "q_shared.h"
#include <stdio.h>

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

int main(int argc, char **argv)
{
	int i;

	for (i = 1; i < argc; i++)
	{
		char text[256];

		Q_strncpyz(text, argv[i], sizeof(text));
		ETA_ObituaryForYou(text, sizeof(text));
		printf("%s\n", text);
	}
	return 0;
}
'''


def read(path):
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


def function_whole(text, name):
    match = re.search(r"static void %s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return ""
    return text[match.start():match.end()] + function_body(text, name) + "}\n"


def mod_messages(misc):
    """The game's death messages: each row's kill, self-kill and no-attacker words."""
    rows = re.findall(r"^\t\{ (MOD_\w+),(.*)\},\s*$", misc, re.M)
    out = []
    for name, rest in rows:
        fields = re.findall(r'"[^"]*"|NULL', rest)
        if len(fields) >= 4:
            out.append((name,) + tuple(None if f == "NULL" else f[1:-1] for f in fields[:4]))
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    event = read(os.path.join(root, EVENT))
    draw = read(os.path.join(root, DRAW))
    ui = read(os.path.join(root, UI))
    misc = read(os.path.join(root, BG_MISC))
    failures = []

    if "ETA_NarrateObituary" not in event:
        sys.exit("no death narration in %s - the feature this test measures is gone" % EVENT)

    # --- the game's own words, said of "You" --------------------------------
    messages = mod_messages(misc)
    if len(messages) < 40:
        sys.exit("the game's table of deaths was not read (%d rows)" % len(messages))
    landmine = [m for m in messages if m[0] == "MOD_LANDMINE"]
    if not landmine or landmine[0][1] != "failed to spot" or landmine[0][2] != "'s Landmine":
        failures.append("the game no longer says a landmine death as \"failed to spot\" someone's \"'s Landmine\"")

    said = []
    for name, kill1, kill2, selfkill, world in messages:
        if kill1:
            said.append("You %s Hans%s" % (kill1, kill2 or ""))
        for words in (selfkill, world):
            if words:
                said.append("You %s" % words)
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "foryou.c")
        binary = os.path.join(tmp, "foryou")
        with open(source, "w") as handle:
            handle.write(HARNESS.replace("%(LIFTED)s", function_whole(event, "ETA_ObituaryForYou")))
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-I", os.path.join(root, "src", "qcommon"), "-I", os.path.join(root, "src"),
             "-o", binary, source, os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c"), "-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted death words do not build:\n%s" % build.stderr[-3000:])
        out = subprocess.run([binary] + said, capture_output=True, text=True, timeout=60).stdout.splitlines()

    wrong = [line for line in out if re.search(r"^You was\b|\bhimself\b|\bhis\b", line)]
    if len(out) != len(said) or wrong:
        failures.append("said of \"You\", the game's words are left wrong: %r" % wrong[:5])
    elif "You failed to spot Hans's Landmine" not in out or "You were killed by Hans's MP 40" not in out \
            or "You failed to spot your own landmine" not in out or "You killed yourself" not in out:
        failures.append("the game's words for \"You\" did not come out as they should: %r" % out[:8])
    else:
        print("[deaths] all %d of the game's death messages read right said of \"You\": "
              "\"You failed to spot Hans's Landmine\", \"You were killed by Hans's MP 40\"" % len(out))

    narrate = strip_comments(function_body(event, "ETA_NarrateObituary"))
    obituary = strip_comments(function_body(event, "CG_Obituary"))
    for ok, what in (
            ("ETA_NarrateObituary(target, attacker, mod);" in obituary, "a death is never said"),
            ("cg.snap->ps.clientNum" in narrate and "if (target != viewed && attacker != viewed)" in narrate,
             "deaths are said that are not the player's, nor the watched player's - every death in the match"),
            (all(f in narrate for f in ("obituaryKillMessage1", "obituaryKillMessage2", "obituarySelfKillMessage",
                                        "obituaryNoAttackerMessage")),
             "a death is not said in the game's own words"),
            ("killed %s%s" in narrate and '"teammate "' in narrate, "a kill is not said, or a teammate killed is not said as one"),
            ("Q_CleanStr(text);" in narrate, "a name's colour codes are read out"),
            ("Q_strncpyz(eta_deathWords, text, sizeof(eta_deathWords));" in narrate
             and "CG_AccessibilityDeathWords(qfalse)" in function_body(draw, "ETA_NarratePlayState")
             and "CG_AccessibilityDeathWords(qtrue)" in function_body(draw, "ETA_NarrateDeathWords")
             and "ETA_NarrateDeathWords();" in draw,
             "the player's own death is not said in one line with the \"Down\" after it, or not at all")):
        if not ok:
            failures.append(what)
    if not [f for f in failures if "said" in f and "\"You\"" not in f or "colour" in f]:
        print("[deaths] said for the player and the one watched only, kills too, in the game's words; "
              "the player's own with the \"Down\" after it, as one line")

    # --- watching -----------------------------------------------------------
    now = function_body(draw, "ETA_PlayStateNow")
    speak = function_body(draw, "ETA_SpeakPlayState")
    describe = function_body(draw, "ETA_DescribeFollowed")
    revive = strip_comments(function_body(draw, "ETA_NarrateFollowedRevive"))
    if "ETA_DescribeFollowed(following, who, sizeof(who));" not in speak or "who);" not in speak:
        failures.append("who is being watched is said by name alone")
    elif not ("BG_ClassnameForNumber(ci->cls)" in describe and "ps->stats[STAT_HEALTH]" in describe
              and '"Axis "' in describe and "down" in describe):
        failures.append("the one watched is not said with side, class and health")
    elif "Q_strncpyz(following, cgs.clientinfo[ps->clientNum].name" not in now or "health" in now:
        failures.append("a change in the watched player's health would say who it is all over again")
    else:
        print("[watching] \"following Hans, Axis Medic, 85 health\" - said when the view lands, not at every hit")
    if not ("ETA_NarrateFollowedRevive();" in draw and "PMF_FOLLOW" in revive
            and "Distance(ps->origin, downAt) <= ETA_REVIVED_NEAR" in revive and "%s revived" in revive):
        failures.append("the one watched getting up where they fell is not said")
    else:
        print("[watching] the one watched, back up where they fell: \"Hans revived\"")

    # --- the console --------------------------------------------------------
    cg_console = strip_comments(function_body(draw, "ETA_NarrateConsole"))
    ui_console = strip_comments(function_body(ui, "UI_AccessibilityConsoleFrame"))
    active = strip_comments(function_body(draw, "CG_DrawActive"))
    refresh = strip_comments(function_body(ui, "UI_Refresh"))
    for name, body in (("match", cg_console), ("menus", ui_console)):
        if not ("KEYCATCH_CONSOLE" in body and "if (open == wasOpen)" in body
                and '"Console open. The same key closes it"' in body and '"Console closed"' in body):
            failures.append("in the %s, the console opening and closing is not said, once each" % name)
    if "ETA_NarrateConsole();" not in active or "UI_AccessibilityConsoleFrame();" not in refresh:
        failures.append("the console is not watched every frame")
    elif "cstate.connState == CA_ACTIVE" not in ui_console:
        failures.append("in a match, the console would be said twice, by the menus and the match")
    if not [f for f in failures if "console" in f]:
        print("[console] \"Console open. The same key closes it\" and \"Console closed\", in a match and in the menus")

    if failures:
        for failure in failures:
            print("[deaths] FAIL %s" % failure)
        sys.exit(1)
    print("deaths_watching_console_test: deaths are said, the one watched described, the console told")


if __name__ == "__main__":
    main()

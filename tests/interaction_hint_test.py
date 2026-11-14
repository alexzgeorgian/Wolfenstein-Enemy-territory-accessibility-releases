#!/usr/bin/env python3
"""Check every cursor hint the game draws has words, and the right ones.

Why this exists
---------------
ET already tells a sighted player when they can use what is in front of
them: an icon appears under the crosshair - pliers on a construction, a
stick of dynamite where one goes, a syringe over a body still worth
reviving. It is how an engineer knows an objective is workable at all,
and until now the mod answered it with one undifferentiated click.

Two ways to get this wrong, and they fail in opposite directions.

The first is silence. The engine picks the icon from a switch on its own
hint enum; if the mod's switch has no case for one of them, that hint
produces nothing, and nothing is exactly what the player hears when
there is nothing there. So this reads the engine's own drawing switch -
the real list of hints that put something on screen - and requires the
mod to name each one, or to have an explicit case saying it deliberately
does not. Either is fine. Forgetting is not, and forgetting is what
happens when an engine adds a hint.

The second is confident nonsense, which is worse. The enum has holes in
it: ET: Legacy struck a dozen hints out as unused and renumbered
nothing, so HINT_ACTIVATE is 3, HINT_HEALTH is 13, HINT_BUILD is 38. A
mapping written as a table indexed by position would be off by one gap
for everything after the first hole and would confidently announce
"revive" over a crate. So the mapping has to switch on the names, and
this fails if a numeric literal turns up where a hint belongs.

It also pins the two the tester asked for by name. The pliers and the
dynamite are the icons an engineer plays by, and "build" and "defuse"
have to be distinguishable in the first two words, because planting
where you meant to defuse is a round.

Finally it pins the settle. The sound fires the instant an icon appears
and should; the words wait. Turning through a supply room puts four or
five hints under the crosshair inside a second, and a narrator that read
all of them out would be worse than the click it replaced.

What it does NOT check
----------------------
Whether the words are the ones a player wants to hear, or whether a
quarter of a second is the right wait. Those need ears.

Usage
-----
    ./interaction_hint_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

PUBLIC = os.path.join("src", "game", "bg_public.h")
NARRATOR = os.path.join("src", "accessibility", "hud", "hud_narrator.c")

# Where each engine draws the icon, and where the mod names it. Both
# trees hook the hint in the file that already owned it, so the pair
# differs; what the test asks of them does not.
PLACES = {
    "etlegacy": {
        "draw": os.path.join("src", "cgame", "cg_newDraw.c"),
        "mod": os.path.join("src", "cgame", "cg_draw.c"),
    },
    "id-software": {
        "draw": os.path.join("src", "cgame", "cg_newDraw.c"),
        "mod": os.path.join("src", "cgame", "cg_newDraw.c"),
    },
}

# The hints the tester asked for, and the word that has to survive in
# each. Not the whole phrase: the wording is allowed to be rewritten,
# the meaning it carries is not.
REQUIRED_WORDS = {
    "HINT_BUILD": "liers",
    "HINT_DISARM": "liers",
    "HINT_DYNAMITE": "ynamite",
}


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


def body_of(text, name, where):
    start = text.find(name)
    if start < 0:
        sys.exit("could not find %s in %s - the narration this test guards "
                 "is gone, and passing without it would mean nothing"
                 % (name, where))
    end = text.find("\n}", start)
    if end < 0:
        sys.exit("could not find the end of %s in %s" % (name, where))
    return text[start:end]


def drawn_hints(draw_c, where):
    """Every hint the engine's own cursor-hint switch gives an icon to."""
    body = body_of(draw_c, "CG_DrawCursorhint", where)
    found = sorted(set(re.findall(r'case\s+(HINT_[A-Z_0-9]+)\s*:', body)))
    if len(found) < 10:
        sys.exit("only %d hint(s) found in the engine's own drawing switch "
                 "- this test reads the mod against that list and cannot "
                 "tell whether anything is missing" % len(found))
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    parser.add_argument("--engine", default="etlegacy",
                        choices=tuple(PLACES))
    parser.add_argument("--library", default=None,
                        help="accessibility-mode checkout (default: this one)")
    args = parser.parse_args()

    library_root = args.library or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))

    where = PLACES[args.engine]
    draw = strip_comments(read(args.root, where["draw"],
                               "is this an engine checkout?"))
    mod_c = strip_comments(read(args.root, where["mod"],
                                "is the patch series applied?"))
    public = read(args.root, PUBLIC, "is this an engine checkout?")
    narrator = strip_comments(read(library_root, NARRATOR,
                                   "is this the accessibility checkout?"))

    failures = []

    mapping = body_of(mod_c, "ETA_InteractionForHint", where["mod"])
    named = set(re.findall(r'case\s+(HINT_[A-Z_0-9]+)\s*:', mapping))

    # --- nothing the engine draws may be missing from the mapping ------
    for hint in drawn_hints(draw, where["draw"]):
        if hint not in named:
            failures.append(
                "the engine draws an icon for %s and the mod has no case "
                "for it, so that hint is answered with silence - which is "
                "what the player hears when there is nothing there at all"
                % hint)

    # --- and nothing may be named that the engine does not have --------
    for hint in sorted(named):
        if not re.search(r'\b%s\b' % re.escape(hint), public):
            failures.append(
                "the mod maps %s, which is not in the engine's hint enum - "
                "it either never existed or has been removed, and either "
                "way that case is dead" % hint)

    # --- the mapping must switch on names, not on positions ------------
    if "switch" not in mapping:
        failures.append(
            "ETA_InteractionForHint is not a switch on the hint - the enum "
            "has holes in it (HINT_ACTIVATE is 3, HINT_HEALTH 13, "
            "HINT_BUILD 38), so anything indexed by position is off by one "
            "gap for every hint after the first hole")

    for literal in re.findall(r'case\s+(-?\d+)\s*:', mapping):
        failures.append(
            "the mapping has a numeric case (%s) where a hint belongs. The "
            "two engines number these differently and both leave gaps; a "
            "number here is right in one tree and announces the wrong "
            "thing in the other" % literal)

    # --- the two the tester asked for ----------------------------------
    names = body_of(narrator, "ETA_HudNarrator_InteractionName", NARRATOR)

    for hint, word in sorted(REQUIRED_WORDS.items()):
        if hint not in named:
            failures.append(
                "%s is not mapped at all - it is one of the two icons the "
                "report asked for by name" % hint)
            continue

        state = state_for(mapping, hint)
        if not state:
            failures.append("could not tell what %s maps to" % hint)
            continue

        spoken = phrase_for(names, state)
        if spoken is None:
            failures.append(
                "%s maps to %s and the library has no words for it"
                % (hint, state))
        elif word not in spoken:
            failures.append(
                '%s is spoken as "%s", which does not carry "%s" - that is '
                "the word the report asked for, and it is what an ET "
                "player calls the tool" % (hint, spoken, word))

    build = state_for(mapping, "HINT_BUILD")
    disarm = state_for(mapping, "HINT_DISARM")

    if build and disarm and build == disarm:
        failures.append(
            "building and defusing map to the same report. They are "
            "different icons on screen and different jobs at an "
            "objective; planting where you meant to defuse is a round")

    # --- the climb is announced while it climbs ------------------------
    #
    # The interaction report speaks the progress figure once, when the
    # icon settles, and then goes quiet - and a construction takes
    # seconds of holding a key. A tester finished one and said they had
    # only known to keep holding because they remembered the bar on
    # screen.
    build = body_of(mod_c, "ETA_NarrateBuildProgress", where["mod"])

    if "cursorHintValue" not in build:
        failures.append(
            "the build narration does not read the progress value, so it "
            "is not reporting the bar the player can see")

    if "HINT_BUILD" not in build:
        failures.append(
            "the build narration is not restricted to the build hint, so "
            "it would announce a percentage over anything that happens to "
            "carry a bar - a breakable's health, a tank's")

    if "ETA_HudNarrator_UpdateBuildProgress" not in build:
        failures.append(
            "the build progress is spoken directly rather than through "
            "the milestone gate, so a number that changes every frame "
            "becomes a voice that never stops")

    # --- and completion comes from the engine, not from the bar --------
    #
    # This is the half that was got wrong first time. A construction's
    # progress is reset to zero in the same frame it crosses the finish
    # line, so a value that stopped arriving means EITHER "built" OR
    # "you let go" and nothing distinguishes them - reading completion
    # out of the figure would be a confident lie. That much still holds.
    #
    # What was missed is that the engine says so outright:
    # G_ConstructiblePlayerBuild stamps lastTaskAchievedTime, and
    # G_CheckForCursorHints then sends HINT_COMPLETED with a value of
    # 255, which is what fills the on-screen bar to the top. A tester
    # reported the narration "stops at 75 instead of reaching 100",
    # which was that missing announcement.
    #
    # So the rule is not "never say complete". It is "only say it when
    # the engine did".
    # Whether there is an event to use is the engine's business, not
    # this test's: ET: Legacy added HINT_COMPLETED and the 2010 tree
    # never had it. So the question asked is decided by the engine's own
    # hint enum, and the day the older tree grows one, the requirement
    # turns itself on rather than waiting for somebody to notice.
    engine_has_completed = "HINT_COMPLETED" in public

    if not engine_has_completed:
        # No event to read, so the original rule stands undiluted: a
        # completion claim here could only have come from the figure.
        if re.search(r'complete|built|finished', build, re.I):
            failures.append(
                "this engine has no HINT_COMPLETED, so the build "
                "narration has no honest way to know a construction "
                "finished - the progress value is reset to zero the "
                "instant it does, which cannot be told from a player "
                "letting go of the key")
    elif "HINT_COMPLETED" not in build:
        failures.append(
            "the engine sends HINT_COMPLETED and the build narration "
            "does not look at it, so a finished construction is "
            "announced by nothing at all - the narration simply stops "
            "partway up and the player cannot tell a finished job from "
            "one they walked away from")
    elif "ETA_HudNarrator_SpeakBuildComplete" not in build:
        failures.append(
            "nothing in the build narration speaks the completion, so "
            "the engine's own HINT_COMPLETED event is being read and "
            "then dropped")
    else:
        # The claim has to sit inside the HINT_COMPLETED branch. If it
        # can be reached from the progress path instead, it is being
        # inferred from the figure again, which is the original defect.
        completed_at = build.index("HINT_COMPLETED")
        speaks_at = build.index("ETA_HudNarrator_SpeakBuildComplete")

        if speaks_at < completed_at:
            failures.append(
                "the build narration claims completion before it has "
                "looked at HINT_COMPLETED, so the claim is not coming "
                "from the engine's event")
        elif "cursorHintValue" in build[completed_at:speaks_at]:
            failures.append(
                "the build narration reads the progress value between "
                "HINT_COMPLETED and the completion callout, so the claim "
                "may be coming from the figure - which is reset to zero "
                "the instant a construction finishes and cannot tell a "
                "finished job from a player who let go")

    # The library must not be able to announce completion off a
    # percentage either, on either engine, whatever the engine side does.
    update_body = body_of(narrator, "ETA_HudNarrator_UpdateBuildProgress",
                          NARRATOR)

    if re.search(r'complete', update_body, re.I):
        failures.append(
            "ETA_HudNarrator_UpdateBuildProgress can speak a completion. "
            "That function is fed a percentage, and a percentage cannot "
            "know a construction is finished - only the engine's event "
            "can")

    # --- the words wait, the sound does not ----------------------------
    hint_fn = body_of(mod_c, "ETA_NarrateInteractionHint", where["mod"])

    if "ETA_HINT_SETTLE_MS" not in hint_fn:
        failures.append(
            "the spoken hint has no settle - a turn through a supply room "
            "puts four or five hints under the crosshair inside a second, "
            "and reading all of them out is worse than the click it "
            "replaced")

    settle = re.search(r'#define\s+ETA_HINT_SETTLE_MS\s+(\d+)', mod_c)
    if settle and not 50 <= int(settle.group(1)) <= 1000:
        failures.append(
            "the settle is %s ms, which is either too short to damp a "
            "sweep or long enough that the words arrive after the player "
            "has moved on" % settle.group(1))

    cue = hint_fn.find("ETA_AudioCueSystem_PlayInteractionCue")
    speak = hint_fn.find("ETA_HudNarrator_SpeakInteraction")

    if cue < 0:
        failures.append(
            "the interaction cue is gone - the sound is the instant half "
            "of this and the words are the slow half; losing the sound "
            "means nothing is heard for a quarter of a second")
    elif speak < 0:
        failures.append("the hint is never spoken")
    elif cue > speak:
        failures.append(
            "the words are produced before the cue. The point of having "
            "both is that the sound is immediate and the words are not")

    # The plainest icon says only "Usable". The tester, in a tank, was
    # left to guess what; the thing under the crosshair is named first.
    # ET: Legacy only - the id Software tree is not what the tester plays,
    # and keeps the plain word.
    named = None if args.engine != "etlegacy" else  re.search(r"if \(what == ETA_INTERACT_USABLE\)\s*\{[^}]*ETA_UsableThingName\(thing, sizeof\(thing\)\);"
                      r"\s*ETA_HudNarrator_SpeakNamedInteraction\(thing, what, percent\);", hint_fn)
    namer = re.search(r"static void ETA_UsableThingName\(char \*out, size_t outSize\)\s*\{(.*?)\n\}", mod_c, re.S)
    if args.engine != "etlegacy":
        pass
    elif not named:
        failures.append("\"Usable\" is said without what it is")
    elif not namer or "CG_Trace(" not in namer.group(1) or "CG_AccessibilityObjectName(" not in namer.group(1) \
            or "ET_MG42_BARREL" not in namer.group(1) or "DotProduct(" not in namer.group(1):
        failures.append("what is usable is not named from what lies under the crosshair, ahead of the player")

    if failures:
        print("interaction_hint_test: FAIL (%s)" % args.engine)
        for line in failures:
            print("  - %s" % line)
        return 1

    print("interaction_hint_test: %s - all %d hint(s) the engine draws are "
          "accounted for by name, the pliers and the dynamite say so, and "
          "the words settle while the cue does not"
          % (args.engine, len(drawn_hints(draw, where["draw"]))))
    return 0


def state_for(mapping, hint):
    """The ETA_INTERACT_* a given hint's case falls through to."""
    at = re.search(r'case\s+%s\s*:' % re.escape(hint), mapping)
    if not at:
        return None
    after = re.search(r'return\s+(ETA_INTERACT_[A-Z_0-9]+)\s*;',
                      mapping[at.end():])
    return after.group(1) if after else None


def phrase_for(names, state):
    """The string the library returns for that state."""
    at = re.search(r'case\s+%s\s*:' % re.escape(state), names)
    if not at:
        return None
    after = re.search(r'return\s+"([^"]*)"\s*;', names[at.end():])
    return after.group(1) if after else None


if __name__ == "__main__":
    sys.exit(main())

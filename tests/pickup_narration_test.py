#!/usr/bin/env python3
"""Check that every pickup the engine shows on screen is also spoken.

Why this exists
---------------
Walking over something gave a sound and nothing else. A sighted player
reads what they picked up off the popup feed; a blind player had to
recognise the stock sound effect, which a new player cannot do at all.

The fix hangs the narration on `CG_ItemPickup`, which is where the
engine builds that popup. That placement is the whole of why it is
correct, and it is exactly what a later change could quietly break:

- **Both pickup events must funnel through it.** `EV_ITEM_PICKUP` /
  `EV_ITEM_PICKUP_QUIET` and `EV_GLOBAL_ITEM_PICKUP` each call it. If a
  future event path skipped it, that whole class of pickup would go
  silent while everything still compiled.
- **The spoken line must be the popup's own text.** The narration builds
  its string from `CG_PickupItemText`, the same call `CG_AddPMItem` is
  given. A separate table of names would drift from the screen, and
  would lose the engine's translations.

So this reads both properties out of the patched engine rather than
trusting that they still hold.

Usage
-----
    ./pickup_narration_test.py <engine-root>

Run it against an engine checkout with the patch series applied. Works
on both supported trees.
"""

import argparse
import os
import re
import sys

EVENT = os.path.join("src", "cgame", "cg_event.c")
DRAW = os.path.join("src", "cgame", "cg_draw.c")

NARRATOR = "ETA_NarrateItemPickup"
SAMPLER = "CG_AccessibilitySampleTotals"
FUNNEL = "CG_ItemPickup"
POPUP_TEXT = "CG_PickupItemText"

# The events that hand a pickup to the client.
PICKUP_EVENTS = ("EV_ITEM_PICKUP", "EV_ITEM_PICKUP_QUIET", "EV_GLOBAL_ITEM_PICKUP")


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


def function_body(text, name):
    match = re.search(r'\b%s\s*\([^;{}]*\)\s*\{' % re.escape(name), text)
    if not match:
        return None
    depth, i = 0, match.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def case_block(text, label):
    """The switch arm for one event.

    Brace-aware on purpose. These arms open a block and guard the item
    index with an early `break`, so "everything up to the first break"
    stops before the call that matters and reports a false failure - which
    is exactly what the first draft of this test did. Only a `break` at
    the arm's own depth ends it.

    Consecutive labels fall through to one shared body, so a label
    immediately followed by another is credited with what follows.
    """
    match = re.search(r'case\s+%s\s*:' % re.escape(label), text)
    if not match:
        return None

    i = match.end()

    # Skip labels that fall straight through to a shared body.
    while True:
        nxt = re.match(r'\s*(?:case\s+[A-Za-z0-9_]+|default)\s*:', text[i:])
        if not nxt:
            break
        i += nxt.end()

    depth = 0
    start = i
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:          # ran off the end of the switch
                return text[start:i]
        elif depth == 0:
            if text.startswith("break;", i):
                return text[start:i]
            nxt = re.match(r'(?:case\s+[A-Za-z0-9_]+|default)\s*:', text[i:])
            if nxt:
                return text[start:i]
        i += 1

    return text[start:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout, patch series applied")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    path = os.path.join(root, EVENT)

    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an Enemy Territory checkout?"
                 % (EVENT, root))

    with open(path, "r", errors="replace") as handle:
        text = strip_comments(handle.read())

    failures = []

    body = function_body(text, NARRATOR)
    if body is None:
        sys.exit("could not find %s in %s - the pickup narration this test "
                 "exists to guard is gone" % (NARRATOR, EVENT))

    funnel = function_body(text, FUNNEL)
    if funnel is None:
        sys.exit("could not find %s in %s - this test is out of date with "
                 "the engine, and passing without reading it would defeat "
                 "its purpose" % (FUNNEL, EVENT))

    # 1. The narration hangs off the funnel, not off one event path.
    if NARRATOR + "(" not in funnel.replace(" ", ""):
        failures.append(
            "%s does not call %s. Hanging the narration off an individual "
            "event instead means any pickup arriving by another event goes "
            "silent" % (FUNNEL, NARRATOR))
    else:
        print("[pickup] %s calls %s" % (FUNNEL, NARRATOR))

    # 2. Every pickup event still reaches the funnel.
    for event in PICKUP_EVENTS:
        arm = case_block(text, event)
        if arm is None:
            print("[pickup]   %s: not in this engine" % event)
            continue
        if FUNNEL + "(" in arm.replace(" ", ""):
            print("[pickup]   %s -> %s" % (event, FUNNEL))
        else:
            failures.append(
                "%s no longer reaches %s, so that kind of pickup would be "
                "drawn on screen and never spoken" % (event, FUNNEL))

    # 3. What is spoken is what is drawn.
    if POPUP_TEXT not in body:
        failures.append(
            "%s no longer builds its line from %s - the spoken name would "
            "be the mod's own and free to drift from the popup the engine "
            "draws, and would lose its translations" % (NARRATOR, POPUP_TEXT))
    else:
        print("[pickup] %s speaks the engine's own popup text" % NARRATOR)

    # 4. The "before" totals are sampled once a frame, from the draw
    #    path - never from the event path.
    #
    #    A pickup arrives with a new snapshot, and by the time the event
    #    is dispatched cg.snap->ps already holds what the server granted.
    #    The gain is only recoverable because the totals were recorded a
    #    frame earlier. Sample them anywhere inside snapshot processing
    #    and every pickup would measure itself against its own result:
    #    every gain reads zero and the mod says "already full" every
    #    time, which is worse than saying nothing because it is wrong.
    draw_path = os.path.join(root, DRAW)
    if not os.path.isfile(draw_path):
        sys.exit("no %s under %s" % (DRAW, root))

    with open(draw_path, "r", errors="replace") as handle:
        draw = strip_comments(handle.read())

    if SAMPLER not in text:
        failures.append(
            "%s is not defined in %s - there is nothing recording the "
            "totals a pickup is measured against" % (SAMPLER, EVENT))
    else:
        active = function_body(draw, "CG_DrawActive")
        if active is None:
            sys.exit("could not find CG_DrawActive in %s - this test is out "
                     "of date with the engine" % DRAW)

        if SAMPLER + "(" not in active.replace(" ", ""):
            failures.append(
                "%s is not called from CG_DrawActive. The totals have to be "
                "recorded once a frame, outside snapshot processing, or a "
                "pickup is measured against its own result and every gain "
                "reads zero" % SAMPLER)
        else:
            print("[pickup] %s runs once a frame from CG_DrawActive" % SAMPLER)

        if SAMPLER + "(" in (funnel or "").replace(" ", ""):
            failures.append(
                "%s is called from %s. Re-sampling at pickup time destroys "
                "the comparison the gain depends on" % (SAMPLER, FUNNEL))

    if failures:
        print()
        for failure in failures:
            print("[pickup] FAIL %s" % failure)
        sys.exit(1)

    print("[pickup] ok")


if __name__ == "__main__":
    main()

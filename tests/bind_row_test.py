#!/usr/bin/env python3
"""Check the controls list can be read and changed without a mouse.

Why this exists
---------------
A tester went to the controls list and reported that it "didn't tell me
which keys are being bound", and concluded from that the controls were
still not changeable at all. Both halves of that are worth pinning down,
because they are different failures with the same symptom - silence.

**Reading.** A bind row draws its label and, beside it, the key it is
on. The narration spoke only the label, so seventy-seven rows all
announced themselves as a name and nothing else: "Crouch" tells a player
the control exists and nothing about it. The key is the entire content
of the row.

**Changing.** The row asked for the mouse pointer to be inside it before
Enter would start a capture, which from the keyboard can never be true -
the same defect that made game types unchangeable, in the last control
still carrying it.

**And the capture itself is a trap when it is silent.** Pressing Enter
puts the game into a state where the very next key pressed becomes the
binding. A sighted player sees the row turn red. A player who hears
nothing does not know the game is waiting on them, and finds out by
pressing something.

What it requires
----------------
  * the spoken row is built from the engine's own rendering of the
    binding, not from a string assembled here
  * "no binding" is said in words, not read out as the punctuation the
    engine draws
  * Enter reaches the row from the keyboard
  * all four outcomes speak: the capture opening, a key taken, a clear,
    and a cancel
  * a cancel and a clear read the binding back rather than just saying
    something happened

Usage
-----
    ./bind_row_test.py <engine-root> [--engine etlegacy|id-software]

Run it against a checkout with the patch series applied.
"""

import argparse
import os
import re
import sys

PLACES = {
    "etlegacy": os.path.join("src", "ui", "ui_menuitem.c"),
    "id-software": os.path.join("src", "ui", "ui_shared.c"),
}

# Where each engine decides what a focused item says. ET: Legacy builds
# the "label, value" text in one place; the 2010 tree, which has no such
# helper, composes it at the point it narrates focus.
SPEAKS_FOCUS = {
    "etlegacy": "ETA_MenuItem_SettingText",
    "id-software": "Item_SetFocus",
}

# The engine's own name for "nothing is bound here". It is drawn as
# punctuation, which a screen reader reads as punctuation.
UNBOUND_DRAWN = '"(?'


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def body_of(text, name, where):
    match = re.search(r'\b%s\s*\([^;{]*\)\s*\{' % re.escape(name), text)
    if not match:
        sys.exit("could not find %s in %s - the narration this test "
                 "guards is gone, and passing without it would mean "
                 "nothing" % (name, where))

    depth, start = 0, match.end() - 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def bind_rows(root):
    """How many controls the stock menus actually offer."""
    directory = os.path.join(root, "etmain", "ui")
    if not os.path.isdir(directory):
        return None

    menus = [name for name in sorted(os.listdir(directory))
             if name.endswith(".menu")]
    if not menus:
        # The 2010 GPL drop ships none - its menus live in the pak
        # files rather than the source release - so there is nothing to
        # count and nothing wrong.
        return None

    count = 0
    for name in menus:
        with open(os.path.join(directory, name), "r",
                  errors="replace") as handle:
            count += len(re.findall(r'^\s*BIND\(', handle.read(), re.M))
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--engine", default="etlegacy",
                        choices=sorted(PLACES))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    where = PLACES[args.engine]
    source = read(root, where)
    failures = []

    # --- the row says which key it is on ------------------------------
    if "ETA_BindingText" not in source:
        failures.append(
            "%s no longer defines ETA_BindingText, so a controls row "
            "speaks its label and nothing else - which is what made a "
            "tester conclude the controls could not be changed at all"
            % where)
    else:
        binding_text = body_of(source, "ETA_BindingText", where)

        # It has to be the engine's own rendering. A second
        # implementation would drift from what is drawn beside the
        # label, and then the mod and the screen would disagree about
        # which key a control is on.
        if not re.search(r'Binding_?FromName', binding_text):
            failures.append(
                "ETA_BindingText does not use the engine's own "
                "BindingFromName, so what is spoken could drift from "
                "what is drawn beside the label")

        # And an unbound control has to be said in words.
        if "not bound" not in binding_text:
            failures.append(
                "ETA_BindingText has no words for a control that is not "
                "bound. The engine draws %s there, which a screen reader "
                "reads out as punctuation" % UNBOUND_DRAWN)

    # The reading has to be wired into what FOCUS speaks - not merely
    # used somewhere in the file. Arrowing down the list is how a player
    # reads it, and a helper that only the change path reaches leaves
    # every row still announcing a bare label.
    focus_fn = SPEAKS_FOCUS[args.engine]
    focus_body = body_of(source, focus_fn, where)

    if "ETA_BindingText" not in focus_body:
        failures.append(
            "%s does not reach ETA_BindingText, so arrowing onto a "
            "controls row still speaks the label alone - which is the "
            "report this was written for" % focus_fn)

    # --- and it can be changed from the keyboard ----------------------
    handler = body_of(source, "Item_Bind_HandleKey", where)

    if "ETA_ItemTakesKey" not in handler:
        failures.append(
            "Item_Bind_HandleKey still requires the mouse pointer to be "
            "inside the row before Enter will do anything, which from "
            "the keyboard can never be true - the row is unreachable")

    if "Rect_ContainsPoint" not in handler:
        failures.append(
            "Item_Bind_HandleKey no longer tests the pointer at all, so "
            "clicking a row is broken - the keyboard path is an "
            "addition, not a replacement")

    # --- every outcome says something ---------------------------------
    spoken = handler.count("ETA_MenuNarrator_OnValueChanged")
    if spoken < 4:
        failures.append(
            "Item_Bind_HandleKey speaks on %d of its four outcomes. "
            "Opening the capture, taking a key, clearing and cancelling "
            "all change what the control is on, and a player who hears "
            "nothing cannot tell which of them happened - least of all "
            "that the game is now waiting for a key" % spoken)

    for phrase, why in (
            ("press the key",
             "the capture opens silently, so a player presses Enter, "
             "hears nothing, and does not know the next key they touch "
             "becomes the binding"),
            ("not bound",
             "clearing a control says nothing, so it cannot be told "
             "from a key press that did not register"),
            ("unchanged",
             "cancelling says nothing, so a player cannot tell a cancel "
             "from a binding that silently failed"),
            ("bound to",
             "a key that was taken is not read back")):
        if phrase not in handler:
            failures.append("%s (looked for \"%s\")" % (why, phrase))

    # Cancelling and clearing must read the row back, not just announce
    # that something happened - after a cancel, what the control is on
    # is the one thing the player cannot infer from what they pressed.
    if handler.count("ETA_BindingText") < 2:
        failures.append(
            "Item_Bind_HandleKey reads the binding back on fewer than "
            "two of its outcomes. A cancel and a key taken both have to "
            "say where the control ended up")

    rows = bind_rows(root)
    if rows is not None and rows == 0:
        sys.exit("found no BIND rows in etmain/ui. This test cannot pass "
                 "vacuously: if the menus stopped defining controls, or "
                 "the macro was renamed, it has nothing to check")

    if failures:
        print("bind_row_test: FAIL (%s)" % args.engine)
        for failure in failures:
            print("  - %s" % failure)
        sys.exit(1)

    print("bind_row_test: %s - a controls row says which key it is on%s, "
          "Enter opens the capture from the keyboard, and all four "
          "outcomes speak"
          % (args.engine, "" if rows is None else " (%d rows)" % rows))


if __name__ == "__main__":
    main()

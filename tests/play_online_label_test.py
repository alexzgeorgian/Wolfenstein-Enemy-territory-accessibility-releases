#!/usr/bin/env python3
"""Check the main menu's first button is said as "Play online".

The button reads "PLAY" on screen and opens the Play Online screen, and
the tester knows it by that name. 1.4.4 looked for "open playonline" in
the button's action and was never matched: the menu parser keeps an
action as it rebuilt it, each word of more than one character in quotes
("open" "playonline"), so the tester still heard "Play". This rebuilds
the button's action from the stock main.menu the way the engine's
PC_Script_Parse does, and checks the label code's test against it:

- the parser still quotes words, as this test assumes;
- the label code names the menu the button is in, and looks for a word
  of the rebuilt action that names the screen it opens;
- and what it says is "Play online".

    ./play_online_label_test.py <engine-root>
"""

import os
import re
import sys

PARSE = os.path.join("src", "ui", "ui_parse.c")
ITEM = os.path.join("src", "ui", "ui_menuitem.c")
MAIN_MENU = os.path.join("etmain", "ui", "main.menu")


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this the engine checkout this test "
                 "expects?" % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def body_of(text, name):
    start = text.find(name + "(")
    while start != -1 and text.rfind("\n", 0, start) != -1 \
            and not re.match(r"[a-zA-Z_ *]*$", text[text.rfind("\n", 0, start) + 1:start]):
        start = text.find(name + "(", start + 1)
    if start == -1:
        return None
    open_brace = text.find("{", start)
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace:i + 1]
    return None


def menu_block(text, name):
    """The menuDef whose name is the one given."""
    for match in re.finditer(r"menuDef\s*\{", text):
        depth = 0
        for i in range(match.end() - 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    block = text[match.start():i + 1]
                    if re.search(r'\bname\s+"%s"' % re.escape(name), block):
                        return block
                    break
    return None


def rebuilt_action(raw):
    """The action as PC_Script_Parse keeps it: each token, a word of more
    than one character in quotes, followed by a space."""
    raw = re.sub(r"/\*.*?\*/", " ", raw, flags=re.S)
    tokens = re.findall(r"[A-Za-z0-9_\.\-]+|;", raw)
    return "".join(('"%s"' % t if len(t) > 1 else t) + " " for t in tokens)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = sys.argv[1]
    failures = []

    parse = read(root, PARSE)
    if 'va("\\"%s\\"", token.string)' not in parse:
        failures.append("PC_Script_Parse no longer quotes the words of an "
                        "action; this test's picture of a stored action is "
                        "out of date")

    menu = read(root, MAIN_MENU)
    block = menu_block(menu, "main")
    button = None
    if block:
        button = re.search(r'BUTTON\s*\((.*?_\("MSGID_MENU_MAIN_PLAY"\).*?)\)\s*\n', block, re.S)
    if not button:
        sys.exit("no MSGID_MENU_MAIN_PLAY button in the main menu of %s" % MAIN_MENU)
    args = button.group(1).split(",", 7)
    action = rebuilt_action(args[7] if len(args) == 8 else "")
    print("[play] stored action: %s" % action.strip())

    item = read(root, ITEM)
    label = body_of(item, "ETA_MenuItem_Label")
    if not label:
        sys.exit("no ETA_MenuItem_Label in %s" % ITEM)

    say = re.search(r'return\s+"(Play online)";', label)
    if not say:
        failures.append("ETA_MenuItem_Label no longer says \"Play online\"")

    needles = re.findall(r'Q_stristr\(item->action,\s*"([^"]+)"\)', label)
    if not needles:
        failures.append("ETA_MenuItem_Label no longer looks in the action "
                        "for the screen the button opens")
    for needle in needles:
        if needle.lower() not in action.lower():
            failures.append("ETA_MenuItem_Label looks for %r, which the "
                            "stored action %r never holds, so the button is "
                            "still said as \"Play\"" % (needle, action.strip()))

    menus = re.findall(r'window\.name,\s*"([^"]+)"\)', label)
    if "main" not in menus:
        failures.append("ETA_MenuItem_Label does not tie the name to the "
                        "main menu, so another button opening Play Online "
                        "would be renamed too")

    if failures:
        for failure in failures:
            print("[play] FAIL %s" % failure)
        sys.exit(1)
    print("[play] ok")


if __name__ == "__main__":
    main()

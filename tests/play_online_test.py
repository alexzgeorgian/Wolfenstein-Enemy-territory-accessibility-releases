#!/usr/bin/env python3
"""Check the Play Online page can be heard, every control on it.

The tester found the server browser went silent after the server name
box: the nine filter boxes beside it have no words of their own - the
screen labels them with small icons - and the server list itself said
nothing as it was arrowed through. This checks, against the patched
engine and the stock menu:

- every control on the page with no text of its own - each three-way
  filter box and the name box - is given a spoken name;
- a filter box's state is said without the dots the game draws, and a
  blank state is said for what it does;
- moving through any list says the row, and arriving on a list says
  what it lists and the row it is on;
- a server is said in words: name, map, game type, players and bots out
  of the maximum, the ping, and every icon the row would show;
- the number of servers found is said when a refresh ends.

    ./play_online_test.py <engine-root>
"""

import os
import re
import sys

MENU_ITEM = os.path.join("src", "ui", "ui_menuitem.c")
UI_MAIN = os.path.join("src", "ui", "ui_main.c")
PAGE = os.path.join("etmain", "ui", "playonline.menu")


def read(root, relative):
    path = os.path.join(root, relative)
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


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    item = read(root, MENU_ITEM)
    code = strip_comments(item)
    ui = strip_comments(read(root, UI_MAIN))
    page = read(root, PAGE)
    failures = []

    if "eta_unlabelled[]" not in item:
        sys.exit("no names for the page's unlabelled controls in %s - the feature this test measures is gone" % MENU_ITEM)

    # --- every unlabelled control on the page is named ---------------------
    named = set(re.findall(r'\{\s*"(ui_[A-Za-z]+)",\s*"[^"]+"\s*\}', item))
    unlabelled = set(re.findall(r'TRICHECKBOXACTIONMULTI\([^"]*"(ui_\w+)"', page))
    unlabelled |= set(re.findall(r'EDITFIELDSIMPLE\([^"]*"[^"]*",[^"]*"(ui_\w+)"', page))
    missing = sorted(unlabelled - named)
    if not unlabelled:
        failures.append("found no filter boxes on the Play Online page - the menu changed shape")
    elif missing:
        failures.append("these controls on the Play Online page have no spoken name: %s" % ", ".join(missing))
    else:
        print("[online] all %i unlabelled controls on the page are named: %s"
              % (len(unlabelled), ", ".join(sorted(unlabelled))))

    label = function_body(code, "ETA_MenuItem_Label")
    focus = function_body(code, "ETA_MenuItem_FocusText")
    setting = function_body(code, "ETA_MenuItem_SettingText")
    if "eta_unlabelled[i].label" not in label or "ETA_MenuItem_Label(item)" not in focus:
        failures.append("a control with no text of its own is still said without a name")
    elif "ETA_MenuNarrator_OnValueChanged(item->text," in code:
        failures.append("a value change is still said against the control's own text, which an "
                        "unlabelled control does not have, so it is not said at all")
    elif "setting[--length] = '\\0';" not in setting or '"only these"' not in setting:
        failures.append("a filter box's state is said with the game's dots, or a blank state is silent")
    else:
        print("[online] filter boxes say their name and state; changing one says the new state")

    # --- lists -------------------------------------------------------------
    handle = function_body(code, "Item_HandleKey")
    if "ETA_MenuItem_NarrateListRow(item);" not in handle or "item->cursorPos != before" not in handle:
        failures.append("moving through a list does not say the row")
    elif "ITEM_TYPE_LISTBOX" not in focus or "ETA_ListBoxRowText(item, row, sizeof(row))" not in focus:
        failures.append("arriving on a list does not say what it lists and the row it is on")
    else:
        print("[online] moving through a list says the row, and arriving on one says what it lists")

    rows = function_body(code, "ETA_ListBoxRowText")
    if "DC->feederItemText(item->special, index, j" not in rows or "Q_CleanStr(cell)" not in rows \
            or '", %i of %i"' not in rows:
        failures.append("a list row is not said from its columns, cleaned of colour codes, "
                        "with where it is in the list")

    # --- servers -----------------------------------------------------------
    server = function_body(ui, "UI_AccessibilityFeederRow")
    flags = [("needpass", "password"), ("friendlyFire", "friendly fire"), ("maxlives", "max lives"),
             ("weaprestrict", "weapon limits"), ("g_antilag", "anti-lag"), ("balancedteams", "balanced teams")]
    lost = [said for key, said in flags if '"%s"' % key not in server or '", %s"' % said not in server]
    if not server or "ETA_FeederRowText = UI_AccessibilityFeederRow;" not in ui:
        failures.append("a server in the list is not said in words")
    elif lost or '"mapname"' not in server or '"ping %i"' not in server or "clients - humans" not in server:
        failures.append("a server is said without its map, players and bots, ping, or these icons: %s"
                        % ", ".join(lost))
    else:
        print("[online] a server is said: name, map, game type, players and bots of the maximum, "
              "ping, and every icon its row shows")

    stop = function_body(ui, "UI_StopServerRefresh")
    if "UI_AccessibilityUpdateSay(" not in stop or "numDisplayServers" not in stop:
        failures.append("the number of servers found is not said when a refresh ends")
    else:
        print("[online] how many servers were found is said when a refresh ends")

    if failures:
        for failure in failures:
            print("[online] FAIL %s" % failure)
        sys.exit(1)
    print("play_online_test: every control on the Play Online page can be heard")


if __name__ == "__main__":
    main()

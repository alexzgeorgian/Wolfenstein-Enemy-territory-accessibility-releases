#!/usr/bin/env python3
"""Check the in-game updater is wired end to end.

The updater is four pieces in four places, and each joint between them
fails silently:

- the ui module opens a popup by name - a name with no menuDef behind it
  opens nothing, and the offer is never heard;
- each popup's buttons run a uiScript - one the ui module does not
  answer is a button that does nothing when pressed;
- a popup that is not marked `popup` is not read out when it opens, so
  the offer appears on a screen nobody can see;
- the release workflow writes eta-update.txt, and the ui module reads
  it - a key spelled differently on either side is an update check that
  finds nothing, forever, and says nothing about why;
- GitHub's releases/latest never names a pre-release, so a workflow that
  goes back to marking releases as pre-releases breaks every check;
- this repository is private, so the game reads a public copy of each
  release in another repository - the one the workflow copies to has to
  be the one the game asks, and a missing token has to stop the run
  rather than leave the public page a version behind with nobody told.

    ./update_popup_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
UI_MAIN = os.path.join("src", "ui", "ui_main.c")
POPUPS = os.path.join(REPO, "release", "ui", "accessibility_update.menu")
HUB = os.path.join(REPO, "release", "ui", "options_accessibility.menu")
BUILD = os.path.join(REPO, "release", "build-release.sh")
RELEASE = os.path.join(REPO, ".github", "workflows", "release.yml")
UPDATE_C = os.path.join(REPO, "src", "accessibility", "update", "update_check.c")
UPDATE_H = os.path.join(REPO, "src", "accessibility", "update", "update_check.h")


def read(path):
    if not os.path.isfile(path):
        sys.exit("no %s" % path)
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def strip_c_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def accessibility_blocks(text):
    """Only what sits inside #ifdef FEATURE_ACCESSIBILITY, so a feature
    that leaked outside its guard is not mistaken for wiring."""
    out, depth, ours = [], 0, []
    for line in text.splitlines():
        d = line.strip()
        if re.match(r"#\s*if", d):
            depth += 1
            ours.append(bool(re.match(r"#\s*ifdef\s+FEATURE_ACCESSIBILITY\b", d)))
            continue
        if re.match(r"#\s*endif", d):
            depth -= 1
            ours.pop()
            continue
        if any(ours):
            out.append(line)
    return "\n".join(out)


def menu_defs(text):
    """name -> body of each menuDef in a .menu file."""
    defs = {}
    for match in re.finditer(r"menuDef\s*\{", text):
        start = match.end()
        depth, i = 1, start
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[start:i - 1]
        name = re.search(r'\bname\s+"([^"]+)"', body)
        if name:
            defs[name.group(1)] = body
    return defs


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    root = os.path.abspath(sys.argv[1])
    failures = []

    ui = accessibility_blocks(strip_c_comments(read(os.path.join(root, UI_MAIN))))
    popups = read(POPUPS)
    hub = read(HUB)
    defs = menu_defs(popups)

    # --- the popups are loaded, and the ones the ui opens exist ---------
    if '"ui/accessibility_update.menu"' not in ui:
        failures.append("nothing in %s parses ui/accessibility_update.menu, "
                        "so every offer opens a menu that does not exist"
                        % UI_MAIN)

    opened = set(re.findall(r'"(eta_update_[a-z_]+)"', ui))
    if not opened:
        failures.append("the ui module opens no update popup at all")
    for name in sorted(opened - set(defs)):
        failures.append("the ui module opens %r, which no menuDef in "
                        "accessibility_update.menu is called" % name)
    for name in sorted(set(defs) - opened):
        failures.append("%r is in accessibility_update.menu but nothing "
                        "opens it" % name)

    # --- each one is read out, says the message, and can be left --------
    for name, body in sorted(defs.items()):
        if not re.search(r"^\s*popup\s*$", body, re.M):
            failures.append("%s is not marked popup, so it is not read out "
                            "when it opens" % name)
        if '"eta_updateMessage"' not in body:
            failures.append("%s does not show eta_updateMessage, so the "
                            "offer itself is never said" % name)
        if not re.search(r"onESC\s*\{[^}]*\bclose\s+%s\b" % name, body, re.S):
            failures.append("Escape does not close %s" % name)
        buttons = re.findall(r"BUTTON\(", body)
        if len(buttons) != 2:
            failures.append("%s has %d buttons; each popup is a question "
                            "with two answers" % (name, len(buttons)))
        else:
            print("[update] %s is a popup that says the offer and has two "
                  "answers" % name)

    # --- every script a button runs is answered --------------------------
    scripts = set(re.findall(r"uiScript\s+(accessibility\w+)", popups + hub))
    answered = set(re.findall(r'Q_stricmp\(name,\s*"(accessibility\w+)"\)', ui))
    for script in sorted(scripts - answered):
        failures.append("a button runs uiScript %s, which the ui module "
                        "does not answer - it would do nothing" % script)
    if "accessibilityUpdateCheck" not in scripts:
        failures.append("the ACCESSIBILITY menu has no CHECK FOR UPDATES "
                        "button")
    if scripts and not (scripts - answered):
        print("[update] all %d update script(s) are answered: %s"
              % (len(scripts), ", ".join(sorted(scripts))))

    # The ui module answers its scripts before the stock chain, so the
    # call has to be in UI_RunMenuScript, and the frame and shutdown
    # hooks have to be called.
    for call, why in (("UI_AccessibilityUpdateScript(name)", "no button would do anything"),
                      ("UI_AccessibilityUpdateFrame();", "no check would ever run"),
                      ("ETA_WindowsUpdate_Shutdown();", "a running download would be unloaded under its thread"),
                      ("UI_AccessibilityRegisterUpdateCvars();", "eta_updateCheck would not exist")):
        if call not in ui:
            failures.append("%s is never called, so %s" % (call, why))

    if not re.search(r'trap_Cvar_Register\([^,]+,\s*"eta_updateMessage"', ui):
        failures.append("eta_updateMessage is never registered")

    # --- the build packs the popups --------------------------------------
    build = read(BUILD)
    if not re.search(r"^\s*accessibility_update\.menu\s*\\$", build, re.M):
        failures.append("build-release.sh does not pack "
                        "accessibility_update.menu, so the pk3 ships without "
                        "the popups")
    for flag in ("-DETA_RELEASE_VERSION=", "-DETA_ENGINE_TAG="):
        if flag not in build:
            failures.append("build-release.sh does not pass %s, so a release "
                            "calls itself a development build and never "
                            "checks" % flag.strip("-="))

    # --- what the release writes is what the game reads ------------------
    written = set(re.findall(r'echo "([a-z0-9]+)=\$', build))
    parsed = set(re.findall(r'keyLength == \d+ && !strncmp\(line, "([a-z0-9]+)"',
                            read(UPDATE_C)))
    if not parsed:
        failures.append("read no manifest keys out of update_check.c - this "
                        "test is out of date")
    elif written != parsed:
        failures.append("build-release.sh writes %s into eta-update.txt but "
                        "the game reads %s" % (sorted(written), sorted(parsed)))
    else:
        print("[update] eta-update.txt is written and read with the same "
              "keys: %s" % ", ".join(sorted(parsed)))

    release = read(RELEASE)
    private_at = release.find("- name: Publish the release")
    public_at = release.find("- name: Copy the release to the public downloads page")
    if private_at < 0 or public_at < private_at:
        failures.append("the release workflow does not publish the release "
                        "and then copy it to the public downloads page")
        public_at = len(release)
    for where, publish in (("this repository", release[private_at:public_at]),
                           ("the public downloads page", release[public_at:])):
        for asset in ("zzz_accessibility.pk3", "eta-update.txt"):
            if publish.count(asset) < 2:
                failures.append("the release workflow does not upload %s to %s "
                                "on both a new release and a re-run" % (asset, where))
        if re.search(r"^\s*--prerelease\s*\\?$", publish, re.M):
            failures.append("the release workflow marks releases on %s as "
                            "pre-releases, which GitHub's releases/latest never "
                            "names - the game would never find an update" % where)
        if publish.count("--latest") < 2:
            failures.append("the release workflow does not mark every release "
                            "on %s as the latest" % where)

    # The copy the game reads: the same repository on both sides, written
    # with a token that can reach it, and no silent skip without one.
    public = release[public_at:]
    mirror = re.search(r"^\s*PUBLIC_RELEASES:\s*(\S+)\s*$", release, re.M)
    header = read(UPDATE_H)
    asked = re.search(r'"https://github\.com/([^/"]+/[^/"]+)/releases"', header)
    if not mirror or not asked:
        failures.append("could not read which repository the workflow copies "
                        "releases to, or which one the game asks")
    elif mirror.group(1) != asked.group(1):
        failures.append("the workflow copies releases to %s but the game asks "
                        "%s - no update would ever be found"
                        % (mirror.group(1), asked.group(1)))
    else:
        print("[update] the game asks %s, the public copy the release "
              "workflow writes" % asked.group(1))
    if asked and asked.group(1).endswith("/Wolfenstein-Enemy-territory-accessibility-mode"):
        failures.append("the game asks the private repository, whose releases "
                        "answer not found to a game that is not signed in")
    if "secrets.RELEASES_TOKEN" not in public or not re.search(r'if \[ -z "\$GH_TOKEN" \]; then\s*echo "::error::', public):
        failures.append("the public copy is not written with RELEASES_TOKEN, "
                        "or a missing token is skipped instead of failing the run")
    if "releases/latest/download/eta-update.txt" not in public or "curl -fsSL" not in public:
        failures.append("the release workflow does not fetch the public "
                        "eta-update.txt the way the game does to check it is there")

    if "/latest/download/eta-update.txt" not in header:
        failures.append("the game does not ask releases/latest for "
                        "eta-update.txt")

    # --- what is said at start-up, and where the player is ----------------
    # The tester asked to hear from the start whether there is a new
    # version - "Checking for updates", then the answer either way - and
    # then "Main menu"; and in a match, which menu Escape brought up.
    frame = re.search(r"static void UI_AccessibilityUpdateFrame\(void\)\s*\{(.*?)\n\}", ui, re.S)
    frame = frame.group(1) if frame else ""
    start = frame.find('UI_AccessibilityUpdateSay("Checking for updates.");')
    if start < 0 or start > frame.find("UI_AccessibilityUpdateStartCheck(qfalse);"):
        failures.append("the start-up check does not say it is checking")
    delay = re.search(r"#define ETA_UPDATE_STARTUP_DELAY_MS (\d+)", ui)
    if not delay or int(delay.group(1)) > 3000:
        failures.append("the start-up check waits so long it is not the first "
                        "thing heard")
    checked = re.search(r"static void UI_AccessibilityUpdateChecked\(void\)\s*\{(.*?)\n\}", ui, re.S)
    checked = checked.group(1) if checked else ""
    if 'UI_AccessibilityStartupSay(va("You have the latest version, %s.", version));' not in checked:
        failures.append("at start-up, being up to date is not said")
    if ui.count('UI_AccessibilityStartupSay("Could not check for updates.");') < 3:
        failures.append("a start-up check that fails is not said every way it "
                        "can fail - not starting, not reached, not understood")
    if "etaMenuTitle[0] = '\\0';" not in checked:
        failures.append("an offer does not take the place of the menu's name")
    say_menu = re.search(r"static void UI_AccessibilitySayMenu\(const char \*title\)\s*\{(.*?)\n\}", ui, re.S)
    if not say_menu or "UI_AccessibilityStartupCheckPending()" not in say_menu.group(1):
        failures.append("the menu's name does not wait for the start-up check's "
                        "answer, and would be cut off by it")
    if ui.count('UI_AccessibilitySayMenu("Main menu");') < 2 or 'UI_AccessibilitySayMenu("In-game menu");' not in ui:
        failures.append("the main menu or the in-game menu does not say which it "
                        "is when it opens")
    limbo = read(os.path.join(root, "src", "cgame", "cg_limbopanel.c"))
    if 'ETA_Speech_Say("Limbo menu");' not in limbo \
            or not re.search(r"#ifdef FEATURE_ACCESSIBILITY\s*CG_AccessibilityLimboOpened\(\);\s*#endif\s*\}", limbo):
        failures.append("the limbo panel does not say which menu it is")
    if not [f for f in failures if "start-up" in f or "menu" in f]:
        print("[update] at start-up: checking, then the answer and the menu's "
              "name together; each menu says which it is")

    if failures:
        for failure in failures:
            print("[update] FAIL %s" % failure)
        sys.exit(1)

    print("update_popup_test: the updater is wired from the release "
          "workflow through to the popups")


if __name__ == "__main__":
    main()

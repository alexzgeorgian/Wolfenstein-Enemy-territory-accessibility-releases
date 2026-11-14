#!/usr/bin/env python3
"""Check the ladder sounds read the map the way the engine does, and that
a thing above or below the player is said to be.

Ladders are not entities, so the sound on them comes from the map file
itself (src/accessibility/map/bsp_ladders.c). That reader keeps its own
copy of the map format's numbers - the version, which lump is which, how
big each record is, which bit marks a ladder - and the engine's brush
loader's rule for which faces of a brush are its box. Every one of those
agreeing with the engine is the difference between a knock on the ladder
and a knock in the middle of a room: so each is read out of the engine
here and compared.

Then the joints in the game:

- the map is read as it loads, from the same file the collision map was
  just loaded from;
- the sound plays only in play, can be switched off, stops while
  climbing, and is the ladder's own sound in the loop table;
- the command map survey counts the ladders in a square;
- an objective, the approach to it, and anything the use key turns to
  say how far up or down it is, measured as the thing minus the player,
  so "above" is above.

    ./ladder_cues_test.py <engine-root>
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
READER = os.path.join(REPO, "src", "accessibility", "map", "bsp_ladders.c")
NARRATOR = os.path.join(REPO, "src", "accessibility", "hud", "hud_narrator.c")
SOUNDS = os.path.join(REPO, "release", "make-cue-sounds.py")
AUTOEXEC = os.path.join(REPO, "release", "autoexec.cfg")
MENU = os.path.join(REPO, "release", "ui", "options_accessibility_environment.menu")

QFILES = os.path.join("src", "qcommon", "qfiles.h")
SURFACE = os.path.join("src", "game", "surfaceflags.h")
CM_LOAD = os.path.join("src", "qcommon", "cm_load.c")
SHARED = os.path.join("src", "qcommon", "q_shared.h")
DRAW = os.path.join("src", "cgame", "cg_draw.c")
MAIN = os.path.join("src", "cgame", "cg_main.c")
LOCAL = os.path.join("src", "cgame", "cg_local.h")
CONSOLE = os.path.join("src", "cgame", "cg_consolecmds.c")
COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")


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
        return None
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def define(text, name):
    match = re.search(r"#define\s+%s\s+(.+?)\s*$" % re.escape(name), text, re.M)
    return strip_comments(match.group(1)).strip() if match else None


def number(text):
    text = strip_comments(text).strip()
    return int(text, 0)


def struct_size(qfiles, name, constants):
    """Bytes in one of the map file's records, from its typedef."""
    match = re.search(r"typedef struct\s*\{([^}]*)\}\s*%s\s*;" % re.escape(name), qfiles)
    if not match:
        return None
    size = 0
    for line in strip_comments(match.group(1)).split(";"):
        line = line.strip()
        if not line:
            continue
        kind, names = line.split(None, 1)
        each = {"int": 4, "float": 4, "char": 1}[kind]
        for field in names.split(","):
            count = 1
            for dim in re.findall(r"\[(\w+)\]", field):
                count *= int(constants.get(dim, dim))
            size += each * count
    return size


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    root = os.path.abspath(sys.argv[1])
    failures = []

    reader = read(READER)
    qfiles = read(os.path.join(root, QFILES))

    # --- the map format, as the engine has it -------------------------
    constants = {"MAX_QPATH": number(define(read(os.path.join(root, SHARED)), "MAX_QPATH"))}
    engine = {
        "ETA_BSP_VERSION": number(define(qfiles, "BSP_VERSION")),
        "ETA_BSP_LUMPS": number(define(qfiles, "HEADER_LUMPS")),
        "ETA_BSP_SHADERS": number(define(qfiles, "LUMP_SHADERS")),
        "ETA_BSP_PLANES": number(define(qfiles, "LUMP_PLANES")),
        "ETA_BSP_MODELS": number(define(qfiles, "LUMP_MODELS")),
        "ETA_BSP_BRUSHES": number(define(qfiles, "LUMP_BRUSHES")),
        "ETA_BSP_BRUSHSIDES": number(define(qfiles, "LUMP_BRUSHSIDES")),
        "ETA_BSP_SHADER_SIZE": struct_size(qfiles, "dshader_t", constants),
        "ETA_BSP_PLANE_SIZE": struct_size(qfiles, "dplane_t", constants),
        "ETA_BSP_MODEL_SIZE": struct_size(qfiles, "dmodel_t", constants),
        "ETA_BSP_BRUSH_SIZE": struct_size(qfiles, "dbrush_t", constants),
        "ETA_BSP_SIDE_SIZE": struct_size(qfiles, "dbrushside_t", constants),
        "ETA_SURF_LADDER": number(define(read(os.path.join(root, SURFACE)), "SURF_LADDER")),
    }
    for name, value in sorted(engine.items()):
        ours = define(reader, name)
        if ours is None or value is None or number(ours) != value:
            failures.append("bsp_ladders.c has %s %s, the engine %s - the "
                            "reader would misread every map" % (name, ours, value))
    if define(reader, "ETA_BSP_IDENT") != define(qfiles, "BSP_IDENT"):
        failures.append("bsp_ladders.c and the engine disagree on the map "
                        "file's first four bytes")
    if not [f for f in failures if "bsp_ladders.c" in f]:
        print("[ladders] the reader's map format matches the engine's: "
              "version %d, %d lumps, records of %d/%d/%d/%d/%d bytes"
              % (engine["ETA_BSP_VERSION"], engine["ETA_BSP_LUMPS"],
                 engine["ETA_BSP_SHADER_SIZE"], engine["ETA_BSP_PLANE_SIZE"],
                 engine["ETA_BSP_MODEL_SIZE"], engine["ETA_BSP_BRUSH_SIZE"],
                 engine["ETA_BSP_SIDE_SIZE"]))

    # The fields inside each record, at the offsets the reader uses.
    dshader = re.search(r"typedef struct\s*\{\s*char shader\[MAX_QPATH\];\s*int surfaceFlags;", qfiles)
    dmodel = re.search(r"float mins\[3\], maxs\[3\];\s*int firstSurface, numSurfaces;\s*int firstBrush, numBrushes;", qfiles)
    if not dshader or "ETA_Bsp_Int(shader + 64)" not in reader:
        failures.append("a shader's surface flags are not where the reader "
                        "looks for them")
    if not dmodel or "ETA_Bsp_Int(model + 32)" not in reader or "ETA_Bsp_Int(model + 36)" not in reader:
        failures.append("the world model's brushes are not where the reader "
                        "looks for them")

    # The engine's box rule: sides 0..5 are -x +x -y +y -z +z.
    bound = function_body(strip_comments(read(os.path.join(root, CM_LOAD))), "CM_BoundBrush")
    rule = re.findall(r"b->bounds\[(\d)\]\[(\d)\]\s*=\s*(-?)b->sides\[(\d)\]\.plane->dist", bound or "")
    expect = [("0", "0", "-", "0"), ("1", "0", "", "1"), ("0", "1", "-", "2"),
              ("1", "1", "", "3"), ("0", "2", "-", "4"), ("1", "2", "", "5")]
    ours = re.findall(r"ladder\.(mins|maxs)\[(\d)\]\s*=\s*(-?)ladders\[i\]\.dist\[(\d)\]", reader)
    ours = [("0" if m == "mins" else "1", axis, sign, side) for m, axis, sign, side in ours]
    if sorted(rule) != sorted(expect):
        failures.append("CM_BoundBrush no longer takes a brush's box from its "
                        "first six faces - the reader's boxes are wrong")
    elif sorted(ours) != sorted(expect):
        failures.append("the reader does not take a ladder's box from its "
                        "faces the way CM_BoundBrush does: %s" % ours)
    else:
        print("[ladders] boxes from the first six faces, as CM_BoundBrush")

    # --- read as the map loads ----------------------------------------
    main_c = strip_comments(read(os.path.join(root, MAIN)))
    init = main_c[main_c.find("trap_CM_LoadMap(cgs.mapname);"):]
    if not re.match(r"trap_CM_LoadMap\(cgs\.mapname\);\s*#ifdef FEATURE_ACCESSIBILITY\s*CG_AccessibilityLoadLadders\(\);", init):
        failures.append("the ladders are not read right after the collision "
                        "map is loaded")
    draw = strip_comments(read(os.path.join(root, DRAW)))
    reopen = function_body(draw, "ETA_MapFileRestart") or ""
    if "trap_FS_FOpenFile(cgs.mapname" not in reopen or "FS_READ" not in reopen:
        failures.append("the ladder reader does not open the map the engine "
                        "just loaded")
    load = function_body(draw, "CG_AccessibilityLoadLadders") or ""
    if "ETA_BspLadders_Find(" not in load or "trap_FS_FCloseFile" not in load:
        failures.append("loading the ladders does not read the map and close "
                        "the file again")
    if not [f for f in failures if "loaded" in f or "open" in f or "close" in f]:
        print("[ladders] read from cgs.mapname as the map loads")

    # --- the sound ----------------------------------------------------
    beacon = function_body(draw, "ETA_BeaconLadders")
    if beacon is None:
        sys.exit("no ETA_BeaconLadders in %s" % DRAW)
    flat = re.sub(r"\s+", " ", beacon)
    for need, why in (("pm_type != PM_NORMAL", "it would play to a spectator or the dead"),
                      ("!eta_ladderCues.integer", "eta_ladderCues does not turn it off"),
                      ("CG_AccessibilityClimbing()", "it keeps knocking while the player climbs"),
                      ("CG_AccessibilityLoopSound(ETA_LOOP_LADDER)", "it does not play the ladder's sound"),
                      ("trap_S_AddLoopingSound(", "it never plays")):
        if need not in flat:
            failures.append("the ladder sound: %s" % why)
    if not re.search(r"ETA_BeaconLadders\(\);", draw.replace(beacon, "")):
        failures.append("ETA_BeaconLadders is never called")

    local = strip_comments(read(os.path.join(root, LOCAL)))
    enum_body = re.search(r"typedef enum\s*\{([^}]*)\}\s*eta_loopSoundType_t", local)
    table = re.search(r"eta_loopSounds\[\]\s*=\s*\{(.*?)\};", main_c, re.S)
    if not enum_body or not table:
        failures.append("could not read the loop sound enum and table")
    else:
        order = [e.strip().split("=")[0].strip() for e in enum_body.group(1).split(",") if e.strip()]
        rows = re.findall(r'"(eta_cue\w+)",\s*"sound/accessibility/([a-z_]+)\.wav"', table.group(1))
        at = order.index("ETA_LOOP_LADDER") if "ETA_LOOP_LADDER" in order else -1
        if at < 0 or at >= len(rows) or rows[at] != ("eta_cueLadder", "ladder"):
            failures.append("ETA_LOOP_LADDER does not index eta_cueLadder and "
                            "ladder.wav in the loop table")
        elif len(order) != len(rows):
            failures.append("the loop enum has %d sounds and the table %d"
                            % (len(order), len(rows)))
        else:
            print("[ladders] ETA_LOOP_LADDER plays ladder.wav, switchable as "
                  "eta_cueLadder")

    if not re.search(r'&eta_ladderCues,\s*"eta_ladderCues",\s*"1"', main_c):
        failures.append("eta_ladderCues is not registered on by default")

    if not re.search(r'^\s*"ladder\.wav":', read(SOUNDS), re.M):
        failures.append("make-cue-sounds.py does not make ladder.wav")
    autoexec = read(AUTOEXEC)
    for line in (r'seta eta_ladderCues\s+"1"', r'seta eta_cueLadder\s+"sound/accessibility/ladder\.wav"'):
        if not re.search(line, autoexec):
            failures.append("autoexec.cfg has no %s" % line.replace("\\", ""))
    loops = len(re.findall(r"^seta eta_cue\w+\s+\"sound/accessibility/", autoexec, re.M))
    words = {8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
             14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen"}
    if "The %s sounds the mod brings with it" % words.get(loops, loops) not in autoexec:
        failures.append("autoexec.cfg lists %d of the mod's own sounds but "
                        "does not say so" % loops)
    if '"eta_ladderCues"' not in read(MENU):
        failures.append("the ENVIRONMENT menu has no row for eta_ladderCues")

    # --- the survey ----------------------------------------------------
    cell = function_body(strip_comments(read(os.path.join(root, COMMANDMAP))), "ETA_MapCellContents") or ""
    if "CG_AccessibilityMapLadder(" not in cell or not re.search(r'ETA_MapAppendCount\([^;]*ladders,\s*"ladder"', cell):
        failures.append("the command map survey does not say the ladders in "
                        "a square")
    else:
        print("[ladders] the command map survey counts them")

    # --- up or down ----------------------------------------------------
    console = strip_comments(read(os.path.join(root, CONSOLE)))
    narrate = function_body(console, "CG_AccessibilityNarrateObjective") or ""
    if not re.search(r"AnnounceDistance\([^;]*;\s*ETA_NavigationSystem_AnnounceHeight\(\(objective\.origin\[2\] - ps->origin\[2\]\)", narrate):
        failures.append("the objective report does not say how far up or "
                        "down the objective is, right after how far")
    # The distances on the way are the marker's, the objective's own
    # taken out for them; they say up or down in the marker's name.
    approach = function_body(strip_comments(read(os.path.join(root, COMMANDMAP))),
                             "CG_AccessibilityMarkerApproach") or ""
    if not re.search(r"if \(ETA_NavigationSystem_UpdateMarkerApproach\([^{]*\{\s*ETA_NavigationSystem_AnnounceMarkerHeight\(\(eta_marker\.origin\[2\] - cg\.predictedPlayerState\.origin\[2\]\)", approach):
        failures.append("the distances called on the way to the marker "
                        "do not say up or down")
    aim = function_body(console, "ETA_AimSay") or ""
    if not re.search(r"ETA_HudNarrator_HeightText\(\(point\[2\] - cg\.predictedPlayerState\.origin\[2\]\)", aim) or "height" not in aim.split("ETA_Speech_Say", 1)[-1]:
        failures.append("what the use key turns to is not said with how far "
                        "up or down it is")
    narrator = read(NARRATOR)
    height = function_body(narrator, "ETA_HudNarrator_HeightText") or ""
    if not re.search(r'heightMeters > 0\.0f \? "above" : "below"', height):
        failures.append("HeightText does not say above for a positive "
                        "height - the objective minus the player")
    if not [f for f in failures if "up or down" in f or "above" in f]:
        print("[ladders] objectives, the approach and the use key say how "
              "far above or below")

    if failures:
        for failure in failures:
            print("[ladders] FAIL %s" % failure)
        sys.exit(1)

    print("ladder_cues_test: ladders are read the way the engine reads them, "
          "heard, surveyed, and height is said")


if __name__ == "__main__":
    main()

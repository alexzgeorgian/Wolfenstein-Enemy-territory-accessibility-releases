#!/usr/bin/env python3
"""Check SAPI 5 lets each line finish instead of cutting it off.

The tester, with NVDA closed, found SAPI 5 missing what NVDA said. Every
line was spoken with SPF_PURGEBEFORESPEAK, which stops whatever SAPI is
saying first; in a match the narrator says a few things a second, so
each line cut the one before it short. NVDA queues (its speakText waits
behind what it is saying), which is why only SAPI went wrong.

This checks windows_speech.c, which only runs on Windows:

- a line is spoken with SPF_ASYNC alone, queued behind the last;
- SPF_PURGEBEFORESPEAK is added only when a backlog of lines is already
  waiting, counted from SAPI's own status, so the voice never falls far
  behind;
- a stop still purges, so a key the player pressed cuts in at once;
- the file builds for Windows, where a cross-compiler is installed.

    ./speech_queue_test.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SPEECH = os.path.join(REPO, "src", "accessibility", "platform", "windows", "windows_speech.c")


def function_body(text, name):
    match = re.search(r"\b%s\s*\([^;{)]*\)\s*\{" % re.escape(name), text)
    if not match:
        return ""
    depth, i = 1, match.end()
    while depth and i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[match.end():i - 1]


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def main():
    with open(SPEECH, "r", errors="replace") as handle:
        source = handle.read()
    windows = source[:source.find("#else")]
    speak = strip_comments(function_body(windows, "ETA_WindowsSpeech_Speak"))
    waiting = strip_comments(function_body(windows, "ETA_WindowsSpeech_Waiting"))
    stop = strip_comments(function_body(windows, "ETA_WindowsSpeech_Stop"))
    backlog = re.search(r"#define\s+ETA_SAPI_BACKLOG\s+(\d+)", windows)
    failures = []

    if not speak:
        sys.exit("no ETA_WindowsSpeech_Speak in %s" % SPEECH)

    if not re.search(r"DWORD\s+flags\s*=\s*SPF_ASYNC;", speak):
        failures.append("a line is not spoken queued: SAPI cuts off whatever it was saying")
    elif not re.search(r"if \(ETA_WindowsSpeech_Waiting\(\) >= ETA_SAPI_BACKLOG\)\s*\{\s*flags \|= SPF_PURGEBEFORESPEAK;", speak):
        failures.append("the backlog is never cleared, so the voice can fall far behind the game")
    elif not backlog or not 1 <= int(backlog.group(1)) <= 5:
        failures.append("the backlog allowed is not a few lines")
    elif "ISpVoice_GetStatus" not in waiting or "ulLastStreamQueued - status.ulCurrentStream" not in waiting \
            or "SPRS_DONE" not in waiting:
        failures.append("the lines waiting are not counted from SAPI's own status")
    else:
        print("[sapi] a line is queued behind the last; only a backlog of %s is cleared" % backlog.group(1))

    if "SPF_PURGEBEFORESPEAK" not in stop:
        failures.append("stopping no longer cuts SAPI off, so a key pressed for an answer waits")
    else:
        print("[sapi] a stop still cuts in at once")

    compiler = shutil.which("x86_64-w64-mingw32-gcc")
    if compiler:
        with tempfile.TemporaryDirectory() as tmp:
            build = subprocess.run([compiler, "-std=gnu99", "-Wall", "-Werror", "-c", SPEECH,
                                    "-I", os.path.join(REPO, "src", "accessibility"),
                                    "-o", os.path.join(tmp, "speech.o")], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append("windows_speech.c does not build for Windows:\n%s" % build.stderr[-2000:])
        else:
            print("[sapi] builds for Windows, warnings as errors")
    else:
        print("[sapi] no Windows cross-compiler here; the Windows build job compiles it")

    if failures:
        for failure in failures:
            print("[sapi] FAIL %s" % failure)
        sys.exit(1)
    print("speech_queue_test: SAPI 5 lets each line finish")


if __name__ == "__main__":
    main()

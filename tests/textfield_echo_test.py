#!/usr/bin/env python3
"""Check that typing into a menu text box is spoken as the right character.

Why this exists
---------------
A text box is the one place in the menus where the player is producing
the content rather than choosing from it, and the only feedback they get
is the character echo. If that echo is off by one, or hands back half of
a multi-byte character, the field is worse than silent: it actively
misleads someone who cannot check the screen.

None of that is catchable by compiling. `ETA_CharacterAt` returning the
wrong character is perfectly well-formed C. It is only wrong to the
person listening - which is the same shape of defect as the mirrored
bearings, and is guarded the same way.

So this lifts the real character extractor out of the patched engine
tree, compiles it against that engine's own UTF-8 implementation, and
asks it for characters whose answers are known.

Lifting rather than copying is the point. A test carrying its own copy
of the function passes happily while the shipped one is broken.

What is checked
---------------
1. Plain ASCII, at the start and end of a field.
2. Out-of-range indices report nothing, so the caller can say "end"
   rather than read past the buffer.
3. The punctuation a server address and a player name are made of comes
   back as a spoken name - a space echoed as " " is silence, which is
   indistinguishable from the key not registering.
4. A multi-byte character comes back whole. Assuming one byte per
   character is the obvious mistake here and it produces a mojibake
   fragment, which is what a screen reader would then try to pronounce.

Usage
-----
    ./textfield_echo_test.py <engine-root>

Run it against an ET: Legacy tree with the patch series applied. It
exits non-zero on any mismatch.
"""

import argparse
import os
import subprocess
import sys
import tempfile

SOURCE = os.path.join("src", "ui", "ui_menuitem.c")
UNICODE = os.path.join("src", "qcommon", "q_unicode.c")

# The extractor and its punctuation table, lifted as one run of text.
# It ends at the close of ETA_CharacterAt rather than at whatever happens
# to follow it: anchoring on the next function's comment meant anything
# inserted between them was dragged in too, and the test then failed to
# compile for a reason that had nothing to do with what it checks.
BEGIN = "static const char *ETA_SpokenPunctuation(char c)"
LAST = "static qboolean ETA_CharacterAt("

# (field, index, expected spoken form); "<none>" means nothing was written.
CASES = [
    ("Alex", 0, "A"),
    ("Alex", 3, "x"),
    ("Alex", 4, "<none>"),
    ("Alex", -1, "<none>"),
    ("", 0, "<none>"),
    ("a b", 1, "space"),
    ("1.2", 1, "dot"),
    ("a-b", 1, "dash"),
    ("a_b", 1, "underscore"),
    ("h:27960", 1, "colon"),
    ("a/b", 1, "slash"),
    ("a@b", 1, "at"),
    ("s\\xc3\\xa9", 1, "\\xc3\\xa9"),
    ("\\xc3\\xa9x", 1, "x"),
]

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <stdlib.h>

typedef int qboolean;
#define qtrue 1
#define qfalse 0
size_t Q_UTF8_Strlen(const char *str);
int Q_UTF8_ByteOffset(const char *str, int offset);
#define Com_Memcpy memcpy
static void Q_strncpyz(char *d, const char *s, int n) { strncpy(d, s, n - 1); d[n - 1] = 0; }

/* Stubs for symbols q_unicode.c links against but these paths never
   reach. Aborting rather than returning keeps a silent wrong answer from
   passing as a right one. */
void Com_sprintf(char *d, int n, const char *f, ...) { (void)d; (void)n; (void)f; abort(); }
void Q_strncpyz_f(char *d, const char *s, int n, const char *file, int line)
{ (void)d; (void)s; (void)n; (void)file; (void)line; abort(); }

@@LIFTED@@

static int failures = 0;

static void expect(const char *label, const char *text, int index, const char *want)
{
    char got[64];
    qboolean ok = ETA_CharacterAt(text, index, got, sizeof(got));
    const char *shown = ok ? got : "<none>";

    if (strcmp(shown, want) != 0)
    {
        printf("[echo] FAIL %s [%d] -> %s, expected %s\n", label, index, shown, want);
        failures++;
    }
    else
    {
        printf("[echo]   %-12s [%2d] -> %s\n", label, index, shown);
    }
}

int main(void)
{
@@CASES@@
    if (failures)
    {
        printf("[echo] %d failure(s)\n", failures);
        return 1;
    }

    printf("[echo] ok\n");
    return 0;
}
'''


def lift(root):
    path = os.path.join(root, SOURCE)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is this an ET: Legacy checkout?" % (SOURCE, root))

    with open(path, "r", errors="replace") as handle:
        text = handle.read()

    if BEGIN not in text:
        sys.exit("%s has no ETA_SpokenPunctuation - is the patch series "
                 "applied? A pass here without it would be testing nothing"
                 % SOURCE)

    start = text.index(BEGIN)

    if LAST not in text[start:]:
        sys.exit("%s has no ETA_CharacterAt after ETA_SpokenPunctuation - "
                 "this extractor is out of date with the source" % SOURCE)

    last = start + text[start:].index(LAST)
    if "\n}\n" not in text[last:]:
        sys.exit("could not find the end of ETA_CharacterAt in %s" % SOURCE)

    end = last + text[last:].index("\n}\n") + len("\n}\n")
    return text[start:end]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="engine checkout with the patch series applied")
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    unicode_path = os.path.join(root, UNICODE)
    if not os.path.isfile(unicode_path):
        sys.exit("no %s under %s" % (UNICODE, root))

    lifted = lift(root)
    print("[echo] lifted %d bytes of ETA_CharacterAt from %s" % (len(lifted), SOURCE))

    body = ""
    for text, index, want in CASES:
        label = text if text else "(empty)"
        body += '    expect("%s", "%s", %d, "%s");\n' % (label, text, index, want)

    # Plain substitution, not %-formatting: the harness is C and is full
    # of its own printf conversions.
    program = HARNESS.replace("@@LIFTED@@", lifted).replace("@@CASES@@", body)

    with tempfile.TemporaryDirectory() as work:
        source = os.path.join(work, "echo.c")
        binary = os.path.join(work, "echo")
        with open(source, "w") as handle:
            handle.write(program)

        build = subprocess.run([args.cc, "-std=gnu90", "-o", binary, source, unicode_path],
                               capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stderr)
            sys.exit("[echo] the lifted extractor did not compile against the "
                     "engine's own UTF-8 code")

        # Bytes, not text. The defect this test exists to catch produces a
        # broken multi-byte character, and decoding strictly would abort on
        # it with a traceback instead of reporting which case failed - the
        # test would be least readable in exactly the case it is for.
        run = subprocess.run([binary], capture_output=True)
        sys.stdout.write(run.stdout.decode("utf-8", errors="replace"))
        if run.stderr:
            sys.stderr.write(run.stderr.decode("utf-8", errors="replace"))
        sys.exit(run.returncode)


if __name__ == "__main__":
    main()

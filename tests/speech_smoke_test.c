#include "core/accessibility_runtime.h"
#include "smoke_check.h"
#include "speech/speech_manager.h"

#include <stdlib.h>
#include <string.h>

static char *OverlongText(size_t length)
{
    char *text = (char *)malloc(length + 1);

    memset(text, 'a', length);
    text[length] = '\0';

    return text;
}

int main(void)
{
    char *overlong;

    SMOKE_BANNER("speech");

    /* Lifecycle: nothing should report the runtime as running before Init. */
    CHECK(!ETA_AccessibilityRuntime_IsRunning());
    CHECK(ETA_AccessibilityRuntime_GetState() == ETA_ACCESSIBILITY_RUNTIME_STOPPED);

    ETA_AccessibilityRuntime_Init();

    CHECK(ETA_AccessibilityRuntime_IsRunning());
    CHECK(ETA_AccessibilityRuntime_GetState() == ETA_ACCESSIBILITY_RUNTIME_RUNNING);

    ETA_AccessibilityRuntime_RunSpeechSmokeTest();

    CHECK_ACCEPTS(ETA_Speech_Say("Accessibility speech online"));
    CHECK_ACCEPTS(ETA_Speech_RepeatLast());
    CHECK_ACCEPTS(ETA_Speech_Stop());

    /* Everything the engine narrates funnels through Say, so its guard is the
       last line of defence for a null or empty string coming out of the game. */
    CHECK_REJECTS(ETA_Speech_Say(NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_Speech_Say(""), ETA_ERROR_INVALID_STRING);

    overlong = OverlongText(ETA_MAX_SPEECH_TEXT_LENGTH + 1);
    CHECK_REJECTS(ETA_Speech_Say(overlong), ETA_ERROR_STRING_TOO_LONG);
    free(overlong);

    overlong = OverlongText(ETA_MAX_SPEECH_TEXT_LENGTH);
    CHECK_ACCEPTS(ETA_Speech_Say(overlong));
    free(overlong);

    /* A rejected message must not become the repeat target: repeating after a
       failed Say should still replay the last message that was accepted. */
    CHECK_ACCEPTS(ETA_Speech_Say("Last good message"));
    CHECK_REJECTS(ETA_Speech_Say(NULL), ETA_ERROR_NULL_POINTER);
    CHECK_ACCEPTS(ETA_Speech_RepeatLast());

    /*
     * Report batching.
     *
     * This exists because of a defect that shipped: the SAPI backend speaks
     * with SPF_PURGEBEFORESPEAK, so every message cancels the one still being
     * spoken. A status report built from six Say calls was therefore audible
     * only as its last fragment, and which fragment survived depended on
     * which backend the player happened to be running. Composing the report
     * into one message removes the dependency on backend behaviour, and this
     * checks the composition rather than trusting it.
     */
    ETA_Speech_BeginReport();
    ETA_Speech_Say("Health 80");
    ETA_Speech_Say("Thompson");
    ETA_Speech_Say("Ammo 30");
    ETA_Speech_EndReport();
    CHECK(ETA_Speech_GetLastMessage() != NULL);
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Health 80, Thompson, Ammo 30") == 0);

    /* The game's markup is never read out. The main menu's Play button is
       stored as "PL^_AY" - "^_" marks the hotkey letter - and a tester
       heard it spelled out in both NVDA and SAPI 5. Colour codes are the
       same shape ("^1Axis^7"), and are in every player's name. */
    ETA_Speech_Say("PL^_AY");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "PLAY") == 0);
    ETA_Speech_Say("^_HOST");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "HOST") == 0);
    ETA_Speech_Say("^1Ax^7is ^3Rifleman");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Axis Rifleman") == 0);
    /* In a report too, part by part. */
    ETA_Speech_BeginReport();
    ETA_Speech_Say("^2Pl^_ayer");
    ETA_Speech_Say("45 XP");
    ETA_Speech_EndReport();
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Player, 45 XP") == 0);
    /* What the engine does not count as a code is left alone: a caret
       before a space, at the end, doubled, or before a byte of a
       multi-byte character. */
    ETA_Speech_Say("5 ^ 2 ^^ up^");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "5 ^ 2 ^^ up^") == 0);
    ETA_Speech_Say("a^\xc3\xa9" "b");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "a^\xc3\xa9" "b") == 0);
    /* A line that is nothing but markup says nothing. */
    ETA_Speech_Say("Marker before markup-only line");
    ETA_Speech_Say("^7^_");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Marker before markup-only line") == 0);

    /* One part is still one line, with no stray separator at either end. */
    ETA_Speech_BeginReport();
    ETA_Speech_Say("Health 80");
    ETA_Speech_EndReport();
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Health 80") == 0);

    /* An empty report says nothing rather than speaking an empty string,
       which the guard would reject and log as an error. */
    CHECK_ACCEPTS(ETA_Speech_Say("Marker before empty report"));
    ETA_Speech_BeginReport();
    ETA_Speech_EndReport();
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Marker before empty report") == 0);

    /* End without Begin is a no-op, not a crash or a repeat. */
    ETA_Speech_EndReport();
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Marker before empty report") == 0);

    /* A report left open speaks nothing: Say collects instead of speaking,
       so the last spoken line must not have changed. */
    ETA_Speech_BeginReport();
    ETA_Speech_Say("Collected, never spoken");
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Marker before empty report") == 0);
    ETA_Speech_EndReport();
    CHECK(strcmp(ETA_Speech_GetLastMessage(), "Collected, never spoken") == 0);

    /* A part that would overflow is dropped whole, and drops its separator
       with it: half a weapon name or half a distance is worse than silence,
       and a trailing ", " would be read out as a pause into nothing. */
    {
        char *bulk = OverlongText(ETA_MAX_SPEECH_TEXT_LENGTH - 4);

        ETA_Speech_BeginReport();
        ETA_Speech_Say(bulk);
        ETA_Speech_Say("this part cannot fit");
        ETA_Speech_EndReport();
        CHECK(strcmp(ETA_Speech_GetLastMessage(), bulk) == 0);
        free(bulk);
    }

    /* The serial and the duration estimate, which together are how the
       music knows to get out of the way. A tester turned the music up and
       found the narrator underneath it. */
    {
        int before = ETA_Speech_GetSpokenSerial();

        /* Every line the mod decides to say advances it, including a
           repeat - a repeat is speech, and the music owes it the same
           room as the first time. */
        ETA_Speech_Say("Health 42");
        CHECK(ETA_Speech_GetSpokenSerial() == before + 1);

        ETA_Speech_RepeatLast();
        CHECK(ETA_Speech_GetSpokenSerial() == before + 2);

        /* A report is one line, so it advances the serial once however
           many parts went into it. Ducking per part would re-dip the
           music in the middle of a sentence. */
        before = ETA_Speech_GetSpokenSerial();
        ETA_Speech_BeginReport();
        ETA_Speech_Say("Health 42");
        ETA_Speech_Say("Thompson");
        ETA_Speech_Say("objective 2 of 4");
        ETA_Speech_EndReport();
        CHECK(ETA_Speech_GetSpokenSerial() == before + 1);

        /* An empty report speaks nothing, so it owes the music nothing. */
        before = ETA_Speech_GetSpokenSerial();
        ETA_Speech_BeginReport();
        ETA_Speech_EndReport();
        CHECK(ETA_Speech_GetSpokenSerial() == before);

        /* Nothing to say is nothing to wait for. */
        CHECK(ETA_Speech_EstimateDurationMs(NULL) == 0);
        CHECK(ETA_Speech_EstimateDurationMs("") == 0);

        /* Longer lines take longer, and both ends are clamped: a
           two-word answer still outlasts the dip, and no line mutes the
           music indefinitely. */
        CHECK(ETA_Speech_EstimateDurationMs("Sky") == ETA_SPEECH_MIN_DURATION_MS);
        CHECK(ETA_Speech_EstimateDurationMs("Concrete ground, 3 meters")
              > ETA_Speech_EstimateDurationMs("Sky"));

        {
            char *bulk = OverlongText(ETA_MAX_SPEECH_TEXT_LENGTH - 4);

            CHECK(ETA_Speech_EstimateDurationMs(bulk) == ETA_SPEECH_MAX_DURATION_MS);
            free(bulk);
        }

        /* The estimate must outlast the fade down, or the music would be
           told to come back up before it had finished going down. */
        CHECK(ETA_SPEECH_MIN_DURATION_MS > 0);
        CHECK(ETA_SPEECH_MAX_DURATION_MS > ETA_SPEECH_MIN_DURATION_MS);
    }

    /* The SAPI voice settings. These come from cvars, and a cvar holds
       whatever somebody typed - SAPI's own setters fail silently on a
       value out of range, which looks exactly like a setting that does
       nothing. */
    {
        ETA_Speech_SetVoice(3, -2, 80);
        CHECK(ETA_Speech_GetVoiceRate() == 3);
        CHECK(ETA_Speech_GetVoicePitch() == -2);
        CHECK(ETA_Speech_GetVoiceVolume() == 80);

        ETA_Speech_SetVoice(999, -999, 999);
        CHECK(ETA_Speech_GetVoiceRate() == ETA_SPEECH_RATE_MAX);
        CHECK(ETA_Speech_GetVoicePitch() == ETA_SPEECH_PITCH_MIN);
        CHECK(ETA_Speech_GetVoiceVolume() == ETA_SPEECH_VOLUME_MAX);

        ETA_Speech_SetVoice(-999, 999, -999);
        CHECK(ETA_Speech_GetVoiceRate() == ETA_SPEECH_RATE_MIN);
        CHECK(ETA_Speech_GetVoicePitch() == ETA_SPEECH_PITCH_MAX);
        CHECK(ETA_Speech_GetVoiceVolume() == ETA_SPEECH_VOLUME_MIN);

        /* Back to the defaults, so nothing below inherits a shouted voice. */
        ETA_Speech_SetVoice(0, 0, ETA_SPEECH_VOLUME_MAX);
    }

    /* Escaping for the pitch markup. A player called "Tom & Jerry" or
       "<axis>" is not hypothetical, and an unescaped one would not
       mispronounce - it would make the line unparseable and silence it. */
    {
        char out[64];

        CHECK(ETA_Speech_EscapeXml("Health 42", out, sizeof(out)) == 9);
        CHECK(strcmp(out, "Health 42") == 0);

        ETA_Speech_EscapeXml("Tom & Jerry", out, sizeof(out));
        CHECK(strcmp(out, "Tom &amp; Jerry") == 0);

        ETA_Speech_EscapeXml("<axis>", out, sizeof(out));
        CHECK(strcmp(out, "&lt;axis&gt;") == 0);

        /* An ampersand must not be rescanned: &lt; escaped twice comes
           out as &amp;lt; and is read aloud as punctuation. */
        ETA_Speech_EscapeXml("&lt;", out, sizeof(out));
        CHECK(strcmp(out, "&amp;lt;") == 0);

        /* Truncation lands on a whole character. Half an entity would
           break the parse and take the whole line with it, which is a
           worse outcome than a clipped tail. */
        {
            char tiny[6];

            ETA_Speech_EscapeXml("a&b", tiny, sizeof(tiny));
            CHECK(strcmp(tiny, "a") == 0);

            /* And it always terminates, even with no room for anything. */
            tiny[0] = 'x';
            ETA_Speech_EscapeXml("&", tiny, 1);
            CHECK(tiny[0] == '\0');
        }

        /* A NULL in or out is answered rather than dereferenced. */
        CHECK(ETA_Speech_EscapeXml(NULL, out, sizeof(out)) == 0);
        CHECK(ETA_Speech_EscapeXml("x", NULL, sizeof(out)) == 0);
    }

    /* A page longer than one line can carry is said in pieces, each within
       the limit, split after a sentence, with its line breaks as spaces -
       except on the Mac, where VoiceOver keeps only the last of several
       announcements made at once, and the page goes whole. */
    {
        char page[2400];
        int  before = ETA_Speech_GetSpokenSerial();
        int  i;

        page[0] = '\0';
        for (i = 0; i < 40; i++)
        {
            strcat(page, "Meet Kessler in the village.\n\n   ");
        }
        ETA_Speech_SayLong(page);

#ifdef __APPLE__
        CHECK(ETA_Speech_GetSpokenSerial() - before == 1);
        CHECK(ETA_Speech_GetLastMessage() != NULL);
        CHECK(strlen(ETA_Speech_GetLastMessage()) > ETA_SPEECH_PIECE_LENGTH);
#else
        CHECK(ETA_Speech_GetSpokenSerial() - before >= 3);
        CHECK(ETA_Speech_GetLastMessage() != NULL);
        CHECK(strlen(ETA_Speech_GetLastMessage()) <= ETA_SPEECH_PIECE_LENGTH);
#endif
        CHECK(strchr(ETA_Speech_GetLastMessage(), '\n') == NULL);
        CHECK(ETA_Speech_GetLastMessage()[strlen(ETA_Speech_GetLastMessage()) - 1] == '.');

        before = ETA_Speech_GetSpokenSerial();
        ETA_Speech_SayLong("Good luck.");
        CHECK(ETA_Speech_GetSpokenSerial() - before == 1);
        CHECK(strcmp(ETA_Speech_GetLastMessage(), "Good luck.") == 0);

        CHECK_ACCEPTS(ETA_Speech_SayLong(NULL));
    }

    ETA_AccessibilityRuntime_Shutdown();

    CHECK(!ETA_AccessibilityRuntime_IsRunning());
    CHECK(ETA_AccessibilityRuntime_GetState() == ETA_ACCESSIBILITY_RUNTIME_STOPPED);

    return SMOKE_REPORT("speech");
}

#include "speech_manager.h"
#include "../core/runtime_guard.h"
#include "../platform/windows/windows_nvda.h"
#include "../platform/windows/windows_speech.h"
#ifdef __APPLE__
#include "../platform/macos/macos_speech.h"
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * A copy of every line spoken, appended to the file ETA_SPEECH_LOG names
 * when that is set. For testing a build where there is no one to listen:
 * the game run headless, on a system with no speech of its own. Unset, as
 * it is for every player, nothing is written.
 */
static void ETA_Speech_LogLine(const char *message)
{
    static FILE *log = NULL;
    static int   opened = 0;

    if (!opened)
    {
        const char *path = getenv("ETA_SPEECH_LOG");

        opened = 1;
        if (path && path[0])
        {
            log = fopen(path, "a");
        }
    }

    if (log)
    {
        fprintf(log, "%s\n", message);
        fflush(log);
    }
}

/* Big enough for a page said whole (ETA_Speech_SayLong, on the Mac). */
static char gLastSpeechMessage[4096];
static int gHasLastSpeechMessage = 0;

/*
 * Report batching. See the header for why this exists: a multi-part report
 * spoken as several messages is not heard whole on every backend, so it is
 * joined into one message here instead of trusting any of them to queue.
 */
static char gReportBuffer[ETA_MAX_SPEECH_TEXT_LENGTH + 1];
static int gReportOpen = 0;
static size_t gReportLength = 0;

/*
 * NVDA first, SAPI as the fallback.
 *
 * When a player is already running NVDA, speaking through it is the right
 * answer: the message inherits their voice, rate and punctuation settings,
 * and it queues with the rest of their screen reader output rather than
 * talking over it. SAPI, which speaks independently of any screen reader,
 * is what's left for players who don't run NVDA.
 *
 * The choice is made per message rather than once at startup, because
 * ETA_WindowsNvda_Speak reports whether NVDA actually took it. A player who
 * starts or quits NVDA mid-session is picked up on the next line spoken,
 * with no polling.
 */
static int gSpokenSerial = 0;

static void ETA_Speech_Dispatch(const char *message)
{
    /* Counted before the backends rather than after, and counted even when
       both of them drop the line. The counter's job is "the mod decided to
       say something just now", which is what the caller ducking the music
       needs to know; whether a screen reader was listening is not something
       either backend reports, and a duck that only happened when speech
       definitely came out would be a duck that never happened at all on a
       machine with no speech configured. */
    gSpokenSerial++;

    ETA_Speech_LogLine(message);

    if (ETA_WindowsNvda_Speak(message))
    {
        return;
    }

#ifdef __APPLE__
    /* The Mac's pair: VoiceOver, or the system voice when it is off. */
    if (ETA_MacSpeech_Speak(message))
    {
        return;
    }
#endif

    ETA_WindowsSpeech_Speak(message);
}

int ETA_Speech_GetSpokenSerial(void)
{
    return gSpokenSerial;
}

static int ETA_Speech_Clamp(int value, int low, int high)
{
    if (value < low)  { return low; }
    if (value > high) { return high; }
    return value;
}

static int gVoiceRate;
static int gVoicePitch;
static int gVoiceVolume = ETA_SPEECH_VOLUME_MAX;

void ETA_Speech_SetVoice(int rate, int pitch, int volume)
{
    /* Clamped here rather than at the call site, because the values come
       from cvars and a cvar holds whatever somebody typed. SAPI's own
       SetRate rejects anything outside its range and returns a failure
       nobody is reading, which would look exactly like a setting that
       does nothing. */
    gVoiceRate   = ETA_Speech_Clamp(rate, ETA_SPEECH_RATE_MIN, ETA_SPEECH_RATE_MAX);
    gVoicePitch  = ETA_Speech_Clamp(pitch, ETA_SPEECH_PITCH_MIN, ETA_SPEECH_PITCH_MAX);
    gVoiceVolume = ETA_Speech_Clamp(volume, ETA_SPEECH_VOLUME_MIN, ETA_SPEECH_VOLUME_MAX);

    ETA_WindowsSpeech_SetVoice(gVoiceRate, gVoicePitch, gVoiceVolume);
#ifdef __APPLE__
    ETA_MacSpeech_SetVoice(gVoiceRate, gVoicePitch, gVoiceVolume);
#endif
}

int ETA_Speech_GetVoiceRate(void)   { return gVoiceRate; }
int ETA_Speech_GetVoicePitch(void)  { return gVoicePitch; }
int ETA_Speech_GetVoiceVolume(void) { return gVoiceVolume; }

int ETA_Speech_EscapeXml(const char *in, char *out, size_t outSize)
{
    static const struct
    {
        char        character;
        const char *replacement;
    } escapes[] =
    {
        /* & first in spirit if not in order: it is the escape character,
           so a replacement containing it must never be rescanned. This
           loop copies the replacement straight out, so it is not, but the
           ordering is worth stating because getting it wrong produces
           &amp;lt; and nobody looks at the output. */
        { '&',  "&amp;"  },
        { '<',  "&lt;"   },
        { '>',  "&gt;"   },
        { '"',  "&quot;" },
        { '\'', "&apos;" }
    };

    size_t written = 0;
    size_t i;

    if (!in || !out || outSize == 0)
    {
        return 0;
    }

    for (i = 0; in[i]; i++)
    {
        const char *replacement = NULL;
        size_t      e;
        size_t      length;

        for (e = 0; e < sizeof(escapes) / sizeof(escapes[0]); e++)
        {
            if (in[i] == escapes[e].character)
            {
                replacement = escapes[e].replacement;
                break;
            }
        }

        length = replacement ? strlen(replacement) : 1;

        /* No room for this character and the terminator: stop on a whole
           character rather than emitting half an entity, which would make
           the whole line unparseable and silence it entirely. Losing the
           tail of a long sentence is survivable; losing all of it is not. */
        if (written + length + 1 > outSize)
        {
            break;
        }

        if (replacement)
        {
            memcpy(out + written, replacement, length);
        }
        else
        {
            out[written] = in[i];
        }

        written += length;
    }

    out[written] = '\0';
    return (int)written;
}

int ETA_Speech_EstimateDurationMs(const char *message)
{
    size_t length;
    int    estimate;

    if (!message)
    {
        return 0;
    }

    length = strlen(message);

    if (length == 0)
    {
        return 0;
    }

    /* An estimate, because neither backend will say. SAPI speaks
       asynchronously and NVDA's controller client has no completion
       callback at all - it has three entry points, and none of them is
       "tell me when you have finished". So the length of the line is the
       only evidence there is.

       ETA_SPEECH_MS_PER_CHARACTER is set for a deliberately unhurried
       voice. Guessing slow costs a few hundred milliseconds of music
       staying quiet after the words end, which nobody notices; guessing
       fast brings the music up over the end of a sentence, which is
       exactly the complaint this exists to fix. The rise is slow for the
       same reason - an estimate that expires early should be heard as the
       music coming back, not as a click. */
    estimate = (int)length * ETA_SPEECH_MS_PER_CHARACTER;

    if (estimate < ETA_SPEECH_MIN_DURATION_MS)
    {
        estimate = ETA_SPEECH_MIN_DURATION_MS;
    }

    if (estimate > ETA_SPEECH_MAX_DURATION_MS)
    {
        estimate = ETA_SPEECH_MAX_DURATION_MS;
    }

    return estimate;
}

void ETA_Speech_Init(void)
{
    ETA_WindowsNvda_Init();

    /* SAPI comes up either way, so the fallback is ready if NVDA goes away. */
    ETA_WindowsSpeech_Init();

#ifdef __APPLE__
    ETA_MacSpeech_Init();
#endif
}

/*
 * The game's own markup, taken out before anything is spoken.
 *
 * ET writes colour into its text as a caret and one character - "^1"
 * for red, "^7" for white - and marks a menu button's hotkey the same
 * way with "^_", so the main menu's "Play" is stored as "PL^_AY". Drawn,
 * both vanish. Spoken, a screen reader reads them out: a tester heard
 * the Play button spelled "P L", a symbol, "A Y", in both NVDA and
 * SAPI 5. The rule is the engine's own (Q_IsColorString): a caret
 * followed by any printable character other than another caret, which
 * leaves a caret before a space or the end of the line, and "^^", as
 * they were. Only ASCII counts as printable here, so a caret in front
 * of a multi-byte character never takes half the character with it.
 */
static void ETA_Speech_StripMarkup(const char *in, char *out, size_t outSize)
{
    size_t used = 0;

    while (*in && used + 1 < outSize)
    {
        unsigned char next = (unsigned char)in[1];

        if (in[0] == '^' && next > ' ' && next < 0x7f && next != '^')
        {
            in += 2;
            continue;
        }

        out[used++] = *in++;
    }

    out[used] = '\0';
}

void ETA_Speech_Say(const char *message)
{
    char clean[ETA_MAX_SPEECH_TEXT_LENGTH + 1];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(message, ETA_MAX_SPEECH_TEXT_LENGTH, "speech_manager.Say")))
    {
        return;
    }

    ETA_Speech_StripMarkup(message, clean, sizeof(clean));

    if (!clean[0])
    {
        /* Nothing but markup: nothing to say. */
        return;
    }

    message = clean;

    if (gReportOpen)
    {
        size_t remaining;

        /* Parts are joined with ", " so the backend reads them as one
           sentence with pauses, rather than running the words together. */
        if (gReportLength > 0)
        {
            remaining = sizeof(gReportBuffer) - gReportLength - 1;

            if (remaining < 2)
            {
                return;
            }

            memcpy(gReportBuffer + gReportLength, ", ", 2);
            gReportLength += 2;
        }

        remaining = sizeof(gReportBuffer) - gReportLength - 1;

        if (remaining == 0)
        {
            return;
        }

        /* A part that will not fit is dropped whole rather than cut in half:
           half a distance or half a weapon name is worse than its absence. */
        if (strlen(message) > remaining)
        {
            if (gReportLength >= 2)
            {
                gReportLength -= 2;
                gReportBuffer[gReportLength] = '\0';
            }

            return;
        }

        memcpy(gReportBuffer + gReportLength, message, strlen(message));
        gReportLength += strlen(message);
        gReportBuffer[gReportLength] = '\0';
        return;
    }

    snprintf(gLastSpeechMessage, sizeof(gLastSpeechMessage), "%s", message);
    gHasLastSpeechMessage = 1;

    ETA_Speech_Dispatch(message);
}

/*
 * A page of text, said in pieces each line can carry: a mission's orders
 * run to well over a thousand characters, and a single line is refused
 * past ETA_MAX_SPEECH_TEXT_LENGTH. Runs of spaces and line breaks become
 * one space, and each piece ends on a sentence where one ends in reach,
 * else on a word. The pieces are said one after another, and NVDA queues
 * them; SAPI 5, which cuts each line off with the next, is left the last.
 * On the Mac the page is one line: VoiceOver does not queue.
 */
void ETA_Speech_SayLong(const char *text)
{
    char   flat[4096];
    size_t used = 0;
    size_t start = 0;
    int    space = 1;

    if (!text)
    {
        return;
    }

    for (; *text && used < sizeof(flat) - 1; text++)
    {
        unsigned char c = (unsigned char)*text;

        if (c == '\n' || c == '\r' || c == '\t' || c == ' ')
        {
            if (!space)
            {
                flat[used++] = ' ';
                space = 1;
            }
            continue;
        }

        flat[used++] = (char)c;
        space = 0;
    }

    while (used > 0 && flat[used - 1] == ' ')
    {
        used--;
    }
    flat[used] = '\0';

#ifdef __APPLE__
    /* VoiceOver keeps only the last of several announcements made at once,
       and the system voice clears a backlog: in pieces, a briefing was
       heard as its last line. Both take a page whole, so it goes as one. */
    {
        char clean[sizeof(flat)];

        ETA_Speech_StripMarkup(flat, clean, sizeof(clean));
        if (clean[0])
        {
            snprintf(gLastSpeechMessage, sizeof(gLastSpeechMessage), "%s", clean);
            gHasLastSpeechMessage = 1;
            ETA_Speech_Dispatch(clean);
        }
        return;
    }
#endif

    while (start < used)
    {
        char   piece[ETA_SPEECH_PIECE_LENGTH + 1];
        size_t length = used - start;

        if (length > ETA_SPEECH_PIECE_LENGTH)
        {
            size_t cut = 0;
            size_t i;

            for (i = ETA_SPEECH_PIECE_LENGTH; i > ETA_SPEECH_PIECE_LENGTH / 2; i--)
            {
                char before = flat[start + i - 1];

                if (flat[start + i] == ' ' && (before == '.' || before == '!' || before == '?' || before == ':'))
                {
                    cut = i;
                    break;
                }
            }

            for (i = ETA_SPEECH_PIECE_LENGTH; !cut && i > 0; i--)
            {
                if (flat[start + i] == ' ')
                {
                    cut = i;
                }
            }

            length = cut ? cut : ETA_SPEECH_PIECE_LENGTH;
        }

        memcpy(piece, flat + start, length);
        piece[length] = '\0';
        start += length;

        while (start < used && flat[start] == ' ')
        {
            start++;
        }

        if (piece[0])
        {
            ETA_Speech_Say(piece);
        }
    }
}

void ETA_Speech_BeginReport(void)
{
    /* A Begin while one is already open would otherwise throw away what has
       been collected so far; the outer report wins and the inner one is a
       no-op, so a stray Begin cannot silently lose a line. */
    if (gReportOpen)
    {
        return;
    }

    gReportOpen = 1;
    gReportLength = 0;
    gReportBuffer[0] = '\0';
}

void ETA_Speech_EndReport(void)
{
    if (!gReportOpen)
    {
        return;
    }

    gReportOpen = 0;

    if (gReportLength == 0)
    {
        return;
    }

    /* Speaks through Say, now that the report is closed, so the joined line
       becomes the repeat target exactly like any other message. */
    ETA_Speech_Say(gReportBuffer);
}

void ETA_Speech_Stop(void)
{
    /* Whichever backend spoke last, this cancels it. */
    ETA_WindowsNvda_Stop();
    ETA_WindowsSpeech_Stop();
#ifdef __APPLE__
    ETA_MacSpeech_Stop();
#endif
}

void ETA_Speech_RepeatLast(void)
{
    if (!gHasLastSpeechMessage)
    {
        return;
    }

    ETA_Speech_Dispatch(gLastSpeechMessage);
}

const char *ETA_Speech_GetLastMessage(void)
{
    return gHasLastSpeechMessage ? gLastSpeechMessage : NULL;
}

void ETA_Speech_Shutdown(void)
{
    ETA_WindowsNvda_Shutdown();
    ETA_WindowsSpeech_Shutdown();
#ifdef __APPLE__
    ETA_MacSpeech_Shutdown();
#endif
}

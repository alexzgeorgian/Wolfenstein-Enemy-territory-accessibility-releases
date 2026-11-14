#include "windows_speech.h"
#include "../../speech/speech_manager.h"

#include <stdio.h>

#ifdef _WIN32

#include "../../core/runtime_guard.h"

#define COBJMACROS
#define INITGUID

#ifndef _SAPI_VER
#define _SAPI_VER 0x51
#endif

#include <windows.h>
#include <sapi.h>

#include <stdio.h>

static ISpVoice *gVoice = NULL;
static int gComInitialized = 0;

void ETA_WindowsSpeech_Init(void)
{
    HRESULT hr;

    if (gVoice)
    {
        return;
    }

    hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);

    if (SUCCEEDED(hr))
    {
        gComInitialized = 1;
    }
    else if (hr != RPC_E_CHANGED_MODE)
    {
        printf("[Accessibility] Failed to initialize COM for speech (0x%08lX)\n", (unsigned long)hr);
        return;
    }

    hr = CoCreateInstance(&CLSID_SpVoice, NULL, CLSCTX_ALL, &IID_ISpVoice, (void **)&gVoice);

    if (FAILED(hr))
    {
        printf("[Accessibility] Failed to create SAPI voice (0x%08lX)\n", (unsigned long)hr);
        gVoice = NULL;

        if (gComInitialized)
        {
            CoUninitialize();
            gComInitialized = 0;
        }

        return;
    }

    printf("[Accessibility] Windows speech (SAPI) initialized\n");
}

static int gPitch = 0;
static int gSetRate = -1000, gSetVolume = -1;

void ETA_WindowsSpeech_SetVoice(int rate, int pitch, int volume)
{
    /* Kept even when there is no voice yet, so settings read from a
       config before Init lands are not lost - Init applies them. */
    gPitch = pitch;

    /* The cgame pushes the settings every frame; the voice is only told
       when they change. */
    if (!gVoice || (rate == gSetRate && volume == gSetVolume))
    {
        return;
    }
    gSetRate   = rate;
    gSetVolume = volume;

    /* Both take the value directly; the caller has already clamped to
       SAPI's ranges. Pitch has no setter of its own, which is why it is
       held here and written as markup at speaking time. */
    ISpVoice_SetRate(gVoice, (long)rate);
    ISpVoice_SetVolume(gVoice, (USHORT)volume);
}

/*
 * How many lines may wait behind the one being spoken before the oldest
 * are dropped.
 *
 * Each line used to cut off the one before it. NVDA lets a line finish
 * and queues the next (its speakText is queued behind what it is saying),
 * and the narrator was written against that - so with NVDA closed, the
 * tester heard SAPI 5 miss things: in a match the lines come a few a
 * second, and each one cut the last off in its first syllable. Now SAPI
 * queues them too. Only a backlog this deep is cleared, so the voice
 * never falls far behind the game; a line that has to cut in - a key
 * the player pressed - still stops the voice first (ETA_Speech_Stop).
 */
#define ETA_SAPI_BACKLOG 3

static int ETA_WindowsSpeech_Waiting(void)
{
    SPVOICESTATUS status;

    if (FAILED(ISpVoice_GetStatus(gVoice, &status, NULL)) || status.dwRunningState == SPRS_DONE)
    {
        return 0;
    }

    /* Streams are numbered as they are queued: the one being spoken, and
       every one queued after it. */
    return (int)(status.ulLastStreamQueued - status.ulCurrentStream);
}

void ETA_WindowsSpeech_Speak(const char *message)
{
    char    marked[(ETA_MAX_SPEECH_TEXT_LENGTH * 6) + 32];
    wchar_t wideMessage[sizeof(marked)];
    const char *toSpeak = message;
    DWORD   flags       = SPF_ASYNC;
    int     converted;

    if (!message || !gVoice)
    {
        return;
    }

    if (ETA_WindowsSpeech_Waiting() >= ETA_SAPI_BACKLOG)
    {
        flags |= SPF_PURGEBEFORESPEAK;
    }

    /* Plain text unless the player actually asked for a pitch change.
       The markup path means handing the line to a parser, and a line that
       has not been through a parser cannot be broken by one - so the
       default path stays exactly as it was. */
    if (gPitch != 0)
    {
        char escaped[(ETA_MAX_SPEECH_TEXT_LENGTH * 6) + 1];

        ETA_Speech_EscapeXml(message, escaped, sizeof(escaped));

        /* absmiddle, not middle: an absolute offset from the voice's own
           default, so the pitch does not drift further from centre with
           every line spoken. */
        snprintf(marked, sizeof(marked), "<pitch absmiddle=\"%d\"/>%s",
                 gPitch, escaped);

        toSpeak = marked;
        flags  |= SPF_IS_XML;
    }

    converted = MultiByteToWideChar(CP_UTF8, 0, toSpeak, -1, wideMessage,
                                    (int)(sizeof(wideMessage) / sizeof(wideMessage[0])));

    if (converted <= 0)
    {
        return;
    }

    ISpVoice_Speak(gVoice, wideMessage, flags, NULL);
}

void ETA_WindowsSpeech_Stop(void)
{
    if (!gVoice)
    {
        return;
    }

    ISpVoice_Speak(gVoice, NULL, SPF_PURGEBEFORESPEAK, NULL);
}

void ETA_WindowsSpeech_Shutdown(void)
{
    if (gVoice)
    {
        ISpVoice_Release(gVoice);
        gVoice = NULL;
    }

    /* A new voice starts at its defaults, so the next settings pushed
       are applied to it. */
    gSetRate   = -1000;
    gSetVolume = -1;

    if (gComInitialized)
    {
        CoUninitialize();
        gComInitialized = 0;
    }

    printf("[Accessibility] Windows speech (SAPI) shutdown\n");
}

#else

#include "../../core/debug_log.h"

void ETA_WindowsSpeech_Init(void)
{
    ETA_DebugLog_Warning("windows_speech", "No speech backend available on this platform yet");
}

void ETA_WindowsSpeech_Speak(const char *message)
{
    (void)message;
}

void ETA_WindowsSpeech_SetVoice(int rate, int pitch, int volume)
{
    (void)rate;
    (void)pitch;
    (void)volume;
}

void ETA_WindowsSpeech_Stop(void)
{
}

void ETA_WindowsSpeech_Shutdown(void)
{
}

#endif

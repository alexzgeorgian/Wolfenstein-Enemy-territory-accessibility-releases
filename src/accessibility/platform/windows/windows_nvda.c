#include "windows_nvda.h"

#ifdef _WIN32

#include "../../core/runtime_guard.h"

#include <windows.h>
#include <stdio.h>

/*
 * NVDA's controller client is loaded at runtime rather than linked against.
 * That keeps the NVDA SDK out of the build entirely - no headers, no import
 * library - and means a module built with NVDA support still loads normally
 * for players who don't run NVDA, instead of failing on a missing DLL.
 *
 * The exported functions are __stdcall and return error_status_t (an
 * unsigned long, 0 on success). error_status_t comes from the RPC headers;
 * it is spelled out here so this file needs nothing beyond windows.h.
 */
typedef unsigned long ETA_NvdaStatus;

typedef ETA_NvdaStatus(__stdcall *ETA_NvdaTestIfRunningFn)(void);
typedef ETA_NvdaStatus(__stdcall *ETA_NvdaSpeakTextFn)(const wchar_t *text);
typedef ETA_NvdaStatus(__stdcall *ETA_NvdaCancelSpeechFn)(void);

/*
 * GetProcAddress hands back a FARPROC, and casting that straight to a
 * typed function pointer trips -Wcast-function-type: the compiler has no
 * way to know what is on the other side. A union carries the conversion
 * instead, which stays quiet under -Wpedantic as well - a cast via void *
 * silences -Wcast-function-type but not -Wpedantic, since ISO C has no
 * conversion between function and object pointers even though Windows
 * guarantees one.
 *
 * Nothing here makes the signatures correct; that came from reading
 * nvdaControllerClient.def and nvdaController.idl in nvaccess/nvda.
 */
typedef union
{
    FARPROC                  proc;
    ETA_NvdaTestIfRunningFn  testIfRunning;
    ETA_NvdaSpeakTextFn      speakText;
    ETA_NvdaCancelSpeechFn   cancelSpeech;
} ETA_NvdaProc;

static HMODULE gNvdaClient = NULL;
static ETA_NvdaTestIfRunningFn gTestIfRunning = NULL;
static ETA_NvdaSpeakTextFn gSpeakText = NULL;
static ETA_NvdaCancelSpeechFn gCancelSpeech = NULL;

/*
 * NVDA 2024.1 dropped the architecture suffix from the client library:
 * nvdaControllerClient32.dll / ...64.dll became plain
 * nvdaControllerClient.dll, with the architecture chosen by which of the
 * x86/x64/arm64 build outputs you ship (NVDA changes.md, 2024.1, #15718 /
 * #15717). Current releases are tried first, then the pre-2024.1 name
 * matching this build, so players on an older NVDA still get speech.
 */
static HMODULE ETA_WindowsNvda_LoadClient(void)
{
    static const char *const names[] = {
        "nvdaControllerClient.dll",
#ifdef _WIN64
        "nvdaControllerClient64.dll"
#else
        "nvdaControllerClient32.dll"
#endif
    };
    size_t i;

    for (i = 0; i < sizeof(names) / sizeof(names[0]); i++)
    {
        HMODULE module = LoadLibraryA(names[i]);

        if (module)
        {
            return module;
        }
    }

    return NULL;
}

void ETA_WindowsNvda_Init(void)
{
    /* Declared up front: this file is also built as gnu90 by the id
       Software integration, and ET: Legacy compiles the mod with
       -Wdeclaration-after-statement. */
    ETA_NvdaProc resolved;

    if (gNvdaClient)
    {
        return;
    }

    gNvdaClient = ETA_WindowsNvda_LoadClient();

    if (!gNvdaClient)
    {
        printf("[Accessibility] NVDA controller client not found, using SAPI\n");
        return;
    }

    resolved.proc = GetProcAddress(gNvdaClient, "nvdaController_testIfRunning");
    gTestIfRunning = resolved.testIfRunning;

    resolved.proc = GetProcAddress(gNvdaClient, "nvdaController_speakText");
    gSpeakText = resolved.speakText;

    resolved.proc = GetProcAddress(gNvdaClient, "nvdaController_cancelSpeech");
    gCancelSpeech = resolved.cancelSpeech;

    if (!gTestIfRunning || !gSpeakText || !gCancelSpeech)
    {
        printf("[Accessibility] NVDA controller client is missing expected exports, using SAPI\n");
        ETA_WindowsNvda_Shutdown();
        return;
    }

    if (ETA_WindowsNvda_IsAvailable())
    {
        printf("[Accessibility] NVDA speech initialized\n");
    }
    else
    {
        printf("[Accessibility] NVDA controller client loaded, NVDA not running yet\n");
    }
}

int ETA_WindowsNvda_IsAvailable(void)
{
    if (!gTestIfRunning)
    {
        return 0;
    }

    return gTestIfRunning() == 0;
}

int ETA_WindowsNvda_Speak(const char *message)
{
    wchar_t wideMessage[ETA_MAX_SPEECH_TEXT_LENGTH + 1];
    int converted;

    if (!message || !gSpeakText)
    {
        return 0;
    }

    converted = MultiByteToWideChar(CP_UTF8, 0, message, -1, wideMessage, ETA_MAX_SPEECH_TEXT_LENGTH + 1);

    if (converted <= 0)
    {
        return 0;
    }

    /*
     * No testIfRunning call first: speakText fails on its own when NVDA
     * isn't there, so one call covers both the check and the send, and the
     * caller falls back for exactly the messages NVDA didn't take. That
     * also handles NVDA being started or stopped mid-session without any
     * polling.
     *
     * Relying on that is safe rather than hopeful: every function in
     * nvdaController.acf carries [fault_status, comm_status], so MIDL
     * generates stubs that *return* an RPC failure as the status value.
     * A missing NVDA comes back as an error code, not a structured
     * exception, so there is nothing here to catch.
     */
    return gSpeakText(wideMessage) == 0;
}

void ETA_WindowsNvda_Stop(void)
{
    if (!gCancelSpeech)
    {
        return;
    }

    gCancelSpeech();
}

void ETA_WindowsNvda_Shutdown(void)
{
    gTestIfRunning = NULL;
    gSpeakText = NULL;
    gCancelSpeech = NULL;

    if (gNvdaClient)
    {
        FreeLibrary(gNvdaClient);
        gNvdaClient = NULL;
    }
}

#else

void ETA_WindowsNvda_Init(void)
{
}

int ETA_WindowsNvda_IsAvailable(void)
{
    return 0;
}

int ETA_WindowsNvda_Speak(const char *message)
{
    (void)message;
    return 0;
}

void ETA_WindowsNvda_Stop(void)
{
}

void ETA_WindowsNvda_Shutdown(void)
{
}

#endif

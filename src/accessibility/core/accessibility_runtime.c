#include "accessibility_runtime.h"
#include "../speech/speech_manager.h"

static ETA_AccessibilityRuntimeState gAccessibilityRuntimeState = ETA_ACCESSIBILITY_RUNTIME_STOPPED;

void ETA_AccessibilityRuntime_Init(void)
{
    gAccessibilityRuntimeState = ETA_ACCESSIBILITY_RUNTIME_INITIALIZING;

    ETA_Speech_Init();

    gAccessibilityRuntimeState = ETA_ACCESSIBILITY_RUNTIME_RUNNING;
}

void ETA_AccessibilityRuntime_Shutdown(void)
{
    ETA_Speech_Shutdown();

    gAccessibilityRuntimeState = ETA_ACCESSIBILITY_RUNTIME_STOPPED;
}

void ETA_AccessibilityRuntime_RunSpeechSmokeTest(void)
{
    if (gAccessibilityRuntimeState != ETA_ACCESSIBILITY_RUNTIME_RUNNING)
    {
        return;
    }

    ETA_Speech_Say("Accessibility runtime speech test initialized.");
}

int ETA_AccessibilityRuntime_IsRunning(void)
{
    return gAccessibilityRuntimeState == ETA_ACCESSIBILITY_RUNTIME_RUNNING;
}

ETA_AccessibilityRuntimeState ETA_AccessibilityRuntime_GetState(void)
{
    return gAccessibilityRuntimeState;
}

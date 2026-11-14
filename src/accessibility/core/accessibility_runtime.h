#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ETA_AccessibilityRuntimeState
{
    ETA_ACCESSIBILITY_RUNTIME_STOPPED = 0,
    ETA_ACCESSIBILITY_RUNTIME_INITIALIZING,
    ETA_ACCESSIBILITY_RUNTIME_RUNNING,
    ETA_ACCESSIBILITY_RUNTIME_ERROR
} ETA_AccessibilityRuntimeState;

void ETA_AccessibilityRuntime_Init(void);
void ETA_AccessibilityRuntime_Shutdown(void);
void ETA_AccessibilityRuntime_RunSpeechSmokeTest(void);
int ETA_AccessibilityRuntime_IsRunning(void);
ETA_AccessibilityRuntimeState ETA_AccessibilityRuntime_GetState(void);

#ifdef __cplusplus
}
#endif

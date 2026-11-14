#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ETA_GuardResult
{
    ETA_GUARD_OK = 0,
    ETA_GUARD_NULL_POINTER,
    ETA_GUARD_EMPTY_STRING,
    ETA_GUARD_STRING_TOO_LONG,
    ETA_GUARD_INVALID_VALUE
} ETA_GuardResult;

#define ETA_MAX_SPEECH_TEXT_LENGTH 512
#define ETA_MAX_MENU_TEXT_LENGTH 256
#define ETA_MAX_HUD_TEXT_LENGTH 256
#define ETA_MAX_NAVIGATION_TEXT_LENGTH 256

ETA_GuardResult ETA_RuntimeGuard_CheckPointer(const void *value, const char *source);
ETA_GuardResult ETA_RuntimeGuard_CheckString(const char *value, size_t maxLength, const char *source);
ETA_GuardResult ETA_RuntimeGuard_CheckIntRange(int value, int minimum, int maximum, const char *source);
int ETA_RuntimeGuard_IsOk(ETA_GuardResult result);
const char *ETA_RuntimeGuard_GetResultName(ETA_GuardResult result);

#ifdef __cplusplus
}
#endif

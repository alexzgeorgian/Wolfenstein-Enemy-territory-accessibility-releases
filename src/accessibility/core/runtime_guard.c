#include "runtime_guard.h"
#include "debug_log.h"
#include "error_handler.h"

#include <string.h>

ETA_GuardResult ETA_RuntimeGuard_CheckPointer(const void *value, const char *source)
{
    if (!value)
    {
        ETA_ErrorHandler_Report(
            ETA_ERROR_NULL_POINTER,
            source,
            "Null pointer detected"
        );

        return ETA_GUARD_NULL_POINTER;
    }

    return ETA_GUARD_OK;
}

ETA_GuardResult ETA_RuntimeGuard_CheckString(const char *value, size_t maxLength, const char *source)
{
    size_t length;

    if (!value)
    {
        ETA_ErrorHandler_Report(
            ETA_ERROR_NULL_POINTER,
            source,
            "Null string detected"
        );

        return ETA_GUARD_NULL_POINTER;
    }

    length = strlen(value);

    if (length == 0)
    {
        ETA_DebugLog_Warning(source, "Empty string detected");

        ETA_ErrorHandler_Report(
            ETA_ERROR_INVALID_STRING,
            source,
            "Empty string detected"
        );

        return ETA_GUARD_EMPTY_STRING;
    }

    if (length > maxLength)
    {
        ETA_ErrorHandler_Report(
            ETA_ERROR_STRING_TOO_LONG,
            source,
            "String length exceeded limit"
        );

        return ETA_GUARD_STRING_TOO_LONG;
    }

    return ETA_GUARD_OK;
}

ETA_GuardResult ETA_RuntimeGuard_CheckIntRange(int value, int minimum, int maximum, const char *source)
{
    if (value < minimum || value > maximum)
    {
        ETA_ErrorHandler_Report(
            ETA_ERROR_INVALID_VALUE,
            source,
            "Integer value outside allowed range"
        );

        return ETA_GUARD_INVALID_VALUE;
    }

    return ETA_GUARD_OK;
}

int ETA_RuntimeGuard_IsOk(ETA_GuardResult result)
{
    return result == ETA_GUARD_OK;
}

const char *ETA_RuntimeGuard_GetResultName(ETA_GuardResult result)
{
    switch (result)
    {
        case ETA_GUARD_OK:
            return "ok";

        case ETA_GUARD_NULL_POINTER:
            return "null_pointer";

        case ETA_GUARD_EMPTY_STRING:
            return "empty_string";

        case ETA_GUARD_STRING_TOO_LONG:
            return "string_too_long";

        case ETA_GUARD_INVALID_VALUE:
            return "invalid_value";

        default:
            return "unknown";
    }
}

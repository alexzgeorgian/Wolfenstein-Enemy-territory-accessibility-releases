#include "error_handler.h"
#include "debug_log.h"

static ETA_ErrorState gLastErrorState =
{
    ETA_ERROR_NONE,
    0,
    0
};

void ETA_ErrorHandler_Clear(void)
{
    gLastErrorState.code = ETA_ERROR_NONE;
    gLastErrorState.source = 0;
    gLastErrorState.message = 0;
}

void ETA_ErrorHandler_Report(ETA_ErrorCode code, const char *source, const char *message)
{
    gLastErrorState.code = code;
    gLastErrorState.source = source;
    gLastErrorState.message = message;

    ETA_DebugLog_Error(
        source ? source : "error_handler",
        message ? message : "Unknown runtime error"
    );
}

int ETA_ErrorHandler_HasError(void)
{
    return gLastErrorState.code != ETA_ERROR_NONE;
}

ETA_ErrorState ETA_ErrorHandler_GetLastError(void)
{
    return gLastErrorState;
}

const char *ETA_ErrorHandler_GetCodeName(ETA_ErrorCode code)
{
    switch (code)
    {
        case ETA_ERROR_NONE:
            return "none";

        case ETA_ERROR_NULL_POINTER:
            return "null_pointer";

        case ETA_ERROR_INVALID_STRING:
            return "invalid_string";

        case ETA_ERROR_STRING_TOO_LONG:
            return "string_too_long";

        case ETA_ERROR_INVALID_VALUE:
            return "invalid_value";

        case ETA_ERROR_RUNTIME_NOT_READY:
            return "runtime_not_ready";

        case ETA_ERROR_PLATFORM_FAILURE:
            return "platform_failure";

        default:
            return "unknown";
    }
}

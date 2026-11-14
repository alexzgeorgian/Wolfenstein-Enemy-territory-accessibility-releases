#include "debug_log.h"

#include <stdio.h>

static const char *ETA_DebugLog_GetLevelName(ETA_LogLevel level)
{
    switch (level)
    {
        case ETA_LOG_INFO:
            return "INFO";

        case ETA_LOG_WARNING:
            return "WARNING";

        case ETA_LOG_ERROR:
            return "ERROR";

        default:
            return "UNKNOWN";
    }
}

void ETA_DebugLog_Write(ETA_LogLevel level, const char *source, const char *message)
{
    printf(
        "[Accessibility][%s][%s] %s\n",
        ETA_DebugLog_GetLevelName(level),
        source ? source : "unknown",
        message ? message : "(null)"
    );
}

void ETA_DebugLog_Info(const char *source, const char *message)
{
    ETA_DebugLog_Write(ETA_LOG_INFO, source, message);
}

void ETA_DebugLog_Warning(const char *source, const char *message)
{
    ETA_DebugLog_Write(ETA_LOG_WARNING, source, message);
}

void ETA_DebugLog_Error(const char *source, const char *message)
{
    ETA_DebugLog_Write(ETA_LOG_ERROR, source, message);
}

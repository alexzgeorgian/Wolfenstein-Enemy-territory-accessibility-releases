#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ETA_LogLevel
{
    ETA_LOG_INFO = 0,
    ETA_LOG_WARNING,
    ETA_LOG_ERROR
} ETA_LogLevel;

void ETA_DebugLog_Write(ETA_LogLevel level, const char *source, const char *message);
void ETA_DebugLog_Info(const char *source, const char *message);
void ETA_DebugLog_Warning(const char *source, const char *message);
void ETA_DebugLog_Error(const char *source, const char *message);

#ifdef __cplusplus
}
#endif

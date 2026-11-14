#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ETA_ErrorCode
{
    ETA_ERROR_NONE = 0,
    ETA_ERROR_NULL_POINTER,
    ETA_ERROR_INVALID_STRING,
    ETA_ERROR_STRING_TOO_LONG,
    ETA_ERROR_INVALID_VALUE,
    ETA_ERROR_RUNTIME_NOT_READY,
    ETA_ERROR_PLATFORM_FAILURE
} ETA_ErrorCode;

typedef struct ETA_ErrorState
{
    ETA_ErrorCode code;
    const char *source;
    const char *message;
} ETA_ErrorState;

void ETA_ErrorHandler_Clear(void);
void ETA_ErrorHandler_Report(ETA_ErrorCode code, const char *source, const char *message);
int ETA_ErrorHandler_HasError(void);
ETA_ErrorState ETA_ErrorHandler_GetLastError(void);
const char *ETA_ErrorHandler_GetCodeName(ETA_ErrorCode code);

#ifdef __cplusplus
}
#endif

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ETA_EventType
{
    ETA_EVENT_NONE = 0,
    ETA_EVENT_SPEECH,
    ETA_EVENT_MENU_FOCUS,
    ETA_EVENT_MENU_VALUE,
    ETA_EVENT_MENU_CONFIRM,
    ETA_EVENT_HUD_STATUS,
    ETA_EVENT_NAVIGATION,
    ETA_EVENT_COMMAND,
    ETA_EVENT_ERROR
} ETA_EventType;

typedef struct ETA_Event
{
    ETA_EventType type;
    const char *source;
    const char *message;
} ETA_Event;

void ETA_EventRouter_Emit(ETA_Event event);
const char *ETA_EventRouter_GetTypeName(ETA_EventType type);

#ifdef __cplusplus
}
#endif

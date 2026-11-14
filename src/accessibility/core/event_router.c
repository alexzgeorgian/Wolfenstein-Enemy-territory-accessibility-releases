#include "event_router.h"
#include "../speech/speech_manager.h"

const char *ETA_EventRouter_GetTypeName(ETA_EventType type)
{
    switch (type)
    {
        case ETA_EVENT_SPEECH:
            return "speech";

        case ETA_EVENT_MENU_FOCUS:
            return "menu_focus";

        case ETA_EVENT_MENU_VALUE:
            return "menu_value";

        case ETA_EVENT_MENU_CONFIRM:
            return "menu_confirm";

        case ETA_EVENT_HUD_STATUS:
            return "hud_status";

        case ETA_EVENT_NAVIGATION:
            return "navigation";

        case ETA_EVENT_COMMAND:
            return "command";

        case ETA_EVENT_ERROR:
            return "error";

        default:
            return "unknown";
    }
}

void ETA_EventRouter_Emit(ETA_Event event)
{
    if (!event.message)
    {
        return;
    }

    switch (event.type)
    {
        case ETA_EVENT_SPEECH:
        case ETA_EVENT_MENU_FOCUS:
        case ETA_EVENT_MENU_VALUE:
        case ETA_EVENT_MENU_CONFIRM:
        case ETA_EVENT_HUD_STATUS:
        case ETA_EVENT_NAVIGATION:
        case ETA_EVENT_ERROR:
            ETA_Speech_Say(event.message);
            break;

        default:
            break;
    }
}

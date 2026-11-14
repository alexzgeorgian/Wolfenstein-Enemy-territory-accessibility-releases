#include "menu_narrator.h"
#include "../core/event_router.h"
#include "../core/runtime_guard.h"
#include "../speech/speech_manager.h"

#include <stdio.h>

static char gCurrentMenuItem[ETA_MAX_MENU_TEXT_LENGTH + 1];
static int gHasCurrentMenuItem = 0;

void ETA_MenuNarrator_Init(void)
{
}

void ETA_MenuNarrator_OnFocusChanged(const char *menuName, const char *itemName)
{
    ETA_Event event;

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(itemName, ETA_MAX_MENU_TEXT_LENGTH, "menu_narrator.OnFocusChanged")))
    {
        return;
    }

    snprintf(gCurrentMenuItem, sizeof(gCurrentMenuItem), "%s", itemName);
    gHasCurrentMenuItem = 1;

    event.type = ETA_EVENT_MENU_FOCUS;
    event.source = menuName ? menuName : "menu";
    event.message = itemName;

    ETA_EventRouter_Emit(event);
}

void ETA_MenuNarrator_OnValueChanged(const char *itemName, const char *valueText)
{
    ETA_Event event;

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(itemName, ETA_MAX_MENU_TEXT_LENGTH, "menu_narrator.OnValueChanged")))
    {
        return;
    }

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(valueText, ETA_MAX_MENU_TEXT_LENGTH, "menu_narrator.OnValueChanged")))
    {
        return;
    }

    event.type = ETA_EVENT_MENU_VALUE;
    event.source = itemName;
    event.message = valueText;

    ETA_EventRouter_Emit(event);
}

void ETA_MenuNarrator_OnConfirmDialogShown(const char *dialogText)
{
    ETA_Event event;

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(dialogText, ETA_MAX_MENU_TEXT_LENGTH, "menu_narrator.OnConfirmDialogShown")))
    {
        return;
    }

    snprintf(gCurrentMenuItem, sizeof(gCurrentMenuItem), "%s", dialogText);
    gHasCurrentMenuItem = 1;

    event.type = ETA_EVENT_MENU_CONFIRM;
    event.source = "confirm_dialog";
    event.message = dialogText;

    ETA_EventRouter_Emit(event);
}

void ETA_MenuNarrator_RepeatCurrentItem(void)
{
    if (!gHasCurrentMenuItem)
    {
        return;
    }

    ETA_Speech_Say(gCurrentMenuItem);
}

void ETA_MenuNarrator_Stop(void)
{
    ETA_Speech_Stop();
}

void ETA_MenuNarrator_Shutdown(void)
{
    gCurrentMenuItem[0] = '\0';
    gHasCurrentMenuItem = 0;
}

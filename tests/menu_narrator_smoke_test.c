#include "core/accessibility_runtime.h"
#include "menu/menu_narrator.h"
#include "smoke_check.h"

#include <stdlib.h>
#include <string.h>

/* Allocates a copy and, on free, scribbles over it first: if a narrator kept
   the caller's pointer instead of copying, later narration reads the poison
   rather than the original text. Under a sanitizer it reads freed memory and
   the run aborts outright. */
static char *HeapCopy(const char *text)
{
    char *copy = (char *)malloc(strlen(text) + 1);

    strcpy(copy, text);

    return copy;
}

static void PoisonAndFree(char *text)
{
    memset(text, 'X', strlen(text));
    free(text);
}

static char *OverlongText(size_t length)
{
    char *text = (char *)malloc(length + 1);

    memset(text, 'a', length);
    text[length] = '\0';

    return text;
}

int main(void)
{
    char *itemName;
    char *valueItemName;
    char *valueText;
    char *dialogText;
    char *overlong;

    SMOKE_BANNER("menu_narrator");

    ETA_AccessibilityRuntime_Init();
    ETA_MenuNarrator_Init();

    /* Each narrator entry point must copy the strings it is given rather than
       keep the caller's pointer, so freeing the source right after the call
       must not leave later narration reading freed memory. */

    itemName = HeapCopy("Fullscreen");
    CHECK_ACCEPTS(ETA_MenuNarrator_OnFocusChanged("VideoOptions", itemName));
    PoisonAndFree(itemName);

    CHECK_ACCEPTS(ETA_MenuNarrator_RepeatCurrentItem());

    valueItemName = HeapCopy("Brightness");
    valueText = HeapCopy("75 percent");
    CHECK_ACCEPTS(ETA_MenuNarrator_OnValueChanged(valueItemName, valueText));
    PoisonAndFree(valueItemName);
    PoisonAndFree(valueText);

    dialogText = HeapCopy("Discard changes and quit?");
    CHECK_ACCEPTS(ETA_MenuNarrator_OnConfirmDialogShown(dialogText));
    PoisonAndFree(dialogText);

    CHECK_ACCEPTS(ETA_MenuNarrator_RepeatCurrentItem());
    CHECK_ACCEPTS(ETA_MenuNarrator_Stop());

    /* Engine code passes these straight from menu item definitions, where a
       missing label is a real possibility, so the guards are load-bearing. */
    CHECK_REJECTS(ETA_MenuNarrator_OnFocusChanged("VideoOptions", NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_MenuNarrator_OnFocusChanged("VideoOptions", ""), ETA_ERROR_INVALID_STRING);
    CHECK_REJECTS(ETA_MenuNarrator_OnValueChanged(NULL, "75 percent"), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_MenuNarrator_OnValueChanged("Brightness", NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_MenuNarrator_OnConfirmDialogShown(NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_MenuNarrator_OnConfirmDialogShown(""), ETA_ERROR_INVALID_STRING);

    overlong = OverlongText(ETA_MAX_MENU_TEXT_LENGTH + 1);
    CHECK_REJECTS(ETA_MenuNarrator_OnFocusChanged("VideoOptions", overlong), ETA_ERROR_STRING_TOO_LONG);
    CHECK_REJECTS(ETA_MenuNarrator_OnConfirmDialogShown(overlong), ETA_ERROR_STRING_TOO_LONG);
    free(overlong);

    /* Exactly at the limit must still be accepted. */
    overlong = OverlongText(ETA_MAX_MENU_TEXT_LENGTH);
    CHECK_ACCEPTS(ETA_MenuNarrator_OnFocusChanged("VideoOptions", overlong));
    free(overlong);

    ETA_MenuNarrator_Shutdown();
    ETA_AccessibilityRuntime_Shutdown();

    return SMOKE_REPORT("menu_narrator");
}

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ETA_MenuNarrator_Init(void);
void ETA_MenuNarrator_OnFocusChanged(const char *menuName, const char *itemName);
void ETA_MenuNarrator_OnValueChanged(const char *itemName, const char *valueText);
void ETA_MenuNarrator_OnConfirmDialogShown(const char *dialogText);
void ETA_MenuNarrator_RepeatCurrentItem(void);
void ETA_MenuNarrator_Stop(void);
void ETA_MenuNarrator_Shutdown(void);

#ifdef __cplusplus
}
#endif

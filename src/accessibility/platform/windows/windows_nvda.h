#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ETA_WindowsNvda_Init(void);

/* 1 when the controller client is loaded and NVDA answered a ping. */
int ETA_WindowsNvda_IsAvailable(void);

/* 1 when NVDA accepted the message, 0 when the caller should fall back. */
int ETA_WindowsNvda_Speak(const char *message);

void ETA_WindowsNvda_Stop(void);
void ETA_WindowsNvda_Shutdown(void);

#ifdef __cplusplus
}
#endif

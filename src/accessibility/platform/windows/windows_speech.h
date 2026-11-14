#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ETA_WindowsSpeech_Init(void);
void ETA_WindowsSpeech_Speak(const char *message);

/* SAPI only. NVDA carries no rate, pitch or volume - see the
   comment on ETA_Speech_SetVoice. */
void ETA_WindowsSpeech_SetVoice(int rate, int pitch, int volume);
void ETA_WindowsSpeech_Stop(void);
void ETA_WindowsSpeech_Shutdown(void);

#ifdef __cplusplus
}
#endif

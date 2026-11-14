#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Speech on macOS: VoiceOver first, the system voice when VoiceOver is
 * off - the Mac's own pair to NVDA and SAPI 5 on Windows.
 *
 * With VoiceOver running, a line is handed to it as an announcement, so
 * it is spoken in the player's own VoiceOver voice, rate and verbosity,
 * and waits behind what VoiceOver is saying rather than talking over it.
 * With VoiceOver off, the system voice (AVSpeechSynthesizer) speaks it,
 * at the mod's own rate, pitch and volume settings, as SAPI 5 does.
 *
 * Every function is safe to call before Init and after Shutdown, and
 * all of them do nothing on any other platform.
 */
void ETA_MacSpeech_Init(void);

/* Speaks a line; 1 when one of the two took it. */
int ETA_MacSpeech_Speak(const char *message);

/* The mod's rate and pitch (-10 to 10) and volume (0 to 100), for the
   system voice. VoiceOver keeps the player's own. */
void ETA_MacSpeech_SetVoice(int rate, int pitch, int volume);

/* Cuts off what is being said. */
void ETA_MacSpeech_Stop(void);

void ETA_MacSpeech_Shutdown(void);

#ifdef __cplusplus
}
#endif

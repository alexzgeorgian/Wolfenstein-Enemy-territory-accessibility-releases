#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ETA_WindowsAudioCue_Init(void);
void ETA_WindowsAudioCue_Play(const char *cueName);
void ETA_WindowsAudioCue_PlayDirectional(const char *cueName, int directionDegrees);
void ETA_WindowsAudioCue_Shutdown(void);

#ifdef __cplusplus
}
#endif

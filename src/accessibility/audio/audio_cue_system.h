#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ETA_AudioCueType
{
    ETA_AUDIO_CUE_LOW_HEALTH = 0,
    ETA_AUDIO_CUE_OBJECTIVE,
    ETA_AUDIO_CUE_INTERACTION,
    ETA_AUDIO_CUE_DAMAGE_DIRECTION,
    ETA_AUDIO_CUE_OBJECTIVE_DIRECTION
} ETA_AudioCueType;

/**
 * A cue as handed to a backend.
 *
 * directionDegrees is a view-relative bearing using the engine's own
 * convention - 0 = ahead, 90 = right, 180 = behind, 270 = left - and is
 * only meaningful when hasDirection is non-zero.
 */
typedef void (*ETA_AudioCueBackendFn)(ETA_AudioCueType type,
                                      int directionDegrees,
                                      int hasDirection,
                                      void *userData);

/**
 * Route cues to the game's own sound system instead of the built-in tone
 * generator.
 *
 * The library cannot call the engine itself: it builds standalone, with
 * no engine headers, which is what lets the cue logic be tested without
 * a game. So an integration registers a backend here and plays the cue
 * however its engine prefers - for both ET: Legacy and the 2010 release
 * that means real game sounds, mixed by the engine at the player's own
 * volume, and genuinely positioned in 3D for the directional cues rather
 * than merely panned left and right.
 *
 * With no backend registered, cues fall back to the synthesised tones,
 * so the tests and any host without a sound system still work.
 *
 * Cleared by Shutdown: a backend usually lives in a game module that can
 * be unloaded, and calling through a stale pointer would be worse than
 * falling back to tones. Register again after each Init.
 */
void ETA_AudioCueSystem_SetBackend(ETA_AudioCueBackendFn backend, void *userData);

void ETA_AudioCueSystem_Init(void);
void ETA_AudioCueSystem_PlayLowHealthCue(void);
void ETA_AudioCueSystem_PlayObjectiveCue(void);
void ETA_AudioCueSystem_PlayInteractionCue(void);
void ETA_AudioCueSystem_PlayDamageDirectionCue(int directionDegrees);
void ETA_AudioCueSystem_PlayObjectiveDirectionCue(int directionDegrees);
const char *ETA_AudioCueSystem_GetCueName(ETA_AudioCueType type);
void ETA_AudioCueSystem_Shutdown(void);

#ifdef __cplusplus
}
#endif

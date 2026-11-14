#include "audio_cue_system.h"
#include "../core/runtime_guard.h"
#include "../platform/windows/windows_audio_cue.h"

static ETA_AudioCueBackendFn gBackend     = 0;
static void                  *gBackendData = 0;

void ETA_AudioCueSystem_SetBackend(ETA_AudioCueBackendFn backend, void *userData)
{
    gBackend     = backend;
    gBackendData = userData;
}

/* One route for every cue: to the registered backend when there is one,
   to the synthesised tones otherwise. Keeping it in a single place is
   what stops the two paths drifting apart as cues are added. */
static void ETA_AudioCueSystem_Emit(ETA_AudioCueType type, int directionDegrees, int hasDirection)
{
    if (gBackend)
    {
        gBackend(type, directionDegrees, hasDirection, gBackendData);
        return;
    }

    if (hasDirection)
    {
        ETA_WindowsAudioCue_PlayDirectional(ETA_AudioCueSystem_GetCueName(type), directionDegrees);
    }
    else
    {
        ETA_WindowsAudioCue_Play(ETA_AudioCueSystem_GetCueName(type));
    }
}

void ETA_AudioCueSystem_Init(void)
{
    ETA_WindowsAudioCue_Init();
}

void ETA_AudioCueSystem_PlayLowHealthCue(void)
{
    ETA_AudioCueSystem_Emit(ETA_AUDIO_CUE_LOW_HEALTH, 0, 0);
}

void ETA_AudioCueSystem_PlayObjectiveCue(void)
{
    ETA_AudioCueSystem_Emit(ETA_AUDIO_CUE_OBJECTIVE, 0, 0);
}

void ETA_AudioCueSystem_PlayInteractionCue(void)
{
    ETA_AudioCueSystem_Emit(ETA_AUDIO_CUE_INTERACTION, 0, 0);
}

void ETA_AudioCueSystem_PlayDamageDirectionCue(int directionDegrees)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(directionDegrees, 0, 359, "audio_cue_system.PlayDamageDirectionCue")))
    {
        return;
    }

    ETA_AudioCueSystem_Emit(ETA_AUDIO_CUE_DAMAGE_DIRECTION, directionDegrees, 1);
}

void ETA_AudioCueSystem_PlayObjectiveDirectionCue(int directionDegrees)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(directionDegrees, 0, 359, "audio_cue_system.PlayObjectiveDirectionCue")))
    {
        return;
    }

    ETA_AudioCueSystem_Emit(ETA_AUDIO_CUE_OBJECTIVE_DIRECTION, directionDegrees, 1);
}

const char *ETA_AudioCueSystem_GetCueName(ETA_AudioCueType type)
{
    switch (type)
    {
        case ETA_AUDIO_CUE_LOW_HEALTH:
            return "low_health";

        case ETA_AUDIO_CUE_OBJECTIVE:
            return "objective";

        case ETA_AUDIO_CUE_INTERACTION:
            return "interaction";

        case ETA_AUDIO_CUE_DAMAGE_DIRECTION:
            return "damage_direction";

        case ETA_AUDIO_CUE_OBJECTIVE_DIRECTION:
            return "objective_direction";

        default:
            return "unknown";
    }
}

void ETA_AudioCueSystem_Shutdown(void)
{
    /* Dropped before the platform teardown: the backend usually lives in
       a game module that is about to be unloaded. */
    gBackend     = 0;
    gBackendData = 0;

    ETA_WindowsAudioCue_Shutdown();
}

#include "audio/audio_cue_system.h"
#include "core/accessibility_runtime.h"
#include "smoke_check.h"

#include <string.h>

/* Records what the cue system hands a backend, so the test can assert on
   it rather than on a sound nobody here can hear. */
typedef struct
{
    int              calls;
    ETA_AudioCueType type;
    int              directionDegrees;
    int              hasDirection;
    int              userDataOk;
} CueRecorder;

static CueRecorder gRecorder;

static void RecordCue(ETA_AudioCueType type, int directionDegrees, int hasDirection, void *userData)
{
    gRecorder.calls++;
    gRecorder.type             = type;
    gRecorder.directionDegrees = directionDegrees;
    gRecorder.hasDirection     = hasDirection;
    gRecorder.userDataOk       = (userData == &gRecorder);
}

int main(void)
{
    SMOKE_BANNER("audio_cue");

    ETA_AccessibilityRuntime_Init();
    ETA_AudioCueSystem_Init();

    /* Cue names are what the platform backend is asked to play, so an empty
       or missing one would mean a silent cue. */
    CHECK(strlen(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_LOW_HEALTH)) > 0);
    CHECK(strlen(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_OBJECTIVE)) > 0);
    CHECK(strlen(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_INTERACTION)) > 0);
    CHECK(strlen(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_DAMAGE_DIRECTION)) > 0);
    CHECK(strlen(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_OBJECTIVE_DIRECTION)) > 0);

    /* Every cue type must map to its own sound. */
    CHECK(strcmp(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_DAMAGE_DIRECTION),
                 ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_OBJECTIVE_DIRECTION)) != 0);
    CHECK(strcmp(ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_LOW_HEALTH),
                 ETA_AudioCueSystem_GetCueName(ETA_AUDIO_CUE_OBJECTIVE)) != 0);

    /* An unknown enum value must still return something printable. */
    CHECK(ETA_AudioCueSystem_GetCueName((ETA_AudioCueType)999) != NULL);

    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayLowHealthCue());
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayObjectiveCue());
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayInteractionCue());

    /* Bearings are compass degrees; the engine integrations feed these the
       result of AngleNormalize360, so 0 and 359 are the boundaries that
       must be accepted and 360 must not be. */
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayDamageDirectionCue(0));
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayDamageDirectionCue(90));
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayDamageDirectionCue(359));
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayObjectiveDirectionCue(0));
    CHECK_ACCEPTS(ETA_AudioCueSystem_PlayObjectiveDirectionCue(359));

    /* Out-of-range directions must be rejected by the runtime guard, not
       forwarded to the platform backend. */
    CHECK_REJECTS(ETA_AudioCueSystem_PlayDamageDirectionCue(-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_AudioCueSystem_PlayDamageDirectionCue(360), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_AudioCueSystem_PlayObjectiveDirectionCue(-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_AudioCueSystem_PlayObjectiveDirectionCue(360), ETA_ERROR_INVALID_VALUE);

    /* With a backend registered, cues must reach it instead of the tone
       generator, carrying the right type and bearing. This is what the
       engine integrations rely on to play real game sounds, so a silent
       regression here would take the cues away in-game while every other
       check kept passing. */
    ETA_AudioCueSystem_SetBackend(RecordCue, &gRecorder);

    gRecorder.calls = 0;
    ETA_AudioCueSystem_PlayLowHealthCue();
    CHECK(gRecorder.calls == 1);
    CHECK(gRecorder.type == ETA_AUDIO_CUE_LOW_HEALTH);
    CHECK(gRecorder.hasDirection == 0);
    CHECK(gRecorder.userDataOk);

    ETA_AudioCueSystem_PlayInteractionCue();
    CHECK(gRecorder.calls == 2);
    CHECK(gRecorder.type == ETA_AUDIO_CUE_INTERACTION);

    ETA_AudioCueSystem_PlayDamageDirectionCue(90);
    CHECK(gRecorder.calls == 3);
    CHECK(gRecorder.type == ETA_AUDIO_CUE_DAMAGE_DIRECTION);
    CHECK(gRecorder.hasDirection == 1);
    CHECK(gRecorder.directionDegrees == 90);

    ETA_AudioCueSystem_PlayObjectiveDirectionCue(270);
    CHECK(gRecorder.calls == 4);
    CHECK(gRecorder.type == ETA_AUDIO_CUE_OBJECTIVE_DIRECTION);
    CHECK(gRecorder.directionDegrees == 270);

    /* The range guard still runs ahead of the backend: an out-of-range
       bearing must be rejected, not forwarded to the engine. */
    CHECK_REJECTS(ETA_AudioCueSystem_PlayDamageDirectionCue(360), ETA_ERROR_INVALID_VALUE);
    CHECK(gRecorder.calls == 4);

    /* Shutdown drops the backend, because it usually lives in a module
       that is about to be unloaded. */
    ETA_AudioCueSystem_Shutdown();
    ETA_AudioCueSystem_Init();
    gRecorder.calls = 0;
    ETA_AudioCueSystem_PlayObjectiveCue();
    CHECK(gRecorder.calls == 0);

    ETA_AudioCueSystem_Shutdown();
    ETA_AccessibilityRuntime_Shutdown();

    return SMOKE_REPORT("audio_cue");
}

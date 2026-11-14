#include "windows_audio_cue.h"

#ifdef _WIN32

#include <windows.h>
#include <mmsystem.h>

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ETA_AUDIO_SAMPLE_RATE 22050
#define ETA_AUDIO_CHANNELS 2
#define ETA_AUDIO_BITS_PER_SAMPLE 16
#define ETA_AUDIO_AMPLITUDE 9000.0
/* Linear fade in/out applied to every tone segment, in samples (~10ms), to
   avoid the audible click a hard-edged sine burst would otherwise produce. */
#define ETA_AUDIO_FADE_SAMPLES 220
#define ETA_AUDIO_PI 3.14159265358979323846

#pragma pack(push, 1)
typedef struct ETA_WavHeader
{
    char riffId[4];
    unsigned int riffSize;
    char waveId[4];
    char fmtId[4];
    unsigned int fmtSize;
    unsigned short audioFormat;
    unsigned short numChannels;
    unsigned int sampleRate;
    unsigned int byteRate;
    unsigned short blockAlign;
    unsigned short bitsPerSample;
    char dataId[4];
    unsigned int dataSize;
} ETA_WavHeader;
#pragma pack(pop)

/* A cue is one or more tone segments (with optional trailing silence)
   concatenated into a single short in-memory WAV clip. pan runs from -1.0
   (full left) through 0.0 (center) to 1.0 (full right). */
typedef struct ETA_ToneSegment
{
    double frequencyHz;
    double durationSeconds;
    double pan;
    double silenceAfterSeconds;
} ETA_ToneSegment;

/* The buffer PlaySoundW is currently/last playing from. PlaySoundW stops any
   sound this process is already playing asynchronously before starting a
   new one, so by the time a PlaySoundW call returns, the previous buffer's
   playback has ended and it is safe to free it - see ETA_WindowsAudioCue_PlayBuffer. */
static unsigned char *gCurrentCueBuffer = NULL;

static void ETA_WriteToneSamples(short *samples, int sampleCount, double frequencyHz, double pan)
{
    int i;
    /* Balance-control pan law: the channel on the pan side stays at full
       amplitude and only the opposite channel is attenuated, so a centered
       (pan == 0.0) cue is exactly as loud as a fully panned one. A 50/50
       crossfade law would instead halve peak amplitude at center, making
       the three centered cues (low_health, objective, interaction) sound
       noticeably quieter than the panned ones. */
    double leftGain  = (pan <= 0.0) ? 1.0 : (1.0 - pan);
    double rightGain = (pan >= 0.0) ? 1.0 : (1.0 + pan);

    for (i = 0; i < sampleCount; i++)
    {
        double t         = (double)i / (double)ETA_AUDIO_SAMPLE_RATE;
        double raw        = sin(2.0 * ETA_AUDIO_PI * frequencyHz * t);
        double envelope   = 1.0;

        if (i < ETA_AUDIO_FADE_SAMPLES)
        {
            envelope = (double)i / (double)ETA_AUDIO_FADE_SAMPLES;
        }
        else if (i >= sampleCount - ETA_AUDIO_FADE_SAMPLES)
        {
            envelope = (double)(sampleCount - i) / (double)ETA_AUDIO_FADE_SAMPLES;
        }

        samples[i * 2 + 0] = (short)(raw * envelope * ETA_AUDIO_AMPLITUDE * leftGain);
        samples[i * 2 + 1] = (short)(raw * envelope * ETA_AUDIO_AMPLITUDE * rightGain);
    }
}

static unsigned char *ETA_BuildCueWav(const ETA_ToneSegment *segments, int segmentCount)
{
    int totalSamples = 0;
    int i;
    unsigned char *buffer;
    ETA_WavHeader *header;
    short *samples;
    int sampleOffset;
    unsigned int dataSize;

    for (i = 0; i < segmentCount; i++)
    {
        totalSamples += (int)(segments[i].durationSeconds * ETA_AUDIO_SAMPLE_RATE);
        totalSamples += (int)(segments[i].silenceAfterSeconds * ETA_AUDIO_SAMPLE_RATE);
    }

    if (totalSamples <= 0)
    {
        return NULL;
    }

    dataSize = (unsigned int)(totalSamples * ETA_AUDIO_CHANNELS * (ETA_AUDIO_BITS_PER_SAMPLE / 8));
    buffer   = (unsigned char *)malloc(sizeof(ETA_WavHeader) + dataSize);

    if (!buffer)
    {
        return NULL;
    }

    header = (ETA_WavHeader *)buffer;
    memcpy(header->riffId, "RIFF", 4);
    header->riffSize = (unsigned int)(sizeof(ETA_WavHeader) - 8 + dataSize);
    memcpy(header->waveId, "WAVE", 4);
    memcpy(header->fmtId, "fmt ", 4);
    header->fmtSize       = 16;
    header->audioFormat   = 1; /* PCM */
    header->numChannels   = ETA_AUDIO_CHANNELS;
    header->sampleRate    = ETA_AUDIO_SAMPLE_RATE;
    header->bitsPerSample = ETA_AUDIO_BITS_PER_SAMPLE;
    header->blockAlign    = (unsigned short)(ETA_AUDIO_CHANNELS * (ETA_AUDIO_BITS_PER_SAMPLE / 8));
    header->byteRate      = header->sampleRate * header->blockAlign;
    memcpy(header->dataId, "data", 4);
    header->dataSize = dataSize;

    samples      = (short *)(buffer + sizeof(ETA_WavHeader));
    sampleOffset = 0;

    for (i = 0; i < segmentCount; i++)
    {
        int toneSamples    = (int)(segments[i].durationSeconds * ETA_AUDIO_SAMPLE_RATE);
        int silenceSamples = (int)(segments[i].silenceAfterSeconds * ETA_AUDIO_SAMPLE_RATE);

        ETA_WriteToneSamples(samples + (size_t)sampleOffset * ETA_AUDIO_CHANNELS, toneSamples, segments[i].frequencyHz, segments[i].pan);
        sampleOffset += toneSamples;

        if (silenceSamples > 0)
        {
            memset(samples + (size_t)sampleOffset * ETA_AUDIO_CHANNELS, 0, (size_t)silenceSamples * ETA_AUDIO_CHANNELS * sizeof(short));
            sampleOffset += silenceSamples;
        }
    }

    return buffer;
}

/* Maps a cue name to its tone recipe. Cue identity comes from pitch/pattern
   (so low_health, objective, interaction, and the two directional cues are
   all distinguishable by ear); direction, when present, is conveyed only by
   stereo pan - a deliberate prototype-level simplification with no
   front/back distinction, since 0 and 180 degrees both pan to center. */
static unsigned char *ETA_BuildCueBufferForName(const char *cueName, int directionDegrees, int hasDirection)
{
    ETA_ToneSegment segments[2];
    int segmentCount;
    double pan = 0.0;

    if (hasDirection)
    {
        double radians = (double)directionDegrees * ETA_AUDIO_PI / 180.0;

        pan = sin(radians);
    }

    if (strcmp(cueName, "low_health") == 0)
    {
        segments[0].frequencyHz        = 220.0;
        segments[0].durationSeconds    = 0.09;
        segments[0].pan                = 0.0;
        segments[0].silenceAfterSeconds = 0.04;

        segments[1].frequencyHz        = 220.0;
        segments[1].durationSeconds    = 0.09;
        segments[1].pan                = 0.0;
        segments[1].silenceAfterSeconds = 0.0;

        segmentCount = 2;
    }
    else if (strcmp(cueName, "objective") == 0)
    {
        segments[0].frequencyHz        = 660.0;
        segments[0].durationSeconds    = 0.18;
        segments[0].pan                = 0.0;
        segments[0].silenceAfterSeconds = 0.0;

        segmentCount = 1;
    }
    else if (strcmp(cueName, "interaction") == 0)
    {
        segments[0].frequencyHz        = 1000.0;
        segments[0].durationSeconds    = 0.07;
        segments[0].pan                = 0.0;
        segments[0].silenceAfterSeconds = 0.0;

        segmentCount = 1;
    }
    else if (strcmp(cueName, "damage_direction") == 0)
    {
        segments[0].frequencyHz        = 350.0;
        segments[0].durationSeconds    = 0.15;
        segments[0].pan                = pan;
        segments[0].silenceAfterSeconds = 0.0;

        segmentCount = 1;
    }
    else if (strcmp(cueName, "objective_direction") == 0)
    {
        segments[0].frequencyHz        = 750.0;
        segments[0].durationSeconds    = 0.15;
        segments[0].pan                = pan;
        segments[0].silenceAfterSeconds = 0.0;

        segmentCount = 1;
    }
    else
    {
        segments[0].frequencyHz        = 440.0;
        segments[0].durationSeconds    = 0.15;
        segments[0].pan                = 0.0;
        segments[0].silenceAfterSeconds = 0.0;

        segmentCount = 1;
    }

    return ETA_BuildCueWav(segments, segmentCount);
}

static void ETA_WindowsAudioCue_PlayBuffer(unsigned char *buffer)
{
    unsigned char *previousBuffer;

    if (!buffer)
    {
        return;
    }

    previousBuffer = gCurrentCueBuffer;

    PlaySoundW((LPCWSTR)buffer, NULL, SND_MEMORY | SND_ASYNC | SND_NODEFAULT);

    free(previousBuffer);
    gCurrentCueBuffer = buffer;
}

void ETA_WindowsAudioCue_Init(void)
{
    printf("[Accessibility] Windows audio cue backend initialized\n");
}

void ETA_WindowsAudioCue_Play(const char *cueName)
{
    unsigned char *buffer;

    if (!cueName)
    {
        return;
    }

    buffer = ETA_BuildCueBufferForName(cueName, 0, 0);
    ETA_WindowsAudioCue_PlayBuffer(buffer);
}

void ETA_WindowsAudioCue_PlayDirectional(const char *cueName, int directionDegrees)
{
    unsigned char *buffer;

    if (!cueName)
    {
        return;
    }

    buffer = ETA_BuildCueBufferForName(cueName, directionDegrees, 1);
    ETA_WindowsAudioCue_PlayBuffer(buffer);
}

void ETA_WindowsAudioCue_Shutdown(void)
{
    PlaySoundW(NULL, NULL, 0);

    free(gCurrentCueBuffer);
    gCurrentCueBuffer = NULL;

    printf("[Accessibility] Windows audio cue backend shutdown\n");
}

#else

#include "../../core/debug_log.h"

void ETA_WindowsAudioCue_Init(void)
{
    ETA_DebugLog_Warning("windows_audio_cue", "No audio cue backend available on this platform yet");
}

void ETA_WindowsAudioCue_Play(const char *cueName)
{
    (void)cueName;
}

void ETA_WindowsAudioCue_PlayDirectional(const char *cueName, int directionDegrees)
{
    (void)cueName;
    (void)directionDegrees;
}

void ETA_WindowsAudioCue_Shutdown(void)
{
}

#endif

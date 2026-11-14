#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void ETA_Speech_Init(void);
void ETA_Speech_Say(const char *message);

/*
 * Says text of any length - a page of orders, a letter - as pieces of at
 * most ETA_SPEECH_PIECE_LENGTH characters, split on sentences, with its
 * line breaks and runs of spaces read as single spaces. On the Mac, where
 * VoiceOver keeps only the last of several lines said at once, the whole
 * text is one line.
 */
#define ETA_SPEECH_PIECE_LENGTH 400
void ETA_Speech_SayLong(const char *text);

/*
 * Groups everything said between them into one spoken line.
 *
 * A report made of several Say calls is not heard as several sentences. The
 * SAPI backend speaks with SPF_PURGEBEFORESPEAK, so each message cancels the
 * one still being spoken and only the last survives - a six-part status
 * report becomes its last fragment. Screen readers differ on this, so the
 * fix is not to rely on any of them: a report that must be heard whole is
 * composed into a single message before it reaches a backend at all.
 *
 * Between Begin and End, Say appends rather than speaks. End speaks the
 * joined result once, and that whole line is what RepeatLast replays. Begin
 * without End says nothing, which is the safe way to fail.
 */
void ETA_Speech_BeginReport(void);
void ETA_Speech_EndReport(void);
void ETA_Speech_Stop(void);
void ETA_Speech_RepeatLast(void);

/*
 * The last line actually spoken, or NULL before anything has been. This is
 * the same string RepeatLast replays; it is exposed so a test can assert
 * what a report composed to, which is otherwise only observable by ear.
 */
const char *ETA_Speech_GetLastMessage(void);

/*
 * How many times the mod has decided to say something, ever.
 *
 * A caller that wants to react to speech starting - the music ducking
 * does - watches this for a change rather than being called back, because
 * the speech path is inside a static library with no clock and no way to
 * reach the engine. The engine already runs a frame loop; this is the
 * cheapest thing it can poll.
 *
 * It counts decisions, not sounds. See the comment at the increment.
 */
int ETA_Speech_GetSpokenSerial(void);

/*
 * Roughly how long a line will take to speak, in milliseconds.
 *
 * An estimate from the length of the text, and unavoidably so: SAPI speaks
 * asynchronously and NVDA's controller client exposes no completion
 * callback, so nothing on either path reports when the words stop. Biased
 * slow on purpose - see the comment on the constants.
 *
 * Returns 0 for NULL or an empty string, so a caller can treat "nothing to
 * say" as "nothing to wait for" without a special case.
 */
int ETA_Speech_EstimateDurationMs(const char *message);

/*
 * A deliberately unhurried voice: about 200 words a minute, which is near
 * the slow end of what a screen reader user runs. The floor keeps a
 * two-word answer from being over before the music has finished dipping;
 * the ceiling keeps a pathological line from muting the music for a
 * minute.
 */
#define ETA_SPEECH_MS_PER_CHARACTER 60
#define ETA_SPEECH_MIN_DURATION_MS  700
#define ETA_SPEECH_MAX_DURATION_MS  6000

/*
 * The voice, for the SAPI 5 fallback only.
 *
 * NVDA is deliberately untouched by these. Its controller client has
 * three entry points - is it running, say this, stop - and none of them
 * carries a rate, a pitch or a volume, because NVDA speaks at the
 * settings its own user chose and that is the correct behaviour: a screen
 * reader user has already picked a voice they can follow, and a game
 * quietly overriding it would be a bug, not a feature. So when NVDA is
 * driving, these do nothing, and the install guide says so rather than
 * leaving somebody turning a dead knob.
 *
 * For SAPI, where there is no such user preference to respect, they are
 * the only way to be heard: rate and volume go through ISpVoice directly,
 * pitch through the markup SAPI reads.
 *
 * Ranges are SAPI's own. Rate and pitch run -10 to 10 about a default of
 * 0; volume is a percentage. Out-of-range values are clamped rather than
 * rejected, because these come from cvars and a cvar holds whatever
 * somebody typed - and SAPI's own setters fail silently on a bad value,
 * which is indistinguishable from a setting that does nothing.
 */
#define ETA_SPEECH_RATE_MIN   (-10)
#define ETA_SPEECH_RATE_MAX   10
#define ETA_SPEECH_PITCH_MIN  (-10)
#define ETA_SPEECH_PITCH_MAX  10
#define ETA_SPEECH_VOLUME_MIN 0
#define ETA_SPEECH_VOLUME_MAX 100

void ETA_Speech_SetVoice(int rate, int pitch, int volume);

/* What was actually stored, after clamping - so a test can assert the
   clamp rather than having to listen for it. */
int ETA_Speech_GetVoiceRate(void);
int ETA_Speech_GetVoicePitch(void);
int ETA_Speech_GetVoiceVolume(void);

/*
 * XML-escapes a line for SAPI's markup parser.
 *
 * Only needed on the pitch path: pitch is the one of the three SAPI has
 * no setter for, so it is expressed as markup wrapped around the text,
 * and text handed to a markup parser has to be escaped or it is not the
 * text any more. A player called `<axis>` or `Tom & Jerry` is not
 * hypothetical, and an unescaped one would not mispronounce - it would
 * make the whole line unparseable and silence it.
 *
 * Truncates on a whole character rather than mid-entity, and always
 * terminates. Returns the number of bytes written, excluding the
 * terminator.
 */
int ETA_Speech_EscapeXml(const char *in, char *out, size_t outSize);
void ETA_Speech_Shutdown(void);

#ifdef __cplusplus
}
#endif

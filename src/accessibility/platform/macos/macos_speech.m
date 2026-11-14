#include "macos_speech.h"

#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>

#include <stdio.h>

/*
 * VoiceOver, then the system voice.
 *
 * VoiceOver: an NSAccessibilityAnnouncementRequestedNotification posted
 * on the application is read out by VoiceOver like any other app's
 * announcement, in the player's own voice. Medium priority, so it waits
 * behind what VoiceOver is already saying - the way NVDA queues - and
 * high priority only to cut in, which is how a stop is made: VoiceOver
 * has no other way for an app to silence it.
 *
 * The system voice: AVSpeechSynthesizer, which queues by itself. A line
 * is queued behind the last unless ETA_MAC_BACKLOG are already waiting,
 * when the queue is cleared first so the voice never falls far behind
 * the game - the same rule SAPI 5 follows (windows_speech.c).
 *
 * Built for the oldest macOS ET: Legacy supports, so everything newer is
 * asked for by @available, and is simply silent where it is missing.
 */

#define ETA_MAC_BACKLOG 3

API_AVAILABLE(macos(10.14))
@interface ETAMacSpeechCounter : NSObject <AVSpeechSynthesizerDelegate>
@property (atomic) int waiting;
@end

@implementation ETAMacSpeechCounter
- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer didFinishSpeechUtterance:(AVSpeechUtterance *)utterance
{
    (void)synthesizer;
    (void)utterance;
    if (self.waiting > 0)
    {
        self.waiting--;
    }
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer didCancelSpeechUtterance:(AVSpeechUtterance *)utterance
{
    (void)synthesizer;
    (void)utterance;
    if (self.waiting > 0)
    {
        self.waiting--;
    }
}
@end

static id  gSynthesizer;   /* AVSpeechSynthesizer, held as id so 10.13 still links */
static id  gCounter;
static int gRate;
static int gPitch;
static int gVolume = 100;

static int ETA_MacSpeech_VoiceOverOn(void)
{
    if (@available(macOS 10.13, *))
    {
        return [[NSWorkspace sharedWorkspace] isVoiceOverEnabled] ? 1 : 0;
    }
    return 0;
}

static void ETA_MacSpeech_Announce(NSString *text, NSAccessibilityPriorityLevel priority)
{
    id element = [NSApp mainWindow] ? (id)[NSApp mainWindow] : (id)NSApp;

    if (!element)
    {
        return;
    }

    NSAccessibilityPostNotificationWithUserInfo(element, NSAccessibilityAnnouncementRequestedNotification,
                                                @{ NSAccessibilityAnnouncementKey: text,
                                                   NSAccessibilityPriorityKey: @(priority) });
}

void ETA_MacSpeech_Init(void)
{
    @autoreleasepool
    {
        if (@available(macOS 10.14, *))
        {
            if (!gSynthesizer)
            {
                ETAMacSpeechCounter *counter = [[ETAMacSpeechCounter alloc] init];
                AVSpeechSynthesizer *synthesizer = [[AVSpeechSynthesizer alloc] init];

                synthesizer.delegate = counter;
                gCounter     = counter;
                gSynthesizer = synthesizer;
                printf("[Accessibility] macOS speech initialized\n");
            }
        }
    }
}

void ETA_MacSpeech_SetVoice(int rate, int pitch, int volume)
{
    gRate   = rate;
    gPitch  = pitch;
    gVolume = volume;
}

int ETA_MacSpeech_Speak(const char *message)
{
    if (!message || !message[0])
    {
        return 0;
    }

    @autoreleasepool
    {
        NSString *text = [NSString stringWithUTF8String:message];

        if (!text)
        {
            return 0;
        }

        if (ETA_MacSpeech_VoiceOverOn())
        {
            ETA_MacSpeech_Announce(text, NSAccessibilityPriorityMedium);
            return 1;
        }

        if (@available(macOS 10.14, *))
        {
            AVSpeechSynthesizer *synthesizer = gSynthesizer;
            ETAMacSpeechCounter *counter     = gCounter;
            AVSpeechUtterance   *utterance;
            float               speed;

            if (!synthesizer)
            {
                return 0;
            }

            if (counter.waiting >= ETA_MAC_BACKLOG)
            {
                [synthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];
                counter.waiting = 0;
            }

            utterance = [AVSpeechUtterance speechUtteranceWithString:text];

            /* -10 to 10 round the voice's own default, as SAPI's is. */
            speed = AVSpeechUtteranceDefaultSpeechRate
                    + (float)gRate * (gRate > 0 ? (AVSpeechUtteranceMaximumSpeechRate - AVSpeechUtteranceDefaultSpeechRate)
                                                : (AVSpeechUtteranceDefaultSpeechRate - AVSpeechUtteranceMinimumSpeechRate)) / 10.0f;
            utterance.rate            = speed;
            utterance.pitchMultiplier = 1.0f + (float)gPitch * (gPitch > 0 ? 0.1f : 0.05f);
            utterance.volume          = (float)gVolume / 100.0f;

            counter.waiting++;
            [synthesizer speakUtterance:utterance];
            return 1;
        }
    }

    return 0;
}

void ETA_MacSpeech_Stop(void)
{
    @autoreleasepool
    {
        if (ETA_MacSpeech_VoiceOverOn())
        {
            /* VoiceOver has no stop for an app: a blank line said at high
               priority cuts off what it was saying. */
            ETA_MacSpeech_Announce(@" ", NSAccessibilityPriorityHigh);
            return;
        }

        if (@available(macOS 10.14, *))
        {
            AVSpeechSynthesizer *synthesizer = gSynthesizer;
            ETAMacSpeechCounter *counter     = gCounter;

            [synthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];
            counter.waiting = 0;
        }
    }
}

void ETA_MacSpeech_Shutdown(void)
{
    @autoreleasepool
    {
        if (@available(macOS 10.14, *))
        {
            AVSpeechSynthesizer *synthesizer = gSynthesizer;

            [synthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];
        }
        gSynthesizer = nil;
        gCounter     = nil;
    }
}

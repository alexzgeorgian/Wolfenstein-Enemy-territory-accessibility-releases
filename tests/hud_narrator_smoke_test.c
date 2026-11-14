#include "core/accessibility_runtime.h"
#include "hud/hud_narrator.h"
#include "smoke_check.h"

#include <stdlib.h>
#include <string.h>

static char *HeapCopy(const char *text)
{
    char *copy = (char *)malloc(strlen(text) + 1);

    strcpy(copy, text);

    return copy;
}

/* Scribble over the buffer before freeing: if a narrator kept the caller's
   pointer instead of copying, later narration reads the poison rather than
   the original text, and under a sanitizer it reads freed memory outright. */
static void PoisonAndFree(char *text)
{
    memset(text, 'X', strlen(text));
    free(text);
}

static char *OverlongText(size_t length)
{
    char *text = (char *)malloc(length + 1);

    memset(text, 'a', length);
    text[length] = '\0';

    return text;
}

static ETA_AwareThing Aware(int id, ETA_AwareKind kind, float meters, float leftOfView,
                            const char *name)
{
    ETA_AwareThing thing;

    memset(&thing, 0, sizeof(thing));
    thing.id          = id;
    thing.kind        = kind;
    thing.meters      = meters;
    thing.leftOfView = leftOfView;
    strncpy(thing.name, name, sizeof(thing.name) - 1);

    return thing;
}

int main(void)
{
    char *weaponName;
    char *objectiveText;
    char *overlong;

    SMOKE_BANNER("hud_narrator");

    ETA_AccessibilityRuntime_Init();
    ETA_HudNarrator_Init();

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakHealth(75));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakAmmo(30));

    /* SpeakWeapon/SpeakObjective must not hold onto the caller's pointer past
       the call, so freeing the source right after must not leave anything
       reading freed memory. */

    weaponName = HeapCopy("MP40");
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakWeapon(weaponName));
    PoisonAndFree(weaponName);

    objectiveText = HeapCopy("Capture the forward bunker");
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakObjective(objectiveText));
    PoisonAndFree(objectiveText);

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakRespawn(10));

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakStance(ETA_STANCE_STANDING));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakStance(ETA_STANCE_CROUCHED));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakStance(ETA_STANCE_PRONE));

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakGain(30, 1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakGain(1, 1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakGain(25, 0));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakAlreadyFull());

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakZoom(ETA_ZOOM_OFF));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakZoom(ETA_ZOOM_BINOCULARS));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakZoom(ETA_ZOOM_SCOPE));
    CHECK_REJECTS(ETA_HudNarrator_SpeakZoom((ETA_Zoom)-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakZoom((ETA_Zoom)3), ETA_ERROR_INVALID_VALUE);

    /* The description comes from the engine's own surface and entity
       data, so the same absent-string hazards apply as to a weapon name.
       A negative distance is the caller saying there is no sensible one -
       open sky, or nothing in range - and must not be announced as a
       number. */
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakLookAhead("Wood wall", 12));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakLookAhead("Open sky", -1));
    CHECK_REJECTS(ETA_HudNarrator_SpeakLookAhead(NULL, 5), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_HudNarrator_SpeakLookAhead("", 5), ETA_ERROR_INVALID_STRING);

    /* A gain of nothing is "already full", never "0 rounds": the caller
       decides which of the two it is, and this one must refuse rather
       than announce a gain that did not happen. */
    CHECK_REJECTS(ETA_HudNarrator_SpeakGain(0, 1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakGain(-5, 1), ETA_ERROR_INVALID_VALUE);

    /* The engine integrations pass gitem_t.pickup_name and oidInfo->name
       straight through, either of which can be absent, so these guards are
       the thing standing between a missing name and a crash. */
    CHECK_REJECTS(ETA_HudNarrator_SpeakWeapon(NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_HudNarrator_SpeakWeapon(""), ETA_ERROR_INVALID_STRING);
    CHECK_REJECTS(ETA_HudNarrator_SpeakObjective(NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_HudNarrator_SpeakObjective(""), ETA_ERROR_INVALID_STRING);

    overlong = OverlongText(ETA_MAX_HUD_TEXT_LENGTH + 1);
    CHECK_REJECTS(ETA_HudNarrator_SpeakWeapon(overlong), ETA_ERROR_STRING_TOO_LONG);
    CHECK_REJECTS(ETA_HudNarrator_SpeakObjective(overlong), ETA_ERROR_STRING_TOO_LONG);
    free(overlong);

    /* Exactly at the limit must still be accepted. An objective report can be
       a joined list of names, so this boundary is reachable in real play. */
    overlong = OverlongText(ETA_MAX_HUD_TEXT_LENGTH);
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakObjective(overlong));
    free(overlong);

    /* The engines derive the stance from two independent bit flags, so an
       unmapped combination reaching here is a live possibility rather than a
       theoretical one. It must be refused, not used to index the name table:
       the value is an array subscript, and a wrong one reads out of bounds
       and hands whatever it finds to a screen reader. */
    CHECK_REJECTS(ETA_HudNarrator_SpeakStance((ETA_Stance)-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakStance((ETA_Stance)3), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakStance((ETA_Stance)9999), ETA_ERROR_INVALID_VALUE);

    /* The facing has to agree with the compass a sighted player reads,
       so these are the four cardinals at the yaws the engine puts them
       at: north at 90, east at 0, south at 270, west at 180. Getting
       this backwards is the one failure a blind player cannot detect
       and cannot recover from. */
    CHECK(ETA_HudNarrator_FacingFromYaw(90.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromYaw(0.0f) == ETA_FACING_EAST);
    CHECK(ETA_HudNarrator_FacingFromYaw(270.0f) == ETA_FACING_SOUTH);
    CHECK(ETA_HudNarrator_FacingFromYaw(180.0f) == ETA_FACING_WEST);
    CHECK(ETA_HudNarrator_FacingFromYaw(45.0f) == ETA_FACING_NORTHEAST);
    CHECK(ETA_HudNarrator_FacingFromYaw(135.0f) == ETA_FACING_NORTHWEST);
    CHECK(ETA_HudNarrator_FacingFromYaw(225.0f) == ETA_FACING_SOUTHWEST);
    CHECK(ETA_HudNarrator_FacingFromYaw(315.0f) == ETA_FACING_SOUTHEAST);

    /* Engine yaw is not always wrapped - it accumulates through mouse
       movement and arrives negative or past 360 - so the same heading
       expressed three ways has to give the same word. */
    CHECK(ETA_HudNarrator_FacingFromYaw(-270.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromYaw(450.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromYaw(-0.5f) == ETA_FACING_EAST);
    CHECK(ETA_HudNarrator_FacingFromYaw(720.0f) == ETA_FACING_EAST);

    /* Each point owns the 45 degrees centred on it, so due north is the
       middle of "north" and the boundaries sit at 22.5 either side. */
    CHECK(ETA_HudNarrator_FacingFromYaw(90.0f + 22.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromYaw(90.0f - 22.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromYaw(90.0f + 23.0f) == ETA_FACING_NORTHWEST);
    CHECK(ETA_HudNarrator_FacingFromYaw(90.0f - 23.0f) == ETA_FACING_NORTHEAST);

    /* The tracker speaks the first reading, stays quiet while the view
       holds, and refuses to flip on a boundary wobble - which is where a
       player lining something up actually sits. */
    {
        ETA_Facing facing = ETA_FACING_NORTH;
        int        t      = 10000;

        ETA_HudNarrator_ResetFacing();
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 1);
        CHECK(facing == ETA_FACING_NORTH);
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 0);
        CHECK(ETA_HudNarrator_UpdateFacing(100.0f, t, &facing) == 0);

        /* Just past the boundary is inside the next sector but inside the
           hysteresis margin too, so it is not believed yet. */
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f + 24.0f, t, &facing) == 0);

        /* Well inside the next sector, but only just arrived: the view is
           still moving as far as this knows, so nothing is said yet. */
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f + 35.0f, t, &facing) == 0);

        /* Held there, and it is announced. */
        t += 400;
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f + 35.0f, t, &facing) == 1);
        CHECK(facing == ETA_FACING_NORTHWEST);

        /* Coming back has to clear the same margin the other way, so the
           hysteresis is symmetric rather than a one-way ratchet. */
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f + 24.0f, t, &facing) == 0);
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 0);
        t += 400;
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 1);
        CHECK(facing == ETA_FACING_NORTH);

        /* A sweep of the mouse, sampled the way the game actually calls
           this: every frame, not once per sector. Four sectors crossed,
           each one occupied for several frames but none of them held for
           the settle time. This is the case that produced four reports
           for one movement of the hand.
           
           Two things have to be true through all of it, and an earlier
           version of this test checked neither. Frames *inside* one
           sector must not be enough on their own - sampling once per
           sector let a settle time of zero pass this. And the clock must
           restart on each new sector rather than running from the start
           of the sweep - crossing four sectors takes longer than the
           settle time in total, so a pending timer that is not restarted
           fires mid-sweep, which is the bug being prevented. */
        ETA_HudNarrator_ResetFacing();
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 1);

        {
            static const float sweep[] = { 45.0f, 0.0f, 315.0f, 270.0f };
            int                sector;
            int                frame;

            for (sector = 0; sector < 4; sector++)
            {
                /* 5 frames at 25ms is 125ms in each sector: comfortably
                   more than one frame, comfortably less than the settle
                   time, and 500ms across the whole sweep - more than the
                   settle time, which is what makes the restart matter. */
                for (frame = 0; frame < 5; frame++)
                {
                    t += 25;
                    CHECK(ETA_HudNarrator_UpdateFacing(sweep[sector], t, &facing) == 0);
                }
            }
        }

        /* The hand stops. One report, naming where the view actually
           ended up - not the three it passed through on the way. */
        t += 400;
        CHECK(ETA_HudNarrator_UpdateFacing(270.0f, t, &facing) == 1);
        CHECK(facing == ETA_FACING_SOUTH);

        /* A slow, deliberate turn is not a sweep and must not be
           silenced: it dwells in each sector for longer than the settle
           time, and every heading it passes through is announced. */
        t += 800;
        CHECK(ETA_HudNarrator_UpdateFacing(225.0f, t, &facing) == 0);
        t += 800;
        CHECK(ETA_HudNarrator_UpdateFacing(225.0f, t, &facing) == 1);
        CHECK(facing == ETA_FACING_SOUTHWEST);

        /* Turning away and coming back before anything was said leaves
           nothing owing - the next stop is judged from where the view is
           now, not from a heading it passed through. */
        t += 800;
        CHECK(ETA_HudNarrator_UpdateFacing(180.0f, t, &facing) == 0);
        t += 20;
        CHECK(ETA_HudNarrator_UpdateFacing(225.0f, t, &facing) == 0);
        t += 800;
        CHECK(ETA_HudNarrator_UpdateFacing(225.0f, t, &facing) == 0);

        /* And the case the synthetic "slow turn" above never covered: a
           turn made by holding a key.

           This is not a free parameter. The engine moves the view at
           cl_yawspeed while the key is down - 140 degrees a second by
           default - so each 45-degree sector is occupied for 321 ms. The
           settle used to be 350, so the sector changed 29 ms before it
           ever completed and holding the key announced nothing at all,
           for ever. The player found it; nothing here could, because the
           turn above dwells for 800 ms, which no key can do.

           Sampled every 25 ms like the real frame loop, turning at the
           engine's own speed. Three seconds of holding must produce
           several headings, not silence. */
        {
            const float yawSpeed = 140.0f;   /* cl_yawspeed, ET's default */
            const int   frameMs  = 25;
            float       yaw      = 90.0f;
            int         spoken   = 0;
            int         frame;

            ETA_HudNarrator_ResetFacing();
            CHECK(ETA_HudNarrator_UpdateFacing(yaw, t, &facing) == 1);

            for (frame = 0; frame < 120; frame++)
            {
                t  += frameMs;
                yaw += yawSpeed * ((float)frameMs / 1000.0f);

                if (ETA_HudNarrator_UpdateFacing(yaw, t, &facing))
                {
                    spoken++;
                }
            }

            /* Three seconds at 140 degrees a second is 420 degrees -
               more than a full turn, so every one of the eight points is
               crossed. Anything less than most of them means the settle
               has drifted back above a sector's dwell time. */
            CHECK(spoken >= 6);
        }

        /* With a turn key down, a point is spoken as soon as the view is
           properly inside it, not after the settle wait: a held key is
           always a deliberate turn. Crossing from north (yaw 90) into
           north-east needs 22.5 degrees plus the hysteresis. */
        {
            ETA_HudNarrator_ResetFacing();
            CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 1);

            ETA_HudNarrator_SetFacingKeyTurn(1);
            CHECK(ETA_HudNarrator_UpdateFacing(90.0f - 30.0f, t + 10, &facing) == 0);
            CHECK(ETA_HudNarrator_UpdateFacing(90.0f - 31.0f, t + 20, &facing) == 1);
            CHECK(facing == ETA_FACING_NORTHEAST);

            /* Still inside the boundary's hysteresis: nothing, key or not. */
            CHECK(ETA_HudNarrator_UpdateFacing(90.0f - 45.0f - 24.0f, t + 30, &facing) == 0);

            /* Without the key, the same crossing waits for the settle. */
            ETA_HudNarrator_SetFacingKeyTurn(0);
            CHECK(ETA_HudNarrator_UpdateFacing(0.0f, t + 40, &facing) == 0);
            CHECK(ETA_HudNarrator_UpdateFacing(0.0f, t + 50, &facing) == 0);
            CHECK(ETA_HudNarrator_UpdateFacing(0.0f, t + 40 + 1000, &facing) == 1);
            CHECK(facing == ETA_FACING_EAST);
            t += 2000;
        }

        /* A tap that turned the view onto a point announces it itself;
           marking it held stops the next update saying it again. */
        {
            ETA_HudNarrator_ResetFacing();
            CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 1);

            ETA_HudNarrator_SetFacingHeld(ETA_FACING_EAST);
            CHECK(ETA_HudNarrator_UpdateFacing(0.0f, t + 10, &facing) == 0);
            CHECK(ETA_HudNarrator_UpdateFacing(0.0f, t + 10 + 2000, &facing) == 0);

            /* Nonsense is refused rather than stored. */
            ETA_HudNarrator_SetFacingHeld((ETA_Facing)9);
            CHECK(ETA_HudNarrator_UpdateFacing(0.0f, t + 20 + 2000, &facing) == 0);
            t += 3000;
        }

        /* A reset means the next reading is news again, which is what a
           respawn or a map change needs. */
        ETA_HudNarrator_ResetFacing();
        CHECK(ETA_HudNarrator_UpdateFacing(90.0f, t, &facing) == 1);

        /* A caller with nowhere to put the answer must not be written to
           through a null pointer. */
        CHECK(ETA_HudNarrator_UpdateFacing(180.0f, t, NULL) == 0);
    }

    /* The fall-damage heights are the engine's ladder turned back into a
       distance, so they have to come out at a believable human scale for
       the gravity ET actually ships with. Damage starts a little over six
       metres up and the fall is fatal a little over twelve - one storey
       hurts, three or four kills. A conversion out by a factor would fail
       both of these at once, the same way the metres check does. */
    {
        float injure = ETA_HudNarrator_FallHeightForDelta(38.75f, 800.0f);
        float deadly = ETA_HudNarrator_FallHeightForDelta(77.0f, 800.0f);

        CHECK(injure > 230.0f && injure < 250.0f);
        CHECK(deadly > 470.0f && deadly < 490.0f);

        /* Lower gravity means a longer fall before the same landing
           speed, so the same damage step sits further down. */
        CHECK(ETA_HudNarrator_FallHeightForDelta(77.0f, 400.0f) > deadly);

        /* Nothing falls without gravity, so no drop can ever be far
           enough down to be a hazard. */
        CHECK(ETA_HudNarrator_FallHeightForDelta(77.0f, 0.0f) > 1.0e8f);
    }

    /* The location tracker. Damped far harder than the compass, because
       a stock map carries over a hundred named places and a player at a
       walk crosses several of them without stopping anywhere. */
    {
        int t = 50000;

        ETA_HudNarrator_ResetLocation();

        /* The first place still has to be held - arriving is the event,
           not the snapshot that first mentions it. */
        CHECK(ETA_HudNarrator_UpdateLocation("Old City Wall", t) == 0);
        t += 2500;
        CHECK(ETA_HudNarrator_UpdateLocation("Old City Wall", t) == 1);

        /* Standing still says nothing more. */
        t += 5000;
        CHECK(ETA_HudNarrator_UpdateLocation("Old City Wall", t) == 0);

        /* Walking through somewhere without stopping is not an arrival.
           Sampled every frame, the way the game calls it - three places
           crossed, each one under the player for about a second. An
           earlier version of this named each place once, which passes
           with the settle time set to zero and so tested nothing. */
        {
            static const char *const crossed[] =
            { "Water Pump", "Courtyard", "Axis Command Post" };
            int place;
            int frame;

            for (place = 0; place < 3; place++)
            {
                for (frame = 0; frame < 20; frame++)
                {
                    t += 50;    /* 20 frames at 50ms = 1s in each place */
                    CHECK(ETA_HudNarrator_UpdateLocation(crossed[place], t) == 0);
                }
            }
        }

        /* Stopping there is. */
        t += 2500;
        CHECK(ETA_HudNarrator_UpdateLocation("Axis Command Post", t) == 1);

        /* Stepping out of a doorway and back again says nothing: the
           place being held never actually changed. */
        t += 500;
        CHECK(ETA_HudNarrator_UpdateLocation("Courtyard", t) == 0);
        t += 500;
        CHECK(ETA_HudNarrator_UpdateLocation("Axis Command Post", t) == 0);
        t += 5000;
        CHECK(ETA_HudNarrator_UpdateLocation("Axis Command Post", t) == 0);

        /* And coming back to that doorway later starts the clock over
           rather than resuming it. Without this, a player who steps in
           and out of somewhere repeatedly eventually has it announced
           on a step that never lasted - the part-finished timer from an
           earlier visit is still running underneath. */
        t += 3000;
        CHECK(ETA_HudNarrator_UpdateLocation("Courtyard", t) == 0);
        t += 1000;
        CHECK(ETA_HudNarrator_UpdateLocation("Courtyard", t) == 0);
        t += 1500;
        CHECK(ETA_HudNarrator_UpdateLocation("Courtyard", t) == 1);

        /* A frame with no answer - a snapshot arriving, a lookup that
           found nothing - must be ignored rather than treated as a
           place. Asserting only that it returns 0 proves nothing, since
           an unrecognised name returns 0 anyway; what has to be shown is
           that it does not disturb a settle already under way. So:
           start arriving somewhere, drop a blank frame into the middle,
           and require the arrival to still land on time. */
        t += 100;
        CHECK(ETA_HudNarrator_UpdateLocation("Tunnel Mouth", t) == 0);
        t += 1000;
        CHECK(ETA_HudNarrator_UpdateLocation(NULL, t) == 0);
        CHECK(ETA_HudNarrator_UpdateLocation("", t) == 0);
        t += 500;
        CHECK(ETA_HudNarrator_UpdateLocation("Tunnel Mouth", t) == 0);
        t += 700;
        CHECK(ETA_HudNarrator_UpdateLocation("Tunnel Mouth", t) == 1);

        /* A reset means the next place is news again: a map change. */
        ETA_HudNarrator_ResetLocation();
        CHECK(ETA_HudNarrator_UpdateLocation("Tunnel Mouth", t) == 0);
        t += 2500;
        CHECK(ETA_HudNarrator_UpdateLocation("Tunnel Mouth", t) == 1);

        /* A name longer than the buffer is truncated, not dropped, and
           must not run off the end of it. */
        ETA_HudNarrator_ResetLocation();
        {
            char huge[512];
            memset(huge, 'x', sizeof(huge) - 1);
            huge[sizeof(huge) - 1] = '\0';
            CHECK(ETA_HudNarrator_UpdateLocation(huge, t) == 0);
            t += 2500;
            CHECK(ETA_HudNarrator_UpdateLocation(huge, t) == 1);
        }
    }

    /* Openings along the way. Walking north up a street: walls close to
       the east and west, the way ahead and behind open. The side street
       on the east is the news; the lamp post, the doorway and a door
       swinging open beside someone standing still are not. Sampled every
       100ms, the way the game calls it. */
    {
        /* north, east, south, west; -1 is "runs on past the probe" */
        static const int street[4]   = { -1, 3, -1, 3 };
        static const int corner[4]   = { -1, 30, -1, 3 };
        static const int between[4]  = { -1, 6, -1, 3 };
        static const int square[4]   = { -1, -1, -1, -1 };
        char             text[128];
        int              opened, closed, t = 90000, k;

        ETA_HudNarrator_ResetOpenings();

        /* The first reading is the way things are, however long it is
           held: arriving is not an opening. */
        for (k = 0; k < 20; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(street, 1, t, &opened, &closed) == 0);
        }

        /* A doorway on the east, 300ms wide at a walk: nothing. An
           earlier draft with no settle time would pass everything else
           here and fail this. */
        for (k = 0; k < 3; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(corner, 1, t, &opened, &closed) == 0);
        }
        for (k = 0; k < 10; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(street, 1, t, &opened, &closed) == 0);
        }

        /* The side street: said once it has held, and only once. */
        {
            int spoken = 0, openedSeen = 0, closedSeen = 0;

            for (k = 0; k < 20; k++, t += 100)
            {
                if (ETA_HudNarrator_UpdateOpenings(corner, 1, t, &opened, &closed))
                {
                    spoken++;
                    openedSeen = opened;
                    closedSeen = closed;
                }
            }
            CHECK(spoken == 1);
            CHECK(openedSeen == (1 << 1));
            CHECK(closedSeen == 0);
        }

        /* A reading in the band between wall and open is neither: the
           side stays open, and nothing is said. */
        for (k = 0; k < 20; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(between, 1, t, &opened, &closed) == 0);
        }

        /* Past the corner the wall comes back: said as a wall. */
        {
            int spoken = 0, closedSeen = 0;

            for (k = 0; k < 20; k++, t += 100)
            {
                if (ETA_HudNarrator_UpdateOpenings(street, 1, t, &opened, &closed))
                {
                    spoken++;
                    closedSeen = closed;
                }
            }
            CHECK(spoken == 1);
            CHECK(closedSeen == (1 << 1));
        }

        /* Out of the street into a square: the east opens at once and
           the west a moment later, inside the gap. One announcement
           would be ideal; two, far apart, is what must not happen -
           the west has to wait for the gap and then be said. */
        {
            static const int eastOnly[4] = { -1, -1, -1, 3 };
            int              spokenAt[4], spoken = 0, masks = 0;

            for (k = 0; k < 5; k++, t += 100)
            {
                if (ETA_HudNarrator_UpdateOpenings(eastOnly, 1, t, &opened, &closed))
                {
                    spokenAt[spoken < 4 ? spoken : 3] = t;
                    spoken++;
                    masks |= opened;
                }
            }
            for (k = 0; k < 30; k++, t += 100)
            {
                if (ETA_HudNarrator_UpdateOpenings(square, 1, t, &opened, &closed))
                {
                    spokenAt[spoken < 4 ? spoken : 3] = t;
                    spoken++;
                    masks |= opened;
                }
            }
            CHECK(spoken == 2);
            CHECK(masks == ((1 << 1) | (1 << 3)));
            CHECK(spoken < 2 || spokenAt[1] - spokenAt[0] >= ETA_OPENING_GAP_MS);
        }

        /* Standing still, a change is taken in and not spoken - and not
           saved up to be spoken on the first step either. */
        for (k = 0; k < 20; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(street, 0, t, &opened, &closed) == 0);
        }
        for (k = 0; k < 20; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(street, 1, t, &opened, &closed) == 0);
        }

        /* A reset makes the next reading the baseline again: a respawn
           or a new map is not a wall appearing. */
        ETA_HudNarrator_ResetOpenings();
        for (k = 0; k < 20; k++, t += 100)
        {
            CHECK(ETA_HudNarrator_UpdateOpenings(square, 1, t, &opened, &closed) == 0);
        }

        CHECK(ETA_HudNarrator_UpdateOpenings(NULL, 1, t, &opened, &closed) == 0);

        /* The words. */
        ETA_HudNarrator_OpeningsText(1 << 1, 0, text, sizeof(text));
        CHECK(strcmp(text, "Opening to the east") == 0);
        ETA_HudNarrator_OpeningsText((1 << 0) | (1 << 1), 1 << 3, text, sizeof(text));
        CHECK(strcmp(text, "Opening to the north and east, wall to the west") == 0);
        ETA_HudNarrator_OpeningsText(0, (1 << 0) | (1 << 1) | (1 << 2), text, sizeof(text));
        CHECK(strcmp(text, "Wall to the north, east and south") == 0);
        ETA_HudNarrator_OpeningsText(0, 0, text, sizeof(text));
        CHECK(text[0] == '\0');
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakOpenings(1 << 2, 0));
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakOpenings(0, 0));
    }

    /* Who and what is near. */
    {
        ETA_AwareThing list[8];
        char           said[160];
        int            t = 100000;

        /* Left is positive, as the engine's yaw runs: a mirrored sign
           here sends a player the wrong way round an enemy. */
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(0.0f), "ahead") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(90.0f), "left") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(-90.0f), "right") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(45.0f), "ahead left") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(-135.0f), "behind right") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(180.0f), "behind") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(-180.0f), "behind") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(450.0f), "left") == 0);
        CHECK(strcmp(ETA_HudNarrator_RelativeDirection(-20.0f), "ahead") == 0);

        /* An enemy steps out: said at once, over other speech. */
        ETA_HudNarrator_ResetAwareness();
        list[0] = Aware(5, ETA_AWARE_ENEMY, 18.0f, 50.0f, "");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t, 0, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy, ahead left, 18 meters") == 0);

        /* Standing where it is: nothing more. */
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 100, 5000, 1, said, sizeof(said)) == 0);

        /* Running in: the nearer band, once the gap for that enemy has
           passed, and then only the band it is in by then. */
        list[0].meters = 12.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 500, 5000, 1, said, sizeof(said)) == 0);
        list[0].meters = 7.0f;
        list[0].leftOfView = 80.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 2100, 0, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy closer, left, 7 meters") == 0);

        /* Pacing on the edge of a band says nothing... */
        list[0].meters = 8.5f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 4500, 5000, 1, said, sizeof(said)) == 0);
        /* ...and backing off past it is said. */
        list[0].meters = 17.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 4600, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy moving away, left, 17 meters") == 0);

        /* Gone behind a wall: said once it has stayed gone. */
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 0, t + 5000, 5000, 1, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 0, t + 6200, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy out of sight, last seen left") == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 0, t + 9000, 5000, 1, said, sizeof(said)) == 0);

        /* Back in sight: news again. */
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 9500, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy, left, 17 meters") == 0);

        /* Shot down: not "out of sight" - an enemy down. */
        list[0].kind   = ETA_AWARE_ENEMY_DOWN;
        list[0].meters = 12.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 11000, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy down, left, 12 meters") == 0);

        /* While a build is being counted out, even an enemy waits for the
           voice: a tester heard no build progress at all once enemies
           began to be called over it. Said as soon as it is free. */
        ETA_HudNarrator_ResetAwareness();
        t = 150000;
        list[0] = Aware(8, ETA_AWARE_ENEMY, 20.0f, 0.0f, "");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t, 0, 0, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 100, 100, 0, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 600, 400, 0, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy, ahead, 20 meters") == 0);

        /* A spawn full of teammates is one line, not one each - and then
           quiet, including as they walk off. */
        ETA_HudNarrator_ResetAwareness();
        t = 200000;
        list[0] = Aware(1, ETA_AWARE_TEAMMATE, 9.0f, 0.0f, "Ann");
        list[1] = Aware(2, ETA_AWARE_TEAMMATE, 4.0f, -90.0f, "Bob");
        list[2] = Aware(3, ETA_AWARE_TEAMMATE, 12.0f, 170.0f, "Cy");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "3 teammates, nearest Bob, right, 4 meters") == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t + 3000, 5000, 1, said, sizeof(said)) == 0);
        list[1].meters = 10.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t + 9000, 5000, 1, said, sizeof(said)) == 0);
        /* Coming close again, once its gap has passed. */
        list[1].meters = 3.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t + 9500, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Teammate Bob close, right, 3 meters") == 0);

        /* Something on the ground waits for the voice to be free. */
        ETA_HudNarrator_ResetAwareness();
        t = 300000;
        list[0] = Aware(40, ETA_AWARE_ITEM, 2.6f, -30.0f, "MP40");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t, 0, 1, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 100, 1000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "MP40 on the ground, ahead right, 3 meters") == 0);
        /* Walked away and back: said again. Not before it is well away. */
        list[0].meters = 8.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 3000, 5000, 1, said, sizeof(said)) == 0);
        list[0].meters = 3.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 4000, 5000, 1, said, sizeof(said)) == 0);
        list[0].meters = 12.0f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 5000, 5000, 1, said, sizeof(said)) == 0);
        list[0].meters = 0.4f;
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t + 6000, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "MP40 on the ground, ahead right, 1 meter") == 0);

        /* An enemy before anything else waiting, and a wounded teammate
           before a weapon on the floor. */
        ETA_HudNarrator_ResetAwareness();
        t = 400000;
        list[0] = Aware(40, ETA_AWARE_ITEM, 2.0f, 0.0f, "Ammo Pack");
        list[1] = Aware(7, ETA_AWARE_WOUNDED, 12.0f, 180.0f, "Dee");
        list[2] = Aware(9, ETA_AWARE_ENEMY, 30.0f, -100.0f, "");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy, right, 30 meters") == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t + 2000, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Wounded teammate Dee, behind, 12 meters") == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 3, t + 4000, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Ammo Pack on the ground, ahead, 2 meters") == 0);

        /* An enemy body, for a covert op. */
        ETA_HudNarrator_ResetAwareness();
        list[0] = Aware(60, ETA_AWARE_BODY, 4.0f, 90.0f, "");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t, 5000, 1, said, sizeof(said)) == 1);
        CHECK(strcmp(said, "Enemy body with a uniform, left, 4 meters") == 0);

        /* Out of range is not news. */
        ETA_HudNarrator_ResetAwareness();
        list[0] = Aware(9, ETA_AWARE_ENEMY, 60.0f, 0.0f, "");
        list[1] = Aware(1, ETA_AWARE_TEAMMATE, 25.0f, 0.0f, "Ann");
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 2, t, 5000, 1, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_AwareRange(ETA_AWARE_ENEMY) == 40.0f);

        /* Nonsense in, nothing out. */
        CHECK(ETA_HudNarrator_UpdateAwareness(NULL, 3, t, 5000, 1, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, -1, t, 5000, 1, said, sizeof(said)) == 0);
        CHECK(ETA_HudNarrator_UpdateAwareness(list, 1, t, 5000, 1, NULL, 0) == 0);
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakAwareness("Enemy, ahead, 10 meters"));
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakAwareness(""));
        ETA_HudNarrator_ResetAwareness();
    }

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakLocation("Old City Wall"));
    CHECK_REJECTS(ETA_HudNarrator_SpeakLocation(NULL), ETA_ERROR_NULL_POINTER);

    /* "Under cover" is a measurement, "unknown" is the absence of one -
       so the absence must produce no name and no announcement rather
       than a plausible-sounding default. */
    CHECK(ETA_HudNarrator_OverheadName(ETA_OVERHEAD_UNKNOWN) == NULL);
    CHECK(ETA_HudNarrator_OverheadName(ETA_OVERHEAD_OPEN_SKY) != NULL);
    CHECK(ETA_HudNarrator_OverheadName(ETA_OVERHEAD_COVERED) != NULL);
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakOverhead(ETA_OVERHEAD_UNKNOWN));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakOverhead(ETA_OVERHEAD_COVERED));

    /* Drops and waterlevels both index name tables from engine values. */
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakDrop(ETA_DROP_DEADLY, 20));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakDrop(ETA_DROP_LEDGE, 1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakDrop(ETA_DROP_WATER, -1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakDrop(ETA_DROP_NONE, 5));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakDrop((ETA_Drop)99, 5));
    CHECK_REJECTS(ETA_HudNarrator_SpeakWater((ETA_Water)-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakWater((ETA_Water)4), ETA_ERROR_INVALID_VALUE);
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakWater(ETA_WATER_SWIMMING));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakWater(ETA_WATER_DRY));

    /* Out-of-range facings index a name table, same hazard as the stance,
       and the name accessor is reachable from the integrations directly. */
    CHECK_REJECTS(ETA_HudNarrator_SpeakFacing((ETA_Facing)-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakFacing((ETA_Facing)8), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_FacingName((ETA_Facing)8), ETA_ERROR_INVALID_VALUE);
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakFacing(ETA_FACING_SOUTHWEST));

    /* Lean is three states and comes from the sign of a float the engine
       maintains, so the same bounds hazard applies. */
    CHECK_REJECTS(ETA_HudNarrator_SpeakLean((ETA_Lean)-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_HudNarrator_SpeakLean((ETA_Lean)3), ETA_ERROR_INVALID_VALUE);
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakLean(ETA_LEAN_LEFT));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakLean(ETA_LEAN_UPRIGHT));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakLean(ETA_LEAN_RIGHT));

    /* The footing material is an engine string like the look-ahead's, and
       it is freed by the caller the same way. */
    {
        char *material = HeapCopy("Gravel");

        CHECK_ACCEPTS(ETA_HudNarrator_SpeakFooting(material));
        PoisonAndFree(material);
    }
    CHECK_REJECTS(ETA_HudNarrator_SpeakFooting(NULL), ETA_ERROR_NULL_POINTER);
    CHECK_REJECTS(ETA_HudNarrator_SpeakFooting(""), ETA_ERROR_INVALID_STRING);

    /* Stairs and interaction hints both name out of a switch, and both
       are reached with a value the engine chose rather than one this
       library did: an unmapped hint must come back with no name at all
       and say nothing, because the alternative - falling through to
       whatever the last case happened to be - would announce "revive"
       over a crate. */
    CHECK(ETA_HudNarrator_StairsName(ETA_STAIRS_NONE) == NULL);
    CHECK(ETA_HudNarrator_StairsName(ETA_STAIRS_STEP_UP) != NULL);
    CHECK(ETA_HudNarrator_StairsName(ETA_STAIRS_UP) != NULL);
    CHECK(ETA_HudNarrator_StairsName((ETA_Stairs)99) == NULL);
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakStairs(ETA_STAIRS_NONE));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakStairs(ETA_STAIRS_DOWN));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakStairs((ETA_Stairs)99));

    CHECK(ETA_HudNarrator_InteractionName(ETA_INTERACT_NONE) == NULL);
    CHECK(ETA_HudNarrator_InteractionName(ETA_INTERACT_COUNT) == NULL);
    CHECK(ETA_HudNarrator_InteractionName((ETA_Interaction)-1) == NULL);
    CHECK(ETA_HudNarrator_InteractionName((ETA_Interaction)999) == NULL);

    /* Every state between NONE and COUNT has to have words. A gap here
       is a hint the engine can raise and the mod answers with silence,
       which is indistinguishable from there being nothing to use. */
    {
        int state;

        for (state = ETA_INTERACT_NONE + 1; state < ETA_INTERACT_COUNT; state++)
        {
            CHECK(ETA_HudNarrator_InteractionName((ETA_Interaction)state) != NULL);
        }
    }

    /* The tester asked for these two by name, and asked for them
       because the icons are how an engineer knows an objective is
       workable. The words have to carry the tool and the verb. */
    CHECK(strstr(ETA_HudNarrator_InteractionName(ETA_INTERACT_BUILD), "liers") != NULL);
    CHECK(strstr(ETA_HudNarrator_InteractionName(ETA_INTERACT_DISARM), "liers") != NULL);
    CHECK(strcmp(ETA_HudNarrator_InteractionName(ETA_INTERACT_BUILD),
                 ETA_HudNarrator_InteractionName(ETA_INTERACT_DISARM)) != 0);
    CHECK(strstr(ETA_HudNarrator_InteractionName(ETA_INTERACT_PLANT_DYNAMITE),
                 "ynamite") != NULL);
    /* The team's own dynamite is armed with the same pliers that defuse
       an enemy's; saying "defuse" over it tells the player to undo
       what they came to do. */
    CHECK(strstr(ETA_HudNarrator_InteractionName(ETA_INTERACT_ARM_DYNAMITE), "liers") != NULL);
    CHECK(strstr(ETA_HudNarrator_InteractionName(ETA_INTERACT_ARM_DYNAMITE), "arm") != NULL);
    CHECK(strcmp(ETA_HudNarrator_InteractionName(ETA_INTERACT_ARM_DYNAMITE),
                 ETA_HudNarrator_InteractionName(ETA_INTERACT_DISARM)) != 0);

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakInteraction(ETA_INTERACT_NONE, -1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakInteraction(ETA_INTERACT_BUILD, -1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakInteraction(ETA_INTERACT_BUILD, 0));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakInteraction(ETA_INTERACT_BUILD, 100));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakInteraction((ETA_Interaction)999, 50));

    /* The plainest icon with what it is in front: the tester, in a tank,
       heard only "Usable". */
    {
        char text[128];

        ETA_HudNarrator_NamedInteractionText("tank", ETA_INTERACT_USABLE, -1, text, sizeof(text));
        CHECK(strcmp(text, "Tank, usable") == 0);
        ETA_HudNarrator_NamedInteractionText("Mounted machine gun", ETA_INTERACT_USABLE, 40, text, sizeof(text));
        CHECK(strcmp(text, "Mounted machine gun, usable, 40 percent") == 0);
        ETA_HudNarrator_NamedInteractionText(NULL, ETA_INTERACT_USABLE, -1, text, sizeof(text));
        CHECK(strcmp(text, "Usable") == 0);
        ETA_HudNarrator_NamedInteractionText("", ETA_INTERACT_BUILD, 10, text, sizeof(text));
        CHECK(strncmp(text, ETA_HudNarrator_InteractionName(ETA_INTERACT_BUILD),
                      strlen(ETA_HudNarrator_InteractionName(ETA_INTERACT_BUILD))) == 0
              && strstr(text, ", 10 percent") != NULL);
        ETA_HudNarrator_NamedInteractionText("tank", ETA_INTERACT_NONE, -1, text, sizeof(text));
        CHECK(text[0] == '\0');
        ETA_HudNarrator_NamedInteractionText("tank", ETA_INTERACT_USABLE, -1, text, 5);
        CHECK(strlen(text) == 4);
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakNamedInteraction("tank", ETA_INTERACT_USABLE, -1));
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakNamedInteraction(NULL, ETA_INTERACT_NONE, -1));
    }

    /* The hold that stops the scenery talking over an answer the player
       asked for. A tester lost the objective distance to a wall report
       twice, once while deliberately pressing the key for it. */
    {
        int t = 100000;

        ETA_HudNarrator_ReleasePassive();
        CHECK(ETA_HudNarrator_PassiveHeld(t) == 0);

        ETA_HudNarrator_HoldPassive(t);
        CHECK(ETA_HudNarrator_PassiveHeld(t) == 1);
        CHECK(ETA_HudNarrator_PassiveHeld(t + ETA_HUD_HOLD_MS - 1) == 1);

        /* It has to end on its own. A hold that never expired would
           silence the scenery for the rest of the map. */
        CHECK(ETA_HudNarrator_PassiveHeld(t + ETA_HUD_HOLD_MS + 1) == 0);

        /* ... and having expired, it stays expired. */
        CHECK(ETA_HudNarrator_PassiveHeld(t + 1) == 0);

        /* Asking again while held pushes the end out rather than
           stacking: two questions in a row is still one answer to
           protect. */
        ETA_HudNarrator_HoldPassive(t);
        ETA_HudNarrator_HoldPassive(t + 1000);
        CHECK(ETA_HudNarrator_PassiveHeld(t + ETA_HUD_HOLD_MS + 500) == 1);
        CHECK(ETA_HudNarrator_PassiveHeld(t + 1000 + ETA_HUD_HOLD_MS + 1) == 0);

        /* The engine's clock restarts on a map change. A hold set just
           before one must not survive it - the clock would take most of
           an hour to catch up, with the scenery silent the whole time. */
        ETA_HudNarrator_HoldPassive(500000);
        CHECK(ETA_HudNarrator_PassiveHeld(50) == 0);

        ETA_HudNarrator_ReleasePassive();
        CHECK(ETA_HudNarrator_PassiveHeld(t) == 0);
    }

    /* Looking up and down. The band only decides when to ask the
       question; the caller traces what is actually up there. */
    {
        ETA_HudNarrator_ResetLookPitch();

        /* The first reading is swallowed - it is where the player
           already is, not somewhere they chose to look. */
        CHECK(ETA_HudNarrator_UpdateLookPitch(0.0f, 1000) == 0);

        /* Inside the band, and inside the hysteresis past its edge,
           nothing is owed however long it is held. */
        CHECK(ETA_HudNarrator_UpdateLookPitch(5.0f, 2000) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(11.0f, 3000) == 0);

        /* Clear of the edge, but a sweep is a sweep until it stops. */
        CHECK(ETA_HudNarrator_UpdateLookPitch(-30.0f, 4000) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-30.0f, 4100) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-30.0f, 4500) == 1);

        /* Having reported, the same angle owes nothing more. */
        CHECK(ETA_HudNarrator_UpdateLookPitch(-30.0f, 5000) == 0);

        /* A view that keeps moving never settles, so it never queues a
           report it is about to make stale. */
        CHECK(ETA_HudNarrator_UpdateLookPitch(-45.0f, 6000) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-60.0f, 6400) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-75.0f, 6800) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-75.0f, 7200) == 1);

        /* Down is the mirror of up, and the band either side of level
           must not be twice as wide as the rest - which a truncating
           cast would have made it. */
        ETA_HudNarrator_ResetLookPitch();
        CHECK(ETA_HudNarrator_UpdateLookPitch(0.0f, 1000) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(30.0f, 2000) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(30.0f, 2400) == 1);

        /* A clock rewound by a map change costs one late report, not
           silence until the next reset. */
        ETA_HudNarrator_ResetLookPitch();
        CHECK(ETA_HudNarrator_UpdateLookPitch(0.0f, 900000) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-40.0f, 5) == 0);
        CHECK(ETA_HudNarrator_UpdateLookPitch(-40.0f, 500) == 1);

        ETA_HudNarrator_ResetLookPitch();
    }

    /* Building under the pliers. The tester asked for this after
       finishing a construction and realising they had only known to
       keep holding because they remembered the bar on screen. */
    {
        int spoke;

        ETA_HudNarrator_ResetBuildProgress();

        /* Nothing below the first milestone. */
        CHECK(ETA_HudNarrator_UpdateBuildProgress(0) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(24) == 0);

        /* Each milestone once, and only once. */
        CHECK(ETA_HudNarrator_UpdateBuildProgress(25) == 1);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(26) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(49) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(50) == 1);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(74) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(75) == 1);

        /* 90 exists because a tester reported the narration stopping at
           75 with a quarter of the work left and nothing following it.
           The engine's own progress tops out just under 98, so 90 is the
           last figure a climbing construction can actually reach. */
        CHECK(ETA_HudNarrator_UpdateBuildProgress(89) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(90) == 1);

        /* Past that it goes quiet rather than counting to 100. 100 never
           arrives: the engine resets the progress in the same frame it
           crosses its finish line, so the figure is never the thing that
           says a construction is done. The completion callout is a
           separate event and is not reachable from here. */
        CHECK(ETA_HudNarrator_UpdateBuildProgress(99) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(100) == 0);

        /* A construction decays when abandoned. Coming back to it is a
           fresh climb and has to be announced again, or the player is
           met with silence where they most need to know it is working. */
        CHECK(ETA_HudNarrator_UpdateBuildProgress(10) == 0);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(25) == 1);

        /* Arriving part-way says where it stands, once, rather than
           reading out every milestone below it. */
        ETA_HudNarrator_ResetBuildProgress();
        spoke = ETA_HudNarrator_UpdateBuildProgress(80);
        CHECK(spoke == 1);
        CHECK(ETA_HudNarrator_UpdateBuildProgress(80) == 0);

        /* Completion says so plainly, and speaks no percentage - the
           figure it would have to quote is the one the engine has
           already thrown away. */
        ETA_HudNarrator_SpeakBuildComplete();
        CHECK(ETA_ErrorHandler_GetLastError().code == ETA_ERROR_NONE);

        /* Out of range is refused rather than spoken. */
        CHECK_REJECTS(ETA_HudNarrator_UpdateBuildProgress(-1),
                      ETA_ERROR_INVALID_VALUE);
        CHECK_REJECTS(ETA_HudNarrator_UpdateBuildProgress(101),
                      ETA_ERROR_INVALID_VALUE);

        ETA_HudNarrator_ResetBuildProgress();
    }

    /* A ladder: which way, where, how far, and the key. */
    {
        char ladder[96];

        ETA_HudNarrator_LadderText(0, "ahead left", 2, ladder, sizeof(ladder));
        CHECK(strcmp(ladder, "Ladder down, ahead left, 2 meters. F climbs") == 0);
        ETA_HudNarrator_LadderText(1, "right", 1, ladder, sizeof(ladder));
        CHECK(strcmp(ladder, "Ladder up, right, 1 meter. F climbs") == 0);
        /* Closer than a metre is still "1 meter", never "0 meters". */
        ETA_HudNarrator_LadderText(1, "ahead", 0, ladder, sizeof(ladder));
        CHECK(strcmp(ladder, "Ladder up, ahead, 1 meter. F climbs") == 0);
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakLadder(1, "behind", 3));
    }

    /* Above or below, past a stair's height. */
    {
        char height[64];

        ETA_HudNarrator_HeightText(4.2f, height, sizeof(height));
        CHECK(strcmp(height, "4 meters above you") == 0);
        ETA_HudNarrator_HeightText(-6.6f, height, sizeof(height));
        CHECK(strcmp(height, "7 meters below you") == 0);
        ETA_HudNarrator_HeightText(2.0f, height, sizeof(height));
        CHECK(strcmp(height, "2 meters above you") == 0);
        /* the same floor, or a step or two off it, is not worth a word */
        ETA_HudNarrator_HeightText(1.9f, height, sizeof(height));
        CHECK(height[0] == '\0');
        ETA_HudNarrator_HeightText(-1.9f, height, sizeof(height));
        CHECK(height[0] == '\0');
        ETA_HudNarrator_HeightText(0.0f, height, sizeof(height));
        CHECK(height[0] == '\0');
        ETA_HudNarrator_HeightText(4.0f, NULL, 0);
    }

    /* In the match or watching it. */
    {
        char state[128];

        ETA_HudNarrator_PlayStateText(ETA_PLAY_SPECTATING, NULL, NULL, NULL, state, sizeof(state));
        CHECK(strcmp(state, "Spectating") == 0);
        ETA_HudNarrator_PlayStateText(ETA_PLAY_SPECTATING, NULL, NULL, "Alex", state, sizeof(state));
        CHECK(strcmp(state, "Spectating, following Alex") == 0);
        ETA_HudNarrator_PlayStateText(ETA_PLAY_IN_PLAY, "Allies", "Medic", NULL, state, sizeof(state));
        CHECK(strcmp(state, "In play, Allies, Medic") == 0);
        /* Following someone means nothing while playing; it is not said. */
        ETA_HudNarrator_PlayStateText(ETA_PLAY_IN_PLAY, "Axis", "", "Alex", state, sizeof(state));
        CHECK(strcmp(state, "In play, Axis") == 0);
        ETA_HudNarrator_PlayStateText(ETA_PLAY_DOWN, "Axis", "Engineer", NULL, state, sizeof(state));
        CHECK(strcmp(state, "Down, a medic can revive you") == 0);
        ETA_HudNarrator_PlayStateText(ETA_PLAY_LIMBO, "Axis", "Engineer", "Sam", state, sizeof(state));
        CHECK(strcmp(state, "Waiting to respawn, following Sam") == 0);
        ETA_HudNarrator_PlayStateText(ETA_PLAY_MATCH_OVER, NULL, NULL, NULL, state, sizeof(state));
        CHECK(strcmp(state, "Match over") == 0);
        ETA_HudNarrator_PlayStateText(ETA_PLAY_UNKNOWN, NULL, NULL, NULL, state, sizeof(state));
        CHECK(state[0] == '\0');
        CHECK_ACCEPTS(ETA_HudNarrator_SpeakPlayState(ETA_PLAY_SPECTATING, NULL, NULL, NULL));
    }

    /* Numeric HUD values are unguarded by design - they are formatted, not
       validated - so the contract is simply that odd values pass through
       without being reported as errors. */
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakHealth(0));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakHealth(-25));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakAmmo(0));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakRespawn(0));

    ETA_HudNarrator_Shutdown();
    ETA_AccessibilityRuntime_Shutdown();

    return SMOKE_REPORT("hud_narrator");
}

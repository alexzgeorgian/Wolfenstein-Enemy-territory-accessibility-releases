#include "hud_narrator.h"
#include "../core/event_router.h"
#include "../core/runtime_guard.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

static void ETA_HudNarrator_EmitMessage(const char *source, const char *message)
{
    ETA_Event event;

    event.type = ETA_EVENT_HUD_STATUS;
    event.source = source;
    event.message = message;

    ETA_EventRouter_Emit(event);
}

void ETA_HudNarrator_Init(void)
{
    ETA_HudNarrator_ResetOpenings();
    ETA_HudNarrator_ResetAwareness();
}

void ETA_HudNarrator_SpeakHealth(int health)
{
    static char buffer[64];

    snprintf(buffer, sizeof(buffer), "Health %d", health);

    ETA_HudNarrator_EmitMessage("health", buffer);
}

void ETA_HudNarrator_SpeakAmmo(int ammo)
{
    static char buffer[64];

    snprintf(buffer, sizeof(buffer), "Ammo %d", ammo);

    ETA_HudNarrator_EmitMessage("ammo", buffer);
}

void ETA_HudNarrator_SpeakAmmoDetail(int loaded, int reserve)
{
    static char buffer[64];

    if (reserve >= 0)
    {
        snprintf(buffer, sizeof(buffer), "%d loaded, %d in reserve", loaded, reserve);
    }
    else
    {
        snprintf(buffer, sizeof(buffer), "Ammo %d", loaded);
    }

    ETA_HudNarrator_EmitMessage("ammo", buffer);
}

void ETA_HudNarrator_SpeakWeapon(const char *weaponName)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(weaponName, ETA_MAX_HUD_TEXT_LENGTH, "hud_narrator.SpeakWeapon")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("weapon", weaponName);
}

void ETA_HudNarrator_SpeakStance(ETA_Stance stance)
{
    static const char *const names[] = { "Prone", "Crouched", "Standing" };

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange((int)stance,
                                                              ETA_STANCE_PRONE,
                                                              ETA_STANCE_STANDING,
                                                              "hud_narrator.SpeakStance")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("stance", names[stance]);
}

void ETA_HudNarrator_SpeakGain(int amount, int isRounds)
{
    static char buffer[64];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(amount, 1, 100000, "hud_narrator.SpeakGain")))
    {
        return;
    }

    if (isRounds)
    {
        snprintf(buffer, sizeof(buffer), "%d round%s", amount, amount == 1 ? "" : "s");
    }
    else
    {
        snprintf(buffer, sizeof(buffer), "%d health", amount);
    }

    ETA_HudNarrator_EmitMessage("gain", buffer);
}

void ETA_HudNarrator_SpeakAlreadyFull(void)
{
    ETA_HudNarrator_EmitMessage("gain", "already full");
}

void ETA_HudNarrator_SpeakZoom(ETA_Zoom zoom)
{
    static const char *const names[] = { "Zoom off", "Binoculars", "Scope" };

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange((int)zoom,
                                                              ETA_ZOOM_OFF,
                                                              ETA_ZOOM_SCOPE,
                                                              "hud_narrator.SpeakZoom")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("zoom", names[zoom]);
}

void ETA_HudNarrator_SpeakLookAhead(const char *what, int distanceMeters)
{
    static char buffer[ETA_MAX_HUD_TEXT_LENGTH + 32];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(what, ETA_MAX_HUD_TEXT_LENGTH, "hud_narrator.SpeakLookAhead")))
    {
        return;
    }

    if (distanceMeters >= 0)
    {
        snprintf(buffer, sizeof(buffer), "%s, %d meters", what, distanceMeters);
    }
    else
    {
        snprintf(buffer, sizeof(buffer), "%s", what);
    }

    ETA_HudNarrator_EmitMessage("lookahead", buffer);
}

/*
 * How far past the halfway line the view has to travel before a new
 * compass point is adopted, in degrees.
 *
 * Without it the announcement changes on the boundary itself, which is
 * exactly where a player lining up on a doorway tends to sit.
 */
#define ETA_FACING_HYSTERESIS_DEGREES 5.0f

/*
 * How long a new compass point has to be held before it is spoken, in
 * milliseconds.
 *
 * This is the whole of the fix for a narrator that could not keep up
 * with a sweep of the mouse. Long enough that a swing across several
 * sectors announces only where it ended; short enough that stopping on a
 * heading and being told it feels immediate.
 *
 * It also has to be short enough that a turn made with a *key* is
 * announced while it is happening, and that is not a free choice - the
 * engine sets the speed. Holding a turn key moves the view at
 * cl_yawspeed, which ET defaults to 140 degrees a second, so the view
 * spends 45/140 = 321 ms in each sector. At the 350 ms this used to be,
 * the sector under the view changed 29 ms before the settle completed,
 * every time, for ever: holding the key announced nothing at all, and
 * the heading only arrived a third of a second after the player let go.
 *
 * A near miss, and invisible from inside the code - the comment above
 * already claimed a deliberate turn was "announced sector by sector",
 * and the test that checked it used a synthetic turn slower than any
 * key can produce. It took a player holding the key and waiting.
 *
 * So the value now sits between the two speeds it has to tell apart:
 * above a mouse sweep's time in a sector (a hand crossing half the
 * compass gives each sector well under 150 ms) and below a key turn's
 * 321 ms. tests/compass_test.py reads cl_yawspeed out of the engine and
 * fails if that gap ever closes.
 */
#define ETA_FACING_SETTLE_MS 200

/* Half a sector. Eight points, so each one owns 45 degrees. */
#define ETA_FACING_SECTOR_DEGREES 45.0f

/*
 * Wraps an angle into [0, 360).
 *
 * Done with integer arithmetic rather than fmodf so this library keeps
 * needing nothing but libc: it is linked into two engines' mod libraries,
 * and the 2010 tree's build scripts do not link libm.
 */
static float ETA_HudNarrator_NormalizeDegrees(float degrees)
{
    long  whole;
    float fraction;
    float wrapped;

    /* Far outside anything an engine produces, and past where the cast
       below is defined. Nothing sensible to return, so return north. */
    if (!(degrees > -1.0e9f && degrees < 1.0e9f))
    {
        return 0.0f;
    }

    whole    = (long)degrees;
    fraction = degrees - (float)whole;
    whole   %= 360;

    if (whole < 0)
    {
        whole += 360;
    }

    wrapped = (float)whole + fraction;

    /* The fraction keeps the sign of the input, so a small negative angle
       lands just below zero here and a wrap of exactly 360 just above it. */
    if (wrapped < 0.0f)
    {
        wrapped += 360.0f;
    }
    else if (wrapped >= 360.0f)
    {
        wrapped -= 360.0f;
    }

    return wrapped;
}

/*
 * The compass bearing of a view yaw: degrees clockwise from north.
 *
 * ET puts north at yaw 90 and east at yaw 0, and yaw runs anticlockwise
 * while a compass runs clockwise, which is the whole of the conversion.
 */
float ETA_HudNarrator_BearingFromYaw(float yawDegrees)
{
    return ETA_HudNarrator_NormalizeDegrees(90.0f - yawDegrees);
}

ETA_Facing ETA_HudNarrator_FacingFromBearing(float bearingDegrees)
{
    float bearing = ETA_HudNarrator_NormalizeDegrees(bearingDegrees);

    /* Rounding to the nearest sector centre rather than truncating is
       what makes each point own the 45 degrees centred on it, so due
       north is the middle of "north" and not its edge. */
    return (ETA_Facing)(((int)(bearing / ETA_FACING_SECTOR_DEGREES + 0.5f)) % 8);
}

ETA_Facing ETA_HudNarrator_FacingFromYaw(float yawDegrees)
{
    /* One step: a yaw becomes a bearing, a bearing becomes a word. Both
       halves are used on their own elsewhere - the map survey speaks the
       bearing as a number - and keeping them as one chain is what stops
       the number and the word ever describing different directions. */
    return ETA_HudNarrator_FacingFromBearing(ETA_HudNarrator_BearingFromYaw(yawDegrees));
}

const char *ETA_HudNarrator_FacingName(ETA_Facing facing)
{
    static const char *const names[] =
    {
        "north", "north-east", "east", "south-east",
        "south", "south-west", "west", "north-west"
    };

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange((int)facing,
                                                              ETA_FACING_NORTH,
                                                              ETA_FACING_NORTHWEST,
                                                              "hud_narrator.FacingName")))
    {
        return "unknown";
    }

    return names[facing];
}

void ETA_HudNarrator_SpeakFacing(ETA_Facing facing)
{
    static char buffer[64];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange((int)facing,
                                                              ETA_FACING_NORTH,
                                                              ETA_FACING_NORTHWEST,
                                                              "hud_narrator.SpeakFacing")))
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "Facing %s", ETA_HudNarrator_FacingName(facing));

    ETA_HudNarrator_EmitMessage("facing", buffer);
}

static int gFacingHeld = -1;

/* The sector the view has moved into but not yet held long enough to be
   worth speaking, and the time it was first seen there. */
static int gFacingPending      = -1;
static int gFacingPendingSince = 0;

/* A turn key is down: speak each point on arrival rather than after the
   settle wait. See the header. */
static int gFacingKeyTurn = 0;

void ETA_HudNarrator_ResetFacing(void)
{
    gFacingHeld         = -1;
    gFacingPending      = -1;
    gFacingPendingSince = 0;
}

void ETA_HudNarrator_SetFacingKeyTurn(int keyTurning)
{
    gFacingKeyTurn = keyTurning ? 1 : 0;
}

void ETA_HudNarrator_SetFacingHeld(ETA_Facing facing)
{
    if ((int)facing < 0 || (int)facing >= 8)
    {
        return;
    }

    gFacingHeld    = (int)facing;
    gFacingPending = -1;
}

/* Where the view is pointed up or down, in bands.

   Fifteen degrees, which is coarse enough that ordinary aiming does not
   trip it and fine enough that deliberately looking somewhere does. The
   band is only a trigger: what gets spoken is whatever the view
   actually runs into, so the size of the band decides how often the
   question is asked, never what the answer is. */
#define ETA_LOOK_PITCH_BAND_DEGREES 15.0f

/* The margin past a band edge before the change is believed, so a view
   resting on a boundary does not chatter between two bands. */
#define ETA_LOOK_PITCH_HYSTERESIS_DEGREES 4.0f

/* A sweep is a sweep until it stops. The same reasoning as the compass:
   reporting mid-movement describes somewhere the player is already no
   longer looking. */
#define ETA_LOOK_PITCH_SETTLE_MS 350

static int gLookPitchHeld = -1000;
static int gLookPitchPending = -1000;
static int gLookPitchPendingSince;

void ETA_HudNarrator_ResetLookPitch(void)
{
    gLookPitchHeld    = -1000;
    gLookPitchPending = -1000;
}

static int ETA_HudNarrator_PitchBand(float pitchDegrees)
{
    float scaled = pitchDegrees / ETA_LOOK_PITCH_BAND_DEGREES;

    /* Rounded to nearest by hand, symmetrically about zero. Pitch is
       signed - negative is up in this engine - and a plain cast
       truncates towards zero, which would make the band either side of
       level twice as wide as the rest. No maths library either, which
       this file has never needed and the mod libraries do not link. */
    return (scaled >= 0.0f) ? (int)(scaled + 0.5f) : -(int)(-scaled + 0.5f);
}

int ETA_HudNarrator_UpdateLookPitch(float pitchDegrees, int nowMs)
{
    int   band = ETA_HudNarrator_PitchBand(pitchDegrees);
    float offCentre;

    if (gLookPitchHeld == -1000)
    {
        /* The first reading is where the player already is, not a
           change. Holding it silently means the first report comes from
           an actual movement rather than from spawning. */
        gLookPitchHeld    = band;
        gLookPitchPending = -1000;
        return 0;
    }

    if (band == gLookPitchHeld)
    {
        gLookPitchPending = -1000;
        return 0;
    }

    offCentre = pitchDegrees - (float)gLookPitchHeld * ETA_LOOK_PITCH_BAND_DEGREES;

    if (offCentre < 0.0f)
    {
        offCentre = -offCentre;
    }

    if (offCentre <= ETA_LOOK_PITCH_BAND_DEGREES * 0.5f + ETA_LOOK_PITCH_HYSTERESIS_DEGREES)
    {
        gLookPitchPending = -1000;
        return 0;
    }

    if (band != gLookPitchPending)
    {
        gLookPitchPending      = band;
        gLookPitchPendingSince = nowMs;
        return 0;
    }

    /* Subtraction rather than a comparison, so a clock rewound by a map
       change costs one late report instead of silencing this until the
       next reset. */
    if (nowMs - gLookPitchPendingSince < ETA_LOOK_PITCH_SETTLE_MS)
    {
        return 0;
    }

    gLookPitchHeld    = band;
    gLookPitchPending = -1000;

    return 1;
}

int ETA_HudNarrator_UpdateFacing(float yawDegrees, int nowMs, ETA_Facing *facing)
{
    ETA_Facing raw = ETA_HudNarrator_FacingFromYaw(yawDegrees);
    float      compass;
    float      offCentre;

    if (!facing)
    {
        return 0;
    }

    if (gFacingHeld < 0)
    {
        gFacingHeld    = (int)raw;
        gFacingPending = -1;
        *facing        = raw;
        return 1;
    }

    if ((int)raw == gFacingHeld)
    {
        /* Turned away and came back before it was ever spoken. Nothing
           changed, so there is nothing owing. */
        gFacingPending = -1;
        return 0;
    }

    /* How far the view has drifted from the middle of the point being
       held. Half a sector is the boundary; the hysteresis is the margin
       past it that has to be cleared before the change is believed. */
    compass   = ETA_HudNarrator_BearingFromYaw(yawDegrees);
    offCentre = ETA_HudNarrator_NormalizeDegrees(compass - gFacingHeld * ETA_FACING_SECTOR_DEGREES);

    if (offCentre > 180.0f)
    {
        offCentre = 360.0f - offCentre;
    }

    if (offCentre <= ETA_FACING_SECTOR_DEGREES * 0.5f + ETA_FACING_HYSTERESIS_DEGREES)
    {
        gFacingPending = -1;
        return 0;
    }

    /* Past the boundary, but a sweep is still a sweep until it stops.
       Every time the sector under the view changes the clock starts
       again, so a hand that keeps moving never reaches the settle time
       and never queues a report it is about to make stale. */
    if ((int)raw != gFacingPending)
    {
        gFacingPending      = (int)raw;
        gFacingPendingSince = nowMs;
        return 0;
    }

    /* Subtraction rather than a comparison, so a clock that wraps or is
       rewound by a map change costs at most one late announcement
       instead of silencing the feature until the next reset. */
    if (!gFacingKeyTurn && nowMs - gFacingPendingSince < ETA_FACING_SETTLE_MS)
    {
        return 0;
    }

    gFacingHeld    = (int)raw;
    gFacingPending = -1;
    *facing        = raw;

    return 1;
}

float ETA_HudNarrator_FallHeightForDelta(float delta, float gravity)
{
    /* No gravity is not a fall. Returning a huge height rather than
       dividing by zero keeps every caller's comparison the right way
       round: nothing is ever far enough down to be a hazard. */
    if (!(gravity > 0.0f) || !(delta > 0.0f))
    {
        return 1.0e9f;
    }

    return delta * 10000.0f / (2.0f * gravity);
}

void ETA_HudNarrator_SpeakDrop(ETA_Drop drop, int distanceMeters)
{
    static char buffer[96];
    const char *what;

    switch (drop)
    {
    case ETA_DROP_LEDGE:
        what = "Ledge ahead";
        break;
    case ETA_DROP_INJURING:
        what = "Drop ahead";
        break;
    case ETA_DROP_DEADLY:
        what = "Deadly drop ahead";
        break;
    case ETA_DROP_WATER:
        what = "Water below";
        break;
    case ETA_DROP_NONE:
    default:
        return;
    }

    if (distanceMeters < 0)
    {
        /* No bottom found. Saying so beats inventing a number, and a
           drop the probe cannot see the end of is the worst one to be
           vague about. */
        snprintf(buffer, sizeof(buffer), "%s, no bottom in range", what);
    }
    else
    {
        snprintf(buffer, sizeof(buffer), "%s, %d %s down",
                 what, distanceMeters, distanceMeters == 1 ? "metre" : "metres");
    }

    ETA_HudNarrator_EmitMessage("drop", buffer);
}

/*
 * How long a new place has to be held before it is spoken, in
 * milliseconds.
 *
 * Much longer than the compass equivalent, and for a different reason.
 * The compass is damped because a sweep of the mouse crosses several
 * headings in a moment; a location is damped because a stock map has
 * over a hundred named places and a player crossing a courtyard passes
 * through several of them at a walk. Two seconds means "I have arrived
 * somewhere", not "I went past something".
 */
#define ETA_LOCATION_SETTLE_MS 2000

/* Long enough for the longest name in the shipped location files, with
   room to spare. A name that does not fit is truncated rather than
   dropped: half a place name still tells the player where they are. */
#define ETA_LOCATION_MAX 96

static char gLocationHeld[ETA_LOCATION_MAX];
static char gLocationPending[ETA_LOCATION_MAX];
static int  gLocationPendingSince;

void ETA_HudNarrator_ResetLocation(void)
{
    gLocationHeld[0]      = '\0';
    gLocationPending[0]   = '\0';
    gLocationPendingSince = 0;
}

int ETA_HudNarrator_UpdateLocation(const char *location, int nowMs)
{
    char trimmed[ETA_LOCATION_MAX];

    if (!location || !location[0])
    {
        /* No answer from the engine this frame. Deliberately not a
           reset: losing the location for a frame while a snapshot
           arrives must not make the place the player is standing in
           news all over again. */
        return 0;
    }

    /* Truncate first, then compare against the truncated form.
       Comparing the caller's full string against what was stored looks
       equivalent and is not: a name longer than this buffer never
       matches what was kept from it, so its timer restarts on every
       frame and it is never announced at all. Silent, and only for the
       longest place names on a map. The smoke test pins it. */
    snprintf(trimmed, sizeof(trimmed), "%s", location);

    if (strcmp(trimmed, gLocationHeld) == 0)
    {
        gLocationPending[0] = '\0';
        return 0;
    }

    if (strcmp(trimmed, gLocationPending) != 0)
    {
        snprintf(gLocationPending, sizeof(gLocationPending), "%s", trimmed);
        gLocationPendingSince = nowMs;
        return 0;
    }

    if (nowMs - gLocationPendingSince < ETA_LOCATION_SETTLE_MS)
    {
        return 0;
    }

    snprintf(gLocationHeld, sizeof(gLocationHeld), "%s", trimmed);
    gLocationPending[0] = '\0';

    return 1;
}

void ETA_HudNarrator_SpeakLocation(const char *location)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(location,
                                                            ETA_MAX_HUD_TEXT_LENGTH,
                                                            "hud_narrator.SpeakLocation")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("location", location);
}

/* What each side is: not yet known, a wall, or open. */
#define ETA_OPENING_UNKNOWN (-1)
#define ETA_OPENING_WALL    0
#define ETA_OPENING_OPEN    1

static int gOpeningHeld[ETA_OPENING_DIRECTIONS];
static int gOpeningPending[ETA_OPENING_DIRECTIONS];
static int gOpeningPendingSince[ETA_OPENING_DIRECTIONS];
static int gOpeningSpokenAt;
static int gOpeningSpokenSet;

void ETA_HudNarrator_ResetOpenings(void)
{
    int i;

    for (i = 0; i < ETA_OPENING_DIRECTIONS; i++)
    {
        gOpeningHeld[i]         = ETA_OPENING_UNKNOWN;
        gOpeningPending[i]      = ETA_OPENING_UNKNOWN;
        gOpeningPendingSince[i] = 0;
    }

    gOpeningSpokenAt  = 0;
    gOpeningSpokenSet = 0;
}

int ETA_HudNarrator_UpdateOpenings(const int metersByDirection[ETA_OPENING_DIRECTIONS],
                                   int moving, int nowMs, int *opened, int *closed)
{
    int waiting = gOpeningSpokenSet && nowMs - gOpeningSpokenAt < ETA_OPENING_GAP_MS
                  && nowMs >= gOpeningSpokenAt;
    int i;

    *opened = 0;
    *closed = 0;

    if (!metersByDirection)
    {
        return 0;
    }

    for (i = 0; i < ETA_OPENING_DIRECTIONS; i++)
    {
        int meters = metersByDirection[i];
        int now;

        if (meters < 0 || meters >= ETA_OPENING_OPEN_METERS)
        {
            now = ETA_OPENING_OPEN;
        }
        else if (meters <= ETA_OPENING_WALL_METERS)
        {
            now = ETA_OPENING_WALL;
        }
        else
        {
            /* The band between: whatever it was, it still is. A change
               still settling is not cancelled by passing through it. */
            continue;
        }

        if (gOpeningHeld[i] == ETA_OPENING_UNKNOWN)
        {
            /* The way things are, not news. */
            gOpeningHeld[i]    = now;
            gOpeningPending[i] = ETA_OPENING_UNKNOWN;
            continue;
        }

        if (now == gOpeningHeld[i])
        {
            /* Back to what it was before it settled: it never changed. */
            gOpeningPending[i] = ETA_OPENING_UNKNOWN;
            continue;
        }

        if (now != gOpeningPending[i])
        {
            gOpeningPending[i]      = now;
            gOpeningPendingSince[i] = nowMs;
            continue;
        }

        if (nowMs - gOpeningPendingSince[i] < ETA_OPENING_SETTLE_MS)
        {
            continue;
        }

        if (moving && waiting)
        {
            /* Still true once the gap has passed, it is said then. */
            continue;
        }

        gOpeningHeld[i]    = now;
        gOpeningPending[i] = ETA_OPENING_UNKNOWN;

        if (moving)
        {
            if (now == ETA_OPENING_OPEN)
            {
                *opened |= 1 << i;
            }
            else
            {
                *closed |= 1 << i;
            }
        }
    }

    if (*opened || *closed)
    {
        gOpeningSpokenAt  = nowMs;
        gOpeningSpokenSet = 1;
        return 1;
    }

    return 0;
}

/* "east", "north and east", "north, east and south". */
static void ETA_HudNarrator_DirectionList(int mask, char *out, size_t outSize)
{
    static const char *const names[ETA_OPENING_DIRECTIONS] =
    {
        "north", "east", "south", "west"
    };
    int count = 0, total = 0, i;

    out[0] = '\0';

    for (i = 0; i < ETA_OPENING_DIRECTIONS; i++)
    {
        if (mask & (1 << i))
        {
            total++;
        }
    }

    for (i = 0; i < ETA_OPENING_DIRECTIONS; i++)
    {
        size_t used = strlen(out);

        if (!(mask & (1 << i)))
        {
            continue;
        }

        count++;
        snprintf(out + used, outSize - used, "%s%s",
                 count == 1 ? "" : (count == total ? " and " : ", "), names[i]);
    }
}

void ETA_HudNarrator_OpeningsText(int opened, int closed, char *out, size_t outSize)
{
    char openList[48];
    char wallList[48];

    if (!out || outSize == 0)
    {
        return;
    }

    out[0] = '\0';

    ETA_HudNarrator_DirectionList(opened, openList, sizeof(openList));
    ETA_HudNarrator_DirectionList(closed, wallList, sizeof(wallList));

    if (openList[0] && wallList[0])
    {
        snprintf(out, outSize, "Opening to the %s, wall to the %s", openList, wallList);
    }
    else if (openList[0])
    {
        snprintf(out, outSize, "Opening to the %s", openList);
    }
    else if (wallList[0])
    {
        snprintf(out, outSize, "Wall to the %s", wallList);
    }
}

void ETA_HudNarrator_SpeakOpenings(int opened, int closed)
{
    static char buffer[128];

    ETA_HudNarrator_OpeningsText(opened, closed, buffer, sizeof(buffer));

    if (buffer[0])
    {
        ETA_HudNarrator_EmitMessage("openings", buffer);
    }
}

const char *ETA_HudNarrator_OverheadName(ETA_Overhead overhead)
{
    switch (overhead)
    {
    case ETA_OVERHEAD_OPEN_SKY:
        return "open sky above";
    case ETA_OVERHEAD_COVERED:
        return "under cover";
    case ETA_OVERHEAD_UNKNOWN:
    default:
        return NULL;
    }
}

void ETA_HudNarrator_SpeakOverhead(ETA_Overhead overhead)
{
    const char *name = ETA_HudNarrator_OverheadName(overhead);

    if (!name)
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("overhead", name);
}

void ETA_HudNarrator_SpeakWater(ETA_Water water)
{
    static const char *const names[] =
    {
        "Out of the water", "Shallow water", "Deep water", "Swimming"
    };

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange((int)water,
                                                              ETA_WATER_DRY,
                                                              ETA_WATER_SWIMMING,
                                                              "hud_narrator.SpeakWater")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("water", names[water]);
}

void ETA_HudNarrator_SpeakFooting(const char *material)
{
    static char buffer[ETA_MAX_HUD_TEXT_LENGTH + 32];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(material, ETA_MAX_HUD_TEXT_LENGTH, "hud_narrator.SpeakFooting")))
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "%s underfoot", material);

    ETA_HudNarrator_EmitMessage("footing", buffer);
}

void ETA_HudNarrator_SpeakLean(ETA_Lean lean)
{
    static const char *const names[] = { "Leaning left", "Upright", "Leaning right" };

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange((int)lean,
                                                              ETA_LEAN_LEFT,
                                                              ETA_LEAN_RIGHT,
                                                              "hud_narrator.SpeakLean")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("lean", names[lean]);
}

const char *ETA_HudNarrator_StairsName(ETA_Stairs stairs)
{
    switch (stairs)
    {
    case ETA_STAIRS_STEP_UP:
        return "Step up";
    case ETA_STAIRS_STEP_DOWN:
        return "Step down";
    case ETA_STAIRS_UP:
        return "Stairs up";
    case ETA_STAIRS_DOWN:
        return "Stairs down";
    case ETA_STAIRS_NONE:
    default:
        return NULL;
    }
}

void ETA_HudNarrator_SpeakStairs(ETA_Stairs stairs)
{
    const char *name = ETA_HudNarrator_StairsName(stairs);

    if (!name)
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("stairs", name);
}

void ETA_HudNarrator_LadderText(int goesUp, const char *direction, int meters,
                                char *out, size_t outSize)
{
    if (!out || outSize == 0)
    {
        return;
    }

    if (meters < 1)
    {
        meters = 1;
    }

    snprintf(out, outSize, "Ladder %s, %s, %d meter%s. F climbs",
             goesUp ? "up" : "down", direction && direction[0] ? direction : "ahead",
             meters, meters == 1 ? "" : "s");
}

void ETA_HudNarrator_HeightText(float heightMeters, char *out, size_t outSize)
{
    int meters;

    if (!out || outSize == 0)
    {
        return;
    }

    out[0] = '\0';

    if (heightMeters < ETA_HEIGHT_SAY_METERS && heightMeters > -ETA_HEIGHT_SAY_METERS)
    {
        return;
    }

    meters = (int)(heightMeters < 0.0f ? -heightMeters + 0.5f : heightMeters + 0.5f);

    snprintf(out, outSize, "%d meter%s %s you", meters, meters == 1 ? "" : "s",
             heightMeters > 0.0f ? "above" : "below");
}

void ETA_HudNarrator_SpeakLadder(int goesUp, const char *direction, int meters)
{
    static char buffer[96];

    ETA_HudNarrator_LadderText(goesUp, direction, meters, buffer, sizeof(buffer));
    ETA_HudNarrator_EmitMessage("ladder", buffer);
}

void ETA_HudNarrator_PlayStateText(ETA_PlayState state, const char *team, const char *playerClass,
                                   const char *following, char *out, size_t outSize)
{
    const char *base;
    int         haveTeam      = team && team[0];
    int         haveClass     = playerClass && playerClass[0];
    int         haveFollowing = following && following[0];

    if (!out || outSize == 0)
    {
        return;
    }

    out[0] = '\0';

    switch (state)
    {
    case ETA_PLAY_SPECTATING:
        base = "Spectating";
        break;
    case ETA_PLAY_IN_PLAY:
        snprintf(out, outSize, "In play%s%s%s%s", haveTeam ? ", " : "", haveTeam ? team : "",
                 haveClass ? ", " : "", haveClass ? playerClass : "");
        return;
    case ETA_PLAY_DOWN:
        snprintf(out, outSize, "Down, a medic can revive you");
        return;
    case ETA_PLAY_LIMBO:
        base = "Waiting to respawn";
        break;
    case ETA_PLAY_MATCH_OVER:
        snprintf(out, outSize, "Match over");
        return;
    case ETA_PLAY_UNKNOWN:
    default:
        return;
    }

    /* Watching from somebody else's eyes is worth saying: everything the
       narrator reports from here on is about them. */
    if (haveFollowing)
    {
        snprintf(out, outSize, "%s, following %s", base, following);
    }
    else
    {
        snprintf(out, outSize, "%s", base);
    }
}

void ETA_HudNarrator_SpeakPlayState(ETA_PlayState state, const char *team, const char *playerClass,
                                    const char *following)
{
    static char buffer[128];

    ETA_HudNarrator_PlayStateText(state, team, playerClass, following, buffer, sizeof(buffer));

    if (buffer[0])
    {
        ETA_HudNarrator_EmitMessage("play_state", buffer);
    }
}

const char *ETA_HudNarrator_InteractionName(ETA_Interaction what)
{
    switch (what)
    {
    case ETA_INTERACT_USABLE:
        return "Usable";
    case ETA_INTERACT_NOT_USABLE:
        return "Cannot use";
    case ETA_INTERACT_DOOR:
        return "Door";
    case ETA_INTERACT_DOOR_LOCKED:
        return "Locked door";
    case ETA_INTERACT_BUTTON:
        return "Button";
    case ETA_INTERACT_LADDER:
        return "Ladder";
    case ETA_INTERACT_WATER:
        return "Water";
    case ETA_INTERACT_MG42:
        return "Machine gun";
    case ETA_INTERACT_TANK:
        return "Tank";
    case ETA_INTERACT_BREAKABLE:
        return "Breakable";
    case ETA_INTERACT_NEEDS_DYNAMITE:
        return "Needs dynamite";
    /* The two the tester asked for by name. "Pliers" first in both, so
       the tool is known before the sentence finishes; the verb second,
       because planting where you meant to defuse is a round lost. */
    case ETA_INTERACT_BUILD:
        return "Pliers, build here";
    case ETA_INTERACT_DISARM:
        return "Pliers, defuse here";
    case ETA_INTERACT_PLANT_DYNAMITE:
        return "Dynamite goes here";
    case ETA_INTERACT_LANDMINE:
        return "Landmine";
    case ETA_INTERACT_SATCHEL:
        return "Satchel charge";
    case ETA_INTERACT_REVIVE:
        return "Revive";
    case ETA_INTERACT_REVIVE_FIRST:
        return "Revive first";
    case ETA_INTERACT_HEALTH:
        return "Health pack";
    case ETA_INTERACT_AMMO:
        return "Ammo pack";
    case ETA_INTERACT_WEAPON:
        return "Weapon";
    case ETA_INTERACT_RESTRICTED:
        return "Restricted weapon";
    case ETA_INTERACT_OBJECTIVE:
        return "Objective";
    case ETA_INTERACT_UNIFORM:
        return "Uniform";
    case ETA_INTERACT_KNIFE:
        return "Knife";
    case ETA_INTERACT_ALARM:
        return "Alarm";
    case ETA_INTERACT_TREASURE:
        return "Treasure";
    case ETA_INTERACT_CAUTION:
        return "Caution";
    case ETA_INTERACT_DANGER:
        return "Danger";
    case ETA_INTERACT_SECRET:
        return "Secret";
    case ETA_INTERACT_NOTE:
        return "Note";
    case ETA_INTERACT_QUESTION:
        return "Question";
    case ETA_INTERACT_ATTENTION:
        return "Attention";
    case ETA_INTERACT_ARMOUR:
        return "Armour";
    case ETA_INTERACT_ITEM:
        return "Item";
    case ETA_INTERACT_ARM_DYNAMITE:
        return "Pliers, arm dynamite here";
    case ETA_INTERACT_NONE:
    case ETA_INTERACT_COUNT:
    default:
        return NULL;
    }
}

void ETA_HudNarrator_SpeakInteraction(ETA_Interaction what, int percent)
{
    static char buffer[96];
    const char *name = ETA_HudNarrator_InteractionName(what);

    if (!name)
    {
        return;
    }

    if (percent < 0)
    {
        ETA_HudNarrator_EmitMessage("interaction", name);
        return;
    }

    snprintf(buffer, sizeof(buffer), "%s, %d percent", name, percent);

    ETA_HudNarrator_EmitMessage("interaction", buffer);
}

void ETA_HudNarrator_NamedInteractionText(const char *thing, ETA_Interaction what, int percent,
                                          char *out, size_t outSize)
{
    const char *name = ETA_HudNarrator_InteractionName(what);
    char        lower[64];
    size_t      i;

    if (!out || outSize == 0)
    {
        return;
    }

    out[0] = '\0';

    if (!name)
    {
        return;
    }

    if (!thing || !thing[0])
    {
        if (percent < 0)
        {
            snprintf(out, outSize, "%s", name);
        }
        else
        {
            snprintf(out, outSize, "%s, %d percent", name, percent);
        }
        return;
    }

    /* "Tank, usable": the thing leads, so it starts with a capital and
       the icon's word that follows does not. */
    for (i = 0; name[i] && i < sizeof(lower) - 1; i++)
    {
        lower[i] = (char)tolower((unsigned char)name[i]);
    }
    lower[i] = '\0';

    if (percent < 0)
    {
        snprintf(out, outSize, "%s, %s", thing, lower);
    }
    else
    {
        snprintf(out, outSize, "%s, %s, %d percent", thing, lower, percent);
    }

    if (out[0])
    {
        out[0] = (char)toupper((unsigned char)out[0]);
    }
}

void ETA_HudNarrator_SpeakNamedInteraction(const char *thing, ETA_Interaction what, int percent)
{
    static char buffer[128];

    ETA_HudNarrator_NamedInteractionText(thing, what, percent, buffer, sizeof(buffer));

    if (buffer[0])
    {
        ETA_HudNarrator_EmitMessage("interaction", buffer);
    }
}

void ETA_HudNarrator_SpeakMapCell(const char *cellName, const char *contents,
                                  int distanceMeters, int bearingDegrees)
{
    /* As long as speech takes: the things in the square and the kind of
       places it holds make a longer line than the rest of the HUD says. */
    static char buffer[ETA_MAX_SPEECH_TEXT_LENGTH + 1];
    char        where[64];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(cellName,
                                                            ETA_MAX_HUD_TEXT_LENGTH,
                                                            "hud_narrator.SpeakMapCell")))
    {
        return;
    }

    /* An empty square is announced, not skipped. On a grid the player
       cannot see, a keypress that says nothing reads as a keypress that
       did not register - and they would press it again. */
    if (!contents || !contents[0])
    {
        contents = "empty";
    }

    where[0] = '\0';

    if (distanceMeters >= 0 && bearingDegrees >= 0)
    {
        snprintf(where, sizeof(where), ", %d metres, %s, %d degrees",
                 distanceMeters,
                 ETA_HudNarrator_FacingName(
                     ETA_HudNarrator_FacingFromBearing((float)bearingDegrees)),
                 bearingDegrees);
    }
    else if (distanceMeters >= 0)
    {
        snprintf(where, sizeof(where), ", %d metres", distanceMeters);
    }
    else if (bearingDegrees >= 0)
    {
        snprintf(where, sizeof(where), ", %s, %d degrees",
                 ETA_HudNarrator_FacingName(
                     ETA_HudNarrator_FacingFromBearing((float)bearingDegrees)),
                 bearingDegrees);
    }

    snprintf(buffer, sizeof(buffer), "%s. %s%s", cellName, contents, where);

    ETA_HudNarrator_EmitMessage("map", buffer);
}

static int gPassiveHoldUntil = 0;
static int gPassiveHoldSet  = 0;

void ETA_HudNarrator_HoldPassive(int nowMs)
{
    gPassiveHoldUntil = nowMs + ETA_HUD_HOLD_MS;
    gPassiveHoldSet   = 1;
}

void ETA_HudNarrator_ReleasePassive(void)
{
    gPassiveHoldSet = 0;
}

int ETA_HudNarrator_PassiveHeld(int nowMs)
{
    if (!gPassiveHoldSet)
    {
        return 0;
    }

    /* The engine's clock restarts on a map change, and a hold set just
       before one would otherwise last until the clock caught up again -
       most of an hour, with the scenery silent throughout. A time that
       has gone backwards is a new map, not a long wait. */
    if (nowMs > gPassiveHoldUntil || nowMs < gPassiveHoldUntil - ETA_HUD_HOLD_MS)
    {
        gPassiveHoldSet = 0;
        return 0;
    }

    return 1;
}

void ETA_HudNarrator_SpeakMapEdge(void)
{
    ETA_HudNarrator_EmitMessage("map", "Edge of the map");
}

void ETA_HudNarrator_SpeakMapLayer(int layer, int layerCount)
{
    static char buffer[64];

    snprintf(buffer, sizeof(buffer), "Floor %d of %d", layer + 1, layerCount);

    ETA_HudNarrator_EmitMessage("map", buffer);
}

const char *ETA_HudNarrator_ObjectiveStateName(ETA_ObjectiveState state)
{
    switch (state)
    {
    case ETA_OBJECTIVE_COMPLETE:
        return "complete";
    case ETA_OBJECTIVE_FAILED:
        return "failed";
    case ETA_OBJECTIVE_PENDING:
    default:
        return NULL;
    }
}

void ETA_HudNarrator_SpeakObjectiveStep(int number, int total,
                                        ETA_ObjectiveState state,
                                        const char *text)
{
    static char buffer[ETA_MAX_HUD_TEXT_LENGTH + 96];
    const char  *stateName = ETA_HudNarrator_ObjectiveStateName(state);

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(number, 1, total,
                                                              "hud_narrator.SpeakObjectiveStep")))
    {
        return;
    }

    /* The position first, always. It is the short part and the part a
       player can act on, and it survives being cut off by whatever the
       next frame decides to say. */
    if (text && text[0])
    {
        if (stateName)
        {
            snprintf(buffer, sizeof(buffer), "Objective %d of %d, %s: %s",
                     number, total, stateName, text);
        }
        else
        {
            snprintf(buffer, sizeof(buffer), "Objective %d of %d: %s",
                     number, total, text);
        }
    }
    else if (stateName)
    {
        snprintf(buffer, sizeof(buffer), "Objective %d of %d, %s",
                 number, total, stateName);
    }
    else
    {
        snprintf(buffer, sizeof(buffer), "Objective %d of %d", number, total);
    }

    ETA_HudNarrator_EmitMessage("objective", buffer);
}

/* Where the climb is worth a word. Four of them: enough to know the work
   is going somewhere, few enough to be listened to.

   90 is here because a tester reported the narration "stops at 75",
   which it did - the last milestone landed with a quarter of the work
   left and nothing followed it. The engine's progress tops out just
   under 98%, never 100, because the value is reset in the same frame it
   crosses its own finish line; so 90 is the last figure a climbing
   construction can actually reach, and the one that says "nearly". What
   comes after it is not another number, it is the completion callout. */
static const int gBuildMilestones[] = { 25, 50, 75, 90 };
#define ETA_BUILD_MILESTONE_COUNT ((int)(sizeof(gBuildMilestones) / sizeof(gBuildMilestones[0])))

static int gBuildAnnounced[ETA_BUILD_MILESTONE_COUNT];

void ETA_HudNarrator_ResetBuildProgress(void)
{
    int i;

    for (i = 0; i < ETA_BUILD_MILESTONE_COUNT; i++)
    {
        gBuildAnnounced[i] = 0;
    }
}

void ETA_HudNarrator_SpeakBuildComplete(void)
{
    ETA_HudNarrator_EmitMessage("build", "Construction complete");
}

void ETA_HudNarrator_SpeakBuildProgress(int percent)
{
    static char buffer[64];

    snprintf(buffer, sizeof(buffer), "Building, %d percent", percent);

    ETA_HudNarrator_EmitMessage("build", buffer);
}

int ETA_HudNarrator_UpdateBuildProgress(int percent)
{
    int i;
    int crossed = -1;

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(percent, 0, 100,
                                                              "hud_narrator.UpdateBuildProgress")))
    {
        return 0;
    }

    /* Re-arm before testing. A construction left alone decays, and a
       player who comes back to finish it is starting the climb again -
       they should hear it again, not be met with the silence of
       milestones that were passed several minutes ago. */
    for (i = 0; i < ETA_BUILD_MILESTONE_COUNT; i++)
    {
        if (percent < gBuildMilestones[i])
        {
            gBuildAnnounced[i] = 0;
        }
    }

    /* Highest crossed wins, so arriving at a part-built construction
       says where it stands rather than counting up to it. */
    for (i = 0; i < ETA_BUILD_MILESTONE_COUNT; i++)
    {
        if (percent >= gBuildMilestones[i] && !gBuildAnnounced[i])
        {
            gBuildAnnounced[i] = 1;
            crossed            = i;
        }
    }

    if (crossed < 0)
    {
        return 0;
    }

    /* The real figure, not the milestone: the milestone decided when to
       speak and has no business deciding what is true. */
    ETA_HudNarrator_SpeakBuildProgress(percent);

    return 1;
}

void ETA_HudNarrator_SpeakObjectivesComplete(void)
{
    ETA_HudNarrator_EmitMessage("objective", "All objectives complete");
}

void ETA_HudNarrator_SpeakObjective(const char *objectiveText)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(objectiveText, ETA_MAX_HUD_TEXT_LENGTH, "hud_narrator.SpeakObjective")))
    {
        return;
    }

    ETA_HudNarrator_EmitMessage("objective", objectiveText);
}

void ETA_HudNarrator_SpeakRespawn(int secondsRemaining)
{
    static char buffer[64];

    snprintf(buffer, sizeof(buffer), "Respawn in %d seconds", secondsRemaining);

    ETA_HudNarrator_EmitMessage("respawn", buffer);
}

void ETA_HudNarrator_Shutdown(void)
{
}

/*
 * Who and what is near you. See the header for what is news and why.
 */
typedef struct
{
    const char *noun;       /* "Enemy", "Teammate" ... */
    const char *suffix;     /* after the name: " on the ground" */
    const char *plural;     /* "enemies", for several at once */
    const char *closer;     /* the word for coming into a nearer band */
    int         bandCount;
    float       edges[5];   /* metres, furthest first */
    float       margin;     /* how far past an edge before a band is left */
    int         sayCloser;
    int         sayAway;    /* moving away, and out of sight */
    int         gapMs;      /* between two lines about the same thing */
    int         tier;       /* lower is said first */
} ETA_AwareRule;

static const ETA_AwareRule gAwareRules[ETA_AWARE_KINDS] =
{
    /* An enemy: from as far as a sighted player would pick one out, and
       every band on the way in and out. */
    { "Enemy",            "",                 "enemies",            "closer", 5, { 40.0f, 25.0f, 15.0f, 8.0f, 4.0f }, 1.15f, 1, 1, 2000, 0 },
    /* A teammate waiting for a medic: far enough to go and get them. */
    { "Wounded teammate", "",                 "wounded teammates",  "closer", 4, { 30.0f, 15.0f, 8.0f, 3.0f },        1.15f, 1, 0, 4000, 1 },
    /* Teammates are everywhere at a spawn: arriving, and coming close. */
    { "Teammate",         "",                 "teammates",          "close",  2, { 15.0f, 5.0f },                     1.15f, 1, 0, 5000, 3 },
    { "Enemy down",       "",                 "enemies down",       "",       1, { 15.0f },                           1.3f,  0, 0, 0,    3 },
    /* Within a few steps, where it can be walked over and picked up. */
    { "",                 " on the ground",   "things on the ground", "",     1, { 5.0f },                            2.0f,  0, 0, 0,    4 },
    { "Enemy body",       " with a uniform",  "enemy bodies",       "",       1, { 8.0f },                            1.5f,  0, 0, 0,    4 },
};

/* The teammate's words, when a game calls its people something else - the
   campaign's are friends, not teammates. */
static const char *gAwareFriendNoun;
static const char *gAwareFriendPlural;

void ETA_HudNarrator_SetFriendWords(const char *noun, const char *plural)
{
    gAwareFriendNoun   = noun;
    gAwareFriendPlural = plural;
}

static const char *ETA_HudNarrator_AwareNoun(ETA_AwareKind kind)
{
    if (kind == ETA_AWARE_TEAMMATE && gAwareFriendNoun)
    {
        return gAwareFriendNoun;
    }
    return gAwareRules[kind].noun;
}

static const char *ETA_HudNarrator_AwarePlural(ETA_AwareKind kind)
{
    if (kind == ETA_AWARE_TEAMMATE && gAwareFriendPlural)
    {
        return gAwareFriendPlural;
    }
    return gAwareRules[kind].plural;
}

typedef struct
{
    int           used;
    int           id;
    ETA_AwareKind kind;
    int           present;
    int           lastSeen;
    int           band;         /* -1 out of range */
    int           announced;    /* the band last said; -1 none */
    int           lost;         /* an announced enemy that has gone */
    int           spokeSet;
    int           spokeAt;
    float         meters;
    float         leftOfView;
    char          name[48];
} ETA_AwareSlot;

enum
{
    ETA_AWARE_EVENT_NONE,
    ETA_AWARE_EVENT_APPEAR,
    ETA_AWARE_EVENT_CLOSER,
    ETA_AWARE_EVENT_AWAY,
    ETA_AWARE_EVENT_LOST
};

static ETA_AwareSlot gAware[ETA_AWARE_MAX];
static int           gAwareSpokeSet;
static int           gAwareSpokeAt;

/* How long since then; "forever" when it never happened or the clock
   went back, as it does on a new map. */
static int ETA_HudNarrator_Since(int set, int then, int nowMs)
{
    if (!set || nowMs < then)
    {
        return 0x7fffffff;
    }

    return nowMs - then;
}

void ETA_HudNarrator_ResetAwareness(void)
{
    memset(gAware, 0, sizeof(gAware));
    gAwareSpokeSet = 0;
    gAwareSpokeAt  = 0;
}

float ETA_HudNarrator_AwareRange(ETA_AwareKind kind)
{
    if ((int)kind < 0 || kind >= ETA_AWARE_KINDS)
    {
        return 0.0f;
    }

    return gAwareRules[kind].edges[0];
}

const char *ETA_HudNarrator_RelativeDirection(float leftOfView)
{
    float r = ETA_HudNarrator_NormalizeDegrees(leftOfView);
    float a;
    int   left;

    if (r > 180.0f)
    {
        r -= 360.0f;
    }

    left = r > 0.0f;
    a    = left ? r : -r;

    if (a <= 22.5f)
    {
        return "ahead";
    }
    if (a <= 67.5f)
    {
        return left ? "ahead left" : "ahead right";
    }
    if (a <= 112.5f)
    {
        return left ? "left" : "right";
    }
    if (a <= 157.5f)
    {
        return left ? "behind left" : "behind right";
    }
    return "behind";
}

/* The band a distance is in, nearest highest; -1 past the furthest edge.
   Leaving a band outward takes its edge plus the margin. */
static int ETA_HudNarrator_AwareBand(const ETA_AwareRule *rule, float meters, int previous)
{
    int band = -1, i;

    for (i = 0; i < rule->bandCount; i++)
    {
        if (meters <= rule->edges[i])
        {
            band = i;
        }
    }

    if (previous >= 0 && band < previous && meters <= rule->edges[previous] * rule->margin)
    {
        band = previous;
    }

    return band;
}

/* A slot for a new thing: nothing in range yet, nothing said. */
static void ETA_HudNarrator_AwareClaim(ETA_AwareSlot *slot)
{
    memset(slot, 0, sizeof(*slot));
    slot->used      = 1;
    slot->band      = -1;
    slot->announced = -1;
}

static int ETA_HudNarrator_AwareEvent(const ETA_AwareSlot *slot)
{
    const ETA_AwareRule *rule = &gAwareRules[slot->kind];

    if (!slot->present)
    {
        return slot->lost ? ETA_AWARE_EVENT_LOST : ETA_AWARE_EVENT_NONE;
    }
    if (slot->band >= 0 && slot->announced < 0)
    {
        return ETA_AWARE_EVENT_APPEAR;
    }
    if (slot->announced >= 0 && slot->band > slot->announced && rule->sayCloser)
    {
        return ETA_AWARE_EVENT_CLOSER;
    }
    if (slot->announced >= 0 && slot->band < slot->announced && rule->sayAway)
    {
        return ETA_AWARE_EVENT_AWAY;
    }
    return ETA_AWARE_EVENT_NONE;
}

/* Lower is said first: an enemy coming, then a wounded teammate, then an
   enemy going, then the rest by kind. */
static int ETA_HudNarrator_AwareRank(const ETA_AwareSlot *slot, int event)
{
    if (slot->kind == ETA_AWARE_ENEMY)
    {
        return (event == ETA_AWARE_EVENT_APPEAR || event == ETA_AWARE_EVENT_CLOSER) ? 0 : 2;
    }

    return gAwareRules[slot->kind].tier;
}

static int ETA_HudNarrator_AwareMeters(float meters)
{
    int whole = (int)(meters + 0.5f);

    return whole < 1 ? 1 : whole;
}

static void ETA_HudNarrator_AwareSubject(const ETA_AwareSlot *slot, char *out, size_t outSize)
{
    const ETA_AwareRule *rule = &gAwareRules[slot->kind];
    const char          *noun = ETA_HudNarrator_AwareNoun(slot->kind);

    if (noun[0] && slot->name[0])
    {
        snprintf(out, outSize, "%s %s%s", noun, slot->name, rule->suffix);
    }
    else if (noun[0])
    {
        snprintf(out, outSize, "%s%s", noun, rule->suffix);
    }
    else
    {
        snprintf(out, outSize, "%s%s", slot->name[0] ? slot->name : "Something", rule->suffix);
    }
}

int ETA_HudNarrator_UpdateAwareness(const ETA_AwareThing *things, int count,
                                    int nowMs, int quietMs, int mayInterrupt,
                                    char *out, size_t outSize)
{
    ETA_AwareSlot *best = NULL;
    int           bestEvent = ETA_AWARE_EVENT_NONE, bestRank = 0;
    int           sinceAny, i, j;
    char          subject[96];
    int           meters;
    const char    *where;

    if (!out || outSize == 0)
    {
        return 0;
    }
    out[0] = '\0';

    if (count < 0 || (count > 0 && !things))
    {
        return 0;
    }

    for (i = 0; i < ETA_AWARE_MAX; i++)
    {
        gAware[i].present = 0;
    }

    /* This frame's list into the slots. */
    for (j = 0; j < count; j++)
    {
        const ETA_AwareThing *thing = &things[j];
        ETA_AwareSlot        *slot  = NULL;

        if ((int)thing->kind < 0 || thing->kind >= ETA_AWARE_KINDS)
        {
            continue;
        }

        for (i = 0; i < ETA_AWARE_MAX; i++)
        {
            if (gAware[i].used && gAware[i].id == thing->id)
            {
                slot = &gAware[i];
                break;
            }
        }

        if (slot && slot->kind != thing->kind)
        {
            /* The same entity become something else - an enemy gone
               down, a teammate revived. A new thing, not the old one
               going out of sight. */
            ETA_HudNarrator_AwareClaim(slot);
        }

        if (!slot)
        {
            for (i = 0; i < ETA_AWARE_MAX; i++)
            {
                if (!gAware[i].used)
                {
                    slot = &gAware[i];
                    ETA_HudNarrator_AwareClaim(slot);
                    break;
                }
            }
        }

        if (!slot)
        {
            continue;
        }

        slot->id          = thing->id;
        slot->kind        = thing->kind;
        slot->present     = 1;
        slot->lost        = 0;
        slot->lastSeen    = nowMs;
        slot->meters      = thing->meters;
        slot->leftOfView = thing->leftOfView;
        snprintf(slot->name, sizeof(slot->name), "%s", thing->name);
        slot->band = ETA_HudNarrator_AwareBand(&gAwareRules[thing->kind], thing->meters, slot->band);
    }

    /* What is gone. An enemy that was said is said going; anything else
       is forgotten, so it is news again if it comes back. */
    for (i = 0; i < ETA_AWARE_MAX; i++)
    {
        ETA_AwareSlot *slot = &gAware[i];

        if (!slot->used || slot->present || slot->lost)
        {
            continue;
        }

        if (ETA_HudNarrator_Since(1, slot->lastSeen, nowMs) < ETA_AWARE_LOST_MS)
        {
            continue;
        }

        if (slot->announced >= 0 && gAwareRules[slot->kind].sayAway)
        {
            slot->lost = 1;
        }
        else
        {
            memset(slot, 0, sizeof(*slot));
        }
    }

    /* Moving away, for the kinds that do not say it, is taken in quietly
       so coming back in is news again. */
    for (i = 0; i < ETA_AWARE_MAX; i++)
    {
        ETA_AwareSlot *slot = &gAware[i];

        if (slot->used && slot->present && !gAwareRules[slot->kind].sayAway
            && slot->announced >= 0 && slot->band < slot->announced)
        {
            slot->announced = slot->band;
        }
    }

    sinceAny = ETA_HudNarrator_Since(gAwareSpokeSet, gAwareSpokeAt, nowMs);

    /* The most important line waiting, nearest first among equals. */
    for (i = 0; i < ETA_AWARE_MAX; i++)
    {
        ETA_AwareSlot *slot = &gAware[i];
        int           event, rank, urgent;

        if (!slot->used)
        {
            continue;
        }

        event = ETA_HudNarrator_AwareEvent(slot);
        if (event == ETA_AWARE_EVENT_NONE)
        {
            continue;
        }

        urgent = slot->kind == ETA_AWARE_ENEMY
                 && (event == ETA_AWARE_EVENT_APPEAR || event == ETA_AWARE_EVENT_CLOSER);

        if (urgent && !mayInterrupt && quietMs < ETA_AWARE_QUIET_MS)
        {
            continue;
        }

        if (urgent ? sinceAny < ETA_AWARE_ENEMY_GAP_MS
            : (quietMs < ETA_AWARE_QUIET_MS || sinceAny < 2 * ETA_AWARE_ENEMY_GAP_MS))
        {
            continue;
        }

        if ((event == ETA_AWARE_EVENT_CLOSER || event == ETA_AWARE_EVENT_AWAY)
            && ETA_HudNarrator_Since(slot->spokeSet, slot->spokeAt, nowMs) < gAwareRules[slot->kind].gapMs)
        {
            continue;
        }

        rank = ETA_HudNarrator_AwareRank(slot, event);

        if (!best || rank < bestRank || (rank == bestRank && slot->meters < best->meters))
        {
            best      = slot;
            bestEvent = event;
            bestRank  = rank;
        }
    }

    if (!best)
    {
        return 0;
    }

    ETA_HudNarrator_AwareSubject(best, subject, sizeof(subject));
    meters = ETA_HudNarrator_AwareMeters(best->meters);
    where  = ETA_HudNarrator_RelativeDirection(best->leftOfView);

    if (bestEvent == ETA_AWARE_EVENT_LOST)
    {
        snprintf(out, outSize, "%s out of sight, last seen %s", subject, where);
        memset(best, 0, sizeof(*best));
    }
    else if (bestEvent == ETA_AWARE_EVENT_AWAY)
    {
        snprintf(out, outSize, "%s moving away, %s, %d meter%s", subject, where, meters,
                 meters == 1 ? "" : "s");
        best->announced = best->band;
        best->spokeSet  = 1;
        best->spokeAt   = nowMs;
    }
    else if (bestEvent == ETA_AWARE_EVENT_CLOSER)
    {
        snprintf(out, outSize, "%s %s, %s, %d meter%s", subject, gAwareRules[best->kind].closer,
                 where, meters, meters == 1 ? "" : "s");
        best->announced = best->band;
        best->spokeSet  = 1;
        best->spokeAt   = nowMs;
    }
    else
    {
        /* Several of one kind arriving together: one line for them all. */
        int together = 0;

        for (i = 0; i < ETA_AWARE_MAX; i++)
        {
            ETA_AwareSlot *slot = &gAware[i];

            if (slot->used && slot->kind == best->kind
                && ETA_HudNarrator_AwareEvent(slot) == ETA_AWARE_EVENT_APPEAR)
            {
                together++;
            }
        }

        if (together > 1)
        {
            char nearest[64];

            nearest[0] = '\0';
            if (best->name[0])
            {
                snprintf(nearest, sizeof(nearest), "%s, ", best->name);
            }

            snprintf(out, outSize, "%d %s, nearest %s%s, %d meter%s", together,
                     ETA_HudNarrator_AwarePlural(best->kind), nearest, where, meters, meters == 1 ? "" : "s");

            for (i = 0; i < ETA_AWARE_MAX; i++)
            {
                ETA_AwareSlot *slot = &gAware[i];

                if (slot != best && slot->used && slot->kind == best->kind
                    && ETA_HudNarrator_AwareEvent(slot) == ETA_AWARE_EVENT_APPEAR)
                {
                    slot->announced = slot->band;
                    slot->spokeSet  = 1;
                    slot->spokeAt   = nowMs;
                }
            }
        }
        else
        {
            snprintf(out, outSize, "%s, %s, %d meter%s", subject, where, meters, meters == 1 ? "" : "s");
        }

        best->announced = best->band;
        best->spokeSet  = 1;
        best->spokeAt   = nowMs;
    }

    gAwareSpokeSet = 1;
    gAwareSpokeAt  = nowMs;
    return 1;
}

void ETA_HudNarrator_SpeakAwareness(const char *text)
{
    static char buffer[160];

    if (!text || !text[0])
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "%s", text);
    ETA_HudNarrator_EmitMessage("awareness", buffer);
}

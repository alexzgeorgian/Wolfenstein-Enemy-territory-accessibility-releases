#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void ETA_HudNarrator_Init(void);
void ETA_HudNarrator_SpeakHealth(int health);
void ETA_HudNarrator_SpeakAmmo(int ammo);

/*
 * Loaded rounds plus what is left to reload from. A negative reserve means
 * the weapon has none to report - a grenade, a knife - and only the loaded
 * count is spoken.
 */
void ETA_HudNarrator_SpeakAmmoDetail(int loaded, int reserve);
void ETA_HudNarrator_SpeakWeapon(const char *weaponName);

/*
 * The player's posture. An enum rather than a string because these three
 * words are the mod's own, not the engine's: both integrations would
 * otherwise be free to word them differently, and a player moving between
 * builds would hear the same body doing different things.
 *
 * Ordered as the body rises, which is also the order the engines have to
 * test their flags in - going prone sets the crouch flag as well, so
 * anything checking crouch first would call prone "crouched".
 */
typedef enum ETA_Stance
{
    ETA_STANCE_PRONE = 0,
    ETA_STANCE_CROUCHED,
    ETA_STANCE_STANDING
} ETA_Stance;

void ETA_HudNarrator_SpeakStance(ETA_Stance stance);
/*
 * What a pickup actually gave the player.
 *
 * isRounds picks the unit - rounds for ammo, health otherwise - because
 * "30" on its own says nothing, and a mod that spoke "30 rounds" for a
 * health pack would be confidently wrong.
 */
void ETA_HudNarrator_SpeakGain(int amount, int isRounds);

/*
 * That a pickup gave nothing, because the player was already at their
 * limit. Worth saying: the pack is consumed either way, so silence here
 * sounds exactly like a pickup that helped.
 */
void ETA_HudNarrator_SpeakAlreadyFull(void);

/*
 * Whether the player is looking through anything.
 *
 * Worth saying on its own: a scope does not always engage when asked -
 * some weapons refuse while moving or reloading - so silence after
 * pressing zoom is currently indistinguishable from a scope that came up.
 */
typedef enum ETA_Zoom
{
    ETA_ZOOM_OFF = 0,
    ETA_ZOOM_BINOCULARS,
    ETA_ZOOM_SCOPE
} ETA_Zoom;

void ETA_HudNarrator_SpeakZoom(ETA_Zoom zoom);

/*
 * What lies directly along the player's view, and how far off it is.
 *
 * A negative distance means there is no sensible one to give - open sky,
 * or nothing within range - and only the description is spoken.
 */
void ETA_HudNarrator_SpeakLookAhead(const char *what, int distanceMeters);

/*
 * What the player is standing on, named from the engine's own surface
 * flags. Spoken when it changes, which is the only time it is news:
 * a sighted player sees the ground change under them, and this is that
 * moment rather than a running commentary.
 */
void ETA_HudNarrator_SpeakFooting(const char *material);

/*
 * Which way the player is facing, as one of the eight points the game's
 * own compass draws.
 *
 * An enum, and in this order, because the words are the mod's but the
 * directions are not: ET's compass puts north at yaw 90 and east at yaw
 * 0, and a mod that picked its own north would send a player confidently
 * the wrong way while agreeing with nothing on screen.
 */
typedef enum ETA_Facing
{
    ETA_FACING_NORTH = 0,
    ETA_FACING_NORTHEAST,
    ETA_FACING_EAST,
    ETA_FACING_SOUTHEAST,
    ETA_FACING_SOUTH,
    ETA_FACING_SOUTHWEST,
    ETA_FACING_WEST,
    ETA_FACING_NORTHWEST
} ETA_Facing;

/*
 * The compass point a view yaw falls in.
 *
 * This is the engine's own compass arithmetic, kept here rather than in
 * either integration so both speak the same direction for the same yaw,
 * and so it can be checked against the engine without a game running.
 */
ETA_Facing ETA_HudNarrator_FacingFromYaw(float yawDegrees);

/*
 * The same eight points, from a true bearing rather than a view yaw, so
 * a caller that already holds a bearing does not have to convert back
 * into the engine's frame to get the word for it.
 */
ETA_Facing ETA_HudNarrator_FacingFromBearing(float bearingDegrees);

/*
 * The same view yaw as a true bearing: north is 0, east is 90, and it
 * climbs clockwise the way every compass a player has ever read does.
 *
 * This is the exact expression the compass point above is chosen from,
 * exposed rather than written out a second time somewhere else. The map
 * survey speaks a bearing in degrees alongside the cardinal name, and
 * two conversions would eventually disagree - at which point the mod
 * would be saying "north-east, 210 degrees" with complete confidence.
 *
 * Note this is NOT the engine's yaw. ET puts north at yaw 90 and counts
 * anticlockwise, so handing a player a raw yaw as a bearing would be
 * wrong twice over: rotated a quarter turn and running backwards.
 */
float ETA_HudNarrator_BearingFromYaw(float yawDegrees);

/*
 * The spoken name, for callers that want to put a direction inside a
 * longer sentence rather than announce it on its own.
 */
const char *ETA_HudNarrator_FacingName(ETA_Facing facing);

void ETA_HudNarrator_SpeakFacing(ETA_Facing facing);

/*
 * Tracks the facing across frames and reports only changes worth
 * speaking.
 *
 * Two separate things are being suppressed here, and they are not the
 * same problem.
 *
 * Standing on a sector boundary - which happens every time a player
 * lines up on something - would otherwise flip the announcement back and
 * forth with the smallest movement of the mouse, so a new sector is only
 * adopted once the view is properly inside it. That is the hysteresis.
 *
 * Sweeping the mouse is the other one. A swing across half the compass
 * crosses four sectors in a few frames, and announcing each of them in
 * turn produces four reports for one movement of the hand. Speech cannot
 * deliver those faster than they arrive: a backend that queues reads them
 * out one behind the other, so the narration trails the view and is still
 * naming headings the player turned past seconds ago, and a backend that
 * interrupts destroys each report with the next and leaves fragments.
 * Either way it sounds like a narrator that cannot keep up, which is the
 * shape of the complaint that produced this.
 *
 * So a new sector has to be *held* for ETA_FACING_SETTLE_MS before it is
 * spoken. A sweep announces nothing while the hand is moving and one
 * heading - the one actually arrived at - when it stops. A slow,
 * deliberate turn is unaffected: it sits in each sector for longer than
 * the settle time and is announced sector by sector, as it should be.
 *
 * nowMs is the engine's own clock. Returns 1 on the frame the facing
 * becomes speakable, and writes it to *facing.
 */
void ETA_HudNarrator_ResetFacing(void);
int ETA_HudNarrator_UpdateFacing(float yawDegrees, int nowMs, ETA_Facing *facing);

/*
 * Turning with the keys rather than the mouse.
 *
 * The settle wait above exists to tell a mouse sweep from a deliberate
 * turn, and a held turn key is always deliberate - it moves at the
 * engine's fixed speed and nothing else. So while the caller says a turn
 * key is down, a new point is spoken as soon as the view is properly
 * inside it (the hysteresis still applies), rather than after holding it.
 * A tester holding the key heard the points only when tapping instead.
 *
 * SetFacingHeld records a point the caller has just announced itself -
 * the end of a tap that turned the view onto a compass point - so the
 * next update does not announce the same point a second time.
 */
void ETA_HudNarrator_SetFacingKeyTurn(int keyTurning);
void ETA_HudNarrator_SetFacingHeld(ETA_Facing facing);

/*
 * Where the view is pointed up or down.
 *
 * Returns 1 when the player has settled on a materially different
 * vertical angle and a fresh report is owed. It says nothing about what
 * is up there - the caller traces that and speaks it - because the
 * honest answer to "what am I looking at" is whatever the engine's own
 * collision runs into, not an inference from an angle. Pointing at 40
 * degrees up is sky outdoors and a ceiling indoors.
 *
 * The first reading is swallowed: it is where the player already is,
 * not somewhere they chose to look.
 */
void ETA_HudNarrator_ResetLookPitch(void);
int  ETA_HudNarrator_UpdateLookPitch(float pitchDegrees, int nowMs);

/*
 * How far the ground drops away in front of the player.
 *
 * A sighted player sees a ledge without looking for it. Without this the
 * mod described the wall ahead and the ground underfoot and had nothing
 * at all to say about the one piece of terrain that can kill you outright
 * while you are walking in a straight line.
 *
 * The bands are the engine's own, not a judgement of ours: ET works out
 * falling damage from the landing speed in PM_CrashLand, and its own
 * ladder starts doing damage at one number and kills at another. Those
 * two numbers, turned back into heights through the gravity actually in
 * play, are ETA_DROP_INJURING and ETA_DROP_DEADLY. A mod that guessed
 * "about ten metres" would be confidently wrong on any map or server that
 * changed gravity.
 *
 * ETA_DROP_WATER is not a softer version of the others. The engine
 * cancels falling damage outright for a player who lands submerged, so a
 * drop into deep water is a way down rather than a hazard, and calling it
 * deadly would send a player the long way round for no reason.
 */
typedef enum ETA_Drop
{
    ETA_DROP_NONE = 0,
    ETA_DROP_LEDGE,
    ETA_DROP_INJURING,
    ETA_DROP_DEADLY,
    ETA_DROP_WATER
} ETA_Drop;

/*
 * distanceMeters < 0 means the probe found no bottom at all within its
 * reach, which is spoken as such rather than as a number: "no bottom in
 * range" is the honest report, and inventing a depth for it would be the
 * one kind of lie this mod cannot afford.
 */
void ETA_HudNarrator_SpeakDrop(ETA_Drop drop, int distanceMeters);

/*
 * The height a fall has to start from to reach one of the engine's
 * damage steps, in Quake units, for the gravity actually in play.
 *
 * PM_CrashLand compares delta = v * v * 0.0001 against its ladder, and a
 * fall from rest reaches v * v = 2 * g * h, so h = delta * 10000 / (2g).
 * Kept here rather than in either integration so both engines classify a
 * drop the same way, and so it can be checked without a game running.
 */
float ETA_HudNarrator_FallHeightForDelta(float delta, float gravity);

/*
 * How deep in water the player is.
 *
 * These are the engine's own waterlevels, and each word below is tied to
 * something the engine actually does at that level rather than to how
 * deep it looks: at ETA_WATER_DEEP a jump starts a swim instead of a
 * jump, and at ETA_WATER_SWIMMING the movement code says "begin
 * swimming" and falling damage is cancelled entirely.
 */
typedef enum ETA_Water
{
    ETA_WATER_DRY = 0,
    ETA_WATER_SHALLOW,
    ETA_WATER_DEEP,
    ETA_WATER_SWIMMING
} ETA_Water;

void ETA_HudNarrator_SpeakWater(ETA_Water water);

/*
 * Where on the map the player is.
 *
 * ET already answers this for everyone else. Most maps ship a file of
 * named places - "Old City Wall", "Axis Command Post" - and the engine
 * picks the nearest one that is actually in view; it is the same lookup
 * that fills in the location when a sighted player types in team chat.
 * Maps without that file still have the command map's grid, so there is
 * always an answer, and on either path the words match what a teammate
 * would say.
 *
 * The name is the integration's to fetch, because only it can reach the
 * engine. What lives here is the decision of *when* to say it, which is
 * the whole difficulty: a stock map carries over a hundred named places,
 * and announcing each one as it goes by would be a voice that never
 * stops. So a new place has to be held for ETA_LOCATION_SETTLE_MS before
 * it is spoken, exactly as a compass heading does - walking through a
 * doorway and out again says nothing, arriving somewhere says it once.
 *
 * Returns 1 on the frame the location becomes worth speaking.
 */
void ETA_HudNarrator_SpeakLocation(const char *location);
void ETA_HudNarrator_ResetLocation(void);
int  ETA_HudNarrator_UpdateLocation(const char *location, int nowMs);

/*
 * Openings along the way: a side street, the corner of a building, the
 * end of an alley.
 *
 * A sighted player walking down a street sees the turning coming up on
 * the left. A tester playing by ear could hear the street but not where
 * it began or ended, and asked for the corners by compass point. So the
 * integration measures how far the way runs to the north, east, south
 * and west as the player moves, and this decides when that is news:
 *
 *   - a side that runs ETA_OPENING_OPEN_METERS or further (or does not
 *     stop at all, which the integration passes as -1) is open; one that
 *     stops at ETA_OPENING_WALL_METERS or closer is a wall; anything in
 *     between keeps whatever it was, so a wall at the edge of the line
 *     does not flicker;
 *   - a change has to hold for ETA_OPENING_SETTLE_MS before it counts,
 *     so a lamp post or a doorway walked past says nothing;
 *   - it is only spoken while the player is moving. Standing still, a
 *     change is taken in quietly - a door swinging open beside someone
 *     who is waiting is not an opening they walked to;
 *   - a change within ETA_OPENING_GAP_MS of the last one spoken waits
 *     for the gap to pass, and is spoken then if it still holds, so a
 *     corner that opens two sides at once is said once.
 *
 * The first reading after a reset is taken as the way things are, not
 * as news: arriving somewhere is the location's to announce.
 *
 * Directions are indexed north, east, south, west, and *opened and
 * *closed come back as bit masks of the same (bit 0 north). Returns 1
 * when either is worth speaking.
 */
#define ETA_OPENING_DIRECTIONS  4
#define ETA_OPENING_OPEN_METERS 8
#define ETA_OPENING_WALL_METERS 4
#define ETA_OPENING_SETTLE_MS   400
#define ETA_OPENING_GAP_MS      1500

void ETA_HudNarrator_ResetOpenings(void);
int  ETA_HudNarrator_UpdateOpenings(const int metersByDirection[ETA_OPENING_DIRECTIONS],
                                    int moving, int nowMs, int *opened, int *closed);

/*
 * The words for a change: "Opening to the east", "Opening to the north
 * and east, wall to the west". Empty when both masks are.
 */
void ETA_HudNarrator_OpeningsText(int opened, int closed, char *out, size_t outSize);
void ETA_HudNarrator_SpeakOpenings(int opened, int closed);

/*
 * Who and what is near you: players, and things on the ground.
 *
 * A sighted player sees an enemy step round a corner, a teammate lying
 * wounded, a weapon dropped on the floor. A tester heard their own
 * pickups and nothing of any of that, and asked for it to be said - in
 * front, left, right or behind, how far, and when it gets closer or
 * further away. The integration decides what the player could know -
 * an enemy only in clear sight, never through a wall - and hands over
 * this frame's list; this decides what of it is news:
 *
 *   - each kind has distance bands, and a thing is spoken when it first
 *     comes into range and again when it crosses into a nearer band.
 *     Enemies are also spoken moving away, a band at a time, and going
 *     out of sight; teammates only coming close. A band is left only
 *     past its edge plus a margin, so somebody pacing on a line does not
 *     flicker;
 *   - the one line said is the most important one waiting: an enemy
 *     first, then a wounded teammate, then the rest, nearest first.
 *     Several things of one kind arriving together are said as one line
 *     - "3 teammates, nearest ..." - rather than one each;
 *   - an enemy is said as soon as it appears, even over other speech -
 *     unless mayInterrupt is 0, which the integration passes while the
 *     player is busy with something whose words must not be cut off,
 *     such as a build being counted out. Then it waits like the rest.
 *     Everything else waits for the voice to be free (quietMs, how long
 *     it has been silent, from the integration) and for its own gap
 *     since the last line about the same thing.
 *
 * leftOfView is in degrees from the way the player faces, positive to
 * the left - the engine's own yaw sense. Returns 1, with the words in
 * out, when there is something to say.
 */
typedef enum
{
    ETA_AWARE_ENEMY,
    ETA_AWARE_WOUNDED,      /* a teammate down, waiting for a medic */
    ETA_AWARE_TEAMMATE,
    ETA_AWARE_ENEMY_DOWN,   /* an enemy wounded on the ground */
    ETA_AWARE_ITEM,         /* something on the ground to pick up */
    ETA_AWARE_BODY,         /* an enemy body with its uniform still on */
    ETA_AWARE_KINDS
} ETA_AwareKind;

typedef struct
{
    int           id;           /* the entity number: one per thing */
    ETA_AwareKind kind;
    float         meters;
    float         leftOfView;
    char          name[48];     /* a player's or an item's; may be empty */
} ETA_AwareThing;

#define ETA_AWARE_MAX            64
#define ETA_AWARE_LOST_MS        1500
#define ETA_AWARE_ENEMY_GAP_MS   700
#define ETA_AWARE_QUIET_MS       300

void        ETA_HudNarrator_ResetAwareness(void);
int         ETA_HudNarrator_UpdateAwareness(const ETA_AwareThing *things, int count,
                                            int nowMs, int quietMs, int mayInterrupt,
                                            char *out, size_t outSize);
float       ETA_HudNarrator_AwareRange(ETA_AwareKind kind);
const char *ETA_HudNarrator_RelativeDirection(float leftOfView);
void        ETA_HudNarrator_SpeakAwareness(const char *text);
/* What a teammate is called, for a game whose people are something else:
   ("Friend", "friends") in the campaign. NULL puts back "Teammate". */
void        ETA_HudNarrator_SetFriendWords(const char *noun, const char *plural);

/*
 * Whether there is sky overhead.
 *
 * Deliberately not called "indoors". A probe straight up can prove open
 * sky, because the engine flags the sky surface itself - but a ceiling
 * overhead might be a roof, a bridge, a tunnel or an awning, and calling
 * any of those "indoors" would be a guess dressed up as a fact. "Under
 * cover" is exactly what was measured.
 *
 * It also happens to be the more useful of the two: in this game an
 * airstrike or a mortar round needs open sky to arrive through, so
 * whether you have it over you is tactical information, not scenery.
 */
typedef enum ETA_Overhead
{
    ETA_OVERHEAD_UNKNOWN = 0,
    ETA_OVERHEAD_OPEN_SKY,
    ETA_OVERHEAD_COVERED
} ETA_Overhead;

const char *ETA_HudNarrator_OverheadName(ETA_Overhead overhead);
void ETA_HudNarrator_SpeakOverhead(ETA_Overhead overhead);

/*
 * Whether the player is leaning out from cover.
 *
 * Driven by what the lean actually did, never by the key: the engine
 * refuses to lean while moving, firing, prone or mounted, so a mod that
 * spoke on the keypress would announce a lean that never happened - at
 * precisely the moment the player is about to step out from cover on the
 * strength of it.
 */
typedef enum ETA_Lean
{
    ETA_LEAN_LEFT = 0,
    ETA_LEAN_UPRIGHT,
    ETA_LEAN_RIGHT
} ETA_Lean;

void ETA_HudNarrator_SpeakLean(ETA_Lean lean);

/*
 * Whether the ground ahead climbs or falls away in steps.
 *
 * This exists because of the fix that came before it. The obstacle
 * report used to call every stair riser a wall; the cure was to probe
 * with the player's own box lifted by the engine's step height, so
 * anything a player simply walks over stops being an obstacle. That was
 * right, and it left stairs completely silent - a sighted player sees a
 * staircase from across the room, and someone playing by ear now had
 * nothing at all.
 *
 * Four states rather than two because the difference matters when you
 * are deciding where to put your feet: one step is a thing you walk
 * over without thinking, a flight of them is a route to somewhere else.
 *
 * ETA_STAIRS_NONE is not spoken. Flat ground is the usual case, and a
 * mod that announced leaving every staircase - including sideways, or
 * by turning round - would be talking about nothing most of the time.
 */
typedef enum ETA_Stairs
{
    ETA_STAIRS_NONE = 0,
    ETA_STAIRS_STEP_UP,
    ETA_STAIRS_STEP_DOWN,
    ETA_STAIRS_UP,
    ETA_STAIRS_DOWN
} ETA_Stairs;

const char *ETA_HudNarrator_StairsName(ETA_Stairs stairs);
void ETA_HudNarrator_SpeakStairs(ETA_Stairs stairs);

/*
 * A ladder close by, said once as the player comes to it: which way it
 * goes, where it is and how far, and that the use key climbs it -
 * "Ladder down, ahead left, 2 meters. F climbs". direction is a phrase
 * from ETA_HudNarrator_RelativeDirection.
 */
void ETA_HudNarrator_LadderText(int goesUp, const char *direction, int meters,
                                char *out, size_t outSize);
void ETA_HudNarrator_SpeakLadder(int goesUp, const char *direction, int meters);

/*
 * How far above or below the player something is, as words to put after
 * its direction and distance - "4 meters above you". Empty within
 * ETA_HEIGHT_SAY_METERS of the player's own level, because a thing at
 * chest height or on the next stair is not "above" in any useful sense,
 * and saying so every time would bury the cases that matter: an
 * objective on a roof or an upper floor, which a player told only "ahead
 * left" walks straight into the wall underneath.
 */
#define ETA_HEIGHT_SAY_METERS 2.0f

void ETA_HudNarrator_HeightText(float heightMeters, char *out, size_t outSize);

/*
 * Whether the player is in the match or watching it. A sighted player
 * knows at a glance - the HUD, their own weapon in front of them, or a
 * "SPECTATING" banner and somebody else's view. Without them the two
 * sound the same: the keys still do something, the narrator still
 * talks, and nothing says the player is not actually in the game.
 */
typedef enum
{
    ETA_PLAY_UNKNOWN = 0,
    ETA_PLAY_SPECTATING,    /* on no team, watching */
    ETA_PLAY_IN_PLAY,       /* on a team, alive */
    ETA_PLAY_DOWN,          /* wounded: a medic can still revive */
    ETA_PLAY_LIMBO,         /* out of it until the next respawn */
    ETA_PLAY_MATCH_OVER
} ETA_PlayState;

/*
 * The words for a state: "Spectating, following Name", "In play,
 * Allies, Medic", "Down, a medic can revive you", "Waiting to respawn",
 * "Match over". team, playerClass and following may be NULL or empty,
 * and are only used where they mean something.
 */
void ETA_HudNarrator_PlayStateText(ETA_PlayState state, const char *team, const char *playerClass,
                                   const char *following, char *out, size_t outSize);
void ETA_HudNarrator_SpeakPlayState(ETA_PlayState state, const char *team, const char *playerClass,
                                    const char *following);

/*
 * What the game says the player can do with whatever is under their
 * crosshair right now.
 *
 * ET already answers this for everyone else, and answers it well: when
 * you are close enough to use something, an icon appears - pliers on a
 * construction, a stick of dynamite where one goes, a syringe over a
 * body that can still be revived. A sighted player reads it without
 * thinking, and it is how they know an objective is workable at all.
 *
 * An enum rather than a string because these words are the mod's, while
 * the icons are the engine's - and the two engines this mod builds
 * against do not even agree on the list of icons. ET: Legacy has struck
 * a dozen of them out as unused and renumbered nothing, leaving real
 * gaps in the enum; the 2010 tree still carries them all. Mapping each
 * engine's own hint onto these is the integration's job, and doing it
 * this way is what stops the same pliers icon being called two
 * different things in two builds of the same mod.
 *
 * The wording of the two the tester asked for is deliberate. "Pliers"
 * is said out loud rather than "construct" or "repair", because pliers
 * is what the icon is and what an ET player calls the tool; and the
 * plant and the defuse are told apart in the first two words, because
 * mistaking one for the other at an objective is a round.
 */
typedef enum ETA_Interaction
{
    ETA_INTERACT_NONE = 0,
    ETA_INTERACT_USABLE,
    ETA_INTERACT_NOT_USABLE,
    ETA_INTERACT_DOOR,
    ETA_INTERACT_DOOR_LOCKED,
    ETA_INTERACT_BUTTON,
    ETA_INTERACT_LADDER,
    ETA_INTERACT_WATER,
    ETA_INTERACT_MG42,
    ETA_INTERACT_TANK,
    ETA_INTERACT_BREAKABLE,
    ETA_INTERACT_NEEDS_DYNAMITE,
    ETA_INTERACT_BUILD,
    ETA_INTERACT_DISARM,
    ETA_INTERACT_PLANT_DYNAMITE,
    ETA_INTERACT_LANDMINE,
    ETA_INTERACT_SATCHEL,
    ETA_INTERACT_REVIVE,
    ETA_INTERACT_REVIVE_FIRST,
    ETA_INTERACT_HEALTH,
    ETA_INTERACT_AMMO,
    ETA_INTERACT_WEAPON,
    ETA_INTERACT_RESTRICTED,
    ETA_INTERACT_OBJECTIVE,
    ETA_INTERACT_UNIFORM,
    ETA_INTERACT_KNIFE,
    /* Wolfenstein signage, still drawn by the 2010 tree and still
       settable by a map. ET's own server code never raises any of
       these, so they are rare to the point of never - but a map that
       does raise one must not be met with silence, which is
       indistinguishable from nothing being there at all. */
    ETA_INTERACT_ALARM,
    ETA_INTERACT_TREASURE,
    ETA_INTERACT_CAUTION,
    ETA_INTERACT_DANGER,
    ETA_INTERACT_SECRET,
    ETA_INTERACT_NOTE,
    ETA_INTERACT_QUESTION,
    ETA_INTERACT_ATTENTION,
    ETA_INTERACT_ARMOUR,
    ETA_INTERACT_ITEM,
    /* Not an icon of its own: the game raises the defuse icon for the
       team's own dynamite too, which is there to be armed. The cgame
       tells the two apart by what lies under the crosshair. */
    ETA_INTERACT_ARM_DYNAMITE,
    ETA_INTERACT_COUNT
} ETA_Interaction;

const char *ETA_HudNarrator_InteractionName(ETA_Interaction what);

/*
 * percent < 0 means the HUD would show no progress bar beside the icon,
 * and nothing is said about one. When it is not negative it is the same
 * number the bar draws - how far a construction has got, how much is
 * left of a breakable - and it is the difference between "somebody is
 * already building this" and "nobody has started".
 */
void ETA_HudNarrator_SpeakInteraction(ETA_Interaction what, int percent);

/*
 * The same, with what the thing is put first: "Tank, usable". The game's
 * plainest icon says only that something can be used - the tester, in a
 * tank, heard "Usable" and had to guess what. The cgame names the thing
 * under the crosshair where it can; with no name (NULL or empty) this is
 * SpeakInteraction exactly. The text is built by NamedInteractionText,
 * which a test can read.
 */
void ETA_HudNarrator_NamedInteractionText(const char *thing, ETA_Interaction what, int percent,
                                          char *out, size_t outSize);
void ETA_HudNarrator_SpeakNamedInteraction(const char *thing, ETA_Interaction what, int percent);

/*
 * One square of the command map, as the survey cursor lands on it.
 *
 * The shape of the sentence is the whole design: *where* first, then
 * *what*, then *how to get there*. A player walking the grid hears the
 * square name on every step and can stop listening the moment it is one
 * they do not care about, which is what makes crossing an empty half of
 * the map bearable.
 *
 * contents is the integration's list of what is standing there, already
 * worded - "Axis command post, two teammates" - or NULL for an empty
 * square, which is said as such rather than skipped. Silence on a
 * keypress is indistinguishable from a key that did not register.
 *
 * distanceMeters < 0 leaves the distance out, and bearingDegrees < 0
 * leaves the direction out; both are omitted for the square the player
 * is standing in, where there is no distance to give and no direction
 * to face.
 *
 * The bearing is spoken twice over - as a compass point and as a number
 * - because they answer different questions. "North-east" is what you
 * turn to; "52 degrees" is what you hold. Both come from the same
 * conversion the compass narration uses, so they cannot contradict each
 * other or the heading the player is already being told.
 */
void ETA_HudNarrator_SpeakMapCell(const char *cellName, const char *contents,
                                  int distanceMeters, int bearingDegrees);

/*
 * That a step ran off the edge of the map, or off the end of the floors.
 * A player who cannot see the grid has no other way to learn its shape
 * than by walking into its sides.
 */
void ETA_HudNarrator_SpeakMapEdge(void);

/*
 * Which floor the survey is looking at, on a map built in layers.
 * Numbered from the ground up, as the engine stacks them.
 */
void ETA_HudNarrator_SpeakMapLayer(int layer, int layerCount);

/*
 * Holding the scenery quiet after the player has asked a question.
 *
 * Every backend delivers a new line by cutting off the one in progress,
 * so a report that arrives while another is being spoken destroys it.
 * Ordering the per-frame narration fixes that only *within* a frame -
 * and a player who presses the objectives key gets their answer on one
 * frame and the scenery report on the next, which is a collision no
 * ordering can prevent.
 *
 * A tester lost the objective distance to a wall report exactly that
 * way, twice, including while deliberately asking for it. So a report
 * the player asked for holds the passive narration off for a moment
 * afterwards. Asking a question and being talked over is worse than
 * missing a piece of scenery.
 *
 * ETA_HUD_HOLD_MS is long enough for the longest answer the mod gives -
 * the status key, which is health, weapon, ammo, objective, distance
 * and a turn - without being long enough to feel like the scenery has
 * stopped working.
 */
#define ETA_HUD_HOLD_MS 4000

void ETA_HudNarrator_HoldPassive(int nowMs);
void ETA_HudNarrator_ReleasePassive(void);

/*
 * Returns 1 while a passive report should stay quiet.
 *
 * Deliberately not consulted by the drop warning. The one thing allowed
 * to cut off an answer the player asked for is being told they are
 * about to walk off something that will kill them.
 */
int ETA_HudNarrator_PassiveHeld(int nowMs);

/*
 * Where an objective sits in the map's own running order, and whether
 * it is still to be done.
 *
 * A tester playing alone found the gap this fills: the mod was pointing
 * at the *nearest* objective, and a map's objectives have to be done in
 * sequence. Being sent to the closest one is being sent to whichever
 * happens to be nearby, which on most maps is the wrong one, and there
 * was no way to find that out except by wandering.
 *
 * The numbers are the engine's, not this mod's. ET's map scripts set an
 * objective's state with a numbered command per team, and the engine
 * documents the three values in its own error message: 0 default, 1
 * complete, 2 failed. These are those values, so the order spoken is
 * the order the map was written in.
 */
typedef enum
{
    ETA_OBJECTIVE_PENDING = 0,
    ETA_OBJECTIVE_COMPLETE,
    ETA_OBJECTIVE_FAILED
} ETA_ObjectiveState;

const char *ETA_HudNarrator_ObjectiveStateName(ETA_ObjectiveState state);

/*
 * "Objective 2 of 4: destroy the side wall."
 *
 * number counts from 1, as the map script numbers them and as a person
 * would say it. text may be NULL when the map supplied no description,
 * which happens, and then only the position and the state are spoken -
 * "objective 2 of 4" is still worth more than silence.
 */
void ETA_HudNarrator_SpeakObjectiveStep(int number, int total,
                                        ETA_ObjectiveState state,
                                        const char *text);

/*
 * That every objective is done. Said on its own because it is the one
 * moment in a map where there is nothing left to be pointed at, and
 * silence there reads as the narration having failed.
 */
void ETA_HudNarrator_SpeakObjectivesComplete(void);

/*
 * How a construction is coming along under the pliers.
 *
 * The tester built something and said afterwards that they had known to
 * keep holding the key only because they remembered the bar filling on
 * screen. That bar is already arriving - the game sends the
 * construction's progress as the value beside the cursor icon - and
 * nothing was saying it out loud once the work had started.
 *
 * Spoken on milestones rather than continuously, for the same reason
 * the objective distance is: a number that changes every frame is a
 * voice that never stops, and what the player needs is "it is going up,
 * keep holding" three or four times, not forty.
 *
 * Completion is announced, but never inferred from the progress figure.
 * The engine resets it to zero in the same frame it crosses the finish
 * line, so a value that has dropped away is indistinguishable from a
 * player who let go of the key - and "built!" announced over something
 * still half standing is exactly the kind of confident lie this mod
 * cannot afford.
 *
 * What the engine does provide is an explicit event, which an earlier
 * reading of this missed: finishing a task stamps lastTaskAchievedTime,
 * and for the next three quarters of a second the server sends the
 * client HINT_COMPLETED with a value of 255 - which is what fills the
 * on-screen bar to the top. That is the completion a sighted player
 * sees, so it is the one this speaks. The caller decides it happened;
 * this only says it.
 */
void ETA_HudNarrator_ResetBuildProgress(void);

/*
 * Feed it the percentage each frame while the player is building.
 * Returns 1 on the frame it spoke.
 */
int ETA_HudNarrator_UpdateBuildProgress(int percent);
void ETA_HudNarrator_SpeakBuildProgress(int percent);

/*
 * Say the construction is finished. Only ever called on the engine's own
 * completion event - see above.
 */
void ETA_HudNarrator_SpeakBuildComplete(void);

void ETA_HudNarrator_SpeakObjective(const char *objectiveText);
void ETA_HudNarrator_SpeakRespawn(int secondsRemaining);
void ETA_HudNarrator_Shutdown(void);

#ifdef __cplusplus
}
#endif

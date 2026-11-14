#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ETA_NavigationSystem_Init(void);
void ETA_NavigationSystem_AnnounceObjectiveDirection(int directionDegrees);
void ETA_NavigationSystem_AnnounceDistance(int distanceMeters);
void ETA_NavigationSystem_AnnounceRouteCorrection(const char *correctionText);
void ETA_NavigationSystem_ResetStuckDetection(void);
/*
 * Feeds the stuck detector one frame of movement. isTryingToMove is the
 * player's own movement input: without it, standing still would read as
 * being stuck, which in a shooter is the normal case.
 *
 * Returns 1 only on the frame the player is first judged stuck, so the
 * caller announces once. What to announce is the caller's decision -
 * this module has no way to know where the objective is.
 */
int ETA_NavigationSystem_UpdateMovement(float distanceMovedMeters, float elapsedSeconds, int isTryingToMove);
int ETA_NavigationSystem_IsStuck(void);

/*
 * Objective approach callouts.
 *
 * The on-demand report answers "how far is it" when asked. This answers
 * "am I getting there" without being asked, which is the question a
 * player actually has while walking - and the one that needs two
 * remembered numbers and a key press to answer otherwise.
 *
 * Feed it the current distance every frame. It speaks only when the
 * player crosses a milestone inward, so an approach costs a handful of
 * announcements rather than a running commentary, and it speaks the real
 * distance rather than the milestone: the milestone decides *when*, never
 * *what*, so the number said is never a rounded-off fiction.
 *
 * A milestone re-arms once the player is back well outside it, so leaving
 * and returning is announced again, while pacing around its edge is not.
 *
 * Returns 1 when something was said. Reset when the target changes -
 * distance to a different objective is not progress toward this one.
 */
void ETA_NavigationSystem_ResetApproach(void);
int ETA_NavigationSystem_UpdateApproach(int distanceMeters);

/* "Objective is 4 meters above you" - said with the distance when the
   objective is a floor or more up or down; nothing within a stair's
   height of the player's level. */
void ETA_NavigationSystem_AnnounceHeight(float heightMeters);

/*
 * The same callouts toward a marker the player put down themselves.
 *
 * A sighted player can decide to go somewhere - that building, the far
 * side of the bridge - and head for it, because they can see it. The
 * marker is how a blind player makes that decision: they pick a square
 * on the command map, or mark where they stand to come back to it, and
 * these say how the walk is going.
 *
 * Kept apart from the objective's milestones, so walking toward one never
 * spends the other's.
 *
 * Start is called when the marker goes down. It spends, without speaking,
 * the milestones the player is already inside, because the distance was
 * just said as the marker was placed. Update then speaks only on crossing
 * one inward, in the same words the objective uses but naming the marker:
 * "30 meters to marker". Arrival is the caller's to judge - it knows
 * whether the marker is a square or a spot.
 */
void ETA_NavigationSystem_AnnounceMarkerDistance(int distanceMeters);
/* "Marker is 4 meters above you": the marker's own place, in its own
   name - a marker on a room or a sniper spot is not the objective. */
void ETA_NavigationSystem_AnnounceMarkerHeight(float heightMeters);
void ETA_NavigationSystem_StartMarkerApproach(int distanceMeters);
int ETA_NavigationSystem_UpdateMarkerApproach(int distanceMeters);

/*
 * A walkable way to somewhere, around the walls.
 *
 * A sound placed straight toward a destination leads a player who cannot
 * see into the nearest wall between them and it - which is what a tester
 * reported of the marker's ping. A sighted player walks to the doorway
 * first without thinking about it. This finds the doorway.
 *
 * It is an A* search over a grid of squares on the ground. It knows
 * nothing about maps: the caller supplies one question, "can a player
 * walk from here to there, and at what height do they land", and the
 * engine answers that with its own collision. So the search is the
 * same code on every map and in the tests, where the question is
 * answered from a drawn plan instead.
 *
 * The search is spread over frames: Begin sets it up, Step does a
 * bounded amount of work and says whether it has finished. When the
 * node pool runs out before the goal is reached, the result is the way
 * to the square that got closest - still the right first turn, and the
 * search is run again from further along.
 *
 * Squares are keyed by their height band as well as their position, so
 * two floors over one another are different places.
 *
 * Not every way up is a walk. A ledge is jumped onto, and a floor above
 * is often reached only by a ladder - the Oasis command post stands on
 * one, and a player led straight at it walks into the wall underneath.
 * So the question's answer says how the square is reached, and ladders,
 * which join two places a whole floor apart, are handed to the search
 * as links: from the foot to the top and back. Each point of the way
 * found says how it is reached, so the caller can say "jump" or lead to
 * the ladder's foot at the right moment.
 */
typedef enum ETA_PathKind
{
    ETA_PATH_NONE = 0,     /* no way from here to there */
    ETA_PATH_WALK,
    ETA_PATH_JUMP,         /* onto or over something too high to step */
    ETA_PATH_LADDER_UP,
    ETA_PATH_LADDER_DOWN,
    ETA_PATH_CROUCH        /* under a ceiling too low to stand: a tunnel */
} ETA_PathKind;

/* Returns how a player gets from one square to the next, ETA_PATH_NONE
   when they cannot, and sets to[2] to the height they land at. */
typedef int (*ETA_PathMoveFn)(void *context, const float from[3], float to[3]);

#define ETA_PATH_MAX_NODES   16384
#define ETA_PATH_MAX_POINTS  512
#define ETA_PATH_MAX_LINKS   256

typedef enum ETA_PathState
{
    ETA_PATH_IDLE = 0,
    ETA_PATH_SEARCHING,
    ETA_PATH_FOUND,     /* reaches the goal */
    ETA_PATH_PARTIAL,   /* reaches the square nearest it */
    ETA_PATH_FAILED     /* nowhere to go at all */
} ETA_PathState;

/* flatGoal: the goal has no height of its own (a map square), so any
   floor counts as arriving. */
void ETA_PathFinder_Begin(const float start[3], const float goal[3],
                          float cellSize, float goalRadius, int flatGoal);
/*
 * The nearest place of a kind, rather than a place: the way out of a
 * building, to anywhere under the open sky. The search spreads nearest
 * first and stops at the first square isGoal says yes to. With no such
 * square in reach it fails; there is no "nearest" to a kind of place.
 */
typedef int (*ETA_PathGoalFn)(void *context, const float at[3]);
void ETA_PathFinder_BeginSearch(const float start[3], float cellSize, ETA_PathGoalFn isGoal, void *goalContext);
ETA_PathState ETA_PathFinder_Step(int budget, ETA_PathMoveFn move, void *context);
ETA_PathState ETA_PathFinder_State(void);
int  ETA_PathFinder_PointCount(void);
void ETA_PathFinder_Point(int index, float out[3]);
/* How the point is reached from the one before it; the first point,
   where the way starts, is ETA_PATH_WALK. */
ETA_PathKind ETA_PathFinder_PointKind(int index);
void ETA_PathFinder_Reset(void);

/*
 * A way between two places the squares do not join - a ladder's foot
 * and its top. A square within reach of from leads to to. Links stay
 * until cleared, across searches: they belong to the map, not to one
 * walk. Returns 0 when there is no room for another.
 */
int  ETA_PathFinder_AddLink(const float from[3], const float to[3], ETA_PathKind kind);
void ETA_PathFinder_ClearLinks(void);
int  ETA_PathFinder_LinkCount(void);

void ETA_NavigationSystem_Shutdown(void);

#ifdef __cplusplus
}
#endif

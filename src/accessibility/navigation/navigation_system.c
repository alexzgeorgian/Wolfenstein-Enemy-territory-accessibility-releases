#include "navigation_system.h"
#include "../hud/hud_narrator.h"
#include "../audio/audio_cue_system.h"
#include "../core/event_router.h"
#include "../core/runtime_guard.h"

#include <stdio.h>

#define ETA_NAV_MAX_DISTANCE_METERS 100000

/*
 * How little ground counts as no progress, and over how long.
 *
 * Measured across the whole window rather than per frame. The first
 * version compared a single frame's movement against a fixed distance,
 * which is really a speed test with the frame rate as its hidden units:
 * at 125fps, 0.05m per frame is 6.25m/s, so walking, crouching and
 * crawling all registered as not moving. Accumulating over the window
 * asks the question that was meant - has this player got anywhere - and
 * gives the same answer at any frame rate.
 *
 * One metre in three seconds is slower than crawling prone. It is a
 * judgment call, not a value found in the engine, but it is a floor
 * rather than a guess at normal speed: anything actually moving clears
 * it comfortably.
 */
/*
 * Objective approach milestones, in metres, nearest last.
 *
 * Chosen for how a player actually uses them rather than for even
 * spacing: 100 is "it is over there", 50 is "commit", 25 is "expect
 * contact", 10 is "you are on it". They tighten as they matter more.
 * Four callouts is the whole cost of an approach.
 */
static const int gApproachMilestones[] = { 100, 50, 25, 10 };

#define ETA_NAV_APPROACH_COUNT ((int)(sizeof(gApproachMilestones) / sizeof(gApproachMilestones[0])))

/*
 * How far back outside a milestone the player must get before it will
 * speak again. Without it, drifting across a milestone's edge - which is
 * exactly what happens in a firefight near an objective - would announce
 * on every crossing.
 */
#define ETA_NAV_APPROACH_REARM_SCALE 1.25f

/*
 * One per target the player can be walking toward. The objective and the
 * player's own marker keep separate milestones: walking toward one is not
 * progress toward the other, and sharing them would let an objective
 * callout spend the marker's.
 */
typedef struct
{
    int announced[ETA_NAV_APPROACH_COUNT];
} ETA_Approach;

static ETA_Approach gObjectiveApproach;
static ETA_Approach gMarkerApproach;

#define ETA_NAV_STUCK_PROGRESS_METERS 1.0f
#define ETA_NAV_STUCK_TIME_THRESHOLD_SECONDS 3.0f

static float gWindowSeconds = 0.0f;
static float gWindowDistance = 0.0f;
static int gIsStuck = 0;

static void ETA_NavigationSystem_EmitMessage(const char *source, const char *message)
{
    ETA_Event event;

    event.type = ETA_EVENT_NAVIGATION;
    event.source = source;
    event.message = message;

    ETA_EventRouter_Emit(event);
}

void ETA_NavigationSystem_Init(void)
{
    gWindowSeconds = 0.0f;
    gWindowDistance = 0.0f;
    gIsStuck = 0;
}

void ETA_NavigationSystem_AnnounceObjectiveDirection(int directionDegrees)
{
    ETA_AudioCueSystem_PlayObjectiveDirectionCue(directionDegrees);
}

void ETA_NavigationSystem_AnnounceDistance(int distanceMeters)
{
    static char buffer[64];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(distanceMeters, 0, ETA_NAV_MAX_DISTANCE_METERS, "navigation_system.AnnounceDistance")))
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "%d meters to objective", distanceMeters);

    ETA_NavigationSystem_EmitMessage("distance", buffer);
}

void ETA_NavigationSystem_AnnounceRouteCorrection(const char *correctionText)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckString(correctionText, ETA_MAX_NAVIGATION_TEXT_LENGTH, "navigation_system.AnnounceRouteCorrection")))
    {
        return;
    }

    ETA_NavigationSystem_EmitMessage("route_correction", correctionText);
}

void ETA_NavigationSystem_ResetStuckDetection(void)
{
    gWindowSeconds = 0.0f;
    gWindowDistance = 0.0f;
    gIsStuck = 0;
}

int ETA_NavigationSystem_UpdateMovement(float distanceMovedMeters, float elapsedSeconds, int isTryingToMove)
{
    if (elapsedSeconds <= 0.0f)
    {
        return 0;
    }

    /*
     * Standing still is not being stuck.
     *
     * This is what made the old detector fire at random: it only asked
     * whether the player had moved, and in a shooter not moving is
     * ordinary - aiming, covering a doorway, listening, waiting for a
     * spawn wave. Being stuck is wanting to move and not moving, so the
     * player's own input decides whether the question is even asked.
     */
    if (!isTryingToMove)
    {
        gWindowSeconds = 0.0f;
        gWindowDistance = 0.0f;
        gIsStuck = 0;
        return 0;
    }

    gWindowSeconds += elapsedSeconds;
    gWindowDistance += distanceMovedMeters;

    if (gWindowSeconds < ETA_NAV_STUCK_TIME_THRESHOLD_SECONDS)
    {
        return 0;
    }

    if (gWindowDistance >= ETA_NAV_STUCK_PROGRESS_METERS)
    {
        /* Moving. Start a fresh window and drop any earlier latch. */
        gWindowSeconds = 0.0f;
        gWindowDistance = 0.0f;
        gIsStuck = 0;
        return 0;
    }

    gWindowSeconds = 0.0f;
    gWindowDistance = 0.0f;

    if (gIsStuck)
    {
        /* Already reported. Staying stuck is not news, and repeating it
           every few seconds would be worse than saying nothing. */
        return 0;
    }

    gIsStuck = 1;

    /*
     * Returns rather than speaks. What is useful at this moment is which
     * way the objective is and how far, and only the engine knows that -
     * so the caller is told once, and decides what to say.
     */
    return 1;
}

int ETA_NavigationSystem_IsStuck(void)
{
    return gIsStuck;
}

static void ETA_Approach_Reset(ETA_Approach *approach)
{
    int i;

    for (i = 0; i < ETA_NAV_APPROACH_COUNT; i++)
    {
        approach->announced[i] = 0;
    }
}

/*
 * Returns the index of the tightest milestone crossed inward on this
 * update, or -1 when none was.
 */
static int ETA_Approach_Update(ETA_Approach *approach, int distanceMeters)
{
    int i;
    int crossed = -1;

    /* Re-arm before testing, so a player who left and came back is told
       again on the same frame they cross back in. */
    for (i = 0; i < ETA_NAV_APPROACH_COUNT; i++)
    {
        if ((float)distanceMeters > (float)gApproachMilestones[i] * ETA_NAV_APPROACH_REARM_SCALE)
        {
            approach->announced[i] = 0;
        }
    }

    /* Milestones run outermost first, so the last one crossed is the
       tightest - a player who arrives inside several at once (a spawn, a
       new objective) hears where they stand, once, not a countdown. */
    for (i = 0; i < ETA_NAV_APPROACH_COUNT; i++)
    {
        if (distanceMeters <= gApproachMilestones[i] && !approach->announced[i])
        {
            approach->announced[i] = 1;
            crossed = i;
        }
    }

    return crossed;
}

void ETA_NavigationSystem_ResetApproach(void)
{
    ETA_Approach_Reset(&gObjectiveApproach);
}

int ETA_NavigationSystem_UpdateApproach(int distanceMeters)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(distanceMeters, 0, ETA_NAV_MAX_DISTANCE_METERS, "navigation_system.UpdateApproach")))
    {
        return 0;
    }

    if (ETA_Approach_Update(&gObjectiveApproach, distanceMeters) < 0)
    {
        return 0;
    }

    /* The real distance, not the milestone: the milestone decided when to
       speak and has no business deciding what is true. */
    ETA_NavigationSystem_AnnounceDistance(distanceMeters);

    return 1;
}

void ETA_NavigationSystem_AnnounceHeight(float heightMeters)
{
    static char buffer[64];
    char        height[48];

    ETA_HudNarrator_HeightText(heightMeters, height, sizeof(height));

    if (!height[0])
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "Objective is %s", height);
    ETA_NavigationSystem_EmitMessage("height", buffer);
}

void ETA_NavigationSystem_AnnounceMarkerHeight(float heightMeters)
{
    static char buffer[64];
    char        height[48];

    ETA_HudNarrator_HeightText(heightMeters, height, sizeof(height));

    if (!height[0])
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "Marker is %s", height);
    ETA_NavigationSystem_EmitMessage("marker_height", buffer);
}

void ETA_NavigationSystem_AnnounceMarkerDistance(int distanceMeters)
{
    static char buffer[64];

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(distanceMeters, 0, ETA_NAV_MAX_DISTANCE_METERS, "navigation_system.AnnounceMarkerDistance")))
    {
        return;
    }

    snprintf(buffer, sizeof(buffer), "%d meters to marker", distanceMeters);
    ETA_NavigationSystem_EmitMessage("marker_distance", buffer);
}

void ETA_NavigationSystem_StartMarkerApproach(int distanceMeters)
{
    ETA_Approach_Reset(&gMarkerApproach);

    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(distanceMeters, 0, ETA_NAV_MAX_DISTANCE_METERS, "navigation_system.StartMarkerApproach")))
    {
        return;
    }

    /* Spend, silently, every milestone the player is already inside. The
       distance was just spoken as the marker went down, and saying it
       again on the next frame would be the same number twice. */
    (void)ETA_Approach_Update(&gMarkerApproach, distanceMeters);
}

int ETA_NavigationSystem_UpdateMarkerApproach(int distanceMeters)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckIntRange(distanceMeters, 0, ETA_NAV_MAX_DISTANCE_METERS, "navigation_system.UpdateMarkerApproach")))
    {
        return 0;
    }

    if (ETA_Approach_Update(&gMarkerApproach, distanceMeters) < 0)
    {
        return 0;
    }

    ETA_NavigationSystem_AnnounceMarkerDistance(distanceMeters);

    return 1;
}

void ETA_NavigationSystem_Shutdown(void)
{
    gWindowSeconds = 0.0f;
    gWindowDistance = 0.0f;
    gIsStuck = 0;
}

/* ---------------------------------------------------------------------
 * The way around the walls. See navigation_system.h.
 * ------------------------------------------------------------------ */

/* Kept free of the maths library, which the library does not link: the
   few things needed here are written out. */
static float ETA_Path_Abs(float v)
{
    return v < 0.0f ? -v : v;
}

static int ETA_Path_Floor(float v)
{
    int i = (int)v;

    return (v < 0.0f && (float)i != v) ? i - 1 : i;
}

/* Heights further apart than this are different floors, not a slope. */
#define ETA_PATH_LAYER_HEIGHT 64.0f

/* A little greedy: it finds a good way sooner and rarely a much worse
   one, and the search has a frame budget to live within. */
#define ETA_PATH_HEURISTIC_WEIGHT 1.5f

#define ETA_PATH_HASH_SIZE 32768

/* A jump or a climb costs as much as walking four more squares, two
   metres: for a player who cannot see the edge, stairs a little out of
   the way are the better way up, and a missed jump is a fall. */
#define ETA_PATH_EFFORT_SQUARES 4.0f

typedef struct
{
    float pos[3];
    int   ix, iy, iz;
    float g, f, h;
    int   parent;
    int   heapIndex;   /* -1 when not in the open list */
    int   closed;
    int   via;         /* ETA_PathKind: how this square was reached */
} ETA_PathNode;

typedef struct
{
    float        from[3];
    float        to[3];
    ETA_PathKind kind;
} ETA_PathLink;

static ETA_PathNode  gPathNodes[ETA_PATH_MAX_NODES];
static int           gPathNodeCount;
static int           gPathHash[ETA_PATH_HASH_SIZE];
static int           gPathHeap[ETA_PATH_MAX_NODES];
static int           gPathHeapCount;
static float         gPathGoal[3];
static float         gPathCell;
static float         gPathGoalRadius;
static int           gPathFlatGoal;
static ETA_PathGoalFn gPathGoalFn;      /* a search for a kind of place, not a point */
static void         *gPathGoalContext;
static float         gPathOrigin[3];
static int           gPathBest;        /* the node nearest the goal so far */
static int           gPathEnd;         /* where the finished path ends */
static ETA_PathState gPathState = ETA_PATH_IDLE;
static float         gPathPoints[ETA_PATH_MAX_POINTS][3];
static ETA_PathKind  gPathPointKinds[ETA_PATH_MAX_POINTS];
static int           gPathPointCount;
static ETA_PathLink  gPathLinks[ETA_PATH_MAX_LINKS];
static int           gPathLinkCount;

/* The length of the shortest walk on an eight-way grid, which is what
   the search can actually do - and needs no square root. */
static float ETA_Path_FlatDistance(const float a[3], const float b[3])
{
    float dx = ETA_Path_Abs(a[0] - b[0]);
    float dy = ETA_Path_Abs(a[1] - b[1]);

    return dx > dy ? dx + 0.41421356f * dy : dy + 0.41421356f * dx;
}

static float ETA_Path_Heuristic(const float pos[3])
{
    float h;

    /* Looking for a kind of place, nobody knows where: nearest first. */
    if (gPathGoalFn)
    {
        return 0.0f;
    }

    h = ETA_Path_FlatDistance(pos, gPathGoal);

    if (!gPathFlatGoal)
    {
        h += ETA_Path_Abs(pos[2] - gPathGoal[2]);
    }

    return h;
}

static unsigned ETA_Path_HashKey(int ix, int iy, int iz)
{
    unsigned h = (unsigned)ix * 73856093u ^ (unsigned)iy * 19349663u ^ (unsigned)iz * 83492791u;

    return h & (ETA_PATH_HASH_SIZE - 1);
}

static int ETA_Path_Find(int ix, int iy, int iz)
{
    unsigned slot = ETA_Path_HashKey(ix, iy, iz);

    while (gPathHash[slot] >= 0)
    {
        const ETA_PathNode *n = &gPathNodes[gPathHash[slot]];

        if (n->ix == ix && n->iy == iy && n->iz == iz)
        {
            return gPathHash[slot];
        }

        slot = (slot + 1) & (ETA_PATH_HASH_SIZE - 1);
    }

    return -1;
}

static void ETA_Path_Insert(int index)
{
    const ETA_PathNode *n    = &gPathNodes[index];
    unsigned            slot = ETA_Path_HashKey(n->ix, n->iy, n->iz);

    while (gPathHash[slot] >= 0)
    {
        slot = (slot + 1) & (ETA_PATH_HASH_SIZE - 1);
    }

    gPathHash[slot] = index;
}

static void ETA_Path_HeapSwap(int a, int b)
{
    int t = gPathHeap[a];

    gPathHeap[a] = gPathHeap[b];
    gPathHeap[b] = t;
    gPathNodes[gPathHeap[a]].heapIndex = a;
    gPathNodes[gPathHeap[b]].heapIndex = b;
}

static void ETA_Path_HeapUp(int i)
{
    while (i > 0)
    {
        int parent = (i - 1) / 2;

        if (gPathNodes[gPathHeap[parent]].f <= gPathNodes[gPathHeap[i]].f)
        {
            break;
        }

        ETA_Path_HeapSwap(i, parent);
        i = parent;
    }
}

static void ETA_Path_HeapDown(int i)
{
    for (;;)
    {
        int left     = 2 * i + 1;
        int right    = left + 1;
        int smallest = i;

        if (left < gPathHeapCount && gPathNodes[gPathHeap[left]].f < gPathNodes[gPathHeap[smallest]].f)
        {
            smallest = left;
        }

        if (right < gPathHeapCount && gPathNodes[gPathHeap[right]].f < gPathNodes[gPathHeap[smallest]].f)
        {
            smallest = right;
        }

        if (smallest == i)
        {
            return;
        }

        ETA_Path_HeapSwap(i, smallest);
        i = smallest;
    }
}

static void ETA_Path_HeapPush(int index)
{
    gPathHeap[gPathHeapCount]      = index;
    gPathNodes[index].heapIndex    = gPathHeapCount;
    gPathHeapCount++;
    ETA_Path_HeapUp(gPathHeapCount - 1);
}

static int ETA_Path_HeapPop(void)
{
    int top = gPathHeap[0];

    gPathHeapCount--;

    if (gPathHeapCount > 0)
    {
        gPathHeap[0]                       = gPathHeap[gPathHeapCount];
        gPathNodes[gPathHeap[0]].heapIndex = 0;
        ETA_Path_HeapDown(0);
    }

    gPathNodes[top].heapIndex = -1;

    return top;
}

static int ETA_Path_NewNode(const float pos[3], int ix, int iy, int iz)
{
    ETA_PathNode *n;

    if (gPathNodeCount >= ETA_PATH_MAX_NODES)
    {
        return -1;
    }

    n            = &gPathNodes[gPathNodeCount];
    n->pos[0]    = pos[0];
    n->pos[1]    = pos[1];
    n->pos[2]    = pos[2];
    n->ix        = ix;
    n->iy        = iy;
    n->iz        = iz;
    n->g         = 0.0f;
    n->h         = ETA_Path_Heuristic(pos);
    n->f         = 0.0f;
    n->parent    = -1;
    n->heapIndex = -1;
    n->closed    = 0;
    n->via       = ETA_PATH_WALK;

    ETA_Path_Insert(gPathNodeCount);

    return gPathNodeCount++;
}

static int ETA_Path_Layer(float z)
{
    return ETA_Path_Floor((z - gPathOrigin[2]) / ETA_PATH_LAYER_HEIGHT + 0.5f);
}

static int ETA_Path_AtGoal(const float pos[3])
{
    if (gPathGoalFn)
    {
        return gPathGoalFn(gPathGoalContext, pos);
    }

    if (ETA_Path_FlatDistance(pos, gPathGoal) > gPathGoalRadius)
    {
        return 0;
    }

    return gPathFlatGoal || ETA_Path_Abs(pos[2] - gPathGoal[2]) <= ETA_PATH_LAYER_HEIGHT;
}

static void ETA_Path_Build(int end)
{
    int count = 0;
    int i;

    for (i = end; i >= 0 && count < ETA_PATH_MAX_POINTS; i = gPathNodes[i].parent)
    {
        count++;
    }

    gPathPointCount = count;

    for (i = end; i >= 0 && count > 0; i = gPathNodes[i].parent)
    {
        count--;
        gPathPoints[count][0] = gPathNodes[i].pos[0];
        gPathPoints[count][1] = gPathNodes[i].pos[1];
        gPathPoints[count][2] = gPathNodes[i].pos[2];
        gPathPointKinds[count] = (ETA_PathKind)gPathNodes[i].via;
    }

    if (gPathPointCount > 0)
    {
        gPathPointKinds[0] = ETA_PATH_WALK;
    }

    gPathEnd = end;
}

/*
 * Offers the square at to, reached from current by the given kind of
 * move over the given flat distance. Returns 0 when the node pool is
 * full, having finished the search with the best way so far.
 */
static int ETA_Path_Reach(int current, const float to[3], int ix, int iy,
                          float flat, ETA_PathKind kind)
{
    float cost, g;
    int   iz, next;

    iz   = ETA_Path_Layer(to[2]);
    cost = flat + ETA_Path_Abs(to[2] - gPathNodes[current].pos[2]);
    if (kind == ETA_PATH_CROUCH)
    {
        /* Crouched, a player goes at about half the pace. */
        cost += flat;
    }
    else if (kind != ETA_PATH_WALK)
    {
        cost += ETA_PATH_EFFORT_SQUARES * gPathCell;
    }
    g = gPathNodes[current].g + cost;

    next = ETA_Path_Find(ix, iy, iz);

    if (next < 0)
    {
        next = ETA_Path_NewNode(to, ix, iy, iz);

        if (next < 0)
        {
            /* Out of room: the way to the nearest square so far is the
               answer, and the caller searches again from further along. */
            ETA_Path_Build(gPathBest);
            gPathState = gPathBest == 0 ? ETA_PATH_FAILED : ETA_PATH_PARTIAL;
            return 0;
        }
    }
    else if (gPathNodes[next].closed || g >= gPathNodes[next].g)
    {
        return 1;
    }

    gPathNodes[next].g      = g;
    gPathNodes[next].f      = g + gPathNodes[next].h * ETA_PATH_HEURISTIC_WEIGHT;
    gPathNodes[next].parent = current;
    gPathNodes[next].via    = kind;

    if (gPathNodes[next].heapIndex < 0)
    {
        ETA_Path_HeapPush(next);
    }
    else
    {
        ETA_Path_HeapUp(gPathNodes[next].heapIndex);
    }

    return 1;
}

int ETA_PathFinder_AddLink(const float from[3], const float to[3], ETA_PathKind kind)
{
    int i;

    if (!from || !to || gPathLinkCount >= ETA_PATH_MAX_LINKS
        || kind <= ETA_PATH_NONE || kind > ETA_PATH_LADDER_DOWN)
    {
        return 0;
    }

    for (i = 0; i < 3; i++)
    {
        gPathLinks[gPathLinkCount].from[i] = from[i];
        gPathLinks[gPathLinkCount].to[i]   = to[i];
    }
    gPathLinks[gPathLinkCount].kind = kind;
    gPathLinkCount++;
    return 1;
}

void ETA_PathFinder_ClearLinks(void)
{
    gPathLinkCount = 0;
}

int ETA_PathFinder_LinkCount(void)
{
    return gPathLinkCount;
}

ETA_PathKind ETA_PathFinder_PointKind(int index)
{
    if (index < 0 || index >= gPathPointCount)
    {
        return ETA_PATH_NONE;
    }

    return gPathPointKinds[index];
}

void ETA_PathFinder_Reset(void)
{
    gPathState      = ETA_PATH_IDLE;
    gPathNodeCount  = 0;
    gPathHeapCount  = 0;
    gPathPointCount = 0;
}

void ETA_PathFinder_Begin(const float start[3], const float goal[3],
                          float cellSize, float goalRadius, int flatGoal)
{
    int i, first;

    ETA_PathFinder_Reset();
    gPathGoalFn      = NULL;
    gPathGoalContext = NULL;

    if (!start || !goal || cellSize <= 0.0f)
    {
        gPathState = ETA_PATH_FAILED;
        return;
    }

    for (i = 0; i < ETA_PATH_HASH_SIZE; i++)
    {
        gPathHash[i] = -1;
    }

    for (i = 0; i < 3; i++)
    {
        gPathGoal[i]   = goal[i];
        gPathOrigin[i] = start[i];
    }

    gPathCell       = cellSize;
    /* Never tighter than three quarters of a square: the squares are laid
       out from where the player stands, so the goal can fall between
       them, and a radius no square reaches would search the whole map. */
    gPathGoalRadius = goalRadius > cellSize * 0.75f ? goalRadius : cellSize * 0.75f;
    gPathFlatGoal   = flatGoal;

    first                   = ETA_Path_NewNode(start, 0, 0, 0);
    gPathNodes[first].f     = gPathNodes[first].h * ETA_PATH_HEURISTIC_WEIGHT;
    gPathBest               = first;
    ETA_Path_HeapPush(first);

    gPathState = ETA_PATH_SEARCHING;
}

void ETA_PathFinder_BeginSearch(const float start[3], float cellSize, ETA_PathGoalFn isGoal, void *goalContext)
{
    if (!isGoal)
    {
        ETA_PathFinder_Reset();
        gPathState = ETA_PATH_FAILED;
        return;
    }

    /* The goal point is only a placeholder: the heuristic is nought and
       arriving is the question's to answer. */
    ETA_PathFinder_Begin(start, start, cellSize, 0.0f, 1);
    gPathGoalFn      = isGoal;
    gPathGoalContext = goalContext;
}

ETA_PathState ETA_PathFinder_Step(int budget, ETA_PathMoveFn move, void *context)
{
    static const int steps[8][2] =
    {
        { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 },
        { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 }
    };

    if (gPathState != ETA_PATH_SEARCHING || !move)
    {
        return gPathState;
    }

    while (budget-- > 0)
    {
        int current, d;

        if (gPathHeapCount == 0)
        {
            /* Everywhere reachable has been tried. The nearest square is
               still where the way goes, unless it is where we started. */
            ETA_Path_Build(gPathBest);
            gPathState = gPathBest == 0 ? ETA_PATH_FAILED : ETA_PATH_PARTIAL;
            return gPathState;
        }

        current                     = ETA_Path_HeapPop();
        gPathNodes[current].closed  = 1;

        if (ETA_Path_AtGoal(gPathNodes[current].pos))
        {
            ETA_Path_Build(current);
            gPathState = ETA_PATH_FOUND;
            return gPathState;
        }

        if (gPathNodes[current].h < gPathNodes[gPathBest].h)
        {
            gPathBest = current;
        }

        for (d = 0; d < 8; d++)
        {
            float to[3];
            int   ix, iy, kind;

            ix    = gPathNodes[current].ix + steps[d][0];
            iy    = gPathNodes[current].iy + steps[d][1];
            to[0] = gPathOrigin[0] + (float)ix * gPathCell;
            to[1] = gPathOrigin[1] + (float)iy * gPathCell;
            to[2] = gPathNodes[current].pos[2];

            kind = move(context, gPathNodes[current].pos, to);

            if (kind <= ETA_PATH_NONE || kind > ETA_PATH_CROUCH)
            {
                continue;
            }

            if (!ETA_Path_Reach(current, to, ix, iy,
                                (steps[d][0] && steps[d][1]) ? 1.41421356f * gPathCell : gPathCell,
                                (ETA_PathKind)kind))
            {
                return gPathState;
            }
        }

        /* A ladder whose foot (or top) is at this square. */
        for (d = 0; d < gPathLinkCount; d++)
        {
            const ETA_PathLink *link = &gPathLinks[d];
            const float        *here = gPathNodes[current].pos;
            float               dx   = ETA_Path_Abs(link->from[0] - here[0]);
            float               dy   = ETA_Path_Abs(link->from[1] - here[1]);

            if (dx > gPathCell * 0.75f || dy > gPathCell * 0.75f
                || ETA_Path_Abs(link->from[2] - here[2]) > ETA_PATH_LAYER_HEIGHT * 0.75f)
            {
                continue;
            }

            if (!ETA_Path_Reach(current, link->to,
                                ETA_Path_Floor((link->to[0] - gPathOrigin[0]) / gPathCell + 0.5f),
                                ETA_Path_Floor((link->to[1] - gPathOrigin[1]) / gPathCell + 0.5f),
                                ETA_Path_FlatDistance(here, link->to), link->kind))
            {
                return gPathState;
            }
        }
    }

    return gPathState;
}

ETA_PathState ETA_PathFinder_State(void)
{
    return gPathState;
}

int ETA_PathFinder_PointCount(void)
{
    return (gPathState == ETA_PATH_FOUND || gPathState == ETA_PATH_PARTIAL) ? gPathPointCount : 0;
}

void ETA_PathFinder_Point(int index, float out[3])
{
    if (!out)
    {
        return;
    }

    if (index < 0 || index >= ETA_PathFinder_PointCount())
    {
        out[0] = out[1] = out[2] = 0.0f;
        return;
    }

    out[0] = gPathPoints[index][0];
    out[1] = gPathPoints[index][1];
    out[2] = gPathPoints[index][2];
}

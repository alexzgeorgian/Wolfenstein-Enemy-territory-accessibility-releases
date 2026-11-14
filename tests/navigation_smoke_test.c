#include "core/accessibility_runtime.h"
#include "core/error_handler.h"
#include "navigation/navigation_system.h"
#include "smoke_check.h"

#include <stdlib.h>
#include <string.h>

static char *HeapCopy(const char *text)
{
    char *copy = (char *)malloc(strlen(text) + 1);

    strcpy(copy, text);

    return copy;
}

/* Announces a bearing and reports whether the range guard rejected it. */
static int BearingRejected(int directionDegrees)
{
    ETA_ErrorHandler_Clear();
    ETA_NavigationSystem_AnnounceObjectiveDirection(directionDegrees);

    if (!ETA_ErrorHandler_HasError())
    {
        return 0;
    }

    CHECK(ETA_ErrorHandler_GetLastError().code == ETA_ERROR_INVALID_VALUE);
    ETA_ErrorHandler_Clear();

    return 1;
}


/* ---- The way around the walls, on drawn plans --------------------------
 *
 * Each plan is a grid of squares 64 units across: '#' is a wall, anything
 * else is floor, 'S' is where the player starts and 'G' the goal. The
 * move question is answered from the drawing, the way the game answers it
 * from its collision - including not cutting a corner, which a player's
 * body cannot do either.
 */
#define PLAN_CELL 64.0f

typedef struct
{
    const char *const *rows;
    int               width, height;
    int               calls;
} Plan;

static int PlanFree(const Plan *plan, int col, int row)
{
    if (col < 0 || row < 0 || col >= plan->width || row >= plan->height)
    {
        return 0;
    }

    return plan->rows[row][col] != '#';
}

static int PlanCol(float x)
{
    return (int)(x / PLAN_CELL + (x >= 0.0f ? 0.5f : -0.5f));
}

static int PlanMove(void *context, const float from[3], float to[3])
{
    Plan *plan = (Plan *)context;
    int   fc   = PlanCol(from[0]), fr = PlanCol(from[1]);
    int   tc   = PlanCol(to[0]), tr = PlanCol(to[1]);

    plan->calls++;

    if (!PlanFree(plan, tc, tr))
    {
        return 0;
    }

    if (tc != fc && tr != fr && (!PlanFree(plan, tc, fr) || !PlanFree(plan, fc, tr)))
    {
        return 0;
    }

    to[2] = 0.0f;
    return 1;
}

/* A square marked 'c' is under a low ceiling: reached crouched. */
static int PlanMoveCrouch(void *context, const float from[3], float to[3])
{
    Plan *plan = (Plan *)context;
    int   kind = PlanMove(context, from, to);

    if (kind && plan->rows[PlanCol(to[1])][PlanCol(to[0])] == 'c')
    {
        return ETA_PATH_CROUCH;
    }
    return kind;
}

/* The way out's question: is this square outside, 'O'. */
static int PlanOutside(void *context, const float at[3])
{
    const Plan *plan = (const Plan *)context;
    int         col  = PlanCol(at[0]), row = PlanCol(at[1]);

    return PlanFree(plan, col, row) && plan->rows[row][col] == 'O';
}

static const char *const boxedHouse[] =
{
    "OOOOOOOOOO",
    "O########O",
    "O#S.....#O",
    "O#......#O",
    "O########O",
    "OOOOOOOOOO",
};

static void PlanFind(const Plan *plan, char what, float out[3])
{
    int row, col;

    for (row = 0; row < plan->height; row++)
    {
        for (col = 0; col < plan->width; col++)
        {
            if (plan->rows[row][col] == what)
            {
                out[0] = (float)col * PLAN_CELL;
                out[1] = (float)row * PLAN_CELL;
                out[2] = 0.0f;
                return;
            }
        }
    }
}


/* ---- Up and down: drawn plans with floors at different heights --------
 *
 * Each square is a digit, its floor's height in steps of 16 units, or '#'
 * for a wall. A step up of one is walked, as the game walks a stair; up
 * to three (48 units) is a jump, about what a player can get onto; more
 * is a wall unless a ladder joins the two. A drop of up to six (96
 * units) is walked off; a deeper one is climbed down, or not at all.
 */
#define LEVEL_HEIGHT 16.0f

static int LevelAt(const Plan *plan, int col, int row)
{
    char c;

    if (col < 0 || row < 0 || col >= plan->width || row >= plan->height)
    {
        return -1;
    }

    c = plan->rows[row][col];
    return (c >= '0' && c <= '9') ? c - '0' : -1;
}

static int LevelMove(void *context, const float from[3], float to[3])
{
    Plan *plan = (Plan *)context;
    int   fc   = PlanCol(from[0]), fr = PlanCol(from[1]);
    int   tc   = PlanCol(to[0]), tr = PlanCol(to[1]);
    int   here = LevelAt(plan, fc, fr), there = LevelAt(plan, tc, tr);

    plan->calls++;

    if (here < 0 || there < 0)
    {
        return ETA_PATH_NONE;
    }

    if (tc != fc && tr != fr && (LevelAt(plan, tc, fr) < 0 || LevelAt(plan, fc, tr) < 0))
    {
        return ETA_PATH_NONE;
    }

    to[2] = (float)there * LEVEL_HEIGHT;

    if (here - there > 6)
    {
        return ETA_PATH_NONE;
    }

    if (there - here <= 1)
    {
        return ETA_PATH_WALK;
    }

    return there - here <= 3 ? ETA_PATH_JUMP : ETA_PATH_NONE;
}

static void LevelPoint(const Plan *plan, int col, int row, float out[3])
{
    out[0] = (float)col * PLAN_CELL;
    out[1] = (float)row * PLAN_CELL;
    out[2] = (float)LevelAt(plan, col, row) * LEVEL_HEIGHT;
}

static ETA_PathState LevelSearch(Plan *plan, int sc, int sr, int gc, int gr)
{
    float start[3], goal[3];
    int   frames = 0;

    LevelPoint(plan, sc, sr, start);
    LevelPoint(plan, gc, gr, goal);
    ETA_PathFinder_Begin(start, goal, PLAN_CELL, PLAN_CELL * 0.5f, 0);

    while (ETA_PathFinder_Step(4, LevelMove, plan) == ETA_PATH_SEARCHING && frames < 100000)
    {
        frames++;
    }

    return ETA_PathFinder_State();
}

/* How many points of the way are reached by the given kind of move. */
static int LevelCount(ETA_PathKind kind)
{
    int i, n = 0;

    for (i = 0; i < ETA_PathFinder_PointCount(); i++)
    {
        n += ETA_PathFinder_PointKind(i) == kind;
    }

    return n;
}

/* Runs the search to the end in small steps, the way a game frame does,
   and returns how many steps it took. */
static int PlanSearch(Plan *plan, int flatGoal)
{
    float start[3], goal[3];
    int   frames = 0;

    PlanFind(plan, 'S', start);
    PlanFind(plan, 'G', goal);
    ETA_PathFinder_Begin(start, goal, PLAN_CELL, PLAN_CELL * 0.5f, flatGoal);

    while (ETA_PathFinder_Step(4, PlanMove, plan) == ETA_PATH_SEARCHING && frames < 100000)
    {
        frames++;
    }

    return frames;
}

/* Every step of the way is a square a player can stand on, and no step
   goes through a wall or across a corner. */
static int PlanPathWalkable(Plan *plan)
{
    int   count = ETA_PathFinder_PointCount();
    int   i;
    float a[3], b[3];

    for (i = 1; i < count; i++)
    {
        ETA_PathFinder_Point(i - 1, a);
        ETA_PathFinder_Point(i, b);

        if (!PlanMove(plan, a, b))
        {
            return 0;
        }
    }

    return count > 0;
}

static int PlanPathVisits(char what, const Plan *plan)
{
    int   count = ETA_PathFinder_PointCount();
    int   i;
    float p[3];

    for (i = 0; i < count; i++)
    {
        ETA_PathFinder_Point(i, p);

        if (plan->rows[PlanCol(p[1])][PlanCol(p[0])] == what)
        {
            return 1;
        }
    }

    return 0;
}

int main(void)
{
    char *correctionText;
    int i;

    SMOKE_BANNER("navigation");

    ETA_AccessibilityRuntime_Init();
    ETA_NavigationSystem_Init();

    /* Bearings are compass degrees. The engine integrations feed this the
       result of AngleNormalize360, so 0 and 359 are the boundaries that
       matter and must be accepted. */
    CHECK(!BearingRejected(0));
    CHECK(!BearingRejected(180));
    CHECK(!BearingRejected(359));

    /* Out-of-range bearings must be rejected rather than announced. Each of
       these logs one ERROR line: that is the guard doing its job. */
    CHECK(BearingRejected(-10));
    CHECK(BearingRejected(360));
    CHECK(BearingRejected(3600));

    ETA_NavigationSystem_AnnounceDistance(50);

    /* AnnounceRouteCorrection must copy correctionText rather than keep the
       caller's pointer, so freeing it right after must not leave anything
       reading freed memory. */
    correctionText = HeapCopy("Turn left");
    ETA_NavigationSystem_AnnounceRouteCorrection(correctionText);
    free(correctionText);

    CHECK(!ETA_NavigationSystem_IsStuck());

    /*
     * Stuck detection.
     *
     * The original version asked only "has this player moved", and
     * reported anyone who had not for three seconds. In a shooter that is
     * ordinary behaviour - aiming, covering a doorway, waiting for a
     * spawn - so it fired at random during play and told the player
     * something they already knew. Being stuck is *wanting to move and
     * not moving*, and these checks hold it to that.
     */

    /* Standing still on purpose is not stuck, however long it goes on. */
    for (i = 0; i < 10; i++)
    {
        CHECK(!ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 0));
    }
    CHECK(!ETA_NavigationSystem_IsStuck());

    /* Pushing into something and getting nowhere is. It reports on the
       frame the judgement is first made, so the caller speaks once. */
    CHECK(!ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1));
    CHECK(!ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1));
    CHECK(ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1));
    CHECK(ETA_NavigationSystem_IsStuck());

    /* Staying stuck is not news: it must not report again. */
    for (i = 0; i < 6; i++)
    {
        CHECK(!ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1));
    }

    /* Moving again clears it, and a later snag reports afresh. */
    ETA_NavigationSystem_UpdateMovement(5.0f, 1.0f, 1);
    ETA_NavigationSystem_UpdateMovement(5.0f, 1.0f, 1);
    ETA_NavigationSystem_UpdateMovement(5.0f, 1.0f, 1);
    CHECK(!ETA_NavigationSystem_IsStuck());

    /*
     * Slow movement is movement. This is the case the old per-frame
     * distance test got wrong: it compared one frame's travel against a
     * fixed distance, which is a speed test with the frame rate as its
     * units, so crouching and crawling read as stuck. A tenth of a second
     * per frame at half a metre is a crawl, and it must not report.
     */
    ETA_NavigationSystem_ResetStuckDetection();
    for (i = 0; i < 60; i++)
    {
        CHECK(!ETA_NavigationSystem_UpdateMovement(0.5f, 0.1f, 1));
    }
    CHECK(!ETA_NavigationSystem_IsStuck());

    /* Frame rate must not change the verdict. The same crawl delivered in
       many small frames rather than few large ones is still moving. */
    ETA_NavigationSystem_ResetStuckDetection();
    for (i = 0; i < 480; i++)
    {
        CHECK(!ETA_NavigationSystem_UpdateMovement(0.0625f, 0.0125f, 1));
    }
    CHECK(!ETA_NavigationSystem_IsStuck());

    /* Letting go of the movement keys drops the latch. */
    ETA_NavigationSystem_ResetStuckDetection();
    ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1);
    ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1);
    CHECK(ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 1));
    CHECK(!ETA_NavigationSystem_UpdateMovement(0.0f, 1.0f, 0));
    CHECK(!ETA_NavigationSystem_IsStuck());

    ETA_NavigationSystem_ResetStuckDetection();
    CHECK(!ETA_NavigationSystem_IsStuck());

    /* Objective approach milestones.
       Walking in from far away speaks once per milestone crossed, and
       never twice for the same one - a player closing on an objective
       should hear four things, not a countdown. */
    ETA_NavigationSystem_ResetApproach();
    CHECK(!ETA_NavigationSystem_UpdateApproach(400));
    CHECK(!ETA_NavigationSystem_UpdateApproach(150));
    CHECK(!ETA_NavigationSystem_UpdateApproach(101));
    CHECK(ETA_NavigationSystem_UpdateApproach(100));   /* crosses 100 */
    CHECK(!ETA_NavigationSystem_UpdateApproach(99));
    CHECK(!ETA_NavigationSystem_UpdateApproach(60));
    CHECK(ETA_NavigationSystem_UpdateApproach(50));    /* crosses 50  */
    CHECK(!ETA_NavigationSystem_UpdateApproach(30));
    CHECK(ETA_NavigationSystem_UpdateApproach(25));    /* crosses 25  */
    CHECK(ETA_NavigationSystem_UpdateApproach(10));    /* crosses 10  */
    CHECK(!ETA_NavigationSystem_UpdateApproach(0));    /* nothing left */

    /* Standing on the objective must not chatter, however long for. */
    for (i = 0; i < 500; i++)
    {
        CHECK(!ETA_NavigationSystem_UpdateApproach(3));
    }

    /* Drifting across a milestone's edge is exactly what happens in a
       firefight near an objective, and must stay silent. */
    ETA_NavigationSystem_ResetApproach();
    CHECK(ETA_NavigationSystem_UpdateApproach(24));
    for (i = 0; i < 50; i++)
    {
        CHECK(!ETA_NavigationSystem_UpdateApproach(26));
        CHECK(!ETA_NavigationSystem_UpdateApproach(24));
    }

    /* But genuinely leaving and coming back is news again: past the
       re-arm margin, the milestone speaks a second time. */
    CHECK(!ETA_NavigationSystem_UpdateApproach(40));
    CHECK(ETA_NavigationSystem_UpdateApproach(24));

    /* Arriving already inside several milestones at once - a spawn, or
       the objective changing - says where the player stands, once. */
    ETA_NavigationSystem_ResetApproach();
    CHECK(ETA_NavigationSystem_UpdateApproach(40));
    CHECK(!ETA_NavigationSystem_UpdateApproach(40));

    /* A reset is what the engine calls when the target changes: distance
       to a different objective is not progress toward this one. */
    ETA_NavigationSystem_ResetApproach();
    CHECK(ETA_NavigationSystem_UpdateApproach(40));

    /* Nonsense distances are refused rather than announced. */
    ETA_NavigationSystem_ResetApproach();
    CHECK_REJECTS(ETA_NavigationSystem_UpdateApproach(-1), ETA_ERROR_INVALID_VALUE);

    /* The player's own marker. Placed 30 metres off, the distance was
       spoken as it went down, so nothing is said until the player crosses
       a milestone they were not already inside. */
    ETA_NavigationSystem_StartMarkerApproach(30);
    CHECK(!ETA_NavigationSystem_UpdateMarkerApproach(30));
    CHECK(!ETA_NavigationSystem_UpdateMarkerApproach(26));
    CHECK(ETA_NavigationSystem_UpdateMarkerApproach(25));    /* crosses 25 */
    CHECK(!ETA_NavigationSystem_UpdateMarkerApproach(20));
    CHECK(ETA_NavigationSystem_UpdateMarkerApproach(9));     /* crosses 10 */
    CHECK(!ETA_NavigationSystem_UpdateMarkerApproach(2));

    /* Walking toward the marker is not progress toward the objective,
       and the other way round: each keeps its own milestones. */
    ETA_NavigationSystem_ResetApproach();
    CHECK(ETA_NavigationSystem_UpdateApproach(90));
    ETA_NavigationSystem_StartMarkerApproach(200);
    CHECK(ETA_NavigationSystem_UpdateMarkerApproach(90));
    CHECK(!ETA_NavigationSystem_UpdateApproach(90));

    /* A marker placed far away starts with every milestone still to come. */
    ETA_NavigationSystem_StartMarkerApproach(500);
    CHECK(ETA_NavigationSystem_UpdateMarkerApproach(100));
    CHECK(ETA_NavigationSystem_UpdateMarkerApproach(50));

    /* Moving a marker starts its approach again. */
    ETA_NavigationSystem_StartMarkerApproach(500);
    CHECK(ETA_NavigationSystem_UpdateMarkerApproach(100));

    ETA_NavigationSystem_AnnounceMarkerDistance(12);
    CHECK_REJECTS(ETA_NavigationSystem_UpdateMarkerApproach(-1), ETA_ERROR_INVALID_VALUE);
    CHECK_REJECTS(ETA_NavigationSystem_AnnounceMarkerDistance(-5), ETA_ERROR_INVALID_VALUE);

    /* Up or down to the objective: said, or nothing, never refused. */
    CHECK_ACCEPTS(ETA_NavigationSystem_AnnounceHeight(4.0f));
    CHECK_ACCEPTS(ETA_NavigationSystem_AnnounceHeight(-9.0f));
    CHECK_ACCEPTS(ETA_NavigationSystem_AnnounceHeight(0.5f));

    /* And to the marker, in its own name. */
    CHECK_ACCEPTS(ETA_NavigationSystem_AnnounceMarkerHeight(4.0f));
    CHECK_ACCEPTS(ETA_NavigationSystem_AnnounceMarkerHeight(-9.0f));
    CHECK_ACCEPTS(ETA_NavigationSystem_AnnounceMarkerHeight(0.5f));

    /* ---- The way around the walls ------------------------------------ */
    {
        /* The marker is through the wall. The straight line runs into it;
           the way runs through the doorway, 'D'. */
        static const char *const doorway[] =
        {
            "##########",
            "#S..#....#",
            "#...#....#",
            "#...#..G.#",
            "#...D....#",
            "##########",
        };
        /* Walled in completely: nowhere to go but as near as can be. */
        static const char *const sealed[] =
        {
            "##########",
            "#S..#....#",
            "#...#....#",
            "#...#..G.#",
            "#...#....#",
            "##########",
        };
        /* A corridor that doubles back: the goal is close as the crow
           flies and a long way on foot. */
        static const char *const hairpin[] =
        {
            "###########",
            "#S.......D#",
            "#########.#",
            "#G........#",
            "###########",
        };
        Plan  plan;
        float first[3], last[3], goal[3];
        int   frames;

        plan.rows   = doorway;
        plan.width  = 10;
        plan.height = 6;
        plan.calls  = 0;
        frames      = PlanSearch(&plan, 0);
        CHECK(ETA_PathFinder_State() == ETA_PATH_FOUND);
        CHECK(PlanPathWalkable(&plan));
        CHECK(PlanPathVisits('D', &plan));
        /* Spread over frames, not done in one. */
        CHECK(frames > 1);
        ETA_PathFinder_Point(0, first);
        CHECK(PlanCol(first[0]) == 1 && PlanCol(first[1]) == 1);
        ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, last);
        PlanFind(&plan, 'G', goal);
        CHECK(PlanCol(last[0]) == PlanCol(goal[0]) && PlanCol(last[1]) == PlanCol(goal[1]));

        plan.rows  = hairpin;
        plan.width = 11;
        plan.height = 5;
        PlanSearch(&plan, 0);
        CHECK(ETA_PathFinder_State() == ETA_PATH_FOUND);
        CHECK(PlanPathWalkable(&plan));
        CHECK(PlanPathVisits('D', &plan));

        /* Sealed off: the way ends at the nearest reachable square, next
           to the wall, rather than nowhere. */
        plan.rows   = sealed;
        plan.width  = 10;
        plan.height = 6;
        PlanSearch(&plan, 0);
        CHECK(ETA_PathFinder_State() == ETA_PATH_PARTIAL);
        CHECK(PlanPathWalkable(&plan));
        ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, last);
        CHECK(PlanCol(last[0]) == 3);

        /* Walled in where it starts: no way at all, and no points. */
        {
            static const char *const boxed[] =
            {
                "#####",
                "##S##",
                "#####",
                "#..G#",
                "#####",
            };

            plan.rows   = boxed;
            plan.width  = 5;
            plan.height = 5;
            PlanSearch(&plan, 0);
            CHECK(ETA_PathFinder_State() == ETA_PATH_FAILED);
            CHECK(ETA_PathFinder_PointCount() == 0);
        }

        /* The way out of a building: the nearest square under the sky,
           'O', whatever its place - here through the doorway, past the
           nearer outside that is through a wall. */
        {
            static const char *const house[] =
            {
                "OOOOOOOOOO",
                "O########O",
                "O#S.....#O",
                "O#......#O",
                "O####D###O",
                "OOOOOOOOOO",
            };

            plan.rows   = house;
            plan.width  = 10;
            plan.height = 6;
            PlanFind(&plan, 'S', last);
            ETA_PathFinder_BeginSearch(last, PLAN_CELL, PlanOutside, &plan);
            while (ETA_PathFinder_Step(4, PlanMove, &plan) == ETA_PATH_SEARCHING)
            {
            }
            CHECK(ETA_PathFinder_State() == ETA_PATH_FOUND);
            CHECK(PlanPathWalkable(&plan));
            CHECK(PlanPathVisits('D', &plan));
            ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, last);
            CHECK(PlanCol(last[0]) == 5 && PlanCol(last[1]) == 5);

            /* No way out at all: it fails rather than leading anywhere. */
            plan.rows = boxedHouse;
            PlanFind(&plan, 'S', last);
            ETA_PathFinder_BeginSearch(last, PLAN_CELL, PlanOutside, &plan);
            while (ETA_PathFinder_Step(4, PlanMove, &plan) == ETA_PATH_SEARCHING)
            {
            }
            CHECK(ETA_PathFinder_State() == ETA_PATH_FAILED);
            CHECK(ETA_PathFinder_PointCount() == 0);

            /* And an ordinary search after it is an ordinary search. */
            plan.rows   = doorway;
            PlanSearch(&plan, 0);
            CHECK(ETA_PathFinder_State() == ETA_PATH_FOUND);
        }

        /* Through a low tunnel, crouched: the only way, so it is taken,
           and each square under the low ceiling says so. */
        {
            static const char *const tunnel[] =
            {
                "##########",
                "#S.cccc.G#",
                "##########",
            };
            int crouched = 0, i;
            float s[3], g[3];

            plan.rows   = tunnel;
            plan.width  = 10;
            plan.height = 3;
            PlanFind(&plan, 'S', s);
            PlanFind(&plan, 'G', g);
            ETA_PathFinder_Begin(s, g, PLAN_CELL, PLAN_CELL * 0.5f, 0);
            while (ETA_PathFinder_Step(4, PlanMoveCrouch, &plan) == ETA_PATH_SEARCHING)
            {
            }
            CHECK(ETA_PathFinder_State() == ETA_PATH_FOUND);
            for (i = 0; i < ETA_PathFinder_PointCount(); i++)
            {
                crouched += ETA_PathFinder_PointKind(i) == ETA_PATH_CROUCH;
            }
            CHECK(crouched == 4);
        }

        /* Further than the pool of squares reaches: the answer is the way
           toward it as far as the search got, which is still the right
           first step. A 200 by 200 open field with the goal in the far
           corner is 40,000 squares, well past the pool. */
        {
            static char        field[200][201];
            static const char *fieldRows[200];
            float              start[3];
            int                r, c;

            for (r = 0; r < 200; r++)
            {
                for (c = 0; c < 200; c++)
                {
                    field[r][c] = (r == 0 || c == 0 || r == 199 || c == 199) ? '#' : '.';
                }
                field[r][200] = '\0';
                fieldRows[r]  = field[r];
            }
            field[1][1]     = 'S';
            field[198][198] = 'G';
            /* A wall across most of the field, so the straight line is
               blocked and the way has to bend round its end. */
            for (c = 1; c < 190; c++)
            {
                field[20][c] = '#';
            }

            plan.rows   = fieldRows;
            plan.width  = 200;
            plan.height = 200;
            PlanSearch(&plan, 0);
            CHECK(ETA_PathFinder_State() == ETA_PATH_PARTIAL
                  || ETA_PathFinder_State() == ETA_PATH_FOUND);
            CHECK(PlanPathWalkable(&plan));
            ETA_PathFinder_Point(0, start);
            ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, last);
            PlanFind(&plan, 'G', goal);
            /* Nearer the goal than where it started, and past the wall. */
            CHECK((last[0] - goal[0]) * (last[0] - goal[0]) + (last[1] - goal[1]) * (last[1] - goal[1])
                  < (start[0] - goal[0]) * (start[0] - goal[0]) + (start[1] - goal[1]) * (start[1] - goal[1]));
            CHECK(PlanCol(last[1]) > 20);
        }


        /* ---- Up and down ----------------------------------------------- */
        {
            Plan plan;

            plan.calls = 0;

            /* A crate in the way of a ledge: the only way up is a jump. */
            {
                static const char *const ledge[] =
                {
                    "#######",
                    "#00333#",
                    "#######",
                };

                plan.rows   = ledge;
                plan.width  = 7;
                plan.height = 3;
                CHECK(LevelSearch(&plan, 1, 1, 5, 1) == ETA_PATH_FOUND);
                CHECK(LevelCount(ETA_PATH_JUMP) == 1);
                /* The jump is onto the first square of the ledge. */
                CHECK(ETA_PathFinder_PointKind(2) == ETA_PATH_JUMP);
                CHECK(ETA_PathFinder_PointKind(0) == ETA_PATH_WALK);
                CHECK(ETA_PathFinder_PointKind(-1) == ETA_PATH_NONE);
                CHECK(ETA_PathFinder_PointKind(ETA_PathFinder_PointCount()) == ETA_PATH_NONE);
            }

            /* Stairs a square out of the way are taken rather than the jump:
               a player who cannot see is better off on the stairs. */
            {
                static const char *const stairs[] =
                {
                    "#########",
                    "#0000333#",
                    "#01233###",
                    "#########",
                };

                plan.rows   = stairs;
                plan.width  = 9;
                plan.height = 4;
                CHECK(LevelSearch(&plan, 1, 1, 7, 1) == ETA_PATH_FOUND);
                CHECK(LevelCount(ETA_PATH_JUMP) == 0);
            }

            /* A floor far above, reached only by a ladder at the far end. The
               search has to know the goal is up there: standing under it on
               the ground is not arriving. */
            {
                static const char *const tower[] =
                {
                    "#######",
                    "#00000#",
                    "#99999#",
                    "#######",
                };
                float foot[3], top[3], last[3];

                plan.rows   = tower;
                plan.width  = 7;
                plan.height = 4;

                ETA_PathFinder_ClearLinks();
                CHECK(LevelSearch(&plan, 1, 1, 1, 2) != ETA_PATH_FOUND);
                CHECK(LevelCount(ETA_PATH_LADDER_UP) == 0);

                LevelPoint(&plan, 5, 1, foot);
                LevelPoint(&plan, 5, 2, top);
                CHECK(ETA_PathFinder_AddLink(foot, top, ETA_PATH_LADDER_UP));
                CHECK(ETA_PathFinder_AddLink(top, foot, ETA_PATH_LADDER_DOWN));
                CHECK(ETA_PathFinder_LinkCount() == 2);

                CHECK(LevelSearch(&plan, 1, 1, 1, 2) == ETA_PATH_FOUND);
                CHECK(LevelCount(ETA_PATH_LADDER_UP) == 1);
                CHECK(LevelCount(ETA_PATH_LADDER_DOWN) == 0);
                ETA_PathFinder_Point(ETA_PathFinder_PointCount() - 1, last);
                CHECK(last[2] == 9.0f * LEVEL_HEIGHT);

                /* And down again from the top, by the same ladder. */
                CHECK(LevelSearch(&plan, 2, 2, 1, 1) == ETA_PATH_FOUND);
                CHECK(LevelCount(ETA_PATH_LADDER_DOWN) == 1);

                /* Links stay from one search to the next, until cleared. */
                ETA_PathFinder_Reset();
                CHECK(ETA_PathFinder_LinkCount() == 2);
                ETA_PathFinder_ClearLinks();
                CHECK(ETA_PathFinder_LinkCount() == 0);
                CHECK(LevelSearch(&plan, 1, 1, 1, 2) != ETA_PATH_FOUND);

                /* Nothing that is not a way is taken as a link. */
                CHECK(!ETA_PathFinder_AddLink(foot, top, ETA_PATH_NONE));
                CHECK(!ETA_PathFinder_AddLink(NULL, top, ETA_PATH_LADDER_UP));
                CHECK(ETA_PathFinder_LinkCount() == 0);
            }

            /* A move answer outside the kinds is no way, not a crash. */
            ETA_PathFinder_Reset();
        }

        /* Reset forgets the way. */
        ETA_PathFinder_Reset();
        CHECK(ETA_PathFinder_State() == ETA_PATH_IDLE);
        CHECK(ETA_PathFinder_PointCount() == 0);
        ETA_PathFinder_Point(0, last);
        CHECK(last[0] == 0.0f && last[1] == 0.0f);
        CHECK(ETA_PathFinder_Step(8, NULL, NULL) == ETA_PATH_IDLE);
    }

    ETA_NavigationSystem_Shutdown();
    ETA_AccessibilityRuntime_Shutdown();

    return SMOKE_REPORT("navigation");
}

#!/usr/bin/env python3
"""Walk to a marker the way a player would: by following its ping.

Why this exists
---------------
The marker's ping was changed to lead round walls instead of into them,
and a tester who followed it found nothing had changed: it still led
into the wall, and "where is the marker" said the same as before. The
search itself was tested - on drawn grids - and passed. What had never
been tested was the game's side: the walk check against collision, the
timing of the search across frames, when it starts again, and where the
ping ends up while the player is moving.

So this lifts that code out of the patched engine unchanged, gives it a
small world of solid boxes with a collision trace that works the way
the engine's does, and puts a walker in it who does exactly what a
player listening to the ping does: every frame, turn toward the ping
and walk, at running speed, sliding along whatever they bump into. The
walker has a player's width, not the narrower probe the search uses.

Each scene has a wall between the walker and the marker - or, in the
middle four, a floor above it: reached by stairs round the side, by a
ledge the walker is told to jump onto, by a ladder - which the walker
climbs the way the game's own climb does once F is pressed at its foot
- and by steps at one end of a ledge, which are walked, not jumped.
Then walls with a gap the way-finder's probe once fitted and a player
does not, taken from the real Oasis map, where it stopped the tester,
and a beam across the straight way that only a crouch gets under -
the walker crouches when told to, and stands when there is room; and
a balcony with the marker below its edge and the stairs at one side.
Last, landmines the player has been shown: one on the straight way,
one that comes into sight halfway there - the walker must keep further
off each than the game sets one off at - and one in the only doorway,
which the way goes through.
Throughout, the ping must never point back the way the player came
while the way goes on ahead - the tester heard "the way goes
south-west" with the way and the marker both north-east. The walker steps up what a player steps up, falls, and jumps
only when "Jump up" has been said. The walker has
to get there in reasonable time, without spending long pressed against
a wall, and the ping has to be following the way - not the straight
line - within a few seconds of the marker going down.

Usage
-----
    ./marker_route_sim_test.py <engine-root>
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

COMMANDMAP = os.path.join("src", "cgame", "cg_commandmap.c")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

HARNESS = r'''
#include "q_shared.h"
#include "game/surfaceflags.h"
#include "navigation/navigation_system.h"
#include "navigation/place_classifier.h"
#include "hud/hud_narrator.h"
#include "speech/speech_manager.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#ifndef MASK_SOLID
#define MASK_SOLID CONTENTS_SOLID
#endif
#ifndef MASK_PLAYERSOLID
#define MASK_PLAYERSOLID (CONTENTS_SOLID | CONTENTS_PLAYERCLIP | CONTENTS_BODY)
#endif
#define ETA_QU_TO_METERS 0.0254f

void QDECL Com_Error(int code, const char *fmt, ...) { (void)code; (void)fmt; exit(2); }
void QDECL Com_Printf(const char *fmt, ...) { (void)fmt; }

static struct
{
	int           time;
	playerState_t predictedPlayerState;
} cg;

/* ---- a world of solid boxes, traced the way the engine traces ---- */
typedef struct { float mn[3], mx[3]; } box_t;
static box_t worldBoxes[64];
static int   worldCount;
static long  traceCount;

static void AddBox(float x0, float y0, float z0, float x1, float y1, float z1)
{
	box_t *b = &worldBoxes[worldCount++];
	b->mn[0] = x0; b->mn[1] = y0; b->mn[2] = z0;
	b->mx[0] = x1; b->mx[1] = y1; b->mx[2] = z1;
}

/* The game's clock, driven by the work done: each trace is taken to cost
   five microseconds, a fair figure for a detailed map, so a search that
   watches the clock is held to what it would really get done. */
int trap_Milliseconds(void)
{
	return (int)(traceCount / 200);
}

/* Whether the walker is on a ladder: the game's own climb, which the way
   waits for rather than taking the climb for a stray. */
static int walkerClimbing;

qboolean CG_AccessibilityClimbing(void)
{
	return walkerClimbing ? qtrue : qfalse;
}

/* Which side of the view a point is on, for the "Jump up, ahead" the
   way says. The walk has no view to speak of. */
float CG_AccessibilityLeftOfView(const vec3_t point)
{
	(void)point;
	return 0.0f;
}

/* The jump key the jump callout names: space, as the stock game has it. */
int trap_Key_GetKey(const char *binding)
{
	(void)binding;
	return 32;
}

void trap_Key_KeynumToStringBuf(int keynum, char *buf, int buflen)
{
	(void)keynum;
	Q_strncpyz(buf, "SPACE", buflen);
}

int CG_PointContents(const vec3_t point, int passEntityNum)
{
	int i;
	(void)passEntityNum;
	for (i = 0; i < worldCount; i++)
	{
		if (point[0] > worldBoxes[i].mn[0] && point[0] < worldBoxes[i].mx[0]
		    && point[1] > worldBoxes[i].mn[1] && point[1] < worldBoxes[i].mx[1]
		    && point[2] > worldBoxes[i].mn[2] && point[2] < worldBoxes[i].mx[2])
		{
			return CONTENTS_SOLID;
		}
	}
	return 0;
}

void trap_CM_BoxTrace(trace_t *results, const vec3_t start, const vec3_t end,
                      const vec3_t mins, const vec3_t maxs, int model, int brushmask)
{
	static const vec3_t zero = { 0, 0, 0 };
	float best = 1.0f, length;
	int   i, a, hitAxis = -1;
	float hitSign = 0.0f;
	vec3_t d;

	(void)model; (void)brushmask;
	traceCount++;
	if (!mins) mins = zero;
	if (!maxs) maxs = zero;

	memset(results, 0, sizeof(*results));
	VectorSubtract(end, start, d);
	length = VectorLength(d);

	for (i = 0; i < worldCount; i++)
	{
		float lo[3], hi[3], enter = -1.0e9f, leave = 1.0e9f, sign = 0.0f;
		int   axis = -1, inside = 1, miss = 0;

		for (a = 0; a < 3; a++)
		{
			lo[a] = worldBoxes[i].mn[a] - maxs[a];
			hi[a] = worldBoxes[i].mx[a] - mins[a];
			if (!(start[a] > lo[a] + 0.01f && start[a] < hi[a] - 0.01f))
			{
				inside = 0;
			}
		}

		if (inside)
		{
			results->startsolid = qtrue;
			best                = 0.0f;
			continue;
		}

		for (a = 0; a < 3 && !miss; a++)
		{
			if (fabsf(d[a]) < 1.0e-6f)
			{
				if (start[a] <= lo[a] || start[a] >= hi[a])
				{
					miss = 1;
				}
				continue;
			}
			{
				float t1 = (lo[a] - start[a]) / d[a];
				float t2 = (hi[a] - start[a]) / d[a];
				float s  = d[a] > 0 ? -1.0f : 1.0f;
				if (t1 > t2) { float t = t1; t1 = t2; t2 = t; }
				if (t1 > enter) { enter = t1; axis = a; sign = s; }
				if (t2 < leave) { leave = t2; }
			}
		}

		if (miss || enter > leave || leave <= 0.0f || enter < -0.001f || enter >= best)
		{
			continue;
		}

		best    = enter < 0.0f ? 0.0f : enter;
		hitAxis = axis;
		hitSign = sign;
	}

	if (best < 1.0f && length > 0.0f)
	{
		best -= 0.03125f / length;
		if (best < 0.0f) best = 0.0f;
	}

	results->fraction = best;
	VectorMA(start, best, d, results->endpos);
	if (hitAxis >= 0)
	{
		results->plane.normal[hitAxis] = hitSign;
	}
	results->entityNum = best < 1.0f ? ENTITYNUM_WORLD : ENTITYNUM_NONE;
}

/* ---- lifted from the patched engine ---- */
%(LIFTED)s

/* ---- the walker ---- */
typedef struct
{
	const char *name;
	float       start[3], marker[3];
	int         square;
	float       timeLimit;
} scene_t;

/* Ladders, as the game hands them to the way-finder from the map file:
   the foot and the top, joined both ways. */
static float ladderFoot[4][3], ladderTop[4][3];
static int   ladderCount;

static void AddLadder(float fx, float fy, float fz, float tx, float ty, float tz)
{
	float *foot = ladderFoot[ladderCount], *top = ladderTop[ladderCount];

	foot[0] = fx; foot[1] = fy; foot[2] = fz;
	top[0]  = tx; top[1]  = ty; top[2]  = tz;
	ETA_PathFinder_AddLink(foot, top, ETA_PATH_LADDER_UP);
	ETA_PathFinder_AddLink(top, foot, ETA_PATH_LADDER_DOWN);
	ladderCount++;
}

static void BuildScene(int which)
{
	worldCount  = 0;
	ladderCount = 0;
	ETA_PathFinder_ClearLinks();
	/* The ground, everywhere. */
	AddBox(-4096, -4096, -64, 4096, 4096, 0);

	if (which == 0)
	{
		/* A building between the walker and the marker. */
		AddBox(-384, 256, 0, 384, 768, 256);
	}
	else if (which == 1)
	{
		/* A room around the walker, its door facing away from the
		   marker. Walls 32 thick; the doorway 96 wide in the south
		   wall. */
		AddBox(-320, 256, 0, 320, 288, 256);     /* north */
		AddBox(-320, -288, 0, -48, -256, 256);   /* south, left of door */
		AddBox(48, -288, 0, 320, -256, 256);     /* south, right of door */
		AddBox(-320, -288, 0, -288, 288, 256);   /* west */
		AddBox(288, -288, 0, 320, 288, 256);     /* east */
	}
	else if (which == 2)
	{
		/* A long wall with a gap near one end. */
		AddBox(-1600, 400, 0, 1100, 432, 256);
		AddBox(1196, 400, 0, 1600, 432, 256);
	}
	else if (which == 4)
	{
		/* A city wall 150 metres long, the gate far to one side, the
		   marker well beyond it - the scale of a real map. */
		AddBox(-4000, 1200, 0, 2200, 1264, 512);
		AddBox(2400, 1200, 0, 4000, 1264, 512);
	}
	else if (which == 5)
	{
		/* A map square whose middle is inside a building: the square
		   is reached by walking into it, anywhere. */
		AddBox(1200, 1200, 0, 2000, 2000, 512);
	}
	else if (which == 6)
	{
		/* The Oasis command post's problem: the marker on a floor two
		   metres and more up, its front a sheer face, and the way up a
		   flight of stairs round to one side - steps of 16, 32 deep. */
		int k;

		AddBox(-256, 800, 0, 256, 1200, 128);
		for (k = 1; k <= 8; k++)
		{
			AddBox(-256, 800 - 32 * (9 - k), 0, -160, 800 - 32 * (8 - k), 16 * k);
		}
	}
	else if (which == 7)
	{
		/* A ledge a metre up, too high to step onto and with no stairs:
		   the way there is a jump, and the walker has to be told. */
		AddBox(-512, 800, 0, 512, 1200, 40);
	}
	else if (which == 8)
	{
		/* A floor nearly five metres up, a sheer wall, and a ladder up
		   its face - the only way. */
		AddBox(-512, 800, 0, 512, 1200, 192);
		AddLadder(0, 770, 24, 0, 830, 216);
	}
	else if (which == 9)
	{
		/* The real Oasis fault: a ledge a metre up, and two ordinary
		   steps up onto it at one end. The steps are the way, however
		   much shorter the jump is. */
		AddBox(-512, 800, 0, 512, 1200, 40);
		AddBox(-512, 704, 0, -416, 768, 16);
		AddBox(-512, 768, 0, -416, 800, 32);
	}
	else if (which == 10)
	{
		/* The real Oasis fault: a wall across the way with a gap a
		   player cannot fit - 28 units, against a player's 36 - straight
		   ahead, and a proper doorway further along. The way has to take
		   the doorway. */
		AddBox(-1600, 600, 0, -14, 632, 256);
		AddBox(14, 600, 0, 500, 632, 256);
		AddBox(596, 600, 0, 1600, 632, 256);
	}
	else if (which == 11)
	{
		/* A gap the way-finder's probe fits and a player does not: 34
		   units, against a probe of 32 and a player of 36. The real
		   Oasis has two; a walk following the ping stopped at both. */
		AddBox(-1600, 600, 0, -17, 632, 256);
		AddBox(17, 600, 0, 500, 632, 256);
		AddBox(596, 600, 0, 1600, 632, 256);
	}
	else if (which == 12)
	{
		/* A beam across the straight way, 60 up: under it is a crouch,
		   and the way goes under it, telling the player to crouch -
		   rather than round by the doorway further along, which it once
		   took when nothing could say so. */
		AddBox(-1600, 600, 0, -48, 632, 256);
		AddBox(-48, 600, 60, 48, 632, 256);
		AddBox(48, 600, 0, 500, 632, 256);
		AddBox(596, 600, 0, 1600, 632, 256);
	}
	else if (which == 13)
	{
		/* A balcony seven metres up, the marker on the ground beyond its
		   edge, and the stairs down at one side - the Allied Command
		   Post's own on Oasis. The way goes down the stairs; the ping
		   once looked straight off the edge, at the floor below. */
		int k;

		AddBox(-512, 0, 0, 512, 600, 288);
		for (k = 1; k <= 17; k++)
		{
			AddBox(-512, 600 + 32 * (k - 1), 0, -416, 600 + 32 * k, 288 - 16 * k);
		}
	}
	else if (which == 14)
	{
		/* A narrow alley a little over a body wide, and the squares the
		   way is found on all falling on its walls: from where the walk
		   starts they lie every 32 units, at 32 and 64, and a body fits
		   only with its middle from 54 to 60. A proper doorway is a long
		   way round. On Oasis the short way to the Allied command post
		   is such an alley; from some places the way went round through
		   the excavation instead. */
		AddBox(-1600, 600, 0, 36, 632, 256);
		AddBox(78, 600, 0, 1500, 632, 256);
		AddBox(1596, 600, 0, 2600, 632, 256);
	}
	else if (which == 17)
	{
		/* A wall with one doorway, and a landmine in it: there is no way
		   round, so the way goes through, and the warning says where. */
		AddBox(-1600, 600, 0, -48, 632, 256);
		AddBox(48, 600, 0, 1600, 632, 256);
	}
	/* which == 3, 15, 16: open ground */
}

static const scene_t scenes[] =
{
	{ "building in the way", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 60.0f },
	{ "room with its door behind", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 90.0f },
	{ "long wall with a gap", { -800, 0, 24 }, { -800, 900, 24 }, 0, 90.0f },
	{ "open ground", { 0, 0, 24 }, { 900, 900, 24 }, 0, 15.0f },
	{ "city wall with a far gate", { 0, 0, 24 }, { 0, 3200, 24 }, 0, 120.0f },
	{ "square with a building in its middle", { 0, 0, 24 }, { 1600, 1600, 24 }, 1, 60.0f },
	{ "floor above, stairs round the side", { 0, 0, 24 }, { 0, 1000, 152 }, 0, 90.0f },
	{ "ledge to jump onto", { 0, 0, 24 }, { 0, 1000, 64 }, 0, 90.0f },
	{ "floor above, up a ladder", { 0, 0, 24 }, { 0, 1000, 216 }, 0, 90.0f },
	{ "ledge with steps at one end", { 0, 0, 24 }, { 0, 1000, 64 }, 0, 90.0f },
	{ "gap too narrow for a player", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 90.0f },
	{ "gap a player is a little too wide for", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 90.0f },
	{ "beam a player would have to crouch under", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 90.0f },
	{ "balcony, stairs down at one side", { 0, 300, 312 }, { 0, 1100, 24 }, 0, 90.0f },
	{ "narrow alley the squares miss", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 90.0f },
	{ "a landmine on the straight way", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 30.0f },
	{ "a landmine seen halfway there", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 30.0f },
	{ "a landmine in the only doorway", { 0, 0, 24 }, { 0, 1100, 24 }, 0, 60.0f },
};

/* The landmines the player has been shown, as cg_draw.c hands them to
   the way: where, and from when in the walk. */
static const struct { int scene; float at[3]; float from; } mines[] =
{
	{ 15, { 0, 550, 0 }, 0.0f },
	{ 16, { 0, 700, 0 }, 0.8f },
	{ 17, { 0, 616, 0 }, 0.0f },
};

static void ShowMines(int which, float t)
{
	float shown[4][3];
	int   count = 0, i;

	for (i = 0; i < (int)(sizeof(mines) / sizeof(mines[0])); i++)
	{
		if (mines[i].scene == which && t >= mines[i].from)
		{
			VectorCopy(mines[i].at, shown[count]);
			count++;
		}
	}
	CG_AccessibilityRouteAvoid((const float (*)[3])shown, count);
}

static int RunScene(int which)
{
	const scene_t *scene = &scenes[which];
	/* The body that bumps into things as it walks stands a step above
	   the feet, as the game's own stepping does; the feet, below it,
	   find the floor. */
	static const vec3_t bodyMins = { -18, -18, -6 };
	/* Standing; crouched while told to crouch (the game's crouchMaxZ),
	   and until there is room to stand again. */
	vec3_t              bodyMaxs = { 18, 18, 48 };
	static const vec3_t footMins = { -18, -18, -24 };
	static const vec3_t footMaxs = { 18, 18, -6 };
	float  t = 0.0f, dt = 1.0f / 60.0f, pinned = 0.0f, worstPinned = 0.0f;
	float  steeredBy = -1.0f, vz = 0.0f, toldJumpAt = -100.0f, backward = 0.0f;
	float  leftGroundAt = 0.0f, worstFall = 0.0f;
	long   maxTraces = 0;
	int    frames = 0, reached = 0, onGround = 1, jumps = 0, climbs = 0;
	int    saidJump = -1;
	int    crouched = 0;      /* told to crouch, at some point */
	int    stairs = 0;        /* flights of stairs told of */
	float  nearestMine = 1.0e9f;   /* the nearest the walker came to a mine, across the ground */
	vec3_t stairsAt = { 0, 0, 0 };
	vec3_t pos;

	BuildScene(which);
	VectorCopy(scene->start, pos);
	VectorCopy(pos, cg.predictedPlayerState.origin);
	walkerClimbing = 0;

	memset(&eta_marker, 0, sizeof(eta_marker));
	eta_marker.active = qtrue;
	eta_marker.square = scene->square;
	VectorCopy(scene->marker, eta_marker.origin);
	ShowMines(which, 0.0f);
	ETA_RouteForget();
	cg.time = 100000;

	while (t < scene->timeLimit)
	{
		vec3_t target, dir, step, next;
		trace_t tr;
		long   tracesBefore = traceCount;
		vec3_t was;
		int    blocked = 0, l;

		VectorCopy(pos, cg.predictedPlayerState.origin);
		ShowMines(which, t);
		{
			int m;

			for (m = 0; m < (int)(sizeof(mines) / sizeof(mines[0])); m++)
			{
				float mx = pos[0] - mines[m].at[0], my = pos[1] - mines[m].at[1];

				if (mines[m].scene == which && sqrtf(mx * mx + my * my) < nearestMine)
				{
					nearestMine = sqrtf(mx * mx + my * my);
				}
			}
		}
		ETA_RouteFrame();
		if (traceCount - tracesBefore > maxTraces) maxTraces = traceCount - tracesBefore;

		if ((eta_route.steering || eta_route.aimSet) && steeredBy < 0.0f) steeredBy = t;

		/* "Crouch, low ceiling ahead": a player who hears it crouches, and
		   stands when told to and there is room. */
		if (eta_route.crouched)
		{
			bodyMaxs[2] = 24.0f;
			crouched    = 1;
		}
		else if (bodyMaxs[2] < 48.0f)
		{
			vec3_t  standing = { 18, 18, 48 };
			trace_t room;

			trap_CM_BoxTrace(&room, pos, pos, bodyMins, standing, 0, MASK_PLAYERSOLID);
			if (!room.startsolid)
			{
				bodyMaxs[2] = 48.0f;
			}
		}

		/* "Jump up, ahead": a player who hears it jumps when the ledge is
		   in front of them. */
		if (eta_route.saidJump >= 0 && eta_route.saidJump != saidJump)
		{
			saidJump   = eta_route.saidJump;
			toldJumpAt = t;
		}

		if (eta_route.saidStairs && (!stairs || !VectorCompare(stairsAt, eta_route.stairsAt)))
		{
			stairs++;
			VectorCopy(eta_route.stairsAt, stairsAt);
		}

		{
			vec3_t flat;
			VectorSubtract(eta_marker.origin, pos, flat);
			flat[2] = 0;
			if (scene->square ? (fabsf(flat[0]) < 512.0f && fabsf(flat[1]) < 512.0f)
			                  : (VectorLength(flat) < ETA_MARKER_ARRIVE_METERS / ETA_QU_TO_METERS
			                     && fabsf(eta_marker.origin[2] - pos[2]) < 64.0f))
			{
				reached = 1;
				break;
			}
		}

		ETA_MarkerTarget(target);

		/* Is the ping pointing back the way the player came? Measured
		   against where the way itself goes a few squares on, while
		   there is a way and the player is on it: a detour round a wall
		   is the way, and is not counted; the ping turning the player
		   round on a way that goes on ahead is. */
		{
			ETA_PathState state = ETA_PathFinder_State();
			int           count = ETA_PathFinder_PointCount();

			if ((state == ETA_PATH_FOUND || state == ETA_PATH_PARTIAL) && count > 0 && !walkerClimbing
			    && (eta_route.steering || eta_route.aimSet))
			{
				vec3_t onward, near, toPing, toWay;
				int    at = eta_route.along + 3 < count ? eta_route.along + 3 : count - 1;

				ETA_PathFinder_Point(eta_route.along, near);
				ETA_PathFinder_Point(at, onward);
				VectorSubtract(target, pos, toPing);
				VectorSubtract(onward, pos, toWay);
				toPing[2] = toWay[2] = 0.0f;
				if (Distance(pos, near) < ETA_ROUTE_STRAY && VectorNormalize(toWay) > 48.0f
				    && VectorNormalize(toPing) > 1.0f && DotProduct(toPing, toWay) < -0.5f)
				{
					backward += dt;
				}
			}
		}

		/* At a ladder's foot, with the way going up it: F, and the
		   game climbs. */
		if (!walkerClimbing && onGround)
		{
			for (l = 0; l < ladderCount; l++)
			{
				float fx = pos[0] - ladderFoot[l][0], fy = pos[1] - ladderFoot[l][1];

				if (fx * fx + fy * fy < 40.0f * 40.0f && fabsf(pos[2] - ladderFoot[l][2]) < 30.0f
				    && Distance(target, ladderTop[l]) < 4.0f)
				{
					walkerClimbing = 1;
					climbs++;
					break;
				}
			}
		}

		VectorCopy(pos, was);

		if (walkerClimbing)
		{
			vec3_t up;

			VectorCopy(pos, up);
			up[2] += 150.0f * dt;
			trap_CM_BoxTrace(&tr, pos, up, bodyMins, bodyMaxs, 0, MASK_PLAYERSOLID);
			if (tr.fraction < 1.0f)
			{
				walkerClimbing = 0;
			}
			else
			{
				VectorCopy(up, pos);
				for (l = 0; l < ladderCount; l++)
				{
					if (Distance(target, ladderTop[l]) < 4.0f && pos[2] >= ladderTop[l][2] + 2.0f)
					{
						walkerClimbing = 0;
					}
				}
			}
			vz = 0.0f;
			pinned = 0.0f;
		}
		else
		{
			VectorSubtract(target, pos, dir);
			dir[2] = 0;
			if (VectorNormalize(dir) < 1.0f)
			{
				/* The ping is under the walker's feet: nowhere to go. */
				pinned += dt;
			}
			else
			{
				VectorScale(dir, 320.0f * dt, step);
				VectorAdd(pos, step, next);
				trap_CM_BoxTrace(&tr, pos, next, bodyMins, bodyMaxs, 0, MASK_PLAYERSOLID);
				if (tr.fraction >= 1.0f)
				{
					VectorCopy(next, pos);
				}
				else
				{
					/* Slide along the wall, the way the game does. */
					int a;
					blocked = 1;
					for (a = 0; a < 2; a++)
					{
						vec3_t along;
						VectorCopy(pos, along);
						along[a] += step[a];
						trap_CM_BoxTrace(&tr, pos, along, bodyMins, bodyMaxs, 0, MASK_PLAYERSOLID);
						if (tr.fraction >= 1.0f) VectorCopy(along, pos);
					}
				}

				/* Up against the ledge it was told to jump onto. */
				if (blocked && onGround && t - toldJumpAt < 6.0f)
				{
					leftGroundAt = pos[2];
					vz       = 270.0f;
					onGround = 0;
					jumps++;
				}

				if (Distance(was, pos) < 320.0f * dt * 0.3f && onGround)
				{
					pinned += dt;
				}
				else
				{
					pinned = 0.0f;
				}
			}

			/* Up, or down onto the floor: the game's jump and gravity. */
			vz -= 800.0f * dt;
			if (vz > 0.0f)
			{
				vec3_t up;

				VectorCopy(pos, up);
				up[2] += vz * dt;
				trap_CM_BoxTrace(&tr, pos, up, bodyMins, bodyMaxs, 0, MASK_PLAYERSOLID);
				if (tr.fraction < 1.0f) vz = 0.0f;
				else VectorCopy(up, pos);
			}
			else
			{
				vec3_t from, to;

				VectorCopy(pos, from);
				from[2] += 18.0f;
				VectorCopy(pos, to);
				to[2] += vz * dt;
				/* Walking, the game keeps the feet on a stair going down
				   rather than letting the player fly off each step. */
				if (onGround && to[2] > pos[2] - 18.0f)
				{
					to[2] = pos[2] - 18.0f;
				}
				trap_CM_BoxTrace(&tr, from, to, footMins, footMaxs, 0, MASK_PLAYERSOLID);
				if (!tr.startsolid && tr.fraction < 1.0f)
				{
					if (!onGround && leftGroundAt - tr.endpos[2] > worstFall)
					{
						worstFall = leftGroundAt - tr.endpos[2];
					}
					pos[2]   = tr.endpos[2];
					vz       = 0.0f;
					onGround = 1;
				}
				else if (!tr.startsolid)
				{
					if (onGround)
					{
						leftGroundAt = pos[2];
					}
					pos[2]   = to[2];
					onGround = 0;
				}
			}
		}

		if (pinned > worstPinned) worstPinned = pinned;

		t += dt;
		cg.time += (int)(dt * 1000.0f);
		frames++;
	}

	printf("SCENE %d %s reached=%d time=%.1f steeredBy=%.2f worstPinned=%.2f maxTraces=%ld jumps=%d climbs=%d backward=%.2f fell=%.0f\n",
	       which, scene->name, reached, t, steeredBy, worstPinned, maxTraces, jumps, climbs, backward, worstFall);
	printf("STAIRS %d %d\n", which, stairs);
	printf("CROUCHED %d %d\n", which, crouched);
	printf("MINE %d %.0f\n", which, nearestMine);
	return reached;
}

int main(void)
{
	int i;

	for (i = 0; i < (int)(sizeof(scenes) / sizeof(scenes[0])); i++)
	{
		RunScene(i);
	}
	return 0;
}
'''


def read(root, relative):
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        sys.exit("no %s under %s - is the patch series applied?"
                 % (relative, root))
    with open(path, "r", errors="replace") as handle:
        return handle.read()


def lift(text):
    typedef = re.search(r"typedef struct\s*\{[^}]*?qboolean active;.*?\}\s*eta_marker_t;", text, re.S)
    arrive = re.search(r"#define ETA_MARKER_ARRIVE_METERS [^\n]+", text)
    beacon = re.search(r"#define ETA_MARKER_BEACON_DISTANCE [^\n]+", text)
    start = text.find("#define ETA_ROUTE_CELL")
    end = text.find("/**\n * @brief The distance to the marker, in metres.")
    if not typedef or not arrive or not beacon or start < 0 or end < start:
        sys.exit("could not lift the marker's route code out of %s - the "
                 "feature this test walks is gone" % COMMANDMAP)
    # A map square is 1024 across in the walk's world.
    return "\n".join([typedef.group(0), "static eta_marker_t eta_marker;",
                      arrive.group(0), beacon.group(0),
                      "static float ETA_MarkerSquareRadius(void) { return 460.0f; }",
                      text[start:end]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="ET: Legacy checkout, patch series applied")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    commandmap = read(root, COMMANDMAP)
    source_text = HARNESS.replace("%(LIFTED)s", lift(commandmap))

    library = sorted(glob.glob(os.path.join(REPO, "src", "accessibility", "**", "*.c"),
                               recursive=True))

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "walk.c")
        binary = os.path.join(tmp, "walk")
        with open(source, "w") as handle:
            handle.write(source_text)
        build = subprocess.run(
            ["cc", "-std=gnu99", "-O1", "-w", "-DFEATURE_ACCESSIBILITY",
             "-I", os.path.join(root, "src", "qcommon"),
             "-I", os.path.join(root, "src"),
             "-I", os.path.join(REPO, "src", "accessibility"),
             "-o", binary, source,
             os.path.join(root, "src", "qcommon", "q_shared.c"),
             os.path.join(root, "src", "qcommon", "q_math.c")] + library + ["-lm"],
            capture_output=True, text=True)
        if build.returncode != 0:
            sys.exit("the lifted route code does not build in the walk "
                     "harness:\n%s" % build.stderr[-3000:])
        run = subprocess.run([binary], capture_output=True, text=True, timeout=600)

    failures = []
    scenes = re.findall(
        r"SCENE (\d+) (.*?) reached=(\d) time=([\d.]+) steeredBy=([-\d.]+) "
        r"worstPinned=([\d.]+) maxTraces=(\d+) jumps=(\d+) climbs=(\d+) "
        r"backward=([\d.]+) fell=([\d.]+)", run.stdout)
    if len(scenes) != 18:
        sys.exit("the walk harness did not report every scene:\n%s%s"
                 % (run.stdout, run.stderr[-2000:]))

    stairs = dict((int(n), int(c)) for n, c in re.findall(r"STAIRS (\d+) (\d+)", run.stdout))
    # "Stairs up, ahead" before a flight on the way, and "Stairs down"
    # coming off the balcony; nothing on open ground or round a building.
    for number, want in ((6, True), (13, True), (3, False), (0, False)):
        told = stairs.get(number, 0)
        if want and not told:
            failures.append("scene %d: the stairs on the way were never told of" % number)
        elif not want and told:
            failures.append("scene %d: stairs were told of on a way with none" % number)
    if not [f for f in failures if "stairs" in f]:
        print("[walk] the stairs on the way are told of, and nothing is where there are none")

    # "Crouch, low ceiling ahead" under the beam, and nowhere else.
    crouched = dict((int(n), int(c)) for n, c in re.findall(r"CROUCHED (\d+) (\d+)", run.stdout))
    if not crouched.get(12):
        failures.append("scene 12: the walker was never told to crouch under the beam")
    elif [n for n, c in crouched.items() if c and n != 12]:
        failures.append("scenes %r: told to crouch with no low ceiling on the way" % [n for n, c in crouched.items() if c and n != 12])
    else:
        print("[walk] told to crouch under the beam, and nowhere else")

    # A landmine goes off for a player within 64 units of it
    # (sEntWillTriggerMine). Seen before setting off, or halfway there,
    # the way keeps the walker further off than that; in the one doorway,
    # it goes through.
    trigger = re.search(r"#define\s+LANDMINE_TRIGGER_DIST\s+([\d.]+)f",
                        read(root, os.path.join("src", "game", "g_missile.c")))
    nearest = dict((int(n), float(d)) for n, d in re.findall(r"MINE (\d+) ([\d.]+)", run.stdout))
    if not trigger:
        failures.append("the game's landmine trigger distance is not where this walk was built on")
    else:
        for number in (15, 16):
            if nearest.get(number, 0.0) <= float(trigger.group(1)):
                failures.append("scene %d: the walker came %.0f units from a mine it had been shown, "
                                "which goes off at %s" % (number, nearest.get(number, 0.0), trigger.group(1)))
        if not [f for f in failures if "mine" in f]:
            print("[walk] the way keeps %.0f and %.0f units off a mine shown before setting off and halfway "
                  "there; it goes off at %s" % (nearest[15], nearest[16], trigger.group(1)))

    for number, name, reached, taken, steered, pinned, traces, jumps, climbs, backward, fell in scenes:
        number, taken, steered, pinned, traces, jumps, climbs, backward, fell = (
            int(number), float(taken), float(steered), float(pinned), int(traces),
            int(jumps), int(climbs), float(backward), float(fell))
        line = ("%s: reached in %.1fs, following the way after %.1fs, "
                "longest against a wall %.1fs, at most %d traces a frame"
                % (name, taken, steered, pinned, traces))
        if reached != "1":
            failures.append("%s: never got to the marker - %s" % (name, line))
            continue
        # Where the wall is right in front of the walker, the ping has to
        # leave the straight line at once. On open ground and before the
        # far city wall, walking straight to start with is right; the
        # time spent against a wall, below, is what holds those.
        if number in (0, 1, 2, 5, 10) and not 0.0 <= steered <= 1.0:
            failures.append(
                "%s: the ping was still pointing straight at the marker a "
                "second after it went down, into the wall - %s" % (name, line))
        if pinned > 1.0:
            failures.append(
                "%s: the walker spent %.1fs pushed against a wall following "
                "the ping - %s" % (name, pinned, line))
        # The way up: stairs are walked, not jumped; the ledge is reached
        # by the jump the walker was told of; the ladder is climbed.
        if number in (6, 9) and jumps:
            failures.append("%s: the walker was told to jump on a way that "
                            "has stairs - %s" % (name, line))
        if number == 7 and not jumps:
            failures.append("%s: the ledge was reached without a jump being "
                            "said - %s" % (name, line))
        if number == 8 and not climbs:
            failures.append("%s: the floor above was reached without the "
                            "ladder - %s" % (name, line))
        # The tester heard "the way goes south-west" with the marker, and
        # the way itself, north-east: the ping turned them round. On a
        # way that goes on ahead it never points back down it.
        if backward > 0.5:
            failures.append("%s: the ping pointed back the way the player "
                            "came for %.1fs while the way went on ahead - %s"
                            % (name, backward, line))
        # Off the balcony is a seven metre drop; the way is the stairs.
        if number == 13 and fell > 96.0:
            failures.append("%s: the walker followed the ping off an edge "
                            "and fell %.0f units - %s" % (name, fell, line))
        # Through the alley is under 5 seconds' walk; round by the
        # doorway, more than 10.
        if number == 14 and taken > 7.0:
            failures.append("%s: the way went the long way round, not "
                            "through the alley - %s" % (name, line))
        if traces > 800:
            failures.append(
                "%s: %d traces in one frame is a stutter - %s" % (name, traces, line))
        if not failures or name not in failures[-1]:
            print("[walk] " + line)

    if failures:
        print()
        for failure in failures:
            print("[walk] FAIL %s" % failure)
        return 1

    print("marker_route_sim_test: following the ping walks round the walls to "
          "the marker in every scene")
    return 0


if __name__ == "__main__":
    sys.exit(main())

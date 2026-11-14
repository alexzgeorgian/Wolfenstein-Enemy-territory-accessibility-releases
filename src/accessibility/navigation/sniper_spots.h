#pragma once

#include <stddef.h>

#include "place_classifier.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Sniper spots: places up off the ground that look out a long way.
 *
 * The tester asked for the map to help them choose a good spot to use
 * the sniper rifle from. A sighted player picks one by looking: a roof,
 * a balcony or the edge of a terrace, with open ground in front of it
 * that enemies have to cross. The cgame looks for the same thing in the
 * map's own walls and floors - every raised floor there is, and from
 * each, in sixteen directions, how much of the ground out there could be
 * seen from a standing player's eyes, and how far below it lies - and
 * this decides which of those places are worth going to, and says them.
 *
 * Kept free of the engine so the rules can be tested on their own.
 */

#define ETA_SPOT_DIRECTIONS 16   /* clockwise from north, 22.5 degrees apart */
#define ETA_SPOT_SECTOR     4    /* directions in the arc a spot is judged on: 90 degrees */

/* What was seen from one place, direction by direction. */
typedef struct ETA_SpotView
{
    float seenMeters[ETA_SPOT_DIRECTIONS];  /* ground in sight, added up along the look */
    float farMeters[ETA_SPOT_DIRECTIONS];   /* the furthest ground in sight */
    float dropSum[ETA_SPOT_DIRECTIONS];     /* metres down to each piece of ground seen */
    int   dropCount[ETA_SPOT_DIRECTIONS];
} ETA_SpotView;

/* The best quarter of the view. */
typedef struct ETA_SpotRating
{
    float score;         /* ground in sight across the arc, metres */
    float bearing;       /* the middle of the arc, degrees clockwise from north */
    int   viewMeters;    /* the furthest ground in sight across it */
    int   heightMeters;  /* how far above that ground the spot stands, on average */
} ETA_SpotRating;

void ETA_SpotView_Clear(ETA_SpotView *view);

/* One piece of ground looked for in a direction, metres out: whether it
   could be seen, and how far below the spot's floor it lies. */
void ETA_SpotView_Add(ETA_SpotView *view, int direction, float meters, int seen,
                      float dropMeters, float stepMeters);

ETA_SpotRating ETA_Spot_Rate(const ETA_SpotView *view);

/* Up off the ground and looking out a long way. */
#define ETA_SPOT_MIN_HEIGHT_METERS 2.5f
#define ETA_SPOT_MIN_VIEW_METERS   30.0f
#define ETA_SPOT_MIN_SCORE_METERS  40.0f

int  ETA_Spot_Worth(const ETA_SpotRating *rating);

/* "Rooftop, sees 60 meters to the south-east, 6 meters up". */
void ETA_Spot_Text(ETA_PlaceKind kind, const ETA_SpotRating *rating, char *out, size_t outSize);

/* "south-east" for a bearing. */
const char *ETA_Spot_Compass(float bearing);

/*
 * The spots found on a map. Two places close together are the same spot,
 * and the better of the two is kept; with the list full, a better spot
 * takes the place of the worst.
 */
#define ETA_SPOT_MAX         64
#define ETA_SPOT_APART_UNITS 768.0f   /* closer than this, twenty metres: the same spot */

typedef struct ETA_Spot
{
    float          origin[3];
    ETA_PlaceKind  kind;
    ETA_SpotRating rating;
    int            unreachable;   /* the way there was looked for and not found */
    int            checked;       /* whether the way there has been looked for */
} ETA_Spot;

typedef struct ETA_SpotList
{
    ETA_Spot spots[ETA_SPOT_MAX];
    int      count;
} ETA_SpotList;

void ETA_SpotList_Clear(ETA_SpotList *list);

/* Returns 1 when the spot was kept. */
int  ETA_SpotList_Offer(ETA_SpotList *list, const float origin[3], ETA_PlaceKind kind,
                        const ETA_SpotRating *rating);

/* The spots that can still be got to, nearest first: their indexes in
   the list. Returns how many. */
int  ETA_SpotList_Nearest(const ETA_SpotList *list, const float from[3], int *out, int max);

#ifdef __cplusplus
}
#endif

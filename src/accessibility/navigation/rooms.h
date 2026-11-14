#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Rooms: the indoor places of a map, found and named, to walk to.
 *
 * The tester asked for the rooms to be trackable on the map, as the
 * streets and the sniper spots are. The game has no list of rooms; it
 * has walls, floors and roofs. The cgame looks over the whole map on a
 * grid of points, and at each floor with a roof over it - not open sky -
 * says so here. Points next to each other on the grid, at the same
 * height, with nothing between them a player could not walk through,
 * are the same room; a wall between them makes two. A doorway narrower
 * than the grid's spacing is mostly missed by the straight look between
 * two points, which is what keeps two rooms joined by a door apart.
 *
 * Kept free of the engine so the grouping can be tested on its own: the
 * look between two points is the caller's.
 */

#define ETA_ROOM_MAX         96
#define ETA_ROOM_MAX_SAMPLES 4096
#define ETA_ROOM_MAX_GRID    160   /* points to a side of the map's grid */
#define ETA_ROOM_MIN_SAMPLES 2     /* fewer: a porch, an arch, not a room */

typedef struct ETA_RoomSample
{
    int   column, row;   /* on the grid, from the map's north-west corner */
    float origin[3];     /* a player standing there */
    int   upper;         /* a floor with another under it */
} ETA_RoomSample;

typedef struct ETA_Room
{
    float origin[3];      /* the point nearest its middle */
    float minX, minY, maxX, maxY;
    int   samples;
    int   upper;
    char  name[48];       /* the map's own name for the place, or "" */
    int   unreachable;    /* the way there was looked for and not found */
    int   checked;
} ETA_Room;

typedef struct ETA_RoomList
{
    ETA_Room rooms[ETA_ROOM_MAX];
    int      count;
} ETA_RoomList;

/* Whether a player could walk straight from one point to the next. */
typedef int (*ETA_RoomLinkFn)(void *context, const float from[3], const float to[3]);

/*
 * Groups the points into rooms. 'spacing' is the grid's, in units, for
 * the rooms' sizes. The biggest rooms are kept when there are more than
 * fit. Returns how many rooms there are.
 */
int  ETA_Rooms_Build(const ETA_RoomSample *samples, int count, float spacing,
                     ETA_RoomLinkFn link, void *context, ETA_RoomList *out);

/* "Water Pump, ground floor, 8 by 6 meters"; "Room, upper floor, ..."
   when the map has no name for the place. */
void ETA_Room_Text(const ETA_Room *room, float spacing, char *out, size_t outSize);

/* The rooms that can still be got to, nearest first. */
int  ETA_RoomList_Nearest(const ETA_RoomList *list, const float from[3], int *out, int max);

/* How many rooms stand in a box of the map: for the map survey. */
int  ETA_RoomList_CountIn(const ETA_RoomList *list, float minX, float minY, float maxX, float maxY);

#ifdef __cplusplus
}
#endif

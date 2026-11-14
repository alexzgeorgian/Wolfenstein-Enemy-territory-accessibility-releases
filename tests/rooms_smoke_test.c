/*
 * The rooms of a map, from points on a grid with a roof overhead.
 *
 * The tester asked for the rooms to be trackable on the map. Points next
 * to each other at the same height with nothing in between are one
 * room; a wall between them makes two, and a floor above another is
 * another room. Pinned here with rooms drawn as points, and a wall as a
 * line no look crosses.
 */

#include "navigation/rooms.h"
#include "smoke_check.h"

#include <string.h>

static ETA_RoomSample gSamples[64];
static int            gCount;

static void Point(int column, int row, float z, int upper)
{
    ETA_RoomSample *s = &gSamples[gCount++];

    s->column    = column;
    s->row       = row;
    s->origin[0] = (float)column * 128.0f;
    s->origin[1] = -(float)row * 128.0f;
    s->origin[2] = z;
    s->upper     = upper;
}

/* A wall along x = 320, between columns 2 and 3. */
static int Link(void *context, const float from[3], const float to[3])
{
    (void)context;
    return !((from[0] < 320.0f) != (to[0] < 320.0f));
}

int main(void)
{
    static ETA_RoomList list;
    char                text[96];
    int                 order[ETA_ROOM_MAX], n, r, c;
    float               here[3] = { 0.0f, 0.0f, 0.0f };

    SMOKE_BANNER("rooms");

    CHECK(ETA_Rooms_Build(NULL, 0, 128.0f, Link, NULL, &list) == 0);
    CHECK(ETA_Rooms_Build(gSamples, 1, 128.0f, NULL, NULL, &list) == 0);

    /* Two rooms side by side, the wall between them: columns 0-2 and
       3-5, rows 0-2. A floor above the second, rows 0-1. And one point on
       its own, a porch, which is no room. */
    gCount = 0;
    for (r = 0; r < 3; r++)
    {
        for (c = 0; c < 6; c++)
        {
            Point(c, r, 24.0f, 0);
        }
    }
    for (r = 0; r < 2; r++)
    {
        for (c = 3; c < 6; c++)
        {
            Point(c, r, 24.0f + 160.0f, 1);
        }
    }
    Point(10, 10, 24.0f, 0);

    n = ETA_Rooms_Build(gSamples, gCount, 128.0f, Link, NULL, &list);
    CHECK(n == 3);
    CHECK(list.rooms[0].samples == 9);
    CHECK(list.rooms[1].samples == 9);
    CHECK(list.rooms[2].samples == 6);
    CHECK(!list.rooms[0].upper && list.rooms[2].upper);

    /* Marked on its own middle point. */
    CHECK(list.rooms[0].origin[0] == 128.0f && list.rooms[0].origin[1] == -128.0f);

    /* Said with its size: three points across is three squares. */
    ETA_Room_Text(&list.rooms[0], 128.0f, text, sizeof(text));
    CHECK(strcmp(text, "Room, ground floor, 10 by 10 meters") == 0);
    strcpy(list.rooms[2].name, "Water Pump");
    ETA_Room_Text(&list.rooms[2], 128.0f, text, sizeof(text));
    CHECK(strcmp(text, "Water Pump, upper floor, 10 by 7 meters") == 0);

    /* Nearest first; one with no way in left out. */
    here[0] = 700.0f;
    n = ETA_RoomList_Nearest(&list, here, order, ETA_ROOM_MAX);
    CHECK(n == 3);
    CHECK(order[0] == 1 || order[0] == 2);
    CHECK(order[2] == 0);
    list.rooms[1].unreachable = 1;
    n = ETA_RoomList_Nearest(&list, here, order, ETA_ROOM_MAX);
    CHECK(n == 2);
    CHECK(order[0] == 2);

    /* Counted by square, for the map survey. */
    CHECK(ETA_RoomList_CountIn(&list, -64.0f, -400.0f, 320.0f, 64.0f) == 1);
    CHECK(ETA_RoomList_CountIn(&list, 320.0f, -400.0f, 1000.0f, 64.0f) == 1);   /* the one with no way in left out */
    CHECK(ETA_RoomList_CountIn(NULL, 0, 0, 1, 1) == 0);

    return SMOKE_REPORT("rooms");
}

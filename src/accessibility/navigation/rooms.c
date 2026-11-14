#include "rooms.h"

#include <stdio.h>
#include <string.h>

#define ETA_ROOM_LEVEL 48.0f   /* further apart in height than this: another floor */

static int gRoomOf[ETA_ROOM_MAX_SAMPLES];
static int gQueue[ETA_ROOM_MAX_SAMPLES];
static int gFirst[ETA_ROOM_MAX_GRID][ETA_ROOM_MAX_GRID];
static int gNext[ETA_ROOM_MAX_SAMPLES];

static float ETA_Room_Abs(float v)
{
    return v < 0.0f ? -v : v;
}

static void ETA_Room_Fill(ETA_Room *room, const ETA_RoomSample *samples, const int *members, int n)
{
    float sumX = 0.0f, sumY = 0.0f, best = 1.0e30f;
    int   i, upper = 0;

    memset(room, 0, sizeof(*room));
    room->minX = room->maxX = samples[members[0]].origin[0];
    room->minY = room->maxY = samples[members[0]].origin[1];

    for (i = 0; i < n; i++)
    {
        const ETA_RoomSample *s = &samples[members[i]];

        sumX += s->origin[0];
        sumY += s->origin[1];
        upper += s->upper ? 1 : 0;
        if (s->origin[0] < room->minX) room->minX = s->origin[0];
        if (s->origin[0] > room->maxX) room->maxX = s->origin[0];
        if (s->origin[1] < room->minY) room->minY = s->origin[1];
        if (s->origin[1] > room->maxY) room->maxY = s->origin[1];
    }
    sumX /= (float)n;
    sumY /= (float)n;

    /* Where to send the player: the room's own point nearest its middle,
       so an L-shaped room is not marked on the wall inside its corner. */
    for (i = 0; i < n; i++)
    {
        const ETA_RoomSample *s = &samples[members[i]];
        float dx = s->origin[0] - sumX, dy = s->origin[1] - sumY;

        if (dx * dx + dy * dy < best)
        {
            best            = dx * dx + dy * dy;
            room->origin[0] = s->origin[0];
            room->origin[1] = s->origin[1];
            room->origin[2] = s->origin[2];
        }
    }

    room->samples = n;
    room->upper   = upper * 2 > n;
}

int ETA_Rooms_Build(const ETA_RoomSample *samples, int count, float spacing,
                    ETA_RoomLinkFn link, void *context, ETA_RoomList *out)
{
    int i, start;

    (void)spacing;

    if (!out)
    {
        return 0;
    }
    out->count = 0;

    if (!samples || count <= 0 || !link)
    {
        return 0;
    }
    if (count > ETA_ROOM_MAX_SAMPLES)
    {
        count = ETA_ROOM_MAX_SAMPLES;
    }

    for (i = 0; i < ETA_ROOM_MAX_GRID; i++)
    {
        int j;

        for (j = 0; j < ETA_ROOM_MAX_GRID; j++)
        {
            gFirst[i][j] = -1;
        }
    }

    for (i = 0; i < count; i++)
    {
        gRoomOf[i] = -1;
        gNext[i]   = -1;

        if (samples[i].column < 0 || samples[i].column >= ETA_ROOM_MAX_GRID
            || samples[i].row < 0 || samples[i].row >= ETA_ROOM_MAX_GRID)
        {
            gRoomOf[i] = -2;   /* off the grid: never part of a room */
            continue;
        }

        gNext[i] = gFirst[samples[i].row][samples[i].column];
        gFirst[samples[i].row][samples[i].column] = i;
    }

    for (start = 0; start < count; start++)
    {
        int head = 0, tail = 0;

        if (gRoomOf[start] != -1)
        {
            continue;
        }

        gRoomOf[start]  = start;
        gQueue[tail++]  = start;

        while (head < tail)
        {
            static const int steps[4][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } };
            int              at = gQueue[head++], s;

            for (s = 0; s < 4; s++)
            {
                int c = samples[at].column + steps[s][0];
                int r = samples[at].row + steps[s][1];
                int k;

                if (c < 0 || c >= ETA_ROOM_MAX_GRID || r < 0 || r >= ETA_ROOM_MAX_GRID)
                {
                    continue;
                }

                for (k = gFirst[r][c]; k >= 0; k = gNext[k])
                {
                    if (gRoomOf[k] != -1
                        || ETA_Room_Abs(samples[k].origin[2] - samples[at].origin[2]) > ETA_ROOM_LEVEL
                        || !link(context, samples[at].origin, samples[k].origin))
                    {
                        continue;
                    }

                    gRoomOf[k]     = start;
                    gQueue[tail++] = k;
                }
            }
        }

        if (tail < ETA_ROOM_MIN_SAMPLES)
        {
            continue;
        }

        /* Kept when there is room, or in place of the smallest. */
        {
            int slot = -1;

            if (out->count < ETA_ROOM_MAX)
            {
                slot = out->count++;
            }
            else
            {
                int smallest = 0;

                for (i = 1; i < out->count; i++)
                {
                    if (out->rooms[i].samples < out->rooms[smallest].samples)
                    {
                        smallest = i;
                    }
                }
                if (out->rooms[smallest].samples < tail)
                {
                    slot = smallest;
                }
            }

            if (slot >= 0)
            {
                ETA_Room_Fill(&out->rooms[slot], samples, gQueue, tail);
            }
        }
    }

    return out->count;
}

void ETA_Room_Text(const ETA_Room *room, float spacing, char *out, size_t outSize)
{
    int across, along;

    if (!out || outSize == 0)
    {
        return;
    }
    out[0] = '\0';
    if (!room)
    {
        return;
    }

    /* Each point stands for a square of the grid around it. */
    across = (int)((room->maxX - room->minX + spacing) * 0.0254f + 0.5f);
    along  = (int)((room->maxY - room->minY + spacing) * 0.0254f + 0.5f);

    snprintf(out, outSize, "%s, %s floor, %d by %d meters",
             room->name[0] ? room->name : "Room",
             room->upper ? "upper" : "ground",
             across > along ? across : along, across > along ? along : across);
}

static float ETA_Room_Flat(const float a[3], const float b[3])
{
    float dx = a[0] - b[0], dy = a[1] - b[1];

    return dx * dx + dy * dy;
}

int ETA_RoomList_Nearest(const ETA_RoomList *list, const float from[3], int *out, int max)
{
    int count = 0, i, j;

    if (!list || !from || !out || max <= 0)
    {
        return 0;
    }

    for (i = 0; i < list->count && count < max; i++)
    {
        if (!list->rooms[i].unreachable)
        {
            out[count++] = i;
        }
    }

    for (i = 1; i < count; i++)
    {
        int   index = out[i];
        float d     = ETA_Room_Flat(list->rooms[index].origin, from);

        for (j = i; j > 0 && ETA_Room_Flat(list->rooms[out[j - 1]].origin, from) > d; j--)
        {
            out[j] = out[j - 1];
        }
        out[j] = index;
    }

    return count;
}

int ETA_RoomList_CountIn(const ETA_RoomList *list, float minX, float minY, float maxX, float maxY)
{
    int i, count = 0;

    if (!list)
    {
        return 0;
    }

    for (i = 0; i < list->count; i++)
    {
        const ETA_Room *room = &list->rooms[i];

        if (!room->unreachable && room->origin[0] >= minX && room->origin[0] < maxX
            && room->origin[1] >= minY && room->origin[1] < maxY)
        {
            count++;
        }
    }

    return count;
}

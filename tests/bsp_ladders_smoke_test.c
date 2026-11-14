/*
 * The ladder reader, against map files built here byte by byte.
 *
 * Every ladder sound in the game comes from this reader, and a reader
 * that is a little wrong is worse than none: a box off by a sign puts
 * the sound in the middle of a room with no ladder in it, and a player
 * who cannot see walks toward it and finds a wall. So the boxes are
 * checked to the unit against brushes whose sizes are known, along with
 * the things a real map does that a first try would trip on - lumps in
 * any order, a file handed over a few bytes at a time, ladders built
 * from several brushes stacked up, ladders painted on every face, and
 * ladders on doors and lifts, which are not the world's and have no
 * fixed place.
 */

#include "map/bsp_ladders.h"
#include "smoke_check.h"

#include <string.h>

#define SURF_LADDER 0x8

/* ---- a tiny map file ------------------------------------------------ */

typedef struct
{
    unsigned char data[16384];
    int           size;
} Bsp;

typedef struct
{
    float mins[3], maxs[3];
    int   ladderFaces;   /* bit per axial face: 1 -x, 2 +x, 4 -y, 8 +y, 16 -z, 32 +z */
} Box;

static void PutInt(unsigned char *p, int value)
{
    unsigned int v = (unsigned int)value;

    p[0] = (unsigned char)v;
    p[1] = (unsigned char)(v >> 8);
    p[2] = (unsigned char)(v >> 16);
    p[3] = (unsigned char)(v >> 24);
}

static void PutFloat(unsigned char *p, float value)
{
    int bits;

    memcpy(&bits, &value, sizeof(bits));
    PutInt(p, bits);
}

/*
 * Lays out boxes as brushes, the first worldCount of them in the world
 * model and the rest in model 1, with each lump at the place order[]
 * gives it: order lists lump numbers, first in the file first.
 */
static void BuildBsp(Bsp *bsp, const Box *boxes, int count, int worldCount, const int order[5])
{
    unsigned char shaders[2 * 72], planes[64 * 16], models[2 * 40], brushes[16 * 12], sides[64 * 8];
    int           sizes[17] = { 0 };
    unsigned char *bodies[17] = { 0 };
    int           planeCount = 0, sideCount = 0;
    int           offset = 8 + 17 * 8;
    int           i, f;

    memset(bsp, 0, sizeof(*bsp));
    memset(shaders, 0, sizeof(shaders));
    memset(models, 0, sizeof(models));

    /* shader 0 is a wall, shader 1 a ladder */
    memcpy(shaders, "textures/wall", 13);
    memcpy(shaders + 72, "common/ladder", 13);
    PutInt(shaders + 72 + 64, SURF_LADDER);

    for (i = 0; i < count; i++)
    {
        PutInt(brushes + i * 12, sideCount);
        PutInt(brushes + i * 12 + 4, 7);
        PutInt(brushes + i * 12 + 8, 0);

        for (f = 0; f < 6; f++)
        {
            int   axis = f / 2, positive = f % 2;
            float n[3] = { 0, 0, 0 };

            n[axis] = positive ? 1.0f : -1.0f;
            PutFloat(planes + planeCount * 16, n[0]);
            PutFloat(planes + planeCount * 16 + 4, n[1]);
            PutFloat(planes + planeCount * 16 + 8, n[2]);
            PutFloat(planes + planeCount * 16 + 12, positive ? boxes[i].maxs[axis] : -boxes[i].mins[axis]);

            PutInt(sides + sideCount * 8, planeCount);
            PutInt(sides + sideCount * 8 + 4, (boxes[i].ladderFaces >> f) & 1);
            planeCount++;
            sideCount++;
        }

        /* A bevel, as the compiler adds: not axial, never a ladder. */
        PutFloat(planes + planeCount * 16, 0.7071f);
        PutFloat(planes + planeCount * 16 + 4, 0.7071f);
        PutFloat(planes + planeCount * 16 + 12, 99999.0f);
        PutInt(sides + sideCount * 8, planeCount);
        PutInt(sides + sideCount * 8 + 4, 0);
        planeCount++;
        sideCount++;
    }

    PutInt(models + 32, 0);
    PutInt(models + 36, worldCount);
    PutInt(models + 40 + 32, worldCount);
    PutInt(models + 40 + 36, count - worldCount);

    bodies[1] = shaders;  sizes[1] = (int)sizeof(shaders);
    bodies[2] = planes;   sizes[2] = planeCount * 16;
    bodies[7] = models;   sizes[7] = (int)sizeof(models);
    bodies[8] = brushes;  sizes[8] = count * 12;
    bodies[9] = sides;    sizes[9] = sideCount * 8;

    PutInt(bsp->data, ('P' << 24) + ('S' << 16) + ('B' << 8) + 'I');
    PutInt(bsp->data + 4, 47);

    for (i = 0; i < 5; i++)
    {
        int lump = order[i];

        PutInt(bsp->data + 8 + lump * 8, offset);
        PutInt(bsp->data + 12 + lump * 8, sizes[lump]);
        memcpy(bsp->data + offset, bodies[lump], (size_t)sizes[lump]);
        offset += sizes[lump];
        /* something between the lumps, as there always is */
        offset += 20;
    }

    bsp->size = offset;
}

/* ---- handing it over, a few bytes at a time -------------------------- */

typedef struct
{
    const Bsp *bsp;
    int        position;
    int        chunk;
    int        restarts;
    int        canRestart;
    int        cutAt;      /* pretend the file ends here; 0 for the whole file */
} Reader;

static int ReadSome(void *context, void *buffer, int length)
{
    Reader *reader = (Reader *)context;
    int     end    = reader->cutAt ? reader->cutAt : reader->bsp->size;
    int     take   = length < reader->chunk ? length : reader->chunk;

    if (take > end - reader->position)
    {
        take = end - reader->position;
    }
    if (take <= 0)
    {
        return 0;
    }

    memcpy(buffer, reader->bsp->data + reader->position, (size_t)take);
    reader->position += take;
    return take;
}

static int Restart(void *context)
{
    Reader *reader = (Reader *)context;

    if (!reader->canRestart)
    {
        return 0;
    }
    reader->position = 0;
    reader->restarts++;
    return 1;
}

static int Find(const Bsp *bsp, int chunk, ETA_BspLadder *out, int max)
{
    Reader reader;

    memset(&reader, 0, sizeof(reader));
    reader.bsp        = bsp;
    reader.chunk      = chunk;
    reader.canRestart = 1;
    return ETA_BspLadders_Find(ReadSome, Restart, &reader, out, max);
}

static int Same(float a, float b)
{
    return a - b < 0.01f && b - a < 0.01f;
}

static int BoxIs(const ETA_BspLadder *l, float x0, float y0, float z0, float x1, float y1, float z1)
{
    return Same(l->mins[0], x0) && Same(l->mins[1], y0) && Same(l->mins[2], z0)
           && Same(l->maxs[0], x1) && Same(l->maxs[1], y1) && Same(l->maxs[2], z1);
}

int main(void)
{
    /* What a map has:
       0 - a ladder up a wall, its +x face the one climbed, 0..8 x 0..64 x 0..256
       1 - the same ladder carried on up by a second brush, 256..512
       2 - a wall, no ladder anywhere on it
       3 - a ladder painted on every face, thin across y
       4 - a ladder on a lift, which belongs to model 1 and not the world */
    static const Box boxes[] = {
        { { 0, 0, 0 },          { 8, 64, 256 },       2 },
        { { 0, 0, 256 },        { 8, 64, 512 },       2 },
        { { -512, -512, -16 },  { 512, 512, 0 },      0 },
        { { 1000, 500, 0 },     { 1064, 504, 128 },   63 },
        { { 2000, 2000, 0 },    { 2008, 2064, 256 },  2 },
    };
    static const int q3map2[5] = { 1, 2, 8, 9, 7 };    /* shaders, planes, brushes, sides, models */
    static const int shuffled[5] = { 7, 9, 2, 8, 1 };
    Bsp           bsp;
    ETA_BspLadder ladders[8];
    int           n, chunk;

    printf("[smoke] bsp_ladders\n");

    /* --- the world's ladders, and only those -------------------------- */
    BuildBsp(&bsp, boxes, 5, 4, q3map2);
    n = Find(&bsp, 1 << 20, ladders, 8);
    CHECK(n == 2);
    if (n == 2)
    {
        /* the stacked brushes are one ladder, the whole height */
        CHECK(BoxIs(&ladders[0], 0, 0, 0, 8, 64, 512));
        CHECK(ladders[0].oneFace);
        CHECK(Same(ladders[0].normal[0], 1) && Same(ladders[0].normal[1], 0) && Same(ladders[0].normal[2], 0));

        /* painted all over: the axis it is thin across, and no more */
        CHECK(BoxIs(&ladders[1], 1000, 500, 0, 1064, 504, 128));
        CHECK(!ladders[1].oneFace);
        CHECK(Same(ladders[1].normal[0], 0) && Same(ladders[1].normal[1], 1));
    }

    /* --- whatever order the lumps are in, however the bytes arrive ---- */
    BuildBsp(&bsp, boxes, 5, 4, shuffled);
    for (chunk = 1; chunk <= 4096; chunk *= 7)
    {
        ETA_BspLadder again[8];

        n = Find(&bsp, chunk, again, 8);
        CHECK(n == 2);
        if (n == 2)
        {
            CHECK(BoxIs(&again[0], 0, 0, 0, 8, 64, 512));
            CHECK(BoxIs(&again[1], 1000, 500, 0, 1064, 504, 128));
        }
    }

    /* --- room for one: the first, never a half-built second ----------- */
    BuildBsp(&bsp, boxes, 5, 4, q3map2);
    n = Find(&bsp, 4096, ladders, 1);
    CHECK(n == 1 && BoxIs(&ladders[0], 0, 0, 0, 8, 64, 512));

    /* --- a map with no ladders ---------------------------------------- */
    BuildBsp(&bsp, boxes + 2, 1, 1, q3map2);
    CHECK(Find(&bsp, 4096, ladders, 8) == 0);

    /* --- files that are not a map, or not all of one ------------------ */
    BuildBsp(&bsp, boxes, 5, 4, q3map2);
    {
        Bsp    broken = bsp;
        Reader reader;

        broken.data[0] = 'X';                 /* not a map */
        CHECK(Find(&broken, 4096, ladders, 8) == 0);

        broken = bsp;
        PutInt(broken.data + 4, 46);          /* another game's map */
        CHECK(Find(&broken, 4096, ladders, 8) == 0);

        memset(&reader, 0, sizeof(reader));   /* cut off part way */
        reader.bsp        = &bsp;
        reader.chunk      = 4096;
        reader.canRestart = 1;
        reader.cutAt      = bsp.size / 2;
        CHECK(ETA_BspLadders_Find(ReadSome, Restart, &reader, ladders, 8) == 0);

        memset(&reader, 0, sizeof(reader));   /* cannot be read again */
        reader.bsp   = &bsp;
        reader.chunk = 4096;
        CHECK(ETA_BspLadders_Find(ReadSome, Restart, &reader, ladders, 8) == 0);

        memset(&reader, 0, sizeof(reader));   /* read twice, no more */
        reader.bsp        = &bsp;
        reader.chunk      = 4096;
        reader.canRestart = 1;
        CHECK(ETA_BspLadders_Find(ReadSome, Restart, &reader, ladders, 8) == 2);
        CHECK(reader.restarts == 1);

        CHECK(ETA_BspLadders_Find(NULL, Restart, &reader, ladders, 8) == 0);
        CHECK(ETA_BspLadders_Find(ReadSome, Restart, &reader, NULL, 8) == 0);
        CHECK(ETA_BspLadders_Find(ReadSome, Restart, &reader, ladders, 0) == 0);
    }

    return SMOKE_REPORT("bsp_ladders");
}

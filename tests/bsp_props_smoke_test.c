/*
 * The furniture reader, against map files built here byte by byte.
 *
 * What the narrator says is in a room comes from this reader: a name
 * read wrong says a chair where there is a wall, and a box read wrong
 * says it a metre from where it stands. So the names are checked against
 * shader names from the game's own maps, and the boxes to the unit
 * against surfaces whose corners are known - along with what a real map
 * does: lumps in any order, a file handed over a few bytes at a time,
 * one thing built from many surfaces, a bed frame the shader only calls
 * furniture under the bed it carries, and two chairs side by side that
 * are two chairs.
 */

#include "map/bsp_props.h"
#include "smoke_check.h"

#include <string.h>

/* ---- a tiny map file ------------------------------------------------ */

typedef struct
{
    unsigned char data[65536];
    int           size;
} Bsp;

typedef struct
{
    int   shader;
    float mins[3], maxs[3];   /* the surface is the eight corners of this box */
} Surface;

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

/* Shaders, corners and surfaces, each lump where order[] puts it: order
   lists lump numbers, first in the file first. */
static void BuildBsp(Bsp *bsp, const char *const *shaders, int shaderCount,
                     const Surface *surfaces, int count, const int order[3])
{
    int at = 8 + 8 * 17, i, k;

    memset(bsp, 0, sizeof(*bsp));
    PutInt(bsp->data, ('P' << 24) + ('S' << 16) + ('B' << 8) + 'I');
    PutInt(bsp->data + 4, 47);

    for (k = 0; k < 3; k++)
    {
        int lump = order[k], start = at;

        if (lump == 1)
        {
            for (i = 0; i < shaderCount; i++, at += 72)
            {
                strncpy((char *)bsp->data + at, shaders[i], 63);
            }
        }
        else if (lump == 10)
        {
            for (i = 0; i < count; i++)
            {
                int c;

                for (c = 0; c < 8; c++, at += 44)
                {
                    PutFloat(bsp->data + at, (c & 1) ? surfaces[i].maxs[0] : surfaces[i].mins[0]);
                    PutFloat(bsp->data + at + 4, (c & 2) ? surfaces[i].maxs[1] : surfaces[i].mins[1]);
                    PutFloat(bsp->data + at + 8, (c & 4) ? surfaces[i].maxs[2] : surfaces[i].mins[2]);
                }
            }
        }
        else
        {
            for (i = 0; i < count; i++, at += 104)
            {
                PutInt(bsp->data + at, surfaces[i].shader);
                PutInt(bsp->data + at + 8, 3);
                PutInt(bsp->data + at + 12, i * 8);
                PutInt(bsp->data + at + 16, 8);
            }
        }

        PutInt(bsp->data + 8 + lump * 8, start);
        PutInt(bsp->data + 12 + lump * 8, at - start);
    }

    bsp->size = at;
}

typedef struct
{
    const Bsp *bsp;
    int        position, chunk;
} Reader;

static int ReadSome(void *context, void *buffer, int length)
{
    Reader *reader = (Reader *)context;
    int     take   = length < reader->chunk ? length : reader->chunk;

    if (take > reader->bsp->size - reader->position)
    {
        take = reader->bsp->size - reader->position;
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
    ((Reader *)context)->position = 0;
    return 1;
}

static int Find(const Bsp *bsp, int chunk, ETA_BspProp *out, int max)
{
    Reader reader;

    reader.bsp      = bsp;
    reader.position = 0;
    reader.chunk    = chunk;
    return ETA_BspProps_Find(ReadSome, Restart, &reader, out, max);
}

static const ETA_BspProp *Named(const ETA_BspProp *props, int count, const char *name, int which)
{
    int i;

    for (i = 0; i < count; i++)
    {
        if (!strcmp(props[i].name, name) && which-- == 0)
        {
            return &props[i];
        }
    }
    return NULL;
}

static int Box(const ETA_BspProp *prop, float x0, float y0, float z0, float x1, float y1, float z1)
{
    return prop && prop->mins[0] == x0 && prop->mins[1] == y0 && prop->mins[2] == z0
           && prop->maxs[0] == x1 && prop->maxs[1] == y1 && prop->maxs[2] == z1;
}

int main(void)
{
    static const char *const shaders[] =
    {
        "textures/egypt_walls_sd/stucco07a",           /* 0 a wall */
        "models/mapobjects/furniture/clubchair",       /* 1 */
        "textures/props/box_c01",                      /* 2 */
        "textures/chat/bedlinen_c02",                  /* 3 */
        "models/mapobjects/furniture/wood1",           /* 4 the bed's frame */
        "models/mapobjects/plants_sd/grass_dry3",      /* 5 */
        "textures/egypt_windows_sd/siwa_windows7",     /* 6 */
    };
    static const Surface surfaces[] =
    {
        { 0, { -1000, -1000, -8 }, { 1000, 1000, 0 } },       /* the floor */
        { 1, { 0, 0, 0 }, { 30, 30, 20 } },                   /* a chair: seat and back */
        { 1, { 0, 26, 20 }, { 30, 30, 50 } },
        { 1, { 200, 0, 0 }, { 230, 30, 50 } },                /* another chair, apart */
        { 2, { 400, 0, 0 }, { 448, 48, 48 } },                /* crates stacked */
        { 2, { 400, 0, 48 }, { 448, 48, 96 } },
        { 4, { 600, 0, 0 }, { 700, 50, 30 } },                /* a bed: frame, then linen */
        { 3, { 600, 0, 30 }, { 700, 50, 40 } },
        { 5, { 0, 300, 0 }, { 10, 310, 10 } },                /* grass: nothing */
        { 6, { 0, 500, 40 }, { 64, 501, 100 } },              /* a window */
    };
    static const int orders[3][3] = { { 1, 10, 13 }, { 13, 10, 1 }, { 10, 13, 1 } };
    static Bsp  bsp;
    ETA_BspProp props[32];
    int         o, chunk;

    /* ---- what a shader says a surface is ---- */
    CHECK(!strcmp(ETA_BspProp_Kind("models/mapobjects/furniture/clubchair"), "Armchair"));
    CHECK(!strcmp(ETA_BspProp_Kind("models/mapobjects/furniture/chair_wood"), "Chair"));
    CHECK(!strcmp(ETA_BspProp_Kind("TEXTURES/PROPS/BOX_M05A"), "Crate"));
    CHECK(!strcmp(ETA_BspProp_Kind("textures/chat/bedlinenpillow_c02"), "Bed"));
    CHECK(!strcmp(ETA_BspProp_Kind("textures/egypt_props_sd/siwa_book1"), "Books"));
    CHECK(!strcmp(ETA_BspProp_Kind("textures/props/barrel_m01"), "Barrel"));
    CHECK(!strcmp(ETA_BspProp_Kind("models/mapobjects/furniture/wood1"), "Furniture"));
    CHECK(!strcmp(ETA_BspProp_Kind("textures/egypt_windows_sd/siwa_windows6"), "Window"));
    CHECK(ETA_BspProp_Kind("textures/skies/sd_skybox") == NULL);
    CHECK(ETA_BspProp_Kind("textures/egypt_wood_sd/wood1a") == NULL);
    CHECK(ETA_BspProp_Kind("models/mapobjects/plants_sd/grass_dry3") == NULL);
    CHECK(ETA_BspProp_Kind(NULL) == NULL);

    /* ---- the things on a map, however the file is laid out or read ---- */
    for (o = 0; o < 3; o++)
    {
        BuildBsp(&bsp, shaders, 7, surfaces, (int)(sizeof(surfaces) / sizeof(surfaces[0])), orders[o]);

        for (chunk = 7; chunk <= 65536; chunk *= 64)
        {
            int count = Find(&bsp, chunk, props, 32);

            CHECK(count == 5);
            CHECK(Box(Named(props, count, "Armchair", 0), 0, 0, 0, 30, 30, 50)
                  || Box(Named(props, count, "Armchair", 1), 0, 0, 0, 30, 30, 50));
            CHECK(Named(props, count, "Armchair", 1) != NULL);
            CHECK(Box(Named(props, count, "Crate", 0), 400, 0, 0, 448, 48, 96));
            CHECK(Box(Named(props, count, "Bed", 0), 600, 0, 0, 700, 50, 40));
            CHECK(Named(props, count, "Furniture", 0) == NULL);
            CHECK(Box(Named(props, count, "Window", 0), 0, 500, 40, 64, 501, 100));
        }
    }

    /* ---- joining, and not ---- */
    {
        const float a0[3] = { 0, 0, 0 }, a1[3] = { 10, 10, 10 };
        const float b0[3] = { 40, 0, 0 }, b1[3] = { 50, 10, 10 };     /* 30 apart: joined at 48 */
        const float c0[3] = { 300, 0, 0 }, c1[3] = { 310, 10, 10 };   /* too wide to join */
        int         count = 0;

        count = ETA_BspProps_Add(props, count, 32, "Barrel", a0, a1, 48.0f);
        count = ETA_BspProps_Add(props, count, 32, "Barrel", b0, b1, 48.0f);
        CHECK(count == 1 && Box(&props[0], 0, 0, 0, 50, 10, 10));
        count = ETA_BspProps_Add(props, count, 32, "Vase", c0, c1, 48.0f);
        CHECK(count == 2);
        count = ETA_BspProps_Add(props, count, 2, "Crate", c0, c1, 48.0f);
        CHECK(count == 2);   /* full */
    }

    /* ---- not a map ---- */
    {
        memset(&bsp, 0, sizeof(bsp));
        bsp.size = 200;
        CHECK(Find(&bsp, 4096, props, 32) == 0);
        CHECK(ETA_BspProps_Find(NULL, Restart, NULL, props, 32) == 0);
    }

    return SMOKE_REPORT("bsp_props");
}

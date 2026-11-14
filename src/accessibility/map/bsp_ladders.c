#include "bsp_ladders.h"

#include <stdlib.h>
#include <string.h>

/* The map format's own numbers (qfiles.h, surfaceflags.h). */
#define ETA_BSP_IDENT        (('P' << 24) + ('S' << 16) + ('B' << 8) + 'I')
#define ETA_BSP_VERSION      47
#define ETA_BSP_LUMPS        17
#define ETA_BSP_SHADERS      1
#define ETA_BSP_PLANES       2
#define ETA_BSP_MODELS       7
#define ETA_BSP_BRUSHES      8
#define ETA_BSP_BRUSHSIDES   9
#define ETA_BSP_SHADER_SIZE  72     /* char name[64], int surfaceFlags, int contentFlags */
#define ETA_BSP_PLANE_SIZE   16     /* float normal[3], float dist */
#define ETA_BSP_MODEL_SIZE   40     /* float mins[3], maxs[3], int 4 */
#define ETA_BSP_BRUSH_SIZE   12     /* int firstSide, numSides, shaderNum */
#define ETA_BSP_SIDE_SIZE    8      /* int planeNum, shaderNum */
#define ETA_SURF_LADDER      0x00000008

/* The map's tables are as big as the map says, and are made that size
   for the read. There is no fixed room for them: the first version kept
   room for 16,384 brushes, the compiler's own limit, and Oasis - one of
   the game's own maps - has 21,052, so it was read as having no ladders
   at all. The engine does not hold maps to that limit, so neither does
   this. These only turn away a header that is plainly not a map. */
#define ETA_SANE_SHADERS     0xffff  /* each face keeps its shader in 16 bits */
#define ETA_SANE_BRUSHES     0x400000
#define ETA_SANE_SIDES       0x1000000
#define ETA_MAX_LADDER_BRUSHES 512

#define ETA_SIDE_LADDER      0x80000000u

typedef struct
{
    int offset;
    int length;
} ETA_BspLump;

typedef struct
{
    ETA_BspRead    read;
    ETA_BspRestart restart;
    void          *context;
    int            position;
} ETA_BspFile;

static unsigned char *gLadderShader;
static int           *gBrushFirst;
static int           *gBrushCount;
static unsigned int  *gSide;        /* plane number, top bit for a ladder face */
static unsigned short *gSideShader; /* each face's shader, judged once all are read */

static int ETA_Bsp_Int(const unsigned char *p)
{
    return (int)((unsigned int)p[0] | ((unsigned int)p[1] << 8) | ((unsigned int)p[2] << 16)
                 | ((unsigned int)p[3] << 24));
}

static float ETA_Bsp_Float(const unsigned char *p)
{
    unsigned int bits = (unsigned int)ETA_Bsp_Int(p);
    float        value;

    memcpy(&value, &bits, sizeof(value));
    return value;
}

static int ETA_Bsp_ReadExactly(ETA_BspFile *file, void *buffer, int length)
{
    int done = 0;

    while (done < length)
    {
        int got = file->read(file->context, (unsigned char *)buffer + done, length - done);

        if (got <= 0)
        {
            return 0;
        }
        done += got;
    }

    file->position += length;
    return 1;
}

/* Forward only: the file cannot be sought, so skipping is reading. */
static int ETA_Bsp_SkipTo(ETA_BspFile *file, int offset)
{
    unsigned char scratch[4096];

    if (offset < file->position)
    {
        return 0;
    }

    while (file->position < offset)
    {
        int take = offset - file->position;

        if (take > (int)sizeof(scratch))
        {
            take = (int)sizeof(scratch);
        }
        if (!ETA_Bsp_ReadExactly(file, scratch, take))
        {
            return 0;
        }
    }

    return 1;
}

static int ETA_Bsp_Header(ETA_BspFile *file, ETA_BspLump lumps[ETA_BSP_LUMPS])
{
    unsigned char header[8 + 8 * ETA_BSP_LUMPS];
    int           i;

    if (!ETA_Bsp_ReadExactly(file, header, (int)sizeof(header))
        || ETA_Bsp_Int(header) != ETA_BSP_IDENT || ETA_Bsp_Int(header + 4) != ETA_BSP_VERSION)
    {
        return 0;
    }

    for (i = 0; i < ETA_BSP_LUMPS; i++)
    {
        lumps[i].offset = ETA_Bsp_Int(header + 8 + i * 8);
        lumps[i].length = ETA_Bsp_Int(header + 12 + i * 8);

        if (lumps[i].offset < 0 || lumps[i].length < 0)
        {
            return 0;
        }
    }

    return 1;
}

static int ETA_Bsp_ByOffset(const void *a, const void *b)
{
    const ETA_BspLump *const *la = (const ETA_BspLump *const *)a;
    const ETA_BspLump *const *lb = (const ETA_BspLump *const *)b;

    return (*la)->offset - (*lb)->offset;
}

static int ETA_Bsp_CompareInt(const void *a, const void *b)
{
    int ia = *(const int *)a, ib = *(const int *)b;

    return ia < ib ? -1 : ia > ib;
}

typedef struct
{
    int   planes[7];    /* the six axial faces, then the ladder face */
    float dist[7];
    float normal[7][3];
    int   oneFace;
} ETA_LadderBrush;

static int ETA_Bsp_Search(ETA_BspFile *file, ETA_BspLump lumps[ETA_BSP_LUMPS],
                          ETA_BspLadder *out, int max);

int ETA_BspLadders_Find(ETA_BspRead read, ETA_BspRestart restart, void *context,
                        ETA_BspLadder *out, int max)
{
    ETA_BspFile file;
    ETA_BspLump lumps[ETA_BSP_LUMPS];
    int         shaderCount, sideCount, brushCount, found;

    if (!read || !restart || !out || max <= 0)
    {
        return 0;
    }

    file.read     = read;
    file.restart  = restart;
    file.context  = context;
    file.position = 0;

    if (!ETA_Bsp_Header(&file, lumps))
    {
        return 0;
    }

    shaderCount = lumps[ETA_BSP_SHADERS].length / ETA_BSP_SHADER_SIZE;
    sideCount   = lumps[ETA_BSP_BRUSHSIDES].length / ETA_BSP_SIDE_SIZE;
    brushCount  = lumps[ETA_BSP_BRUSHES].length / ETA_BSP_BRUSH_SIZE;

    if (shaderCount <= 0 || shaderCount > ETA_SANE_SHADERS || sideCount <= 0 || sideCount > ETA_SANE_SIDES
        || brushCount <= 0 || brushCount > ETA_SANE_BRUSHES)
    {
        return 0;
    }

    gLadderShader = (unsigned char *)calloc((size_t)shaderCount, sizeof(*gLadderShader));
    gBrushFirst   = (int *)calloc((size_t)brushCount, sizeof(*gBrushFirst));
    gBrushCount   = (int *)calloc((size_t)brushCount, sizeof(*gBrushCount));
    gSide         = (unsigned int *)calloc((size_t)sideCount, sizeof(*gSide));
    gSideShader   = (unsigned short *)calloc((size_t)sideCount, sizeof(*gSideShader));

    found = (gLadderShader && gBrushFirst && gBrushCount && gSide && gSideShader)
            ? ETA_Bsp_Search(&file, lumps, out, max) : 0;

    free(gLadderShader);
    free(gBrushFirst);
    free(gBrushCount);
    free(gSide);
    free(gSideShader);
    gSideShader   = NULL;
    gLadderShader = NULL;
    gBrushFirst   = NULL;
    gBrushCount   = NULL;
    gSide         = NULL;

    return found;
}

static int ETA_Bsp_Search(ETA_BspFile *fileIn, ETA_BspLump lumpsIn[ETA_BSP_LUMPS],
                          ETA_BspLadder *out, int max)
{
    static ETA_LadderBrush ladders[ETA_MAX_LADDER_BRUSHES];
    static int             wanted[ETA_MAX_LADDER_BRUSHES * 7];
    ETA_BspFile            file   = *fileIn;
    ETA_BspLump           *lumps  = lumpsIn;
    ETA_BspRestart         restart = file.restart;
    void                  *context = file.context;
    const ETA_BspLump     *order[4];
    int                    worldFirst = 0, worldCount = 0;
    int                    shaderCount, sideCount, brushCount;
    int                    ladderCount = 0, wantedCount = 0, found = 0;
    int                    i, j, k;

    shaderCount = lumps[ETA_BSP_SHADERS].length / ETA_BSP_SHADER_SIZE;
    sideCount   = lumps[ETA_BSP_BRUSHSIDES].length / ETA_BSP_SIDE_SIZE;
    brushCount  = lumps[ETA_BSP_BRUSHES].length / ETA_BSP_BRUSH_SIZE;

    if (lumps[ETA_BSP_MODELS].length < ETA_BSP_MODEL_SIZE)
    {
        return 0;
    }

    /* First pass: the world model, the shaders, the brushes and their
       faces, in whatever order the file has them. */
    order[0] = &lumps[ETA_BSP_MODELS];
    order[1] = &lumps[ETA_BSP_SHADERS];
    order[2] = &lumps[ETA_BSP_BRUSHES];
    order[3] = &lumps[ETA_BSP_BRUSHSIDES];
    qsort(order, 4, sizeof(order[0]), ETA_Bsp_ByOffset);

    for (i = 0; i < 4; i++)
    {
        const ETA_BspLump *lump = order[i];

        if (!ETA_Bsp_SkipTo(&file, lump->offset))
        {
            return 0;
        }

        if (lump == &lumps[ETA_BSP_MODELS])
        {
            unsigned char model[ETA_BSP_MODEL_SIZE];

            if (!ETA_Bsp_ReadExactly(&file, model, ETA_BSP_MODEL_SIZE))
            {
                return 0;
            }
            worldFirst = ETA_Bsp_Int(model + 32);
            worldCount = ETA_Bsp_Int(model + 36);
        }
        else if (lump == &lumps[ETA_BSP_SHADERS])
        {
            for (j = 0; j < shaderCount; j++)
            {
                unsigned char shader[ETA_BSP_SHADER_SIZE];

                if (!ETA_Bsp_ReadExactly(&file, shader, ETA_BSP_SHADER_SIZE))
                {
                    return 0;
                }
                gLadderShader[j] = (unsigned char)((ETA_Bsp_Int(shader + 64) & ETA_SURF_LADDER) != 0);
            }
        }
        else if (lump == &lumps[ETA_BSP_BRUSHES])
        {
            for (j = 0; j < brushCount; j++)
            {
                unsigned char brush[ETA_BSP_BRUSH_SIZE];

                if (!ETA_Bsp_ReadExactly(&file, brush, ETA_BSP_BRUSH_SIZE))
                {
                    return 0;
                }
                gBrushFirst[j] = ETA_Bsp_Int(brush);
                gBrushCount[j] = ETA_Bsp_Int(brush + 4);
            }
        }
        else
        {
            for (j = 0; j < sideCount; j++)
            {
                unsigned char side[ETA_BSP_SIDE_SIZE];
                int           shader;

                if (!ETA_Bsp_ReadExactly(&file, side, ETA_BSP_SIDE_SIZE))
                {
                    return 0;
                }
                shader         = ETA_Bsp_Int(side + 4);
                gSide[j]       = (unsigned int)ETA_Bsp_Int(side) & 0x7fffffffu;
                gSideShader[j] = (unsigned short)(shader >= 0 && shader < shaderCount ? (unsigned)shader : 0xffffu);
            }
        }
    }

    /* Which faces are ladders can only be said once both the faces and the
       shaders have been read, and the file may have them either way round. */
    for (j = 0; j < sideCount; j++)
    {
        if (gSideShader[j] != 0xffffu && gLadderShader[gSideShader[j]])
        {
            gSide[j] |= ETA_SIDE_LADDER;
        }
    }

    if (worldFirst < 0 || worldCount < 0 || worldFirst + worldCount > brushCount)
    {
        return 0;
    }

    /* Which world brushes are ladders, and the planes each needs. */
    for (i = worldFirst; i < worldFirst + worldCount && ladderCount < ETA_MAX_LADDER_BRUSHES; i++)
    {
        int first = gBrushFirst[i], count = gBrushCount[i], ladderSide = -1;

        if (first < 0 || count < 6 || first + count > sideCount)
        {
            continue;
        }

        for (j = 0; j < count; j++)
        {
            if (gSide[first + j] & ETA_SIDE_LADDER)
            {
                ladderSide = first + j;
                break;
            }
        }

        if (ladderSide < 0)
        {
            continue;
        }

        /* The face a player climbs is the one ladder face among the four
           upright sides. A ladder brush painted all over - the usual
           kind, one shader on every face - has no such face, and its
           box says only which way it is thin, so the axis is all that
           is kept and the caller finds the open side. */
        {
            int upright = 0, which = -1;

            for (j = 0; j < 4; j++)
            {
                if (gSide[first + j] & ETA_SIDE_LADDER)
                {
                    upright++;
                    which = first + j;
                }
            }
            ladderSide = upright == 1 ? which : -1;
        }

        for (j = 0; j < 6; j++)
        {
            ladders[ladderCount].planes[j] = (int)(gSide[first + j] & 0x7fffffffu);
        }
        /* No one face: plane 6 repeats side 0, and the box decides. */
        ladders[ladderCount].planes[6] = (int)(gSide[ladderSide >= 0 ? ladderSide : first] & 0x7fffffffu);
        ladders[ladderCount].oneFace   = ladderSide >= 0;

        for (j = 0; j < 7; j++)
        {
            wanted[wantedCount++] = ladders[ladderCount].planes[j];
        }
        ladderCount++;
    }

    if (!ladderCount)
    {
        return 0;
    }

    qsort(wanted, (size_t)wantedCount, sizeof(wanted[0]), ETA_Bsp_CompareInt);

    /* Second pass: the planes, which the file keeps before the brushes. */
    if (!restart(context))
    {
        return 0;
    }
    file.position = 0;

    if (!ETA_Bsp_SkipTo(&file, lumps[ETA_BSP_PLANES].offset))
    {
        return 0;
    }

    {
        int planeCount = lumps[ETA_BSP_PLANES].length / ETA_BSP_PLANE_SIZE;
        int highest    = wanted[wantedCount - 1];

        for (j = 0; j < planeCount && j <= highest; j++)
        {
            unsigned char plane[ETA_BSP_PLANE_SIZE];

            if (!ETA_Bsp_ReadExactly(&file, plane, ETA_BSP_PLANE_SIZE))
            {
                return 0;
            }

            if (!bsearch(&j, wanted, (size_t)wantedCount, sizeof(wanted[0]), ETA_Bsp_CompareInt))
            {
                continue;
            }

            for (i = 0; i < ladderCount; i++)
            {
                for (k = 0; k < 7; k++)
                {
                    if (ladders[i].planes[k] == j)
                    {
                        ladders[i].normal[k][0] = ETA_Bsp_Float(plane);
                        ladders[i].normal[k][1] = ETA_Bsp_Float(plane + 4);
                        ladders[i].normal[k][2] = ETA_Bsp_Float(plane + 8);
                        ladders[i].dist[k]      = ETA_Bsp_Float(plane + 12);
                    }
                }
            }
        }

        if (highest >= planeCount)
        {
            return 0;
        }
    }

    /* Boxes, by the engine's own rule, and brushes beside each other with
       their faces the same way joined into one ladder. */
    for (i = 0; i < ladderCount; i++)
    {
        ETA_BspLadder ladder;

        ladder.mins[0] = -ladders[i].dist[0];
        ladder.maxs[0] = ladders[i].dist[1];
        ladder.mins[1] = -ladders[i].dist[2];
        ladder.maxs[1] = ladders[i].dist[3];
        ladder.mins[2] = -ladders[i].dist[4];
        ladder.maxs[2] = ladders[i].dist[5];
        if (ladders[i].oneFace)
        {
            ladder.normal[0] = ladders[i].normal[6][0];
            ladder.normal[1] = ladders[i].normal[6][1];
        }
        else
        {
            /* Painted all over: it is climbed across its thin side, and
               which of the two faces is open is not in the box. */
            int thinX = ladder.maxs[0] - ladder.mins[0] <= ladder.maxs[1] - ladder.mins[1];

            ladder.normal[0] = thinX ? 1.0f : 0.0f;
            ladder.normal[1] = thinX ? 0.0f : 1.0f;
        }
        ladder.normal[2] = 0.0f;
        ladder.oneFace   = ladders[i].oneFace;

        /* The four upright faces are axial, so a ladder face among them
           already looks straight along x or y. */
        if (ladder.mins[0] > ladder.maxs[0] || ladder.mins[1] > ladder.maxs[1]
            || ladder.mins[2] > ladder.maxs[2]
            || ladder.normal[0] * ladder.normal[0] + ladder.normal[1] * ladder.normal[1] < 0.5f)
        {
            continue;
        }

        for (j = 0; j < found; j++)
        {
            int   touch = 1;
            float same;

            for (k = 0; k < 3; k++)
            {
                if (ladder.mins[k] > out[j].maxs[k] + 8.0f || ladder.maxs[k] < out[j].mins[k] - 8.0f)
                {
                    touch = 0;
                }
            }

            /* Same way, or along the same axis when either only knows
               its axis. */
            same = ladder.normal[0] * out[j].normal[0] + ladder.normal[1] * out[j].normal[1];
            if (!ladder.oneFace || !out[j].oneFace)
            {
                same = same < 0.0f ? -same : same;
            }

            if (touch && same > 0.9f)
            {
                for (k = 0; k < 3; k++)
                {
                    out[j].mins[k] = ladder.mins[k] < out[j].mins[k] ? ladder.mins[k] : out[j].mins[k];
                    out[j].maxs[k] = ladder.maxs[k] > out[j].maxs[k] ? ladder.maxs[k] : out[j].maxs[k];
                }
                if (ladder.oneFace && !out[j].oneFace)
                {
                    out[j].normal[0] = ladder.normal[0];
                    out[j].normal[1] = ladder.normal[1];
                    out[j].oneFace   = 1;
                }
                break;
            }
        }

        if (j == found && found < max)
        {
            out[found++] = ladder;
        }
    }

    return found;
}

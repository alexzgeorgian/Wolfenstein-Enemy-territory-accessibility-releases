#include "bsp_props.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

/* The map format's own numbers (qfiles.h). */
#define ETA_BSP_IDENT        (('P' << 24) + ('S' << 16) + ('B' << 8) + 'I')
#define ETA_BSP_VERSION      47
#define ETA_BSP_LUMPS        17
#define ETA_BSP_SHADERS      1
#define ETA_BSP_DRAWVERTS    10
#define ETA_BSP_SURFACES     13
#define ETA_BSP_SHADER_SIZE  72     /* char name[64], int surfaceFlags, int contentFlags */
#define ETA_BSP_VERT_SIZE    44     /* float xyz[3], st[2], lightmap[2], normal[3], byte color[4] */
#define ETA_BSP_SURFACE_SIZE 104    /* int shaderNum, fogNum, surfaceType, firstVert, numVerts, ... */

#define ETA_SANE_SHADERS     0xffff
#define ETA_SANE_SURFACES    0x400000
#define ETA_MAX_PROP_SURFACES 8192
#define ETA_PROP_GAP         64.0f  /* the parts of one thing are closer than this: a cart's wheels */

/*
 * Words in a shader's name, and what a surface painted with it is. Read
 * in order, so the more particular comes first: a club chair is an
 * armchair before it is a chair, and anything else in the furniture
 * folder is furniture. A word that is part of something else - box in
 * skybox - is written with the slash or underscore that comes before it.
 */
static const struct
{
    const char *word;
    const char *name;
} gKinds[] =
{
    { "bookcase",       "Bookcase" },
    { "bookshel",       "Bookcase" },
    { "_book",          "Books" },
    { "/book",          "Books" },
    { "bedlinen",       "Bed" },
    { "bedframe",       "Bed" },
    { "/bed_",          "Bed" },
    { "_bed",           "Bed" },
    { "clubchair",      "Armchair" },
    { "armchair",       "Armchair" },
    { "chair",          "Chair" },
    { "stool",          "Stool" },
    { "bench",          "Bench" },
    { "sofa",           "Sofa" },
    { "couch",          "Sofa" },
    { "table",          "Table" },
    { "desk",           "Desk" },
    { "cupboard",       "Cupboard" },
    { "wardrobe",       "Wardrobe" },
    { "dresser",        "Dresser" },
    { "drawer",         "Chest of drawers" },
    { "shelf",          "Shelves" },
    { "piano",          "Piano" },
    { "stove",          "Stove" },
    { "fireplace",      "Fireplace" },
    { "sink",           "Sink" },
    { "toilet",         "Toilet" },
    { "bathtub",        "Bath" },
    { "lamp",           "Lamp" },
    { "radio",          "Radio" },
    { "typewriter",     "Typewriter" },
    { "telephone",      "Telephone" },
    { "clock",          "Clock" },
    { "barrel",         "Barrel" },
    { "crate",          "Crate" },
    { "/box_",          "Crate" },
    { "sandbag",        "Sandbags" },
    { "basket",         "Basket" },
    { "vase",           "Vase" },
    { "pitcher",        "Pitcher" },
    { "/jar",           "Jar" },
    { "generator",      "Generator" },
    { "toolshed/tools", "Tools" },
    { "wagon",          "Cart" },
    { "/cart",          "Cart" },
    { "furniture/",     "Furniture" },
    { "window",         "Window" }
};

#define ETA_GENERIC_PROP "Furniture"

const char *ETA_BspProp_Kind(const char *shaderName)
{
    char   lower[64];
    size_t i;

    if (!shaderName)
    {
        return NULL;
    }

    for (i = 0; i + 1 < sizeof(lower) && shaderName[i]; i++)
    {
        lower[i] = (char)tolower((unsigned char)shaderName[i]);
    }
    lower[i] = '\0';

    for (i = 0; i < sizeof(gKinds) / sizeof(gKinds[0]); i++)
    {
        if (strstr(lower, gKinds[i].word))
        {
            return gKinds[i].name;
        }
    }

    return NULL;
}

static int ETA_Prop_Touch(const ETA_BspProp *prop, const float mins[3], const float maxs[3], float gap)
{
    int a;

    for (a = 0; a < 3; a++)
    {
        if (mins[a] > prop->maxs[a] + gap || prop->mins[a] > maxs[a] + gap)
        {
            return 0;
        }
    }

    return 1;
}

static int ETA_Prop_Joinable(const ETA_BspProp *prop, const float mins[3], const float maxs[3])
{
    int a;

    for (a = 0; a < 2; a++)
    {
        float low  = prop->mins[a] < mins[a] ? prop->mins[a] : mins[a];
        float high = prop->maxs[a] > maxs[a] ? prop->maxs[a] : maxs[a];

        if (high - low > ETA_BSP_PROP_WIDEST)
        {
            return 0;
        }
    }

    return 1;
}

int ETA_BspProps_Add(ETA_BspProp *props, int count, int max, const char *name,
                     const float mins[3], const float maxs[3], float gap)
{
    ETA_BspProp joined;
    int         i, a, again = 1;

    if (!props || !name || !mins || !maxs || count < 0)
    {
        return count < 0 ? 0 : count;
    }

    memset(&joined, 0, sizeof(joined));
    strncpy(joined.name, name, sizeof(joined.name) - 1);
    for (a = 0; a < 3; a++)
    {
        joined.mins[a] = mins[a];
        joined.maxs[a] = maxs[a];
    }

    /* Each join can bring the box up to another part, so look again
       until nothing more joins. */
    while (again)
    {
        again = 0;

        for (i = 0; i < count; i++)
        {
            ETA_BspProp *prop    = &props[i];
            int          same    = !strcmp(prop->name, joined.name);
            int          generic = !strcmp(prop->name, ETA_GENERIC_PROP) || !strcmp(joined.name, ETA_GENERIC_PROP);

            if ((!same && !generic)
                || !ETA_Prop_Touch(prop, joined.mins, joined.maxs, same ? gap : 0.0f)
                || !ETA_Prop_Joinable(prop, joined.mins, joined.maxs))
            {
                continue;
            }

            /* The named one names it: a bed frame is the bed. */
            if (!strcmp(joined.name, ETA_GENERIC_PROP))
            {
                memcpy(joined.name, prop->name, sizeof(joined.name));
            }
            for (a = 0; a < 3; a++)
            {
                if (prop->mins[a] < joined.mins[a])
                {
                    joined.mins[a] = prop->mins[a];
                }
                if (prop->maxs[a] > joined.maxs[a])
                {
                    joined.maxs[a] = prop->maxs[a];
                }
            }

            props[i] = props[--count];
            again    = 1;
            break;
        }
    }

    if (count >= max)
    {
        return count;
    }

    props[count] = joined;
    return count + 1;
}

/* ---- reading the map ------------------------------------------------- */

typedef struct
{
    ETA_BspRead    read;
    ETA_BspRestart restart;
    void          *context;
    int            position;
} ETA_PropFile;

typedef struct
{
    int   kind;        /* into gKinds */
    int   firstVert;
    int   numVerts;
    float mins[3];
    float maxs[3];
} ETA_PropSurface;

static int ETA_Prop_Int(const unsigned char *p)
{
    return (int)((unsigned int)p[0] | ((unsigned int)p[1] << 8) | ((unsigned int)p[2] << 16)
                 | ((unsigned int)p[3] << 24));
}

static float ETA_Prop_Float(const unsigned char *p)
{
    unsigned int bits = (unsigned int)ETA_Prop_Int(p);
    float        value;

    memcpy(&value, &bits, sizeof(value));
    return value;
}

static int ETA_Prop_ReadExactly(ETA_PropFile *file, void *buffer, int length)
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

static int ETA_Prop_SkipTo(ETA_PropFile *file, int offset)
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
        if (!ETA_Prop_ReadExactly(file, scratch, take))
        {
            return 0;
        }
    }

    return 1;
}

static int ETA_Prop_Restart(ETA_PropFile *file)
{
    if (!file->restart(file->context))
    {
        return 0;
    }
    file->position = 0;
    return 1;
}

static int ETA_Prop_Header(ETA_PropFile *file, int offsets[ETA_BSP_LUMPS], int lengths[ETA_BSP_LUMPS])
{
    unsigned char header[8 + 8 * ETA_BSP_LUMPS];
    int           i;

    if (!ETA_Prop_ReadExactly(file, header, (int)sizeof(header))
        || ETA_Prop_Int(header) != ETA_BSP_IDENT || ETA_Prop_Int(header + 4) != ETA_BSP_VERSION)
    {
        return 0;
    }

    for (i = 0; i < ETA_BSP_LUMPS; i++)
    {
        offsets[i] = ETA_Prop_Int(header + 8 + i * 8);
        lengths[i] = ETA_Prop_Int(header + 12 + i * 8);

        if (offsets[i] < 0 || lengths[i] < 0)
        {
            return 0;
        }
    }

    return 1;
}

static int ETA_Prop_ByFirstVert(const void *a, const void *b)
{
    return ((const ETA_PropSurface *)a)->firstVert - ((const ETA_PropSurface *)b)->firstVert;
}

/* Which kind each shader is, -1 for none. */
static int ETA_Prop_ReadShaders(ETA_PropFile *file, int offset, int count, signed char *kinds)
{
    unsigned char record[ETA_BSP_SHADER_SIZE];
    int           i;

    if (!ETA_Prop_SkipTo(file, offset))
    {
        return 0;
    }

    for (i = 0; i < count; i++)
    {
        const char *name;
        char        text[65];
        size_t      k;

        if (!ETA_Prop_ReadExactly(file, record, (int)sizeof(record)))
        {
            return 0;
        }
        memcpy(text, record, 64);
        text[64] = '\0';

        kinds[i] = -1;
        name     = ETA_BspProp_Kind(text);
        for (k = 0; name && k < sizeof(gKinds) / sizeof(gKinds[0]); k++)
        {
            if (gKinds[k].name == name)
            {
                kinds[i] = (signed char)k;
                break;
            }
        }
    }

    return 1;
}

static int ETA_Prop_ReadSurfaces(ETA_PropFile *file, int offset, int count, const signed char *kinds,
                                 int shaders, ETA_PropSurface *out, int *found)
{
    unsigned char record[ETA_BSP_SURFACE_SIZE];
    int           i;

    if (!ETA_Prop_SkipTo(file, offset))
    {
        return 0;
    }

    for (i = 0; i < count; i++)
    {
        int shader;

        if (!ETA_Prop_ReadExactly(file, record, (int)sizeof(record)))
        {
            return 0;
        }

        shader = ETA_Prop_Int(record);
        if (shader < 0 || shader >= shaders || kinds[shader] < 0 || *found >= ETA_MAX_PROP_SURFACES)
        {
            continue;
        }

        out[*found].kind      = kinds[shader];
        out[*found].firstVert = ETA_Prop_Int(record + 12);
        out[*found].numVerts  = ETA_Prop_Int(record + 16);
        if (out[*found].firstVert >= 0 && out[*found].numVerts > 0)
        {
            (*found)++;
        }
    }

    return 1;
}

/* The corners of each surface wanted, in the order they lie in the file. */
static int ETA_Prop_ReadCorners(ETA_PropFile *file, int offset, int verts, ETA_PropSurface *surfaces, int count)
{
    unsigned char record[ETA_BSP_VERT_SIZE];
    int           next = 0;   /* the corner the file is at */
    int           i;

    if (!ETA_Prop_SkipTo(file, offset))
    {
        return 0;
    }

    qsort(surfaces, (size_t)count, sizeof(surfaces[0]), ETA_Prop_ByFirstVert);

    for (i = 0; i < count; i++)
    {
        ETA_PropSurface *surface = &surfaces[i];
        int              v, a;

        if (surface->firstVert + surface->numVerts > verts)
        {
            surface->numVerts = 0;
            continue;
        }

        /* Surfaces can share corners; a corner already passed is read
           again from the start. */
        if (surface->firstVert < next)
        {
            if (!ETA_Prop_Restart(file) || !ETA_Prop_SkipTo(file, offset))
            {
                return 0;
            }
            next = 0;
        }
        if (!ETA_Prop_SkipTo(file, offset + surface->firstVert * ETA_BSP_VERT_SIZE))
        {
            return 0;
        }
        next = surface->firstVert;

        for (v = 0; v < surface->numVerts; v++)
        {
            if (!ETA_Prop_ReadExactly(file, record, (int)sizeof(record)))
            {
                return 0;
            }
            next++;

            for (a = 0; a < 3; a++)
            {
                float value = ETA_Prop_Float(record + a * 4);

                if (v == 0 || value < surface->mins[a])
                {
                    surface->mins[a] = value;
                }
                if (v == 0 || value > surface->maxs[a])
                {
                    surface->maxs[a] = value;
                }
            }
        }
    }

    return 1;
}

int ETA_BspProps_Find(ETA_BspRead read, ETA_BspRestart restart, void *context,
                      ETA_BspProp *out, int max)
{
    ETA_PropFile     file;
    int              offsets[ETA_BSP_LUMPS], lengths[ETA_BSP_LUMPS];
    int              shaders, surfaces, verts, found = 0, count = 0, i, ok;
    signed char     *kinds    = NULL;
    ETA_PropSurface *wanted   = NULL;

    if (!read || !restart || !out || max <= 0)
    {
        return 0;
    }

    file.read     = read;
    file.restart  = restart;
    file.context  = context;
    file.position = 0;

    if (!ETA_Prop_Header(&file, offsets, lengths))
    {
        return 0;
    }

    shaders  = lengths[ETA_BSP_SHADERS] / ETA_BSP_SHADER_SIZE;
    surfaces = lengths[ETA_BSP_SURFACES] / ETA_BSP_SURFACE_SIZE;
    verts    = lengths[ETA_BSP_DRAWVERTS] / ETA_BSP_VERT_SIZE;
    if (shaders <= 0 || shaders > ETA_SANE_SHADERS || surfaces <= 0 || surfaces > ETA_SANE_SURFACES || verts <= 0)
    {
        return 0;
    }

    kinds  = (signed char *)malloc((size_t)shaders);
    wanted = (ETA_PropSurface *)calloc(ETA_MAX_PROP_SURFACES, sizeof(*wanted));
    if (!kinds || !wanted)
    {
        free(kinds);
        free(wanted);
        return 0;
    }

    /* The shaders and the surfaces, in whichever order the file has them;
       then the corners, from the start again. */
    if (offsets[ETA_BSP_SHADERS] <= offsets[ETA_BSP_SURFACES])
    {
        ok = ETA_Prop_ReadShaders(&file, offsets[ETA_BSP_SHADERS], shaders, kinds)
             && ETA_Prop_ReadSurfaces(&file, offsets[ETA_BSP_SURFACES], surfaces, kinds, shaders, wanted, &found);
    }
    else
    {
        ok = ETA_Prop_ReadShaders(&file, offsets[ETA_BSP_SHADERS], shaders, kinds)
             && ETA_Prop_Restart(&file)
             && ETA_Prop_ReadSurfaces(&file, offsets[ETA_BSP_SURFACES], surfaces, kinds, shaders, wanted, &found);
    }

    if (ok && found > 0)
    {
        ok = (file.position <= offsets[ETA_BSP_DRAWVERTS] || ETA_Prop_Restart(&file))
             && ETA_Prop_ReadCorners(&file, offsets[ETA_BSP_DRAWVERTS], verts, wanted, found);
    }

    for (i = 0; ok && i < found; i++)
    {
        if (wanted[i].numVerts > 0)
        {
            count = ETA_BspProps_Add(out, count, max, gKinds[wanted[i].kind].name,
                                     wanted[i].mins, wanted[i].maxs, ETA_PROP_GAP);
        }
    }

    free(kinds);
    free(wanted);
    return ok ? count : 0;
}

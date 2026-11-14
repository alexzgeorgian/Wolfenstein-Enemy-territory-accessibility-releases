#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include "bsp_ladders.h"

/*
 * The furniture and the things in a room, read from the map file itself.
 *
 * The tester asked to hear the table, the chair, the bookcase as they
 * walked up to it. Nothing in a snapshot says one is there: a chair is
 * part of the map, a model the map compiler baked into the map's own
 * surfaces, or a few brushes. But every surface keeps the name of what
 * it is painted with, and for the things a map builder put in a room
 * that name says what they are - models/mapobjects/furniture/clubchair,
 * textures/props/box_c01, textures/chat/bedlinen_c02. So the shaders and
 * the surfaces say which surfaces are a chair, and their corners say
 * where it is.
 *
 * A thing is built from many surfaces - the legs of a chair, the sides
 * of a crate - so surfaces of the same kind that touch, or nearly, are
 * one thing. A plain wooden table built from brushes painted with the
 * same wood as the floor says nothing about being a table, and is not
 * found: only what is named.
 *
 * The cgame can only read a file from the start, forward, so the map is
 * read in two passes, the second for the corners, which come before the
 * surfaces in the file. Little-endian, as the map files are.
 */

#define ETA_BSP_PROP_NAME 24

typedef struct
{
    char  name[ETA_BSP_PROP_NAME];   /* "Chair", "Bookcase" */
    float mins[3];
    float maxs[3];
} ETA_BspProp;

/* What a surface painted with this shader is, by its name: "Chair", or
   NULL for anything that is not a thing in a room - a wall, a floor,
   grass. Ignores case. */
const char *ETA_BspProp_Kind(const char *shaderName);

/*
 * Adds a surface's box to the list, joined to a thing of the same kind
 * it touches or nearly touches (within gap), so many surfaces make one
 * thing; and a thing the shader only knows as furniture takes the name
 * of a named one it overlaps, the bed frame the bed's. A join that would
 * make a thing wider than ETA_BSP_PROP_WIDEST is not made. Returns the
 * count, which stays at max when full.
 */
#define ETA_BSP_PROP_WIDEST 512.0f
int ETA_BspProps_Add(ETA_BspProp *props, int count, int max, const char *name,
                     const float mins[3], const float maxs[3], float gap);

/* Fills out with up to max things and returns how many; 0 for a map
   with none, or a file that is not a map this engine would load. */
int ETA_BspProps_Find(ETA_BspRead read, ETA_BspRestart restart, void *context,
                      ETA_BspProp *out, int max);

#ifdef __cplusplus
}
#endif

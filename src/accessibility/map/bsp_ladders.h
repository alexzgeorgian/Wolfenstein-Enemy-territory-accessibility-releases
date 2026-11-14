#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Every ladder on a map, read from the map file itself.
 *
 * A ladder in Wolfenstein: Enemy Territory is not an entity. Nothing in a
 * snapshot says one is there. It is a brush - usually an invisible clip
 * box laid against a wall - whose faces carry the SURF_LADDER flag, and
 * the game finds it only by tracing into it from right in front. So the
 * mod could find a ladder within arm's reach and no further: a sound on
 * a ladder ten metres off needs to know where it is before anybody has
 * walked up to it.
 *
 * The map file says. Its brush list names the shader on each face of each
 * brush, and the shader list says which shaders are ladders, so reading
 * the shaders, the brushes, their faces and a handful of planes gives
 * every ladder's box and the way its face looks. The engine's own brush
 * loader (CM_BoundBrush) relies on each brush's first six faces being the
 * axis-aligned ones, and so does this: their distances are the box.
 *
 * The cgame can only read a file from the start, forward, so this asks
 * for bytes in order and skips by reading past them; the planes, which
 * come before the brushes in the file, are read in a second pass once it
 * is known which ones are wanted. Only the world's own brushes are read -
 * a ladder on a moving platform has no fixed place to put a sound.
 *
 * Little-endian, as the map files are and as every platform this mod
 * builds for is.
 */

typedef struct
{
    float mins[3];
    float maxs[3];
    float normal[3];   /* horizontal: the way the climbing face looks */
    int   oneFace;     /* 0: only the axis is known, not which way along it */
} ETA_BspLadder;

/* Reads up to length bytes into buffer, returning how many arrived. */
typedef int (*ETA_BspRead)(void *context, void *buffer, int length);

/* Starts the file again from its first byte. Returns 0 when it cannot. */
typedef int (*ETA_BspRestart)(void *context);

/*
 * Fills out with up to max ladders - brushes standing next to each other
 * with their faces the same way are one ladder - and returns how many.
 * 0 for a map with none, and for a file that is not a map this engine
 * would load. The map's tables are allocated at the size the map gives
 * for the read and freed after it.
 */
int ETA_BspLadders_Find(ETA_BspRead read, ETA_BspRestart restart, void *context,
                        ETA_BspLadder *out, int max);

#ifdef __cplusplus
}
#endif

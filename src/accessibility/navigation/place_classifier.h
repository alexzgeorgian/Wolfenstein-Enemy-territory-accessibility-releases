#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * What kind of place the player is standing in: a street, an alley, a
 * square, open ground, inside a building, on a balcony or on a roof.
 *
 * The tester asked to be able to follow the streets and the alleys and
 * tell the parts of a building apart - the balconies and rooftops - the
 * way a sighted player reads them off the scene. The game knows none of
 * these words. What it knows is walls and floors, and those are enough:
 * the cgame measures, around the player, how far the floor runs at the
 * same height before a wall or a drop, in eight compass directions;
 * whether there is sky overhead; whether there is a drop close by; and
 * whether there is air under the floor. This turns those measurements
 * into words, and decides when a change is worth saying.
 *
 * Kept free of the engine so the rules can be tested on their own.
 */

#define ETA_PLACE_DIRECTIONS 8   /* north, north-east, east ... clockwise */

typedef enum ETA_PlaceKind
{
    ETA_PLACE_UNKNOWN = 0,
    ETA_PLACE_STREET,
    ETA_PLACE_ALLEY,
    ETA_PLACE_SQUARE,
    ETA_PLACE_OPEN,
    ETA_PLACE_INDOORS,
    ETA_PLACE_UPPER_FLOOR,
    ETA_PLACE_BALCONY,
    ETA_PLACE_ROOFTOP,
    ETA_PLACE_LEDGE,          /* the edge of a drop, solid ground underfoot */
    ETA_PLACE_COUNT
} ETA_PlaceKind;

typedef struct ETA_PlaceProbe
{
    int   skyAbove;     /* open sky straight overhead */
    int   airBelow;     /* a room under the floor - a drawn one, not the
                           sealed space under the map, which is lined with
                           surfaces nobody sees */
    float dropBeside;   /* deepest drop found within a few steps, units; 0 for none */
    /* How far the floor runs at the same height, in units, in each of
       the eight directions, clockwise from north; and whether that run
       ended at a wall (1) or at a drop or the end of the look (0). */
    float reach[ETA_PLACE_DIRECTIONS];
    int   wall[ETA_PLACE_DIRECTIONS];
} ETA_PlaceProbe;

typedef struct ETA_Place
{
    ETA_PlaceKind kind;
    int           axis;    /* streets and alleys: 0 north-south, 1 north-east
                              to south-west, 2 east-west, 3 north-west to
                              south-east; -1 for anything else */
    int           widthMeters;
    int           dropMeters;  /* ledges: how far down the drop beside is */
} ETA_Place;

/* How the measurements are read, in Quake units (one metre is 39.37). */
#define ETA_PLACE_RAISED_UNITS     112.0f   /* a drop this deep: up off the ground */
#define ETA_PLACE_ALLEY_UNITS      160.0f   /* narrower than this: an alley */
#define ETA_PLACE_STREET_UNITS     480.0f   /* narrower than this: a street */
#define ETA_PLACE_LONG_UNITS       480.0f   /* a street or alley runs at least this far */
#define ETA_PLACE_BALCONY_UNITS    200.0f   /* a raised place this narrow: a balcony */

ETA_Place   ETA_Place_Classify(const ETA_PlaceProbe *probe);

/* "Alley, north to south", "Street, east to west, 8 meters wide",
   "Square", "Indoors, upper floor", "Balcony". */
void        ETA_Place_Text(const ETA_Place *place, char *out, size_t outSize);

/* The kind's word on its own, for lists: "street", "balcony". NULL for
   UNKNOWN and out of range. */
const char *ETA_Place_KindName(ETA_PlaceKind kind);

/* "north to south" and the like; NULL for an axis out of range. */
const char *ETA_Place_AxisName(int axis);

/*
 * Whether a place is news. The places seen over the last ETA_PLACE_WINDOW_MS
 * are voted on, and the one most of them agree on - at least ETA_PLACE_HOLD_MS
 * of them, so a doorway crossed is not a new street - has to differ from
 * the last one said. A street narrowing to an alley, or a
 * square opening out, is the same place; a street that bends a little is
 * the same street; turning into one that crosses it is news. Returns 1
 * exactly once per new place.
 */
#define ETA_PLACE_HOLD_MS   1800
#define ETA_PLACE_WINDOW_MS 3000   /* how far back the vote looks */

int  ETA_Place_Update(const ETA_Place *place, int nowMs);
void ETA_Place_Reset(void);

/* The place last said by ETA_Place_Update - what the voting settled on,
   for saying again. 0 when nothing has been said yet. */
int  ETA_Place_Spoken(ETA_Place *out);

/*
 * What a square of the command map holds, for the map survey: "a street
 * running north to south, a square, a building to the east with an upper
 * floor and a balcony".
 *
 * The cgame stands a probe on every floor it finds on an even grid of
 * points across the square - ETA_PLACE_SURVEY_SIDE to a side, rows from
 * the north, columns from the west, floors lowest first - and this reads
 * the whole grid: the ways that run through it and which way, any open
 * space, and the buildings, each with where in the square it stands and
 * what is up on it. A place seen at only a point or two is left out, so a
 * doorway or a gap between two roofs is not called a street.
 */
#define ETA_PLACE_SURVEY_SIDE   10
#define ETA_PLACE_SURVEY_FLOORS 4

typedef struct ETA_PlaceSurvey
{
    unsigned char floors[ETA_PLACE_SURVEY_SIDE][ETA_PLACE_SURVEY_SIDE];
    ETA_Place     place[ETA_PLACE_SURVEY_SIDE][ETA_PLACE_SURVEY_SIDE][ETA_PLACE_SURVEY_FLOORS];
} ETA_PlaceSurvey;

void ETA_PlaceSurvey_Clear(ETA_PlaceSurvey *survey);

/* Adds a floor to a point, above those already there. 0 when the point
   is out of range, full, or the place unknown. */
int  ETA_PlaceSurvey_Add(ETA_PlaceSurvey *survey, int row, int column, const ETA_Place *place);

/* The square in words, or "" when there is nowhere to stand in it. */
void ETA_PlaceSurvey_Describe(const ETA_PlaceSurvey *survey, char *out, size_t outSize);

#ifdef __cplusplus
}
#endif

#include "place_classifier.h"

#include <stdio.h>
#include <string.h>

static const char *const gKindNames[ETA_PLACE_COUNT] =
{
    NULL,
    "street",
    "alley",
    "square",
    "open ground",
    "indoors",
    "upper floor",
    "balcony",
    "rooftop",
    "ledge"
};

static const char *const gAxisNames[4] =
{
    "north to south",
    "north-east to south-west",
    "east to west",
    "north-west to south-east"
};

const char *ETA_Place_KindName(ETA_PlaceKind kind)
{
    if ((int)kind <= (int)ETA_PLACE_UNKNOWN || (int)kind >= (int)ETA_PLACE_COUNT)
    {
        return NULL;
    }

    return gKindNames[kind];
}

const char *ETA_Place_AxisName(int axis)
{
    if (axis < 0 || axis > 3)
    {
        return NULL;
    }

    return gAxisNames[axis];
}

ETA_Place ETA_Place_Classify(const ETA_PlaceProbe *probe)
{
    ETA_Place place;
    float     width[4];
    float     across, along;
    int       narrow = 0, walls = 0, raised, a, d;

    place.kind        = ETA_PLACE_UNKNOWN;
    place.axis        = -1;
    place.widthMeters = 0;
    place.dropMeters  = 0;

    if (!probe)
    {
        return place;
    }

    /* Across each of the four lines through the player: the run one way
       and the run the other. The narrowest is across the way; the way
       itself runs square to it. */
    for (a = 0; a < 4; a++)
    {
        width[a] = probe->reach[a] + probe->reach[a + 4];

        if (width[a] < width[narrow])
        {
            narrow = a;
        }
    }

    across = width[narrow];
    along  = width[(narrow + 2) % 4];

    for (d = 0; d < ETA_PLACE_DIRECTIONS; d++)
    {
        walls += probe->wall[d] ? 1 : 0;
    }

    /* A roof over the head is a building, whatever else: on its upper
       floor when there is a storey's worth of space under the floor. */
    if (!probe->skyAbove)
    {
        place.kind = probe->airBelow ? ETA_PLACE_UPPER_FLOOR : ETA_PLACE_INDOORS;
        return place;
    }

    /* Open sky with rooms under the floor: up on a building. Narrow
       with the house wall at its back, it is a balcony; anything else -
       broad, or narrow only because it is the corner of a flat roof with
       the edge on two sides - is a roof. */
    if (probe->airBelow)
    {
        int againstWall = probe->wall[narrow] || probe->wall[narrow + 4];

        place.kind = across < ETA_PLACE_BALCONY_UNITS && againstWall
                     ? ETA_PLACE_BALCONY : ETA_PLACE_ROOFTOP;
        return place;
    }

    /* Solid ground underfoot and a drop beside deeper than a storey: the
       edge of a terrace, a wall top, a cliff. Said with how far down, for
       the fall it would be. */
    raised = probe->dropBeside >= ETA_PLACE_RAISED_UNITS;

    if (raised)
    {
        place.kind       = ETA_PLACE_LEDGE;
        place.dropMeters = (int)(probe->dropBeside * 0.0254f + 0.5f);
        return place;
    }

    /* On the ground, open to the sky: a way between walls that runs on
       is a street, or when it is narrow an alley; an open space with
       walls round most of it a square; anything else open ground. */
    if (along >= ETA_PLACE_LONG_UNITS && along >= 2.0f * across)
    {
        if (across < ETA_PLACE_ALLEY_UNITS)
        {
            place.kind = ETA_PLACE_ALLEY;
        }
        else if (across < ETA_PLACE_STREET_UNITS)
        {
            place.kind = ETA_PLACE_STREET;
        }
    }

    if (place.kind != ETA_PLACE_UNKNOWN)
    {
        place.axis        = (narrow + 2) % 4;
        place.widthMeters = (int)(across * 0.0254f + 0.5f);
        return place;
    }

    place.kind = walls >= 6 ? ETA_PLACE_SQUARE : ETA_PLACE_OPEN;
    return place;
}

void ETA_Place_Text(const ETA_Place *place, char *out, size_t outSize)
{
    if (!out || outSize == 0)
    {
        return;
    }

    out[0] = '\0';

    if (!place)
    {
        return;
    }

    switch (place->kind)
    {
    case ETA_PLACE_STREET:
        if (ETA_Place_AxisName(place->axis))
        {
            snprintf(out, outSize, "Street, %s, %d meters wide",
                     ETA_Place_AxisName(place->axis), place->widthMeters < 1 ? 1 : place->widthMeters);
        }
        else
        {
            snprintf(out, outSize, "Street");
        }
        break;
    case ETA_PLACE_ALLEY:
        snprintf(out, outSize, ETA_Place_AxisName(place->axis) ? "Alley, %s" : "Alley",
                 ETA_Place_AxisName(place->axis));
        break;
    case ETA_PLACE_SQUARE:
        snprintf(out, outSize, "Square");
        break;
    case ETA_PLACE_OPEN:
        snprintf(out, outSize, "Open ground");
        break;
    case ETA_PLACE_INDOORS:
        snprintf(out, outSize, "Indoors");
        break;
    case ETA_PLACE_UPPER_FLOOR:
        snprintf(out, outSize, "Indoors, upper floor");
        break;
    case ETA_PLACE_BALCONY:
        snprintf(out, outSize, "Balcony");
        break;
    case ETA_PLACE_ROOFTOP:
        snprintf(out, outSize, "Rooftop");
        break;
    case ETA_PLACE_LEDGE:
        if (place->dropMeters >= 25)
        {
            snprintf(out, outSize, "Ledge, a long drop beside");
        }
        else
        {
            snprintf(out, outSize, "Ledge, %d meter drop beside", place->dropMeters < 1 ? 1 : place->dropMeters);
        }
        break;
    case ETA_PLACE_UNKNOWN:
    case ETA_PLACE_COUNT:
    default:
        break;
    }
}

/* Places that are the same place to someone walking through them: a
   street narrowing to an alley, a square opening out. */
static int ETA_Place_Family(ETA_PlaceKind kind)
{
    switch (kind)
    {
    case ETA_PLACE_STREET:
    case ETA_PLACE_ALLEY:
        return 1;
    case ETA_PLACE_SQUARE:
    case ETA_PLACE_OPEN:
        return 2;
    default:
        return 10 + (int)kind;
    }
}

/* Whether two places are the same, as far as news goes. */
static int ETA_Place_Same(ETA_PlaceKind kindA, int axisA, ETA_PlaceKind kindB, int axisB)
{
    if (ETA_Place_Family(kindA) != ETA_Place_Family(kindB))
    {
        return 0;
    }

    /* A way that bends by one compass point is the same way; one that
       crosses it is another. */
    if (ETA_Place_Family(kindA) == 1 && axisA >= 0 && axisB >= 0)
    {
        return ((axisA - axisB + 4) % 4) != 2;
    }

    return 1;
}

/*
 * Recent places, voted on. Walking a real street the measurements flicker
 * - a doorway, a corner, a cart - between street, square and alley every
 * metre or two, and a place that had to be held unbroken was never held
 * long enough to be said: on the real Oasis a walk from the Allied spawn
 * to its command post said nothing outdoors at all. So the last couple of
 * seconds are voted on, and the place most of them agree on is the place.
 */
#define ETA_PLACE_SAMPLES    48
#define ETA_PLACE_MAJORITY   0.6f

typedef struct
{
    ETA_Place place;
    int       at;
} ETA_PlaceSample;

static ETA_PlaceSample gSamples[ETA_PLACE_SAMPLES];
static int             gSampleCount;
static int             gSampleNext;
static ETA_Place       gSpoken;
static int             gSpokenSet;

void ETA_Place_Reset(void)
{
    gSampleCount = 0;
    gSampleNext  = 0;
    gSpokenSet   = 0;
}

int ETA_Place_Update(const ETA_Place *place, int nowMs)
{
    int       family[ETA_PLACE_COUNT + 1];
    int       axisScore[4] = { 0, 0, 0, 0 };
    int       counts[ETA_PLACE_COUNT];
    int       total = 0, oldest = nowMs, i, k, best = -1, bestFamily = -1, bestCount = 0;
    ETA_Place winner;

    if (!place || place->kind <= ETA_PLACE_UNKNOWN || place->kind >= ETA_PLACE_COUNT)
    {
        return 0;
    }

    /* The clock going back - a new map, a demo - starts afresh. */
    if (gSampleCount > 0)
    {
        int last = (gSampleNext + ETA_PLACE_SAMPLES - 1) % ETA_PLACE_SAMPLES;

        if (nowMs < gSamples[last].at)
        {
            gSampleCount = 0;
            gSampleNext  = 0;
        }
    }

    gSamples[gSampleNext].place = *place;
    gSamples[gSampleNext].at    = nowMs;
    gSampleNext                 = (gSampleNext + 1) % ETA_PLACE_SAMPLES;
    if (gSampleCount < ETA_PLACE_SAMPLES)
    {
        gSampleCount++;
    }

    for (k = 0; k < ETA_PLACE_COUNT; k++)
    {
        counts[k] = 0;
    }
    for (k = 0; k <= ETA_PLACE_COUNT; k++)
    {
        family[k] = 0;
    }

    for (i = 0; i < gSampleCount; i++)
    {
        const ETA_PlaceSample *sample = &gSamples[(gSampleNext + ETA_PLACE_SAMPLES - 1 - i) % ETA_PLACE_SAMPLES];

        if (nowMs - sample->at > ETA_PLACE_WINDOW_MS)
        {
            break;
        }

        oldest = sample->at;
        total++;
        counts[sample->place.kind]++;

        /* One vote per sample for its family, indexed by the family's
           first kind so the tally fits the same array. */
        switch (ETA_Place_Family(sample->place.kind))
        {
        case 1:
            family[ETA_PLACE_STREET]++;
            if (sample->place.axis >= 0 && sample->place.axis < 4)
            {
                /* A street read one compass point off still counts
                   half toward the way it really runs. */
                axisScore[sample->place.axis] += 2;
                axisScore[(sample->place.axis + 1) % 4]++;
                axisScore[(sample->place.axis + 3) % 4]++;
            }
            break;
        case 2:
            family[ETA_PLACE_SQUARE]++;
            break;
        default:
            family[sample->place.kind]++;
            break;
        }
    }

    /* Not enough seen yet to know. */
    if (nowMs - oldest < ETA_PLACE_HOLD_MS)
    {
        return 0;
    }

    for (k = 1; k < ETA_PLACE_COUNT; k++)
    {
        if (family[k] > bestCount)
        {
            bestCount  = family[k];
            bestFamily = k;
        }
    }

    if (bestFamily < 0 || (float)bestCount < ETA_PLACE_MAJORITY * (float)total)
    {
        return 0;
    }

    /* What to call it: within a family, the kind most of it was; for a
       way, the way most of it ran; and the latest sample of that for the
       width or the drop. */
    if (bestFamily == ETA_PLACE_STREET)
    {
        best = counts[ETA_PLACE_ALLEY] > counts[ETA_PLACE_STREET] ? ETA_PLACE_ALLEY : ETA_PLACE_STREET;
    }
    else if (bestFamily == ETA_PLACE_SQUARE)
    {
        best = counts[ETA_PLACE_OPEN] > counts[ETA_PLACE_SQUARE] ? ETA_PLACE_OPEN : ETA_PLACE_SQUARE;
    }
    else
    {
        best = bestFamily;
    }

    winner      = *place;
    winner.kind = (ETA_PlaceKind)best;
    winner.axis = -1;

    if (bestFamily == ETA_PLACE_STREET)
    {
        for (k = 0; k < 4; k++)
        {
            if (winner.axis < 0 || axisScore[k] > axisScore[winner.axis])
            {
                winner.axis = k;
            }
        }
    }

    for (i = 0; i < gSampleCount; i++)
    {
        const ETA_PlaceSample *sample = &gSamples[(gSampleNext + ETA_PLACE_SAMPLES - 1 - i) % ETA_PLACE_SAMPLES];

        if (sample->place.kind == winner.kind)
        {
            winner.widthMeters = sample->place.widthMeters;
            winner.dropMeters  = sample->place.dropMeters;
            break;
        }
    }

    if (gSpokenSet && ETA_Place_Same(winner.kind, winner.axis, gSpoken.kind, gSpoken.axis))
    {
        return 0;
    }

    gSpoken    = winner;
    gSpokenSet = 1;
    return 1;
}

int ETA_Place_Spoken(ETA_Place *out)
{
    if (!gSpokenSet || !out)
    {
        return 0;
    }

    *out = gSpoken;
    return 1;
}

/* ---- The map survey ---- */

void ETA_PlaceSurvey_Clear(ETA_PlaceSurvey *survey)
{
    int r, c;

    if (!survey)
    {
        return;
    }

    for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
    {
        for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
        {
            survey->floors[r][c] = 0;
        }
    }
}

int ETA_PlaceSurvey_Add(ETA_PlaceSurvey *survey, int row, int column, const ETA_Place *place)
{
    int n;

    if (!survey || !place || row < 0 || row >= ETA_PLACE_SURVEY_SIDE
        || column < 0 || column >= ETA_PLACE_SURVEY_SIDE
        || place->kind <= ETA_PLACE_UNKNOWN || place->kind >= ETA_PLACE_COUNT)
    {
        return 0;
    }

    n = survey->floors[row][column];
    if (n >= ETA_PLACE_SURVEY_FLOORS)
    {
        return 0;
    }

    survey->place[row][column][n] = *place;
    survey->floors[row][column]   = (unsigned char)(n + 1);
    return 1;
}

static int ETA_PlaceSurvey_Has(const ETA_PlaceSurvey *survey, int row, int column, ETA_PlaceKind kind)
{
    int f;

    for (f = 0; f < survey->floors[row][column]; f++)
    {
        if (survey->place[row][column][f].kind == kind)
        {
            return 1;
        }
    }
    return 0;
}

/* Part of a building: inside it, on an upper floor, or on its roof. */
static int ETA_PlaceSurvey_Building(const ETA_PlaceSurvey *survey, int row, int column)
{
    return ETA_PlaceSurvey_Has(survey, row, column, ETA_PLACE_INDOORS)
           || ETA_PlaceSurvey_Has(survey, row, column, ETA_PLACE_UPPER_FLOOR)
           || ETA_PlaceSurvey_Has(survey, row, column, ETA_PLACE_ROOFTOP);
}

/* Where in the square, from the middle of it: "to the north-east", or
   "in the middle". Rows run from the north, columns from the west. */
static const char *ETA_PlaceSurvey_Where(float row, float column)
{
    static const char *const names[8] =
    {
        "to the north", "to the north-east", "to the east", "to the south-east",
        "to the south", "to the south-west", "to the west", "to the north-west"
    };
    const float middle = (ETA_PLACE_SURVEY_SIDE - 1) * 0.5f;
    float       east   = column - middle;
    float       north  = middle - row;
    int         sector;

    if (east * east + north * north < (ETA_PLACE_SURVEY_SIDE / 6.0f) * (ETA_PLACE_SURVEY_SIDE / 6.0f))
    {
        return "in the middle";
    }

    /* Which eighth of the compass, clockwise from north: compare against
       the lines at 22.5 degrees either side of each point. */
    {
        const float tan22 = 0.41421356f;
        float       ax    = east < 0 ? -east : east;
        float       ay    = north < 0 ? -north : north;

        if (ax <= tan22 * ay)
        {
            sector = north > 0 ? 0 : 4;
        }
        else if (ay <= tan22 * ax)
        {
            sector = east > 0 ? 2 : 6;
        }
        else if (north > 0)
        {
            sector = east > 0 ? 1 : 7;
        }
        else
        {
            sector = east > 0 ? 3 : 5;
        }
    }

    return names[sector];
}

static void ETA_PlaceSurvey_Append(char *out, size_t outSize, const char *part)
{
    size_t used = strlen(out);

    if (used + 2 + strlen(part) + 1 > outSize)
    {
        return;   /* a part cut in half would say something untrue */
    }

    if (used)
    {
        out[used++] = ',';
        out[used++] = ' ';
    }
    strcpy(out + used, part);
}

#define ETA_SURVEY_MAX_BUILDINGS 3

void ETA_PlaceSurvey_Describe(const ETA_PlaceSurvey *survey, char *out, size_t outSize)
{
    int           streets[4] = { 0, 0, 0, 0 }, alleys[4] = { 0, 0, 0, 0 };
    int           squares = 0, opens = 0, samples = 0;
    int           r, c, f, a, top;
    int           label[ETA_PLACE_SURVEY_SIDE][ETA_PLACE_SURVEY_SIDE];
    int           clusters = 0;
    char          part[128];

    if (!out || outSize == 0)
    {
        return;
    }
    out[0] = '\0';

    if (!survey)
    {
        return;
    }

    for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
    {
        for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
        {
            label[r][c] = 0;

            for (f = 0; f < survey->floors[r][c]; f++)
            {
                const ETA_Place *place = &survey->place[r][c][f];

                samples++;
                switch (place->kind)
                {
                case ETA_PLACE_STREET:
                case ETA_PLACE_ALLEY:
                    if (place->axis >= 0 && place->axis < 4)
                    {
                        if (place->kind == ETA_PLACE_STREET)
                        {
                            streets[place->axis]++;
                        }
                        else
                        {
                            alleys[place->axis]++;
                        }
                    }
                    break;
                case ETA_PLACE_SQUARE:
                    squares++;
                    break;
                case ETA_PLACE_OPEN:
                    opens++;
                    break;
                default:
                    break;
                }
            }
        }
    }

    if (!samples)
    {
        return;
    }

    /* The ways through it: the way most of the points lie along, and one
       crossing it square on. One a compass point off the first is the
       same way read a little crooked. */
    top = 0;
    for (a = 1; a < 4; a++)
    {
        if (streets[a] + alleys[a] > streets[top] + alleys[top])
        {
            top = a;
        }
    }

    {
        int minimum = samples / 12 > 3 ? samples / 12 : 3;
        int ways[2], w;

        ways[0] = top;
        ways[1] = (top + 2) % 4;

        for (w = 0; w < 2; w++)
        {
            a = ways[w];
            if (streets[a] + alleys[a] < minimum)
            {
                continue;
            }

            snprintf(part, sizeof(part), "%s running %s",
                     alleys[a] > streets[a] ? "an alley" : "a street", gAxisNames[a]);
            ETA_PlaceSurvey_Append(out, outSize, part);
        }
    }

    /* Open space. */
    {
        int minimum = samples / 6 > 3 ? samples / 6 : 3;

        if (squares + opens >= minimum)
        {
            ETA_PlaceSurvey_Append(out, outSize, opens > squares ? "open ground" : "a square");
        }
    }

    /* The buildings: the points inside one, or up on one, that touch,
       each group said with where it stands and what is up on it. */
    for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
    {
        for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
        {
            int stackRow[ETA_PLACE_SURVEY_SIDE * ETA_PLACE_SURVEY_SIDE];
            int stackColumn[ETA_PLACE_SURVEY_SIDE * ETA_PLACE_SURVEY_SIDE];
            int depth = 0;

            if (label[r][c] || !ETA_PlaceSurvey_Building(survey, r, c))
            {
                continue;
            }

            clusters++;
            label[r][c]        = clusters;
            stackRow[depth]    = r;
            stackColumn[depth] = c;
            depth++;

            while (depth > 0)
            {
                static const int step[4][2] = { { -1, 0 }, { 1, 0 }, { 0, -1 }, { 0, 1 } };
                int              pr, pc, s;

                depth--;
                pr = stackRow[depth];
                pc = stackColumn[depth];

                for (s = 0; s < 4; s++)
                {
                    int nr = pr + step[s][0], nc = pc + step[s][1];

                    if (nr < 0 || nr >= ETA_PLACE_SURVEY_SIDE || nc < 0 || nc >= ETA_PLACE_SURVEY_SIDE
                        || label[nr][nc] || !ETA_PlaceSurvey_Building(survey, nr, nc))
                    {
                        continue;
                    }

                    label[nr][nc]      = clusters;
                    stackRow[depth]    = nr;
                    stackColumn[depth] = nc;
                    depth++;
                }
            }
        }
    }

    {
        int said[ETA_SURVEY_MAX_BUILDINGS + 1];
        int count = 0, k;

        /* Biggest first, and only those big enough to be more than a
           doorway seen from the street. */
        for (k = 0; k < ETA_SURVEY_MAX_BUILDINGS; k++)
        {
            int best = 0, bestSize = 0, id;

            for (id = 1; id <= clusters; id++)
            {
                int size = 0, j, taken = 0;

                for (j = 0; j < count; j++)
                {
                    taken |= said[j] == id;
                }
                if (taken)
                {
                    continue;
                }

                for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
                {
                    for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
                    {
                        size += label[r][c] == id;
                    }
                }

                if (size > bestSize)
                {
                    best     = id;
                    bestSize = size;
                }
            }

            if (bestSize < 3)
            {
                break;
            }
            said[count++] = best;

            {
                float sumRow = 0, sumColumn = 0;
                int   inside = 0, upper = 0, balcony = 0, roof = 0, n = 0;
                const char *extras[3];
                int   extraCount = 0, e;

                for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
                {
                    for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
                    {
                        int dr, dc;

                        /* A balcony stands out from the wall, so one
                           beside the building is on it. */
                        if (!balcony && ETA_PlaceSurvey_Has(survey, r, c, ETA_PLACE_BALCONY))
                        {
                            for (dr = -1; dr <= 1; dr++)
                            {
                                for (dc = -1; dc <= 1; dc++)
                                {
                                    int nr = r + dr, nc = c + dc;

                                    if (nr >= 0 && nr < ETA_PLACE_SURVEY_SIDE && nc >= 0
                                        && nc < ETA_PLACE_SURVEY_SIDE && label[nr][nc] == best)
                                    {
                                        balcony = 1;
                                    }
                                }
                            }
                        }

                        if (label[r][c] != best)
                        {
                            continue;
                        }

                        n++;
                        sumRow    += (float)r;
                        sumColumn += (float)c;
                        inside    |= ETA_PlaceSurvey_Has(survey, r, c, ETA_PLACE_INDOORS);
                        upper     |= ETA_PlaceSurvey_Has(survey, r, c, ETA_PLACE_UPPER_FLOOR);
                        roof      |= ETA_PlaceSurvey_Has(survey, r, c, ETA_PLACE_ROOFTOP);
                    }
                }

                if (upper)
                {
                    extras[extraCount++] = "an upper floor";
                }
                if (balcony)
                {
                    extras[extraCount++] = "a balcony";
                }
                if (roof && (inside || upper))
                {
                    extras[extraCount++] = "a rooftop";
                }

                snprintf(part, sizeof(part), "%s %s",
                         inside || upper ? "a building" : "a rooftop",
                         ETA_PlaceSurvey_Where(sumRow / (float)n, sumColumn / (float)n));

                for (e = 0; e < extraCount; e++)
                {
                    size_t used = strlen(part);

                    snprintf(part + used, sizeof(part) - used, "%s%s",
                             e == 0 ? " with " : e == extraCount - 1 ? " and " : ", ", extras[e]);
                }

                ETA_PlaceSurvey_Append(out, outSize, part);
            }
        }

        /* A balcony on its own - its building outside the square. */
        {
            float sumRow = 0, sumColumn = 0;
            int   n = 0;

            for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
            {
                for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
                {
                    int dr, dc, near = 0;

                    if (!ETA_PlaceSurvey_Has(survey, r, c, ETA_PLACE_BALCONY))
                    {
                        continue;
                    }

                    for (dr = -1; dr <= 1; dr++)
                    {
                        for (dc = -1; dc <= 1; dc++)
                        {
                            int nr = r + dr, nc = c + dc, j;

                            if (nr < 0 || nr >= ETA_PLACE_SURVEY_SIDE || nc < 0 || nc >= ETA_PLACE_SURVEY_SIDE)
                            {
                                continue;
                            }
                            for (j = 0; j < count; j++)
                            {
                                near |= label[nr][nc] == said[j];
                            }
                        }
                    }

                    if (!near)
                    {
                        n++;
                        sumRow    += (float)r;
                        sumColumn += (float)c;
                    }
                }
            }

            if (n >= 2)
            {
                snprintf(part, sizeof(part), "a balcony %s",
                         ETA_PlaceSurvey_Where(sumRow / (float)n, sumColumn / (float)n));
                ETA_PlaceSurvey_Append(out, outSize, part);
            }
        }
    }
}

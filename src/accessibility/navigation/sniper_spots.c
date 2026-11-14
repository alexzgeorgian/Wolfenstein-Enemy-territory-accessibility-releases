#include "sniper_spots.h"

#include <stdio.h>
#include <string.h>

void ETA_SpotView_Clear(ETA_SpotView *view)
{
    if (view)
    {
        memset(view, 0, sizeof(*view));
    }
}

void ETA_SpotView_Add(ETA_SpotView *view, int direction, float meters, int seen,
                      float dropMeters, float stepMeters)
{
    if (!view || direction < 0 || direction >= ETA_SPOT_DIRECTIONS || !seen)
    {
        return;
    }

    view->seenMeters[direction] += stepMeters;
    if (meters > view->farMeters[direction])
    {
        view->farMeters[direction] = meters;
    }
    view->dropSum[direction] += dropMeters;
    view->dropCount[direction]++;
}

ETA_SpotRating ETA_Spot_Rate(const ETA_SpotView *view)
{
    ETA_SpotRating rating;
    int            first, k, best = -1;
    float          bestScore = -1.0f;

    memset(&rating, 0, sizeof(rating));
    if (!view)
    {
        return rating;
    }

    /* Every quarter of the compass, starting at each direction in turn:
       the one with the most ground in sight. */
    for (first = 0; first < ETA_SPOT_DIRECTIONS; first++)
    {
        float score = 0.0f;

        for (k = 0; k < ETA_SPOT_SECTOR; k++)
        {
            score += view->seenMeters[(first + k) % ETA_SPOT_DIRECTIONS];
        }

        if (score > bestScore)
        {
            bestScore = score;
            best      = first;
        }
    }

    if (best < 0 || bestScore <= 0.0f)
    {
        return rating;
    }

    {
        float far = 0.0f, drop = 0.0f;
        int   drops = 0;

        for (k = 0; k < ETA_SPOT_SECTOR; k++)
        {
            int d = (best + k) % ETA_SPOT_DIRECTIONS;

            if (view->farMeters[d] > far)
            {
                far = view->farMeters[d];
            }
            drop  += view->dropSum[d];
            drops += view->dropCount[d];
        }

        rating.score        = bestScore;
        rating.bearing      = ((float)best + (ETA_SPOT_SECTOR - 1) * 0.5f) * (360.0f / ETA_SPOT_DIRECTIONS);
        rating.viewMeters   = (int)(far + 0.5f);
        rating.heightMeters = drops ? (int)(drop / (float)drops + 0.5f) : 0;

        while (rating.bearing >= 360.0f)
        {
            rating.bearing -= 360.0f;
        }
    }

    return rating;
}

int ETA_Spot_Worth(const ETA_SpotRating *rating)
{
    return rating
           && (float)rating->heightMeters >= ETA_SPOT_MIN_HEIGHT_METERS
           && (float)rating->viewMeters >= ETA_SPOT_MIN_VIEW_METERS
           && rating->score >= ETA_SPOT_MIN_SCORE_METERS;
}

const char *ETA_Spot_Compass(float bearing)
{
    static const char *const names[8] =
    {
        "north", "north-east", "east", "south-east",
        "south", "south-west", "west", "north-west"
    };
    int sector;

    while (bearing < 0.0f)
    {
        bearing += 360.0f;
    }
    sector = (int)((bearing + 22.5f) / 45.0f) % 8;
    return names[sector];
}

void ETA_Spot_Text(ETA_PlaceKind kind, const ETA_SpotRating *rating, char *out, size_t outSize)
{
    const char *what;

    if (!out || outSize == 0)
    {
        return;
    }
    out[0] = '\0';
    if (!rating)
    {
        return;
    }

    switch (kind)
    {
    case ETA_PLACE_ROOFTOP:
        what = "Rooftop";
        break;
    case ETA_PLACE_BALCONY:
        what = "Balcony";
        break;
    case ETA_PLACE_UPPER_FLOOR:
        what = "Upper floor window";
        break;
    case ETA_PLACE_LEDGE:
        what = "Ledge";
        break;
    default:
        what = "High ground";
        break;
    }

    snprintf(out, outSize, "%s, sees %d meters to the %s, %d meters up",
             what, rating->viewMeters, ETA_Spot_Compass(rating->bearing), rating->heightMeters);
}

void ETA_SpotList_Clear(ETA_SpotList *list)
{
    if (list)
    {
        list->count = 0;
    }
}

static float ETA_Spot_Flat(const float a[3], const float b[3])
{
    float dx = a[0] - b[0], dy = a[1] - b[1];

    return dx * dx + dy * dy;
}

int ETA_SpotList_Offer(ETA_SpotList *list, const float origin[3], ETA_PlaceKind kind,
                       const ETA_SpotRating *rating)
{
    int i, slot = -1;

    if (!list || !origin || !rating || !ETA_Spot_Worth(rating))
    {
        return 0;
    }

    /* The same spot as one already found: the better of the two. Within
       twenty metres on the same level, a sniper sees the same things -
       and a long roof is one spot to go to, not four. */
    for (i = 0; i < list->count; i++)
    {
        float dz = list->spots[i].origin[2] - origin[2];

        if (ETA_Spot_Flat(list->spots[i].origin, origin) < ETA_SPOT_APART_UNITS * ETA_SPOT_APART_UNITS
            && dz < 128.0f && dz > -128.0f)
        {
            if (rating->score <= list->spots[i].rating.score)
            {
                return 0;
            }
            slot = i;
            break;
        }
    }

    if (slot < 0)
    {
        if (list->count < ETA_SPOT_MAX)
        {
            slot = list->count++;
        }
        else
        {
            int worst = 0;

            for (i = 1; i < list->count; i++)
            {
                if (list->spots[i].rating.score < list->spots[worst].rating.score)
                {
                    worst = i;
                }
            }
            if (rating->score <= list->spots[worst].rating.score)
            {
                return 0;
            }
            slot = worst;
        }
    }

    list->spots[slot].origin[0]   = origin[0];
    list->spots[slot].origin[1]   = origin[1];
    list->spots[slot].origin[2]   = origin[2];
    list->spots[slot].kind        = kind;
    list->spots[slot].rating      = *rating;
    list->spots[slot].unreachable = 0;
    list->spots[slot].checked     = 0;
    return 1;
}

int ETA_SpotList_Nearest(const ETA_SpotList *list, const float from[3], int *out, int max)
{
    int count = 0, i, j;

    if (!list || !from || !out || max <= 0)
    {
        return 0;
    }

    for (i = 0; i < list->count && count < max; i++)
    {
        if (!list->spots[i].unreachable)
        {
            out[count++] = i;
        }
    }

    /* Nearest first; the lists are short. */
    for (i = 1; i < count; i++)
    {
        int   index = out[i];
        float d     = ETA_Spot_Flat(list->spots[index].origin, from);

        for (j = i; j > 0 && ETA_Spot_Flat(list->spots[out[j - 1]].origin, from) > d; j--)
        {
            out[j] = out[j - 1];
        }
        out[j] = index;
    }

    return count;
}

/*
 * Which raised places are worth going to with a sniper rifle, and how
 * they are said.
 *
 * The tester asked for help choosing a good spot to snipe from. A spot
 * is judged on the best quarter of its view: how much ground out there a
 * standing player could see, how far, and how far above it they stand.
 * A view read the wrong way round would send a player up to a roof that
 * looks at a wall, so the direction is pinned here for every quarter.
 */

#include "navigation/sniper_spots.h"
#include "smoke_check.h"

#include <string.h>

/* Ground seen in one direction, every 8 metres out to 'far', 'drop'
   metres below. */
static void Look(ETA_SpotView *view, int direction, float far, float drop)
{
    float m;

    for (m = 8.0f; m <= far; m += 8.0f)
    {
        ETA_SpotView_Add(view, direction, m, 1, drop, 8.0f);
    }
}

int main(void)
{
    ETA_SpotView   view;
    ETA_SpotRating rating;
    char           text[128];
    int            d;

    SMOKE_BANNER("sniper_spots");

    /* --- Nothing seen: nothing worth going to --- */
    ETA_SpotView_Clear(&view);
    rating = ETA_Spot_Rate(&view);
    CHECK(rating.score == 0.0f);
    CHECK(!ETA_Spot_Worth(&rating));
    CHECK(!ETA_Spot_Worth(NULL));

    /* --- A roof looking south-east over open ground, 6 m up --- */
    ETA_SpotView_Clear(&view);
    for (d = 5; d <= 7; d++)            /* east-south-east to south-south-east */
    {
        Look(&view, d, 64.0f, 6.0f);
    }
    Look(&view, 0, 16.0f, 6.0f);        /* a little to the north */
    rating = ETA_Spot_Rate(&view);
    CHECK(rating.viewMeters == 64);
    CHECK(rating.heightMeters == 6);
    CHECK(rating.score >= 3 * 64.0f - 0.01f);
    CHECK(strcmp(ETA_Spot_Compass(rating.bearing), "south-east") == 0);
    CHECK(ETA_Spot_Worth(&rating));
    ETA_Spot_Text(ETA_PLACE_ROOFTOP, &rating, text, sizeof(text));
    CHECK(strcmp(text, "Rooftop, sees 64 meters to the south-east, 6 meters up") == 0);

    /* --- Every quarter of the compass comes out the right way round --- */
    {
        static const char *const want[8] =
        {
            "north", "north-east", "east", "south-east",
            "south", "south-west", "west", "north-west"
        };
        int k;

        for (k = 0; k < 8; k++)
        {
            int middle = k * 2;   /* the direction pointing that way */

            ETA_SpotView_Clear(&view);
            Look(&view, (middle + ETA_SPOT_DIRECTIONS - 1) % ETA_SPOT_DIRECTIONS, 48.0f, 4.0f);
            Look(&view, middle, 64.0f, 4.0f);
            Look(&view, (middle + 1) % ETA_SPOT_DIRECTIONS, 48.0f, 4.0f);
            rating = ETA_Spot_Rate(&view);
            CHECK(strcmp(ETA_Spot_Compass(rating.bearing), want[k]) == 0);
        }
    }

    /* --- Not high enough, or not far enough: not a sniper spot --- */
    ETA_SpotView_Clear(&view);
    for (d = 0; d < 4; d++)
    {
        Look(&view, d, 64.0f, 1.0f);    /* ground level */
    }
    rating = ETA_Spot_Rate(&view);
    CHECK(!ETA_Spot_Worth(&rating));

    ETA_SpotView_Clear(&view);
    for (d = 0; d < 4; d++)
    {
        Look(&view, d, 16.0f, 8.0f);    /* high, but looks at a wall */
    }
    rating = ETA_Spot_Rate(&view);
    CHECK(!ETA_Spot_Worth(&rating));

    /* Unseen ground counts for nothing. */
    ETA_SpotView_Clear(&view);
    ETA_SpotView_Add(&view, 3, 80.0f, 0, 6.0f, 8.0f);
    ETA_SpotView_Add(&view, -1, 80.0f, 1, 6.0f, 8.0f);
    ETA_SpotView_Add(&view, ETA_SPOT_DIRECTIONS, 80.0f, 1, 6.0f, 8.0f);
    rating = ETA_Spot_Rate(&view);
    CHECK(rating.score == 0.0f);

    /* --- The list --- */
    {
        static ETA_SpotList list;
        ETA_SpotRating      good, better, poor;
        float               a[3] = { 0, 0, 100 }, b[3] = { 200, 0, 100 }, c[3] = { 3000, 0, 100 };
        float               upstairs[3] = { 200, 0, 400 }, here[3] = { 2900, 0, 0 };
        int                 order[ETA_SPOT_MAX], n, i;

        memset(&good, 0, sizeof(good));
        good.score        = 120.0f;
        good.viewMeters   = 50;
        good.heightMeters = 5;
        better            = good;
        better.score      = 200.0f;
        poor              = good;
        poor.heightMeters = 1;

        ETA_SpotList_Clear(&list);
        CHECK(ETA_SpotList_Offer(&list, a, ETA_PLACE_ROOFTOP, &good) == 1);
        CHECK(ETA_SpotList_Offer(&list, a, ETA_PLACE_ROOFTOP, &poor) == 0);   /* not worth it */
        CHECK(list.count == 1);

        /* Five metres along the same roof: the same spot, the better
           view kept. */
        CHECK(ETA_SpotList_Offer(&list, b, ETA_PLACE_ROOFTOP, &better) == 1);
        CHECK(list.count == 1);
        CHECK(list.spots[0].origin[0] == 200.0f);
        CHECK(ETA_SpotList_Offer(&list, a, ETA_PLACE_ROOFTOP, &good) == 0);
        CHECK(list.count == 1);

        /* A floor above it is another spot; so is one far off. */
        CHECK(ETA_SpotList_Offer(&list, upstairs, ETA_PLACE_BALCONY, &good) == 1);
        CHECK(ETA_SpotList_Offer(&list, c, ETA_PLACE_LEDGE, &good) == 1);
        CHECK(list.count == 3);

        /* Nearest first, and one with no way there left out. */
        n = ETA_SpotList_Nearest(&list, here, order, ETA_SPOT_MAX);
        CHECK(n == 3);
        CHECK(order[0] == 2);
        list.spots[2].unreachable = 1;
        n = ETA_SpotList_Nearest(&list, here, order, ETA_SPOT_MAX);
        CHECK(n == 2);
        CHECK(order[0] == 0 || order[0] == 1);

        /* Full: a better spot takes the worst one's place, a worse one
           is turned away. */
        ETA_SpotList_Clear(&list);
        for (i = 0; i < ETA_SPOT_MAX; i++)
        {
            float at[3];

            at[0] = (float)i * 1000.0f;
            at[1] = 0.0f;
            at[2] = 0.0f;
            CHECK(ETA_SpotList_Offer(&list, at, ETA_PLACE_ROOFTOP, &good) == 1);
        }
        {
            float far[3] = { 0, 50000, 0 };

            CHECK(ETA_SpotList_Offer(&list, far, ETA_PLACE_ROOFTOP, &good) == 0);
            CHECK(ETA_SpotList_Offer(&list, far, ETA_PLACE_ROOFTOP, &better) == 1);
            CHECK(list.count == ETA_SPOT_MAX);
        }
        CHECK(ETA_SpotList_Nearest(NULL, here, order, ETA_SPOT_MAX) == 0);
    }

    return SMOKE_REPORT("sniper_spots");
}

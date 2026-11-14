/*
 * What kind of place the player is standing in, from what the game can
 * measure around them.
 *
 * The tester asked to follow streets and alleys and to tell the parts of
 * a building apart - balconies, rooftops. Each rule here is pinned with
 * a place drawn in numbers: a street running north to south, the same
 * street turned east to west, an alley, a square, a hall, an upper
 * floor, a balcony and a roof. A street read the wrong way round would
 * send a player down the wrong road with confidence, so both ways are
 * checked, and the diagonals.
 */

#include "navigation/place_classifier.h"
#include "smoke_check.h"

#include <string.h>

static ETA_PlaceProbe Open(float reach)
{
    ETA_PlaceProbe probe;
    int            d;

    memset(&probe, 0, sizeof(probe));
    probe.skyAbove = 1;
    for (d = 0; d < ETA_PLACE_DIRECTIONS; d++)
    {
        probe.reach[d] = reach;
    }
    return probe;
}

/* Walls either side across one axis, the way running on along the
   other: across is the full width between the walls. */
static ETA_PlaceProbe Way(int axis, float across, float along)
{
    ETA_PlaceProbe probe = Open(0.0f);
    int            d;

    for (d = 0; d < ETA_PLACE_DIRECTIONS; d++)
    {
        int a = d % 4;

        if (a == axis)
        {
            probe.reach[d] = along / 2.0f;
        }
        else if (a == (axis + 2) % 4)
        {
            probe.reach[d] = across / 2.0f;
            probe.wall[d]  = 1;
        }
        else
        {
            /* The diagonals meet the walls further off. */
            probe.reach[d] = across / 2.0f * 1.414f;
            probe.wall[d]  = 1;
        }
    }
    return probe;
}

static ETA_Place Kind(ETA_PlaceKind kind, int axis)
{
    ETA_Place place;

    place.kind        = kind;
    place.axis        = axis;
    place.widthMeters = 0;
    place.dropMeters  = 0;
    return place;
}

/* Measured every quarter second from 'from' to 'to': how many times it
   was news, and when it first was. */
static int Feed(const ETA_Place *place, int from, int to, int *saidAt)
{
    int t, times = 0;

    *saidAt = -1;
    for (t = from; t <= to; t += 250)
    {
        if (ETA_Place_Update(place, t))
        {
            if (!times)
            {
                *saidAt = t;
            }
            times++;
        }
    }
    return times;
}

int main(void)
{
    ETA_PlaceProbe probe;
    ETA_Place      place, said;
    char           text[96];
    int            axis, saidAt;

    SMOKE_BANNER("place_classifier");

    /* --- Streets and alleys, every way round --- */
    for (axis = 0; axis < 4; axis++)
    {
        probe = Way(axis, 320.0f, 1600.0f);
        place = ETA_Place_Classify(&probe);
        CHECK(place.kind == ETA_PLACE_STREET);
        CHECK(place.axis == axis);
        CHECK(place.widthMeters == 8);

        probe = Way(axis, 120.0f, 900.0f);
        place = ETA_Place_Classify(&probe);
        CHECK(place.kind == ETA_PLACE_ALLEY);
        CHECK(place.axis == axis);
    }

    probe = Way(0, 320.0f, 1600.0f);
    place = ETA_Place_Classify(&probe);
    ETA_Place_Text(&place, text, sizeof(text));
    CHECK(strcmp(text, "Street, north to south, 8 meters wide") == 0);

    probe = Way(2, 120.0f, 900.0f);
    place = ETA_Place_Classify(&probe);
    ETA_Place_Text(&place, text, sizeof(text));
    CHECK(strcmp(text, "Alley, east to west") == 0);

    /* A short gap between two walls is not a street: it has to run on. */
    probe = Way(0, 320.0f, 400.0f);
    place = ETA_Place_Classify(&probe);
    CHECK(place.kind != ETA_PLACE_STREET && place.kind != ETA_PLACE_ALLEY);

    /* --- Open places --- */
    {
        int d;

        probe = Open(700.0f);
        for (d = 0; d < ETA_PLACE_DIRECTIONS; d++)
        {
            probe.wall[d] = 1;
        }
        place = ETA_Place_Classify(&probe);
        CHECK(place.kind == ETA_PLACE_SQUARE);
        CHECK(place.axis == -1);

        probe = Open(800.0f);
        place = ETA_Place_Classify(&probe);
        CHECK(place.kind == ETA_PLACE_OPEN);
    }

    /* --- Buildings --- */
    probe          = Way(0, 320.0f, 1600.0f);
    probe.skyAbove = 0;
    place          = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_INDOORS);   /* a corridor is still indoors */

    probe.airBelow = 1;
    place          = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_UPPER_FLOOR);
    ETA_Place_Text(&place, text, sizeof(text));
    CHECK(strcmp(text, "Indoors, upper floor") == 0);

    /* --- Up off the ground, open to the sky --- */
    probe            = Way(2, 120.0f, 400.0f);
    probe.dropBeside = 200.0f;
    probe.airBelow   = 1;
    place            = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_BALCONY);

    /* The same, with the house wall on one side only and the drop on
       the other - the way balconies are built. */
    probe.wall[4] = 0;
    probe.wall[3] = probe.wall[5] = 0;
    place         = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_BALCONY);

    probe            = Open(500.0f);
    probe.dropBeside = 300.0f;
    probe.airBelow   = 1;
    place            = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_ROOFTOP);

    /* The corner of a flat roof: narrow across the corner, with the edge
       either side and no wall - still the roof. */
    probe            = Open(500.0f);
    probe.reach[1]   = 80.0f;
    probe.reach[5]   = 80.0f;
    probe.dropBeside = 300.0f;
    probe.airBelow   = 1;
    place            = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_ROOFTOP);

    /* Solid ground and a drop beside: a ledge, said with the drop - the
       fall it would be. Not a balcony: there is no building under it. */
    probe            = Way(2, 120.0f, 400.0f);
    probe.dropBeside = 160.0f;
    place            = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_LEDGE);
    CHECK(place.dropMeters == 4);
    ETA_Place_Text(&place, text, sizeof(text));
    CHECK(strcmp(text, "Ledge, 4 meter drop beside") == 0);
    probe.dropBeside = 1024.0f;
    place            = ETA_Place_Classify(&probe);
    ETA_Place_Text(&place, text, sizeof(text));
    CHECK(strcmp(text, "Ledge, a long drop beside") == 0);

    probe          = Open(500.0f);
    probe.airBelow = 1;
    place          = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_ROOFTOP);

    /* A step down off a kerb is not a balcony. */
    probe            = Way(0, 320.0f, 1600.0f);
    probe.dropBeside = 40.0f;
    place            = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_STREET);

    /* --- Names --- */
    CHECK(ETA_Place_KindName(ETA_PLACE_UNKNOWN) == NULL);
    CHECK(ETA_Place_KindName(ETA_PLACE_COUNT) == NULL);
    CHECK(strcmp(ETA_Place_KindName(ETA_PLACE_ROOFTOP), "rooftop") == 0);
    CHECK(ETA_Place_AxisName(-1) == NULL);
    CHECK(ETA_Place_AxisName(4) == NULL);
    CHECK(ETA_Place_Classify(NULL).kind == ETA_PLACE_UNKNOWN);
    place.kind = ETA_PLACE_UNKNOWN;
    ETA_Place_Text(&place, text, sizeof(text));
    CHECK(text[0] == '\0');

    /* --- When it is said ---
       The game measures four times a second; so do these. */
    ETA_Place_Reset();
    probe = Way(0, 320.0f, 1600.0f);
    place = ETA_Place_Classify(&probe);
    CHECK(Feed(&place, 1000, 1000 + ETA_PLACE_HOLD_MS - 1, &saidAt) == 0); /* just arrived */
    CHECK(Feed(&place, 1000 + ETA_PLACE_HOLD_MS, 6000, &saidAt) == 1);     /* held: said once */
    CHECK(saidAt >= 1000 + ETA_PLACE_HOLD_MS && saidAt <= 1000 + ETA_PLACE_HOLD_MS + 250);
    CHECK(ETA_Place_Spoken(&said) && said.kind == ETA_PLACE_STREET && said.axis == 0);

    /* A doorway's moment of something else does not make it news again. */
    {
        ETA_Place doorway;

        doorway.kind        = ETA_PLACE_INDOORS;
        doorway.axis        = -1;
        doorway.widthMeters = 0;
        doorway.dropMeters  = 0;
        CHECK(Feed(&doorway, 6250, 6750, &saidAt) == 0);
        CHECK(Feed(&place, 7000, 10000, &saidAt) == 0);
    }

    /* A street that bends one compass point, or narrows to an alley, is
       the same street. */
    probe = Way(1, 320.0f, 1600.0f);
    place = ETA_Place_Classify(&probe);
    CHECK(Feed(&place, 10250, 14000, &saidAt) == 0);
    probe = Way(0, 120.0f, 900.0f);
    place = ETA_Place_Classify(&probe);
    CHECK(place.kind == ETA_PLACE_ALLEY);
    CHECK(Feed(&place, 14250, 18000, &saidAt) == 0);

    /* Turning into a street the other way round is news - once most of
       what was seen lately runs the new way, which is a little sooner
       than the hold, as the way already seen is still a way. */
    probe = Way(2, 320.0f, 1600.0f);
    place = ETA_Place_Classify(&probe);
    CHECK(Feed(&place, 18250, 24000, &saidAt) == 1);
    CHECK(saidAt >= 18250 + ETA_PLACE_WINDOW_MS / 2 - 250 && saidAt <= 18250 + ETA_PLACE_HOLD_MS + 250);
    CHECK(ETA_Place_Spoken(&said) && said.kind == ETA_PLACE_STREET && said.axis == 2);

    /* A reading that flickers - every third one open ground - still says
       the street, once, and the open ground never. */
    ETA_Place_Reset();
    {
        ETA_PlaceProbe openProbe = Open(800.0f);
        ETA_Place      open      = ETA_Place_Classify(&openProbe);
        int            t, times = 0;

        probe = Way(0, 320.0f, 1600.0f);
        place = ETA_Place_Classify(&probe);
        for (t = 0; t <= 8000; t += 250)
        {
            times += ETA_Place_Update((t / 250) % 3 == 2 ? &open : &place, t);
        }
        CHECK(times == 1);
        CHECK(ETA_Place_Spoken(&said) && said.kind == ETA_PLACE_STREET);
    }

    /* The clock going back starts the hold again rather than saying it. */
    probe = Open(800.0f);
    place = ETA_Place_Classify(&probe);
    CHECK(Feed(&place, 20000, 20000, &saidAt) == 0);
    CHECK(Feed(&place, 100, 100 + ETA_PLACE_HOLD_MS - 1, &saidAt) == 0);
    CHECK(Feed(&place, 100 + ETA_PLACE_HOLD_MS, 4000, &saidAt) == 1);

    /* --- A square of the map, read as a whole --- */
    {
        static ETA_PlaceSurvey survey;
        ETA_Place              street = Kind(ETA_PLACE_STREET, 0);
        ETA_Place              inside = Kind(ETA_PLACE_INDOORS, -1);
        ETA_Place              roof   = Kind(ETA_PLACE_ROOFTOP, -1);
        ETA_Place              ledge  = Kind(ETA_PLACE_BALCONY, -1);
        ETA_Place              nothing = Kind(ETA_PLACE_UNKNOWN, -1);
        char                   words[200];
        int                    r, c;

        /* Nowhere to stand: nothing said. */
        ETA_PlaceSurvey_Clear(&survey);
        ETA_PlaceSurvey_Describe(&survey, words, sizeof(words));
        CHECK(words[0] == '\0');

        CHECK(ETA_PlaceSurvey_Add(&survey, -1, 0, &street) == 0);
        CHECK(ETA_PlaceSurvey_Add(&survey, 0, ETA_PLACE_SURVEY_SIDE, &street) == 0);
        CHECK(ETA_PlaceSurvey_Add(&survey, 0, 0, &nothing) == 0);
        CHECK(ETA_PlaceSurvey_Add(NULL, 0, 0, &street) == 0);

        /* A street down the middle, and to the east a building with a
           roof, a balcony on its street side. */
        for (r = 0; r < ETA_PLACE_SURVEY_SIDE; r++)
        {
            ETA_PlaceSurvey_Add(&survey, r, 4, &street);
            ETA_PlaceSurvey_Add(&survey, r, 5, &street);

            for (c = 7; c < ETA_PLACE_SURVEY_SIDE; c++)
            {
                ETA_PlaceSurvey_Add(&survey, r, c, &inside);
                ETA_PlaceSurvey_Add(&survey, r, c, &roof);
            }
        }
        ETA_PlaceSurvey_Add(&survey, 3, 6, &ledge);
        ETA_PlaceSurvey_Add(&survey, 4, 6, &ledge);
        ETA_PlaceSurvey_Describe(&survey, words, sizeof(words));
        CHECK(strcmp(words, "a street running north to south, "
                            "a building to the east with a balcony and a rooftop") == 0);

        /* A part that will not fit is left out whole, never cut. */
        ETA_PlaceSurvey_Describe(&survey, words, 40);
        CHECK(strcmp(words, "a street running north to south") == 0);

        /* A street crossing it east to west makes a crossroads; a way
           seen at two points only is not a way, nor one room a building. */
        for (c = 0; c < ETA_PLACE_SURVEY_SIDE; c++)
        {
            ETA_Place across = Kind(ETA_PLACE_ALLEY, 2);

            if (c < 4 || c > 5)
            {
                ETA_PlaceSurvey_Add(&survey, 5, c, &across);
            }
        }
        ETA_PlaceSurvey_Describe(&survey, words, sizeof(words));
        CHECK(strncmp(words, "a street running north to south, an alley running east to west, ", 63) == 0);

        ETA_PlaceSurvey_Clear(&survey);
        {
            ETA_Place diagonal = Kind(ETA_PLACE_STREET, 1);
            ETA_Place square   = Kind(ETA_PLACE_SQUARE, -1);

            ETA_PlaceSurvey_Add(&survey, 0, 0, &diagonal);
            ETA_PlaceSurvey_Add(&survey, 1, 1, &diagonal);
            ETA_PlaceSurvey_Add(&survey, 9, 9, &inside);
            for (r = 2; r < 8; r++)
            {
                for (c = 2; c < 8; c++)
                {
                    ETA_PlaceSurvey_Add(&survey, r, c, &square);
                }
            }
        }
        ETA_PlaceSurvey_Describe(&survey, words, sizeof(words));
        CHECK(strcmp(words, "a square") == 0);

        /* A building in the middle, and one in the north-west corner. */
        ETA_PlaceSurvey_Clear(&survey);
        for (r = 4; r <= 5; r++)
        {
            for (c = 4; c <= 5; c++)
            {
                ETA_PlaceSurvey_Add(&survey, r, c, &inside);
            }
        }
        ETA_PlaceSurvey_Add(&survey, 0, 0, &inside);
        ETA_PlaceSurvey_Add(&survey, 0, 1, &inside);
        ETA_PlaceSurvey_Add(&survey, 1, 0, &inside);
        ETA_PlaceSurvey_Describe(&survey, words, sizeof(words));
        CHECK(strcmp(words, "a building in the middle, a building to the north-west") == 0);
    }

    return SMOKE_REPORT("place_classifier");
}

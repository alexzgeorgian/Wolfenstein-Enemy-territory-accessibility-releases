/*
 * The map survey cursor, and the bearings the survey speaks.
 *
 * Two things in here can be wrong in a way nothing else would catch.
 *
 * The first is the direction of the rows. ET numbers its grid rows from
 * the north edge downward, so north is row 0 and stepping north has to
 * make the row *smaller*. Written the other way round it compiles,
 * runs, and mirrors the whole battlefield north for south - a player
 * sent to defend the wrong end of the map, confidently. This project
 * has already shipped exactly that shape of defect once, as bearings
 * reversed left for right, so it gets pinned here and again against the
 * engine's own grid formula in map_grid_test.py.
 *
 * The second is the bearing. The survey speaks a direction twice over -
 * as a compass point and as a number of degrees - and those come from
 * one conversion on purpose. A player told "north-east, 210 degrees"
 * has been given two facts that cannot both be true and no way to know
 * which to trust. So this requires the number and the word to agree at
 * every one of the eight points, and requires the number itself to be a
 * true bearing: north 0, east 90, climbing clockwise. The engine's yaw
 * is neither - it puts north at 90 and counts the other way - so
 * handing a raw yaw to a player would be wrong twice over.
 */

#include "core/accessibility_runtime.h"
#include "core/error_handler.h"
#include "hud/hud_narrator.h"
#include "map/map_survey.h"
#include "smoke_check.h"

#include <string.h>

int main(void)
{
    ETA_MapCursor cursor;
    int           i;

    SMOKE_BANNER("map_survey");

    ETA_AccessibilityRuntime_Init();
    ETA_HudNarrator_Init();

    /* --- opening only on a grid that was actually read ------------- */

    /* A map whose grid could not be read leaves the survey closed. The
       alternative is a cursor naming squares on a grid this mod
       invented, which would sound exactly as authoritative as the real
       ones and mean nothing to a teammate. */
    CHECK(ETA_MapSurvey_Open(&cursor, 0, 7, 1) == 0);
    CHECK(ETA_MapSurvey_IsOpen(&cursor) == 0);
    CHECK(ETA_MapSurvey_Open(&cursor, 7, 0, 1) == 0);
    CHECK(ETA_MapSurvey_Open(&cursor, -3, 7, 1) == 0);
    CHECK(ETA_MapSurvey_Open(&cursor, ETA_MAP_MAX_COLUMNS + 1, 7, 1) == 0);
    CHECK(ETA_MapSurvey_Open(&cursor, 7, ETA_MAP_MAX_ROWS + 1, 1) == 0);

    /* Nothing works on a closed cursor, and none of it crashes. */
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_NORTH) == 0);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 1) == 0);
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 2, 2, 0) == 0);
    CHECK(ETA_MapSurvey_CellName(&cursor) == NULL);
    CHECK(ETA_MapSurvey_IsOpen(NULL) == 0);

    /* A map with no layers at all still opens, on one floor. */
    CHECK(ETA_MapSurvey_Open(&cursor, 8, 8, 0) == 1);
    CHECK(cursor.layerCount == 1);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 1) == 0);

    /* --- the row direction, which is the dangerous one ------------- */

    CHECK(ETA_MapSurvey_Open(&cursor, 8, 8, 1) == 1);
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 4, 4, 0) == 1);

    /* North must walk the row number DOWN. If this ever reads
       cursor.row == 5 the map is mirrored and every square the survey
       names is on the wrong side of the battlefield. */
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_NORTH) == 1);
    CHECK(cursor.row == 3);
    CHECK(cursor.column == 4);

    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_SOUTH) == 1);
    CHECK(cursor.row == 4);

    /* East walks the letter up, which is the same way the engine's own
       'A' + x does it. */
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_EAST) == 1);
    CHECK(cursor.column == 5);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_WEST) == 1);
    CHECK(cursor.column == 4);

    /* --- the edges are reported, never wrapped --------------------- */

    CHECK(ETA_MapSurvey_MoveTo(&cursor, 0, 0, 0) == 1);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_NORTH) == 0);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_WEST) == 0);

    /* Still where it was: a refused step must not move the cursor.
       Checked through the spoken name as well as the fields, because
       the name is what the player acts on - a cursor that slipped to a
       negative column would keep "working" and start naming squares
       with punctuation for letters. */
    CHECK(cursor.row == 0);
    CHECK(cursor.column == 0);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "A,0") == 0);

    CHECK(ETA_MapSurvey_MoveTo(&cursor, 7, 7, 0) == 1);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_SOUTH) == 0);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_EAST) == 0);
    CHECK(cursor.row == 7);
    CHECK(cursor.column == 7);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "H,7") == 0);

    /* Refused against one edge in the middle of another, where a step
       that quietly moved the OTHER axis would otherwise go unnoticed. */
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 4, 0, 0) == 1);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_NORTH) == 0);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "E,0") == 0);
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 0, 4, 0) == 1);
    CHECK(ETA_MapSurvey_Step(&cursor, ETA_MAP_STEP_WEST) == 0);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "A,4") == 0);

    /* --- layers ---------------------------------------------------- */

    CHECK(ETA_MapSurvey_Open(&cursor, 8, 8, 3) == 1);
    CHECK(cursor.layer == 0);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, -1) == 0);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 1) == 1);
    CHECK(cursor.layer == 1);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 1) == 1);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 1) == 0);
    CHECK(cursor.layer == 2);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 0) == 0);

    /* Changing floor must not move the cursor sideways: a player
       stepping up a storey is looking at the same place from above. */
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 3, 5, 0) == 1);
    CHECK(ETA_MapSurvey_StepLayer(&cursor, 1) == 1);
    CHECK(cursor.column == 3);
    CHECK(cursor.row == 5);

    /* --- MoveTo clamps rather than failing ------------------------- */

    /* The caller converts world coordinates, and a player standing on
       the very edge of the map must not be a failure. */
    CHECK(ETA_MapSurvey_MoveTo(&cursor, -50, -50, -50) == 1);
    CHECK(cursor.column == 0);
    CHECK(cursor.row == 0);
    CHECK(cursor.layer == 0);

    CHECK(ETA_MapSurvey_MoveTo(&cursor, 9999, 9999, 9999) == 1);
    CHECK(cursor.column == 7);
    CHECK(cursor.row == 7);
    CHECK(cursor.layer == 2);

    /* Going nowhere reports going nowhere. */
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 7, 7, 2) == 0);

    /* --- the square's name is the engine's own vocabulary ---------- */

    CHECK(ETA_MapSurvey_Open(&cursor, 8, 8, 1) == 1);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "A,0") == 0);
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 2, 3, 0) == 1);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "C,3") == 0);
    CHECK(ETA_MapSurvey_MoveTo(&cursor, 7, 7, 0) == 1);
    CHECK(strcmp(ETA_MapSurvey_CellName(&cursor), "H,7") == 0);

    ETA_MapSurvey_Close(&cursor);
    CHECK(ETA_MapSurvey_IsOpen(&cursor) == 0);

    /* --- the bearing is a true bearing ----------------------------- */

    /* North is 0 and east is 90. The engine's yaw is neither: it puts
       north at 90 and counts anticlockwise, so a raw yaw handed to a
       player is rotated a quarter turn AND running backwards. */
    CHECK((int)(ETA_HudNarrator_BearingFromYaw(90.0f) + 0.5f) % 360 == 0);
    CHECK((int)(ETA_HudNarrator_BearingFromYaw(0.0f) + 0.5f) == 90);
    CHECK((int)(ETA_HudNarrator_BearingFromYaw(270.0f) + 0.5f) == 180);
    CHECK((int)(ETA_HudNarrator_BearingFromYaw(180.0f) + 0.5f) == 270);

    /* It must stay in range whatever it is handed - yaws arrive from
       the engine already wrapped, but not always the way you expect. */
    for (i = -1080; i <= 1080; i += 7)
    {
        float bearing = ETA_HudNarrator_BearingFromYaw((float)i);

        CHECK(bearing >= 0.0f && bearing < 360.0f);
    }

    /* --- the number and the word cannot disagree ------------------- */

    {
        static const char *const expected[] =
        {
            "north", "north-east", "east", "south-east",
            "south", "south-west", "west", "north-west"
        };

        for (i = 0; i < 8; i++)
        {
            int   bearing = i * 45;
            float yaw     = 90.0f - (float)bearing;

            /* Straight from the bearing... */
            CHECK(strcmp(ETA_HudNarrator_FacingName(
                             ETA_HudNarrator_FacingFromBearing((float)bearing)),
                         expected[i]) == 0);

            /* ...and round through the engine's yaw, which is how the
               compass narration reaches the same word. Both routes have
               to land on it, or the map and the compass would name the
               same direction differently. */
            CHECK(ETA_HudNarrator_FacingFromYaw(yaw)
                  == ETA_HudNarrator_FacingFromBearing((float)bearing));
        }
    }

    /* Each point owns the 45 degrees centred on it, so a bearing just
       either side of due north is still north. */
    CHECK(ETA_HudNarrator_FacingFromBearing(22.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromBearing(338.0f) == ETA_FACING_NORTH);
    CHECK(ETA_HudNarrator_FacingFromBearing(23.0f) == ETA_FACING_NORTHEAST);

    /* --- the spoken line ------------------------------------------- */

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapCell("C,3", "Axis command post", 40, 52));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapCell("C,4", NULL, -1, -1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapCell("C,4", "", -1, -1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapCell("C,3", "two teammates", 40, -1));
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapCell("C,3", "two teammates", -1, 52));
    CHECK_REJECTS(ETA_HudNarrator_SpeakMapCell(NULL, "anything", 1, 1),
                  ETA_ERROR_NULL_POINTER);

    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapEdge());
    CHECK_ACCEPTS(ETA_HudNarrator_SpeakMapLayer(0, 3));

    ETA_HudNarrator_Shutdown();
    ETA_AccessibilityRuntime_Shutdown();

    return SMOKE_REPORT("map_survey");
}

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Walking the command map by keyboard.
 *
 * A sighted player holds the command map key and takes in the whole
 * battlefield in one glance: where the objectives are, which way their
 * team is spread, where the enemies that have been spotted are standing.
 * That glance is the single largest piece of information this mod has
 * never been able to give, and it is not a detail of presentation - it
 * is most of what "playing tactically" means in this game.
 *
 * What lives here is the *cursor*: where on the map the player is
 * currently looking, how it moves, and what that position is called.
 * What is actually standing there is the integration's to find, because
 * only it can reach the engine's entity list.
 *
 * The grid is the game's own. ET divides every map into lettered columns
 * and numbered rows and uses them to fill in a player's position in team
 * chat, so "C,3" is not a coordinate system this mod invented - it is
 * the one the rest of the team is already speaking. A blind player
 * calling out a square is understood without anybody having to learn
 * anything.
 */

/*
 * Rows count from the north edge downward, which is the engine's own
 * arrangement rather than a choice: BG_GetLocationString derives the row
 * from (gridStart - y), and y grows northward in this game. So north is
 * row 0 and pressing up must *decrease* the row.
 *
 * Getting that backwards would compile, run, and mirror the entire map
 * north-for-south - the same shape of defect as the bearings this
 * project once shipped reversed, and just as invisible from the code.
 */
typedef enum
{
    ETA_MAP_STEP_NORTH = 0,
    ETA_MAP_STEP_SOUTH,
    ETA_MAP_STEP_EAST,
    ETA_MAP_STEP_WEST
} ETA_MapStep;

#define ETA_MAP_MAX_COLUMNS 26
#define ETA_MAP_MAX_ROWS 64
#define ETA_MAP_MAX_LAYERS 16

typedef struct
{
    int column;      /* 0 based; the spoken name is 'A' + column */
    int row;         /* 0 based, counting south from the north edge */
    int layer;       /* 0 based floor */

    int columnCount;
    int rowCount;
    int layerCount;  /* 1 on a map with no layers at all */

    int open;
} ETA_MapCursor;

/*
 * Opens the survey with the grid the map actually has. A map whose grid
 * cannot be read comes back closed rather than guessed at, because a
 * cursor over an invented grid would name squares that mean nothing to
 * the team.
 *
 * Returns 1 when the survey is open.
 */
int ETA_MapSurvey_Open(ETA_MapCursor *cursor, int columnCount, int rowCount, int layerCount);
void ETA_MapSurvey_Close(ETA_MapCursor *cursor);
int ETA_MapSurvey_IsOpen(const ETA_MapCursor *cursor);

/*
 * One square in a compass direction.
 *
 * Returns 1 when the cursor moved and 0 when it was already against that
 * edge of the map. The caller says so rather than moving silently: on a
 * grid you cannot see, a keypress that does nothing and a keypress that
 * moved you somewhere identical are the same event.
 */
int ETA_MapSurvey_Step(ETA_MapCursor *cursor, ETA_MapStep step);

/*
 * Up or down a floor. Same contract: 0 when there is no such floor.
 */
int ETA_MapSurvey_StepLayer(ETA_MapCursor *cursor, int delta);

/*
 * Puts the cursor somewhere directly - where the player is standing, or
 * on the next square that has something in it. Out-of-range values are
 * clamped rather than rejected, because the caller is converting from
 * world coordinates and a player standing exactly on the map's edge
 * should not be a failure.
 *
 * Returns 1 when the cursor ended up somewhere other than where it was.
 */
int ETA_MapSurvey_MoveTo(ETA_MapCursor *cursor, int column, int row, int layer);

/*
 * The square's name in the game's own vocabulary: "C,3".
 */
const char *ETA_MapSurvey_CellName(const ETA_MapCursor *cursor);

#ifdef __cplusplus
}
#endif

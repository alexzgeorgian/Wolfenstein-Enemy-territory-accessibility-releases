#include "map_survey.h"
#include "../core/runtime_guard.h"

#include <stdio.h>

static int ETA_MapSurvey_Clamp(int value, int low, int high)
{
    if (value < low)
    {
        return low;
    }

    if (value > high)
    {
        return high;
    }

    return value;
}

int ETA_MapSurvey_Open(ETA_MapCursor *cursor, int columnCount, int rowCount, int layerCount)
{
    if (!ETA_RuntimeGuard_IsOk(ETA_RuntimeGuard_CheckPointer(cursor, "map_survey.Open")))
    {
        return 0;
    }

    cursor->open = 0;

    /* A grid has to have been read off the map before there is anything
       to walk. Refusing here is what keeps the cursor from naming
       squares on a grid this mod made up, which would be worse than
       having no survey at all: the names would sound exactly as
       authoritative as the real ones and mean nothing to the team. */
    if (columnCount < 1 || rowCount < 1
        || columnCount > ETA_MAP_MAX_COLUMNS || rowCount > ETA_MAP_MAX_ROWS)
    {
        return 0;
    }

    if (layerCount < 1)
    {
        layerCount = 1;
    }

    cursor->columnCount = columnCount;
    cursor->rowCount    = rowCount;
    cursor->layerCount  = ETA_MapSurvey_Clamp(layerCount, 1, ETA_MAP_MAX_LAYERS);

    cursor->column = 0;
    cursor->row    = 0;
    cursor->layer  = 0;
    cursor->open   = 1;

    return 1;
}

void ETA_MapSurvey_Close(ETA_MapCursor *cursor)
{
    if (!cursor)
    {
        return;
    }

    cursor->open = 0;
}

int ETA_MapSurvey_IsOpen(const ETA_MapCursor *cursor)
{
    return (cursor && cursor->open) ? 1 : 0;
}

int ETA_MapSurvey_Step(ETA_MapCursor *cursor, ETA_MapStep step)
{
    int column, row;

    if (!ETA_MapSurvey_IsOpen(cursor))
    {
        return 0;
    }

    column = cursor->column;
    row    = cursor->row;

    switch (step)
    {
    /* North is row 0 and rows count southward, so going north walks the
       row number down. See the note in the header: this is the engine's
       arrangement, not a preference. */
    case ETA_MAP_STEP_NORTH:
        row--;
        break;
    case ETA_MAP_STEP_SOUTH:
        row++;
        break;
    case ETA_MAP_STEP_EAST:
        column++;
        break;
    case ETA_MAP_STEP_WEST:
        column--;
        break;
    default:
        return 0;
    }

    if (column < 0 || column >= cursor->columnCount
        || row < 0 || row >= cursor->rowCount)
    {
        /* Against the edge. Deliberately not wrapped round: a cursor
           that reappeared on the far side would be describing somewhere
           a stride of the key could never have reached, and on a map you
           cannot see there is nothing to notice it by. */
        return 0;
    }

    cursor->column = column;
    cursor->row    = row;

    return 1;
}

int ETA_MapSurvey_StepLayer(ETA_MapCursor *cursor, int delta)
{
    int layer;

    if (!ETA_MapSurvey_IsOpen(cursor) || delta == 0)
    {
        return 0;
    }

    layer = cursor->layer + (delta > 0 ? 1 : -1);

    if (layer < 0 || layer >= cursor->layerCount)
    {
        return 0;
    }

    cursor->layer = layer;

    return 1;
}

int ETA_MapSurvey_MoveTo(ETA_MapCursor *cursor, int column, int row, int layer)
{
    int wasColumn, wasRow, wasLayer;

    if (!ETA_MapSurvey_IsOpen(cursor))
    {
        return 0;
    }

    wasColumn = cursor->column;
    wasRow    = cursor->row;
    wasLayer  = cursor->layer;

    cursor->column = ETA_MapSurvey_Clamp(column, 0, cursor->columnCount - 1);
    cursor->row    = ETA_MapSurvey_Clamp(row, 0, cursor->rowCount - 1);
    cursor->layer  = ETA_MapSurvey_Clamp(layer, 0, cursor->layerCount - 1);

    return (cursor->column != wasColumn || cursor->row != wasRow
            || cursor->layer != wasLayer) ? 1 : 0;
}

const char *ETA_MapSurvey_CellName(const ETA_MapCursor *cursor)
{
    static char name[16];

    if (!ETA_MapSurvey_IsOpen(cursor))
    {
        return NULL;
    }

    /* The engine's own format, from BG_GetLocationString: a letter for
       the column, a comma, the row as a number. Said exactly as a
       teammate types it. */
    snprintf(name, sizeof(name), "%c,%d", 'A' + cursor->column, cursor->row);

    return name;
}

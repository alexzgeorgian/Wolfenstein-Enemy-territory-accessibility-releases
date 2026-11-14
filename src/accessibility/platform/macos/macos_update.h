#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Replacing the whole game, on the Mac: for a game whose updates are not
 * one pk3 but the app itself - the RTCW campaign, whose engine changes
 * with every build.
 *
 * Why it is done from inside the game: a build downloaded with a browser
 * is quarantined, and the Mac will not open it until the player finds
 * Open Anyway in System Settings - with every new build. One the game
 * downloads itself (macos_update.m's NSURLSession, in an app that does
 * not ask for quarantine) is not, so once the first build has been let
 * in, each one after it opens like any other app.
 */

/* Where the game is and whether it can be replaced there:
   1, the app's bundle path in out;
   0, the game is not running from an app bundle;
   -1, the Mac is running it from a read-only copy (App Translocation),
   because it has not been moved out of the folder it was unzipped in. */
int ETA_MacUpdate_AppPath(char *out, size_t size);

/* A place for a download beside the player's game files:
   ~/Library/Application Support/RTCW/<name>. 0 when there is none. */
int ETA_MacUpdate_SupportPath(const char *name, char *out, size_t size);

/* Once the game exits, unzips zip, puts the app in it in place of the
   running one (the old one kept until the new one is in), copies the
   download's main/sp_zaccessibility.pk3 and INSTALL.md beside it, removes
   the zip, and opens the new app. 1 when the helper started. */
int ETA_MacUpdate_ScheduleAppReplace(const char *zip);

#ifdef __cplusplus
}
#endif

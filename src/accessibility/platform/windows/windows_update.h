#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/*
 * The network and file half of the updater, on Windows.
 *
 * One job at a time runs on a thread of its own, so the menus keep
 * talking while a slow connection makes up its mind: either fetching a
 * small text file into memory (the release's eta-update.txt) or
 * downloading the pk3 to a file, hashing it as it arrives. The ui polls
 * for the result once a frame.
 *
 * The file swap cannot happen while the game runs: the engine holds
 * every pk3 it loaded open, and Windows will not replace an open file.
 * So the swap is handed to a small PowerShell script that waits for the
 * game to exit, moves the new pk3 into place (keeping the old one as
 * zzz_accessibility.pk3.previous), and starts the game again if asked.
 *
 * On macOS the same calls are made by platform/macos/macos_update.m,
 * where the swap can be done at once (see there).
 *
 * Everywhere else these do nothing and say so: Supported() is 0 and
 * every Start returns 0.
 */

typedef enum
{
    ETA_WINDOWS_UPDATE_IDLE = 0,
    ETA_WINDOWS_UPDATE_BUSY,
    ETA_WINDOWS_UPDATE_DONE,
    ETA_WINDOWS_UPDATE_FAILED
} ETA_WindowsUpdateState;

int ETA_WindowsUpdate_Supported(void);

/* Fetches url (https, UTF-8) into memory, up to 16 KB of text. */
int ETA_WindowsUpdate_StartFetch(const char *url);

/* Downloads url into path (UTF-8), giving up past maxBytes. */
int ETA_WindowsUpdate_StartDownload(const char *url, const char *path, long maxBytes);

/* The job's state. DONE and FAILED stay until the next Start. */
ETA_WindowsUpdateState ETA_WindowsUpdate_Poll(void);

/* After a fetch is DONE: the text, NUL terminated. */
const char *ETA_WindowsUpdate_Text(void);

/* After a download is DONE: its SHA-256 in hex, and its length. */
const char *ETA_WindowsUpdate_DownloadSha256(void);
long ETA_WindowsUpdate_DownloadedBytes(void);

/* Removes a file, for a download that failed its checks. */
void ETA_WindowsUpdate_RemoveFile(const char *path);

/*
 * Starts the helper that moves from onto to once this game has exited,
 * and starts the game again afterwards when restart is set. Returns 1 if
 * the helper is running.
 */
int ETA_WindowsUpdate_ScheduleSwap(const char *from, const char *to, int restart);

/* Abandons a running job and waits briefly for its thread, so the
   module is never unloaded under it. */
void ETA_WindowsUpdate_Shutdown(void);

#ifdef __cplusplus
}
#endif

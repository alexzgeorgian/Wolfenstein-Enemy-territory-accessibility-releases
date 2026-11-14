/*
 * The updater's Windows half, run on a real Windows machine.
 *
 * Nothing else can check it. The decisions are pinned by
 * update_check_smoke_test, but whether WinHTTP follows GitHub's
 * redirects, whether TLS is accepted, whether a download hashes to what
 * Windows itself says it is, and whether the PowerShell helper really
 * swaps the file after the game exits - those only happen on Windows,
 * and a mistake in any of them is an update that never arrives, or a
 * pk3 left half-written and a game that has stopped talking.
 *
 * The Mac half (platform/macos/macos_update.m) is run the same way on a
 * Mac, by the macos job: NSURLSession in place of WinHTTP, and a shell
 * in place of PowerShell for the swap.
 *
 * The CI job (.github/workflows/ci.yml, "Updater on Windows") drives
 * each mode and checks what it left behind:
 *
 *   fetch URL            prints "<sha256> <bytes>" of the text, exit 0
 *                        when it arrived
 *   missing URL          exit 0 when the fetch FAILED, as a 404 must,
 *                        or was refused outright
 *   download URL PATH    prints "<sha256> <bytes>", exit 0 when done
 *   swap FROM TO         holds TO open the way the game holds its pk3,
 *                        starts the helper, and exits three seconds
 *                        later; the job then checks the files. On a
 *                        Mac it also checks nothing moved before it
 *                        exited
 *   restart FROM TO      (Mac) a swap that starts the game again: this
 *                        program, started bare with ETA_RESTART_MARKER
 *                        set, writes that file
 */

#include "platform/windows/windows_update.h"
#include "update/update_check.h"

#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <stdlib.h>
#include <unistd.h>
#endif

static ETA_WindowsUpdateState Wait(void)
{
    int waited;

    for (waited = 0; waited < 600; waited++)
    {
        ETA_WindowsUpdateState state = ETA_WindowsUpdate_Poll();

        if (state != ETA_WINDOWS_UPDATE_BUSY)
        {
            return state;
        }
#ifdef _WIN32
        Sleep(100);
#else
        usleep(100 * 1000);
#endif
    }

    return ETA_WINDOWS_UPDATE_BUSY;
}

int main(int argc, char **argv)
{
#ifdef __APPLE__
    /* Started again by the swap's helper, with nothing on the line. */
    if (argc == 1 && getenv("ETA_RESTART_MARKER"))
    {
        FILE *marker = fopen(getenv("ETA_RESTART_MARKER"), "w");

        if (!marker)
        {
            return 1;
        }
        fputs("restarted\n", marker);
        fclose(marker);
        return 0;
    }
#endif

    if (!ETA_WindowsUpdate_Supported())
    {
        printf("no updater in this build\n");
        return 1;
    }

    if (argc == 3 && !strcmp(argv[1], "fetch"))
    {
        if (!ETA_WindowsUpdate_StartFetch(argv[2]) || Wait() != ETA_WINDOWS_UPDATE_DONE)
        {
            printf("fetch failed\n");
            return 1;
        }
        {
            ETA_Sha256  sha;
            char        hex[ETA_UPDATE_SHA256_HEX_LENGTH + 1];
            const char *text = ETA_WindowsUpdate_Text();

            ETA_Sha256_Begin(&sha);
            ETA_Sha256_Add(&sha, text, strlen(text));
            ETA_Sha256_FinalHex(&sha, hex);
            printf("%s %lu\n", hex, (unsigned long)strlen(text));
            return text[0] ? 0 : 1;
        }
    }

    if (argc == 3 && !strcmp(argv[1], "missing"))
    {
        /* Refused before it starts, as the Mac does plain http, is as
           good as failing once started. The fetch mode shows a sound
           address does start. */
        if (!ETA_WindowsUpdate_StartFetch(argv[2]))
        {
            printf("refused\n");
            return 0;
        }
        return Wait() == ETA_WINDOWS_UPDATE_FAILED ? 0 : 1;
    }

    if (argc == 4 && !strcmp(argv[1], "download"))
    {
        if (!ETA_WindowsUpdate_StartDownload(argv[2], argv[3], 64L * 1024 * 1024)
            || Wait() != ETA_WINDOWS_UPDATE_DONE)
        {
            printf("download failed\n");
            return 1;
        }
        printf("%s %ld\n", ETA_WindowsUpdate_DownloadSha256(), ETA_WindowsUpdate_DownloadedBytes());
        return 0;
    }

    if (argc == 4 && !strcmp(argv[1], "swap"))
    {
#ifdef _WIN32
        /* No FILE_SHARE_DELETE: the same hold the engine's fopen has on
           a pk3, which is what makes a swap in place impossible. */
        HANDLE held = CreateFileA(argv[3], GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                                  FILE_ATTRIBUTE_NORMAL, NULL);

        if (held == INVALID_HANDLE_VALUE || !ETA_WindowsUpdate_ScheduleSwap(argv[2], argv[3], 0))
        {
            printf("swap not scheduled\n");
            return 1;
        }
        Sleep(3000);
        CloseHandle(held);
        return 0;
#else
        /* Held open as the game holds it, until after the helper started. */
        FILE *held = fopen(argv[3], "rb");

        if (!held || !ETA_WindowsUpdate_ScheduleSwap(argv[2], argv[3], 0))
        {
            printf("swap not scheduled\n");
            return 1;
        }
        sleep(3);
        if (access(argv[2], F_OK) != 0)
        {
            printf("the pk3 was replaced while the game was running\n");
            return 1;
        }
        fclose(held);
        return 0;
#endif
    }

#ifdef __APPLE__
    if (argc == 4 && !strcmp(argv[1], "restart"))
    {
        if (!getenv("ETA_RESTART_MARKER") || !ETA_WindowsUpdate_ScheduleSwap(argv[2], argv[3], 1))
        {
            printf("swap not scheduled\n");
            return 1;
        }
        /* The helper waits for this to exit before swapping and starting
           it again. */
        sleep(1);
        return 0;
    }
#endif

    printf("usage: fetch URL | missing URL | download URL PATH | swap FROM TO | restart FROM TO\n");
    return 2;
}

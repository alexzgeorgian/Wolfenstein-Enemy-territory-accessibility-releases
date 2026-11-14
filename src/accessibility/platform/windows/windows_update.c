#include "windows_update.h"

#ifdef _WIN32

#include "../../update/update_check.h"

#include <windows.h>
#include <winhttp.h>

#include <stdio.h>
#include <string.h>

#ifndef WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY
#define WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY 4
#endif
#ifndef WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2
#define WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 0x00000800
#endif
#ifndef WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3
#define WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3 0x00002000
#endif

#define ETA_UPDATE_TEXT_MAX (16 * 1024)

typedef struct
{
    int      download;            /* 0 fetch into text, 1 download into a file */
    wchar_t  url[1024];
    wchar_t  path[MAX_PATH * 2];
    long     maxBytes;
} ETA_UpdateJob;

static ETA_UpdateJob     gJob;
static HANDLE            gThread;
static volatile LONG     gState = ETA_WINDOWS_UPDATE_IDLE;
static volatile LONG     gCancel;
static CRITICAL_SECTION  gHandleLock;
static int               gHandleLockReady;
static HINTERNET         gRequest;   /* closed from Shutdown to abort a read */

static char  gText[ETA_UPDATE_TEXT_MAX + 1];
static char  gSha256[ETA_UPDATE_SHA256_HEX_LENGTH + 1];
static long  gBytes;

static int ETA_WindowsUpdate_Widen(const char *utf8, wchar_t *out, int outCount)
{
    return utf8 && MultiByteToWideChar(CP_UTF8, 0, utf8, -1, out, outCount) > 0;
}

static void ETA_WindowsUpdate_CloseRequest(void)
{
    EnterCriticalSection(&gHandleLock);
    if (gRequest)
    {
        WinHttpCloseHandle(gRequest);
        gRequest = NULL;
    }
    LeaveCriticalSection(&gHandleLock);
}

/* Runs one GET to completion: into gText, or into the job's file. */
static int ETA_WindowsUpdate_Run(void)
{
    URL_COMPONENTS parts;
    wchar_t        host[256];
    wchar_t        path[1024];
    HINTERNET      session, connect, request;
    DWORD          protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 | WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3;
    DWORD          status = 0, statusSize = sizeof(status);
    HANDLE         file = INVALID_HANDLE_VALUE;
    ETA_Sha256     sha;
    int            ok = 0;

    memset(&parts, 0, sizeof(parts));
    parts.dwStructSize = sizeof(parts);
    parts.lpszHostName = host;
    parts.dwHostNameLength = sizeof(host) / sizeof(host[0]);
    parts.lpszUrlPath = path;
    parts.dwUrlPathLength = sizeof(path) / sizeof(path[0]);

    if (!WinHttpCrackUrl(gJob.url, 0, 0, &parts) || parts.nScheme != INTERNET_SCHEME_HTTPS)
    {
        return 0;
    }

    /* The automatic proxy is Windows 8.1 and later; the default one is
       what Windows 7 has. */
    session = WinHttpOpen(L"ETAccessibilityUpdater/1.0", WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                          WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session)
    {
        session = WinHttpOpen(L"ETAccessibilityUpdater/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                              WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    }
    if (!session)
    {
        return 0;
    }

    /* GitHub takes nothing older than TLS 1.2, which Windows 7 does not
       offer unless asked. TLS 1.3 is refused by older systems, so it is
       only added when they accept it. */
    if (!WinHttpSetOption(session, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols)))
    {
        protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2;
        WinHttpSetOption(session, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols));
    }
    WinHttpSetTimeouts(session, 10000, 10000, 15000, 30000);

    connect = WinHttpConnect(session, host, parts.nPort, 0);
    request = connect ? WinHttpOpenRequest(connect, L"GET", path, NULL, WINHTTP_NO_REFERER,
                                           WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE) : NULL;

    EnterCriticalSection(&gHandleLock);
    gRequest = request;
    LeaveCriticalSection(&gHandleLock);

    /* Redirects are followed by WinHTTP itself: the release address
       answers with two of them on its way to the file. */
    if (request && !gCancel
        && WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0)
        && WinHttpReceiveResponse(request, NULL)
        && WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                               WINHTTP_HEADER_NAME_BY_INDEX, &status, &statusSize, WINHTTP_NO_HEADER_INDEX)
        && status == 200)
    {
        char  buffer[16384];
        DWORD got = 0;
        long  total = 0;

        if (gJob.download)
        {
            file = CreateFileW(gJob.path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
            ETA_Sha256_Begin(&sha);
        }

        ok = !gJob.download || file != INVALID_HANDLE_VALUE;

        while (ok && !gCancel)
        {
            if (!WinHttpReadData(request, buffer, sizeof(buffer), &got))
            {
                ok = 0;
                break;
            }
            if (got == 0)
            {
                break;
            }

            if (gJob.download)
            {
                DWORD written = 0;

                if (total + (long)got > gJob.maxBytes
                    || !WriteFile(file, buffer, got, &written, NULL) || written != got)
                {
                    ok = 0;
                    break;
                }
                ETA_Sha256_Add(&sha, buffer, got);
            }
            else
            {
                if (total + (long)got > ETA_UPDATE_TEXT_MAX)
                {
                    ok = 0;
                    break;
                }
                memcpy(gText + total, buffer, got);
            }

            total += (long)got;
        }

        if (gCancel)
        {
            ok = 0;
        }

        if (ok)
        {
            gBytes = total;
            if (gJob.download)
            {
                ETA_Sha256_FinalHex(&sha, gSha256);
            }
            else
            {
                gText[total] = '\0';
            }
        }
    }

    if (file != INVALID_HANDLE_VALUE)
    {
        CloseHandle(file);
        if (!ok)
        {
            DeleteFileW(gJob.path);
        }
    }

    ETA_WindowsUpdate_CloseRequest();
    if (connect)
    {
        WinHttpCloseHandle(connect);
    }
    WinHttpCloseHandle(session);

    return ok;
}

static DWORD WINAPI ETA_WindowsUpdate_Thread(LPVOID unused)
{
    (void)unused;

    InterlockedExchange(&gState, ETA_WindowsUpdate_Run() ? ETA_WINDOWS_UPDATE_DONE : ETA_WINDOWS_UPDATE_FAILED);
    return 0;
}

static int ETA_WindowsUpdate_Start(void)
{
    if (!gHandleLockReady)
    {
        InitializeCriticalSection(&gHandleLock);
        gHandleLockReady = 1;
    }

    if (gThread)
    {
        if (gState == ETA_WINDOWS_UPDATE_BUSY)
        {
            return 0;
        }
        WaitForSingleObject(gThread, INFINITE);
        CloseHandle(gThread);
        gThread = NULL;
    }

    gText[0] = '\0';
    gSha256[0] = '\0';
    gBytes = 0;
    gCancel = 0;
    InterlockedExchange(&gState, ETA_WINDOWS_UPDATE_BUSY);

    gThread = CreateThread(NULL, 0, ETA_WindowsUpdate_Thread, NULL, 0, NULL);
    if (!gThread)
    {
        InterlockedExchange(&gState, ETA_WINDOWS_UPDATE_FAILED);
        return 0;
    }

    return 1;
}

int ETA_WindowsUpdate_Supported(void)
{
    return 1;
}

int ETA_WindowsUpdate_StartFetch(const char *url)
{
    if (gState == ETA_WINDOWS_UPDATE_BUSY)
    {
        return 0;
    }

    memset(&gJob, 0, sizeof(gJob));
    if (!ETA_WindowsUpdate_Widen(url, gJob.url, (int)(sizeof(gJob.url) / sizeof(gJob.url[0]))))
    {
        return 0;
    }

    return ETA_WindowsUpdate_Start();
}

int ETA_WindowsUpdate_StartDownload(const char *url, const char *path, long maxBytes)
{
    if (gState == ETA_WINDOWS_UPDATE_BUSY)
    {
        return 0;
    }

    memset(&gJob, 0, sizeof(gJob));
    gJob.download = 1;
    gJob.maxBytes = maxBytes;
    if (!ETA_WindowsUpdate_Widen(url, gJob.url, (int)(sizeof(gJob.url) / sizeof(gJob.url[0])))
        || !ETA_WindowsUpdate_Widen(path, gJob.path, (int)(sizeof(gJob.path) / sizeof(gJob.path[0]))))
    {
        return 0;
    }

    return ETA_WindowsUpdate_Start();
}

ETA_WindowsUpdateState ETA_WindowsUpdate_Poll(void)
{
    return (ETA_WindowsUpdateState)gState;
}

const char *ETA_WindowsUpdate_Text(void)
{
    return gState == ETA_WINDOWS_UPDATE_DONE ? gText : "";
}

const char *ETA_WindowsUpdate_DownloadSha256(void)
{
    return gState == ETA_WINDOWS_UPDATE_DONE ? gSha256 : "";
}

long ETA_WindowsUpdate_DownloadedBytes(void)
{
    return gState == ETA_WINDOWS_UPDATE_DONE ? gBytes : 0;
}

void ETA_WindowsUpdate_RemoveFile(const char *path)
{
    wchar_t wide[MAX_PATH * 2];

    if (ETA_WindowsUpdate_Widen(path, wide, (int)(sizeof(wide) / sizeof(wide[0]))))
    {
        DeleteFileW(wide);
    }
}

/*
 * Waits for the game, then swaps. Copy-then-move rather than a rename of
 * the old file, so that whatever happens part way, a pk3 is left at the
 * real name. The retries cover a virus scanner that is still holding
 * the file for a moment after the game let go of it.
 */
static const char ETA_SwapScript[] =
    "param([int]$GamePid, [string]$From, [string]$To, [string]$Restart = '')\r\n"
    "try { Wait-Process -Id $GamePid -ErrorAction Stop } catch {}\r\n"
    "for ($i = 0; $i -lt 40; $i++) {\r\n"
    "  try {\r\n"
    "    if (-not (Test-Path -LiteralPath $From)) { break }\r\n"
    "    if (Test-Path -LiteralPath $To) { Copy-Item -LiteralPath $To -Destination ($To + '.previous') -Force -ErrorAction Stop }\r\n"
    "    Move-Item -LiteralPath $From -Destination $To -Force -ErrorAction Stop\r\n"
    "    break\r\n"
    "  } catch { Start-Sleep -Milliseconds 500 }\r\n"
    "}\r\n"
    "if ($Restart -ne '') { Start-Process -FilePath $Restart -WorkingDirectory (Split-Path -Parent $Restart) }\r\n";

int ETA_WindowsUpdate_ScheduleSwap(const char *from, const char *to, int restart)
{
    wchar_t             wideFrom[MAX_PATH * 2], wideTo[MAX_PATH * 2];
    wchar_t             script[MAX_PATH + 64], shell[MAX_PATH + 64], game[MAX_PATH * 2];
    wchar_t             command[MAX_PATH * 10];
    HANDLE              file;
    DWORD               written = 0, length;
    STARTUPINFOW        startup;
    PROCESS_INFORMATION process;

    if (!ETA_WindowsUpdate_Widen(from, wideFrom, MAX_PATH * 2)
        || !ETA_WindowsUpdate_Widen(to, wideTo, MAX_PATH * 2))
    {
        return 0;
    }

    length = GetTempPathW(MAX_PATH, script);
    if (length == 0 || length >= MAX_PATH)
    {
        return 0;
    }
    wcscat(script, L"eta-accessibility-update.ps1");

    file = CreateFileW(script, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE)
    {
        return 0;
    }
    WriteFile(file, ETA_SwapScript, (DWORD)(sizeof(ETA_SwapScript) - 1), &written, NULL);
    CloseHandle(file);
    if (written != sizeof(ETA_SwapScript) - 1)
    {
        return 0;
    }

    /* By full path, so a powershell.exe that happens to sit in the
       game's folder or on the PATH is never the one run. */
    length = GetSystemDirectoryW(shell, MAX_PATH);
    if (length == 0 || length >= MAX_PATH)
    {
        return 0;
    }
    wcscat(shell, L"\\WindowsPowerShell\\v1.0\\powershell.exe");

    if (!GetModuleFileNameW(NULL, game, MAX_PATH * 2))
    {
        game[0] = L'\0';
    }

    /* Windows paths cannot hold a double quote, so quoting each one is
       enough to keep spaces and the rest in their argument. */
    _snwprintf(command, sizeof(command) / sizeof(command[0]) - 1,
               L"\"%ls\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden "
               L"-File \"%ls\" -GamePid %lu -From \"%ls\" -To \"%ls\"%ls%ls%ls",
               shell, script, (unsigned long)GetCurrentProcessId(), wideFrom, wideTo,
               (restart && game[0]) ? L" -Restart \"" : L"",
               (restart && game[0]) ? game : L"",
               (restart && game[0]) ? L"\"" : L"");
    command[sizeof(command) / sizeof(command[0]) - 1] = L'\0';

    memset(&startup, 0, sizeof(startup));
    startup.cb = sizeof(startup);
    memset(&process, 0, sizeof(process));

    /* Out of the game's job, if it has one, so closing the game does not
       take the helper with it. A job that forbids that refuses the flag,
       and the plain start is tried. */
    if (!CreateProcessW(shell, command, NULL, NULL, FALSE, CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB,
                        NULL, NULL, &startup, &process)
        && !CreateProcessW(shell, command, NULL, NULL, FALSE, CREATE_NO_WINDOW,
                           NULL, NULL, &startup, &process))
    {
        return 0;
    }

    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return 1;
}

void ETA_WindowsUpdate_Shutdown(void)
{
    if (!gThread)
    {
        return;
    }

    gCancel = 1;
    ETA_WindowsUpdate_CloseRequest();

    /* Closing the request ends a blocked read at once; the wait is only
       for the thread to get back out of this module. */
    if (WaitForSingleObject(gThread, 5000) == WAIT_OBJECT_0)
    {
        CloseHandle(gThread);
        gThread = NULL;
        InterlockedExchange(&gState, ETA_WINDOWS_UPDATE_IDLE);
    }
}

#elif !defined(__APPLE__)

/* The Mac has its own, in platform/macos/macos_update.m. */

int ETA_WindowsUpdate_Supported(void)
{
    return 0;
}

int ETA_WindowsUpdate_StartFetch(const char *url)
{
    (void)url;
    return 0;
}

int ETA_WindowsUpdate_StartDownload(const char *url, const char *path, long maxBytes)
{
    (void)url;
    (void)path;
    (void)maxBytes;
    return 0;
}

ETA_WindowsUpdateState ETA_WindowsUpdate_Poll(void)
{
    return ETA_WINDOWS_UPDATE_IDLE;
}

const char *ETA_WindowsUpdate_Text(void)
{
    return "";
}

const char *ETA_WindowsUpdate_DownloadSha256(void)
{
    return "";
}

long ETA_WindowsUpdate_DownloadedBytes(void)
{
    return 0;
}

void ETA_WindowsUpdate_RemoveFile(const char *path)
{
    (void)path;
}

int ETA_WindowsUpdate_ScheduleSwap(const char *from, const char *to, int restart)
{
    (void)from;
    (void)to;
    (void)restart;
    return 0;
}

void ETA_WindowsUpdate_Shutdown(void)
{
}

#endif

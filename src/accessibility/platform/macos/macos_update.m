/*
 * The network and file half of the updater, on macOS.
 *
 * The same contract as windows_update.c - the ui drives both through
 * windows_update.h, whose names are older than this file - so the
 * checks, the popups and their words are the ones Windows players have:
 *
 *   - one job at a time, run by NSURLSession on a queue of its own, so
 *     the menus keep talking while a slow connection makes up its mind:
 *     either fetching a small text file (the release's eta-update.txt)
 *     into memory, or downloading the pk3 to a file, hashing it as it
 *     arrives with the library's own SHA-256;
 *   - https only, redirects included, and only a 200 is an answer;
 *   - a download that grows past what the manifest said is stopped and
 *     its partial file removed.
 *
 * The swap waits for the game to exit, as on Windows. macOS would let
 * the file be replaced at once, but the game reads its pk3s again each
 * time it joins a server, and would then load the new game code beside
 * the old menus. So a small shell waits for this game to exit, moves the
 * new pk3 into place - the old one kept as zzz_accessibility.pk3.previous
 * - and, when a restart is asked for, opens the game again.
 */

#include "../windows/windows_update.h"
#include "../../update/update_check.h"

#import <Foundation/Foundation.h>

#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

extern char **environ;

#define ETA_UPDATE_TEXT_MAX (16 * 1024)

static volatile int gState = ETA_WINDOWS_UPDATE_IDLE;
static char         gText[ETA_UPDATE_TEXT_MAX + 1];
static char         gSha256[ETA_UPDATE_SHA256_HEX_LENGTH + 1];
static long         gBytes;

static void ETA_MacUpdate_SetState(int state)
{
    __atomic_store_n(&gState, state, __ATOMIC_SEQ_CST);
}

@interface ETAMacUpdateJob : NSObject <NSURLSessionDataDelegate>
@property (nonatomic) BOOL       download;
@property (nonatomic) long       maxBytes;
@property (nonatomic) long       total;
@property (nonatomic) BOOL       failed;
@property (nonatomic, copy) NSString *path;
@end

@implementation ETAMacUpdateJob
{
    FILE      *_file;
    ETA_Sha256 _sha;
}

- (BOOL)open
{
    _total  = 0;
    _failed = NO;
    if (_download)
    {
        _file = fopen([_path fileSystemRepresentation], "wb");
        if (!_file)
        {
            return NO;
        }
        ETA_Sha256_Begin(&_sha);
    }
    return YES;
}

- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task
    didReceiveResponse:(NSURLResponse *)response
     completionHandler:(void (^)(NSURLSessionResponseDisposition))completionHandler
{
    NSInteger status = [response isKindOfClass:[NSHTTPURLResponse class]]
                       ? [(NSHTTPURLResponse *)response statusCode] : 0;

    (void)session;
    (void)task;
    if (status != 200)
    {
        _failed = YES;
        completionHandler(NSURLSessionResponseCancel);
        return;
    }
    completionHandler(NSURLSessionResponseAllow);
}

/* The release address answers with redirects on its way to the file;
   each must stay on https. */
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    willPerformHTTPRedirection:(NSHTTPURLResponse *)response
                    newRequest:(NSURLRequest *)request
             completionHandler:(void (^)(NSURLRequest *))completionHandler
{
    (void)session;
    (void)task;
    (void)response;
    if (![[[request URL] scheme] isEqualToString:@"https"])
    {
        _failed = YES;
        completionHandler(nil);
        return;
    }
    completionHandler(request);
}

- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data
{
    (void)session;
    if (_failed)
    {
        return;
    }

    [data enumerateByteRangesUsingBlock:^(const void *bytes, NSRange range, BOOL *stop) {
        long length = (long)range.length;

        if (self->_download)
        {
            if (self->_total + length > self->_maxBytes || fwrite(bytes, 1, (size_t)length, self->_file) != (size_t)length)
            {
                self->_failed = YES;
                *stop         = YES;
                return;
            }
            ETA_Sha256_Add(&self->_sha, bytes, (size_t)length);
        }
        else
        {
            if (self->_total + length > ETA_UPDATE_TEXT_MAX)
            {
                self->_failed = YES;
                *stop         = YES;
                return;
            }
            memcpy(gText + self->_total, bytes, (size_t)length);
        }
        self->_total += length;
    }];

    if (_failed)
    {
        [task cancel];
    }
}

- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error
{
    BOOL ok = !error && !_failed;

    (void)task;
    if (_file)
    {
        if (fclose(_file) != 0)
        {
            ok = NO;
        }
        _file = NULL;
    }

    if (ok)
    {
        gBytes = _total;
        if (_download)
        {
            ETA_Sha256_FinalHex(&_sha, gSha256);
        }
        else
        {
            gText[_total] = '\0';
        }
    }
    else if (_download)
    {
        unlink([_path fileSystemRepresentation]);
    }

    [session finishTasksAndInvalidate];
    ETA_MacUpdate_SetState(ok ? ETA_WINDOWS_UPDATE_DONE : ETA_WINDOWS_UPDATE_FAILED);
}
@end

static NSURLSession *gSession;

static int ETA_MacUpdate_Start(const char *url, BOOL download, const char *path, long maxBytes)
{
    @autoreleasepool
    {
        NSString                 *address;
        NSURL                    *target;
        ETAMacUpdateJob          *job;
        NSURLSessionConfiguration *configuration;
        NSOperationQueue         *queue;

        if (!url || __atomic_load_n(&gState, __ATOMIC_SEQ_CST) == ETA_WINDOWS_UPDATE_BUSY)
        {
            return 0;
        }

        address = [NSString stringWithUTF8String:url];
        target  = address ? [NSURL URLWithString:address] : nil;
        if (!target || ![[target scheme] isEqualToString:@"https"])
        {
            return 0;
        }

        job          = [[ETAMacUpdateJob alloc] init];
        job.download = download;
        job.maxBytes = maxBytes;
        job.path     = path ? [NSString stringWithUTF8String:path] : nil;
        if (download && !job.path)
        {
            return 0;
        }

        gText[0]   = '\0';
        gSha256[0] = '\0';
        gBytes     = 0;

        if (![job open])
        {
            return 0;
        }

        configuration                               = [NSURLSessionConfiguration ephemeralSessionConfiguration];
        configuration.timeoutIntervalForRequest     = 30;
        configuration.timeoutIntervalForResource    = 600;
        configuration.HTTPAdditionalHeaders         = @{ @"User-Agent": @"ETAccessibilityUpdater/1.0" };
        queue                                       = [[NSOperationQueue alloc] init];
        queue.maxConcurrentOperationCount           = 1;

        ETA_MacUpdate_SetState(ETA_WINDOWS_UPDATE_BUSY);
        gSession = [NSURLSession sessionWithConfiguration:configuration delegate:job delegateQueue:queue];
        [[gSession dataTaskWithURL:target] resume];
        return 1;
    }
}

int ETA_WindowsUpdate_Supported(void)
{
    return 1;
}

int ETA_WindowsUpdate_StartFetch(const char *url)
{
    return ETA_MacUpdate_Start(url, NO, NULL, 0);
}

int ETA_WindowsUpdate_StartDownload(const char *url, const char *path, long maxBytes)
{
    return ETA_MacUpdate_Start(url, YES, path, maxBytes);
}

ETA_WindowsUpdateState ETA_WindowsUpdate_Poll(void)
{
    return (ETA_WindowsUpdateState)__atomic_load_n(&gState, __ATOMIC_SEQ_CST);
}

const char *ETA_WindowsUpdate_Text(void)
{
    return gText;
}

const char *ETA_WindowsUpdate_DownloadSha256(void)
{
    return gSha256;
}

long ETA_WindowsUpdate_DownloadedBytes(void)
{
    return gBytes;
}

void ETA_WindowsUpdate_RemoveFile(const char *path)
{
    if (path)
    {
        unlink(path);
    }
}

/*
 * The helper: waits for the game (pid $1) to exit, moves $2 onto $3
 * keeping the old one as $3.previous, and if a restart is asked for
 * opens the application bundle $4, or runs the program $5 when the game
 * is not one. A failed move puts the old pk3 back: the game must never
 * be left without one.
 */
static const char ETA_MacUpdate_Helper[] =
    "while kill -0 \"$1\" 2>/dev/null; do sleep 0.5; done\n"
    "rm -f \"$3.previous\"\n"
    "if [ -e \"$3\" ]; then mv -f \"$3\" \"$3.previous\"; fi\n"
    "if ! mv -f \"$2\" \"$3\" && [ -e \"$3.previous\" ] && [ ! -e \"$3\" ]; then mv -f \"$3.previous\" \"$3\"; fi\n"
    "if [ -n \"$4\" ]; then exec open -n \"$4\"; fi\n"
    "if [ -n \"$5\" ]; then exec \"$5\"; fi\n";

int ETA_WindowsUpdate_ScheduleSwap(const char *from, const char *to, int restart)
{
    @autoreleasepool
    {
        NSBundle                  *bundle = [NSBundle mainBundle];
        NSString                  *path   = [bundle bundlePath];
        const char                *app    = "";
        const char                *program = "";
        char                       pid[32];
        char                      *argv[10];
        pid_t                      helper;
        posix_spawnattr_t          attributes;
        posix_spawn_file_actions_t actions;
        int                        started;

        if (!from || !to || access(from, F_OK) != 0)
        {
            return 0;
        }

        if (restart)
        {
            if ([path hasSuffix:@".app"])
            {
                app = [path fileSystemRepresentation];
            }
            else if ([bundle executablePath])
            {
                program = [[bundle executablePath] fileSystemRepresentation];
            }
        }

        snprintf(pid, sizeof(pid), "%d", (int)getpid());
        argv[0] = (char *)"/bin/sh";
        argv[1] = (char *)"-c";
        argv[2] = (char *)ETA_MacUpdate_Helper;
        argv[3] = (char *)"eta-update";
        argv[4] = pid;
        argv[5] = (char *)from;
        argv[6] = (char *)to;
        argv[7] = (char *)app;
        argv[8] = (char *)program;
        argv[9] = NULL;

        /* Its own process group, so a Control-C meant for the game does
           not stop it, and none of the game's files or sockets: only the
           standard three are passed on. */
        posix_spawnattr_init(&attributes);
        posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT);
        posix_spawnattr_setpgroup(&attributes, 0);
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addinherit_np(&actions, STDIN_FILENO);
        posix_spawn_file_actions_addinherit_np(&actions, STDOUT_FILENO);
        posix_spawn_file_actions_addinherit_np(&actions, STDERR_FILENO);

        started = posix_spawn(&helper, "/bin/sh", &actions, &attributes, argv, environ) == 0;

        posix_spawn_file_actions_destroy(&actions);
        posix_spawnattr_destroy(&attributes);
        return started;
    }
}

void ETA_WindowsUpdate_Shutdown(void)
{
    @autoreleasepool
    {
        [gSession invalidateAndCancel];
        gSession = nil;
    }
}

/* ------------------------------------------------------------------ */
/* Replacing the whole app: see macos_update.h.                        */

#include "macos_update.h"

int ETA_MacUpdate_AppPath(char *out, size_t size)
{
    @autoreleasepool
    {
        NSString *path = [[NSBundle mainBundle] bundlePath];

        if (!path || ![path hasSuffix:@".app"])
        {
            return 0;
        }
        if ([path rangeOfString:@"/AppTranslocation/"].location != NSNotFound)
        {
            return -1;
        }
        if (out && size)
        {
            snprintf(out, size, "%s", [path fileSystemRepresentation]);
        }
        return 1;
    }
}

int ETA_MacUpdate_SupportPath(const char *name, char *out, size_t size)
{
    @autoreleasepool
    {
        NSString *home = NSHomeDirectory();
        NSString *dir;

        if (!home || !name || !out || !size)
        {
            return 0;
        }
        dir = [home stringByAppendingPathComponent:@"Library/Application Support/RTCW"];
        [[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:YES
                                                   attributes:nil error:NULL];
        snprintf(out, size, "%s/%s", [dir fileSystemRepresentation], name);
        return 1;
    }
}

/*
 * The helper: waits for the game (pid $1) to exit; unzips $2 with ditto
 * into a folder of its own; moves the running app $3 aside and copies the
 * new one into its place, putting the old one back if that fails; copies
 * the download's sounds pk3 and guide beside the app; cleans up; and
 * opens the app - new or, failing all that, old.
 */
static const char ETA_MacUpdate_AppHelper[] =
    "while kill -0 \"$1\" 2>/dev/null; do sleep 0.5; done\n"
    "zip=\"$2\"; app=\"$3\"; dir=$(dirname \"$app\")\n"
    "tmp=$(mktemp -d \"${TMPDIR:-/tmp}/eta-update.XXXXXX\") || exec open -n \"$app\"\n"
    "if ditto -x -k \"$zip\" \"$tmp\"; then\n"
    "  new=$(find \"$tmp\" -maxdepth 3 -name '*.app' -type d | head -n 1)\n"
    "  if [ -n \"$new\" ]; then\n"
    "    rm -rf \"$app.previous\"\n"
    "    if mv \"$app\" \"$app.previous\"; then\n"
    "      if ditto \"$new\" \"$app\"; then rm -rf \"$app.previous\"\n"
    "      else rm -rf \"$app\"; mv \"$app.previous\" \"$app\"; fi\n"
    "    fi\n"
    "    pk3=$(find \"$tmp\" -maxdepth 3 -path '*/main/sp_zaccessibility.pk3' | head -n 1)\n"
    "    if [ -n \"$pk3\" ]; then mkdir -p \"$dir/main\" && cp -f \"$pk3\" \"$dir/main/\"; fi\n"
    "    guide=$(find \"$tmp\" -maxdepth 2 -name INSTALL.md | head -n 1)\n"
    "    if [ -n \"$guide\" ]; then cp -f \"$guide\" \"$dir/\"; fi\n"
    "  fi\n"
    "fi\n"
    "rm -rf \"$tmp\" \"$zip\"\n"
    "exec open -n \"$app\"\n";

int ETA_MacUpdate_ScheduleAppReplace(const char *zip)
{
    char                       app[4096];
    char                       pid[32];
    char                      *argv[8];
    pid_t                      helper;
    posix_spawnattr_t          attributes;
    posix_spawn_file_actions_t actions;
    int                        started;

    if (!zip || access(zip, F_OK) != 0 || ETA_MacUpdate_AppPath(app, sizeof(app)) != 1)
    {
        return 0;
    }

    snprintf(pid, sizeof(pid), "%d", (int)getpid());
    argv[0] = (char *)"/bin/sh";
    argv[1] = (char *)"-c";
    argv[2] = (char *)ETA_MacUpdate_AppHelper;
    argv[3] = (char *)"eta-update";
    argv[4] = pid;
    argv[5] = (char *)zip;
    argv[6] = app;
    argv[7] = NULL;

    /* Its own process group, and only the standard three descriptors,
       as for the pk3 swap above. */
    {
        posix_spawnattr_init(&attributes);
        posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT);
        posix_spawnattr_setpgroup(&attributes, 0);
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addinherit_np(&actions, STDIN_FILENO);
        posix_spawn_file_actions_addinherit_np(&actions, STDOUT_FILENO);
        posix_spawn_file_actions_addinherit_np(&actions, STDERR_FILENO);

        started = posix_spawn(&helper, "/bin/sh", &actions, &attributes, argv, environ) == 0;

        posix_spawn_file_actions_destroy(&actions);
        posix_spawnattr_destroy(&attributes);
    }
    return started;
}

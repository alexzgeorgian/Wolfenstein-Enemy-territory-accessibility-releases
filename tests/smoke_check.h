#pragma once

/*
 * Shared checking for the smoke tests.
 *
 * Deliberately not assert(). A Release build defines NDEBUG, which compiles
 * assert() away entirely - checks would vanish and a test would pass by doing
 * nothing. CHECK always evaluates its condition and the exit code reports the
 * result, in every build configuration.
 *
 * The counter is static-per-translation-unit, which is fine because each smoke
 * test is a single file with its own main().
 */

#include "core/error_handler.h"
#include "core/runtime_guard.h" /* ETA_MAX_*_TEXT_LENGTH, for boundary cases */

#include <stdio.h>

static int gSmokeFailures = 0;

#define CHECK(condition)                                                       \
    do                                                                         \
    {                                                                          \
        if (!(condition))                                                      \
        {                                                                      \
            printf("[smoke] FAILED %s:%d: %s\n", __FILE__, __LINE__, #condition); \
            gSmokeFailures++;                                                  \
        }                                                                      \
    } while (0)

/* Runs call and requires that the runtime guards accepted its arguments. */
#define CHECK_ACCEPTS(call)                                                    \
    do                                                                         \
    {                                                                          \
        ETA_ErrorHandler_Clear();                                              \
        call;                                                                  \
        CHECK(!ETA_ErrorHandler_HasError());                                   \
        ETA_ErrorHandler_Clear();                                              \
    } while (0)

/* Runs call and requires that a guard rejected it with exactly expectedCode. */
#define CHECK_REJECTS(call, expectedCode)                                      \
    do                                                                         \
    {                                                                          \
        ETA_ErrorHandler_Clear();                                              \
        call;                                                                  \
        CHECK(ETA_ErrorHandler_HasError());                                    \
        CHECK(ETA_ErrorHandler_GetLastError().code == (expectedCode));         \
        ETA_ErrorHandler_Clear();                                              \
    } while (0)

/*
 * Rejection cases log an ERROR line each. That is the guard working, so say
 * so up front rather than leaving a passing run looking broken.
 */
#define SMOKE_BANNER(name)                                                     \
    printf("[smoke] %s: ERROR/WARNING lines below are expected - this test "   \
           "exercises the input guards\n", (name))

#define SMOKE_REPORT(name)                                                     \
    (gSmokeFailures                                                            \
        ? (printf("[smoke] %s: %d check(s) FAILED\n", (name), gSmokeFailures), 1) \
        : (printf("[smoke] %s: all checks passed\n", (name)), 0))

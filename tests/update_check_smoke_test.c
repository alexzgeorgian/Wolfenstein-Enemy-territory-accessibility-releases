/*
 * The updater's decisions, and the checksum it trusts a download by.
 *
 * Everything here is a way to hurt a player who cannot see the screen
 * and therefore cannot notice what went wrong:
 *
 * - Offered an "update" that is older than what they have, or the same
 *   one again every time the game starts.
 * - Offered a mod for an ET: Legacy they do not have, which then loads
 *   to a silent game. Those have to be told to update the game first.
 * - A version name that walks out of the folder or the download address
 *   ("../", a slash, a space) taken at its word.
 * - A cut-off download accepted because the checksum code is wrong in a
 *   way that happens to agree with itself. So the SHA-256 is pinned to
 *   the published FIPS 180-2 test vectors, including the one that spans
 *   blocks, and to one fed a byte at a time.
 */

#include "update/update_check.h"
#include "smoke_check.h"

#include <stdio.h>
#include <string.h>

static void CheckSha(const char *input, const char *expected)
{
    ETA_Sha256 sha;
    char       hex[ETA_UPDATE_SHA256_HEX_LENGTH + 1];

    ETA_Sha256_Begin(&sha);
    ETA_Sha256_Add(&sha, input, strlen(input));
    ETA_Sha256_FinalHex(&sha, hex);
    CHECK(strcmp(hex, expected) == 0);
}

int main(void)
{
    ETA_UpdateManifest manifest;
    char               words[512];
    const char        *good =
        "# accessibility mode update\n"
        "version=beta-0.02.3\r\n"
        "engine=v2.86.0\r\n"
        "sha256=ABCDEF0123456789abcdef0123456789ABCDEF0123456789abcdef0123456789\n"
        "size=4194304\n"
        "notes=something later releases add\n";

    /* --- Versions --- */
    CHECK(ETA_Update_CompareVersions("beta-0.02.3", "beta-0.02.2") > 0);
    CHECK(ETA_Update_CompareVersions("beta-0.02.2", "beta-0.02.3") < 0);
    CHECK(ETA_Update_CompareVersions("beta-0.02.2", "beta-0.02.2") == 0);
    /* The jump for a new ET: Legacy outranks every step before it. */
    CHECK(ETA_Update_CompareVersions("beta-0.03.0", "beta-0.02.9") > 0);
    /* Numbers are numbers: 0.10 is after 0.9, which a string compare gets wrong. */
    CHECK(ETA_Update_CompareVersions("beta-0.10.0", "beta-0.9.0") > 0);
    CHECK(ETA_Update_CompareVersions("beta-0.02.10", "beta-0.02.9") > 0);
    CHECK(ETA_Update_CompareVersions("beta-0.3", "beta-0.3.0") == 0);
    /* Stages, on equal numbers. */
    CHECK(ETA_Update_CompareVersions("beta-1.0.0", "alpha-1.0.0") > 0);
    CHECK(ETA_Update_CompareVersions("1.0.0", "beta-1.0.0") > 0);
    CHECK(ETA_Update_CompareVersions("1.0.0", "beta-0.99.0") > 0);
    /* But the numbers come first: alpha-0.2.0 was the start of all this. */
    CHECK(ETA_Update_CompareVersions("beta-0.01.0", "alpha-0.5.0") < 0);

    /* --- Names --- */
    CHECK(ETA_Update_IsSafeVersionName("beta-0.02.3"));
    CHECK(!ETA_Update_IsSafeVersionName(""));
    CHECK(!ETA_Update_IsSafeVersionName(NULL));
    CHECK(!ETA_Update_IsSafeVersionName(".."));
    CHECK(!ETA_Update_IsSafeVersionName("../beta"));
    CHECK(!ETA_Update_IsSafeVersionName("beta/0.1"));
    CHECK(!ETA_Update_IsSafeVersionName("beta 0.1"));
    CHECK(!ETA_Update_IsSafeVersionName("beta?0.1"));
    CHECK(!ETA_Update_IsSafeVersionName("123456789012345678901234567890123"));
    CHECK(ETA_Update_IsReleaseBuild("beta-0.02.2"));
    CHECK(!ETA_Update_IsReleaseBuild("dev"));
    CHECK(!ETA_Update_IsReleaseBuild(""));
    CHECK(!ETA_Update_IsReleaseBuild("nightly"));

    /* --- Addresses --- */
    CHECK(strcmp(ETA_UPDATE_MANIFEST_URL,
                 "https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-releases/releases/latest/download/eta-update.txt") == 0);
    CHECK(ETA_Update_PackageUrl("beta-0.02.3", words, sizeof(words)));
    CHECK(strcmp(words, "https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-releases/releases/download/beta-0.02.3/zzz_accessibility.pk3") == 0);
    CHECK(ETA_Update_MacGameUrl("1.3.2", words, sizeof(words)));
    CHECK(strcmp(words, "https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-releases/releases/download/1.3.2/qagame_mac") == 0);
    CHECK(!ETA_Update_MacGameUrl("../evil", words, sizeof(words)));
    CHECK(words[0] == '\0');
    CHECK(!ETA_Update_PackageUrl("../evil", words, sizeof(words)));
    CHECK(words[0] == '\0');
    CHECK(!ETA_Update_PackageUrl("beta-0.02.3", words, 20));
    CHECK(words[0] == '\0');
    /* An ordinary build is a development build, and never checks. */
    CHECK(strcmp(ETA_Update_InstalledVersion(), "dev") == 0);
    CHECK(!ETA_Update_IsReleaseBuild(ETA_Update_InstalledVersion()));

    /* --- The manifest --- */
    CHECK(ETA_Update_ParseManifest(good, &manifest));
    CHECK(strcmp(manifest.version, "beta-0.02.3") == 0);
    CHECK(strcmp(manifest.engine, "v2.86.0") == 0);
    CHECK(strcmp(manifest.sha256, "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789") == 0);
    CHECK(manifest.size == 4194304);

    /* Each field is required. A page that says less is not acted on. */
    CHECK(!ETA_Update_ParseManifest("engine=v2.86.0\nsha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nsize=10\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nsha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nsize=10\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nengine=v2.86.0\nsize=10\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nengine=v2.86.0\nsha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n", &manifest));
    /* Damaged fields. */
    CHECK(!ETA_Update_ParseManifest("version=../../x\nengine=v2.86.0\nsha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nsize=10\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nengine=v2.86.0\nsha256=abcdef01\nsize=10\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nengine=v2.86.0\nsha256=zzzzzz0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nsize=10\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nengine=v2.86.0\nsha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nsize=999999999\n", &manifest));
    CHECK(!ETA_Update_ParseManifest("version=beta-0.02.3\nengine=v2.86.0\nsha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nsize=12ab\n", &manifest));
    /* What GitHub sends for a page that is not there. */
    CHECK(!ETA_Update_ParseManifest("Not Found", &manifest));
    CHECK(!ETA_Update_ParseManifest("", &manifest));
    CHECK(!ETA_Update_ParseManifest(NULL, &manifest));

    /* --- Which engine is running --- */
    CHECK(ETA_Update_EngineIs("ET Legacy v2.86.0 win-x86_64 Oct  2 2026", "v2.86.0"));
    CHECK(!ETA_Update_EngineIs("ET Legacy v2.86.1 win-x86_64 Oct  2 2026", "v2.86.0"));
    CHECK(!ETA_Update_EngineIs("ET Legacy v2.86.0-12-g1234abc win-x86_64", "v2.86.0"));
    CHECK(!ETA_Update_EngineIs("ET Legacy v2.86.01 win-x86_64", "v2.86.0"));
    CHECK(ETA_Update_EngineIs("v2.86.0", "v2.86.0"));
    CHECK(!ETA_Update_EngineIs("", "v2.86.0"));

    /* --- What gets offered --- */
    CHECK(ETA_Update_ParseManifest(good, &manifest));
    /* For the system this runs on, whichever it is: which systems a
       release is for is checked on its own below. */
    manifest.platforms = ETA_UPDATE_THIS_PLATFORM;
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 win-x86_64", "v2.86.0") == ETA_UPDATE_INSTALL);
    /* The same version, or an older one, is never offered. */
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.3", "ET Legacy v2.86.0 win-x86_64", "v2.86.0") == ETA_UPDATE_NONE);
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.4", "ET Legacy v2.86.0 win-x86_64", "v2.86.0") == ETA_UPDATE_NONE);
    /* A development build never nags. */
    CHECK(ETA_Update_Decide(&manifest, "dev", "ET Legacy v2.86.0 win-x86_64", "v2.86.0") == ETA_UPDATE_NONE);
    CHECK(ETA_Update_Decide(NULL, "beta-0.02.2", "ET Legacy v2.86.0 win-x86_64", "v2.86.0") == ETA_UPDATE_NONE);

    /* A mod for a newer game: update the game first. */
    strcpy(manifest.version, "beta-0.03.0");
    strcpy(manifest.engine, "v2.87.0");
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.3", "ET Legacy v2.86.0 win-x86_64", "v2.86.0") == ETA_UPDATE_NEEDS_GAME);
    /* Once the game is updated, the same offer becomes an install. */
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.3", "ET Legacy v2.87.0 win-x86_64", "v2.86.0") == ETA_UPDATE_INSTALL);
    /* With nothing from the game, the build's own engine stands in. */
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.3", "", "v2.86.0") == ETA_UPDATE_NEEDS_GAME);
    CHECK(ETA_Update_Decide(&manifest, "beta-0.02.3", NULL, "v2.87.0") == ETA_UPDATE_INSTALL);

    /* --- Which systems a release is for --- */
    /* Saying nothing is a release from before the Mac port: Windows. */
    CHECK(ETA_Update_ParseManifest(good, &manifest));
    CHECK(manifest.platforms == ETA_UPDATE_PLATFORM_WINDOWS);
    CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 win-x86_64", "v2.86.0",
                               ETA_UPDATE_PLATFORM_WINDOWS) == ETA_UPDATE_INSTALL);
    /* A Mac never takes one: the pk3 has no game code for it. Nor is it
       told to update the game for one. */
    CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 macos-aarch64", "v2.86.0",
                               ETA_UPDATE_PLATFORM_MACOS) == ETA_UPDATE_NONE);
    strcpy(manifest.engine, "v2.87.0");
    CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 macos-aarch64", "v2.86.0",
                               ETA_UPDATE_PLATFORM_MACOS) == ETA_UPDATE_NONE);
    {
        char both[512], mac[512], unknown[512];

        snprintf(both, sizeof(both), "%splatforms=windows,macos\r\n", good);
        snprintf(mac, sizeof(mac), "%splatforms= macos , linux\n", good);
        snprintf(unknown, sizeof(unknown), "%splatforms=linux\n", good);

        CHECK(ETA_Update_ParseManifest(both, &manifest));
        CHECK(manifest.platforms == (ETA_UPDATE_PLATFORM_WINDOWS | ETA_UPDATE_PLATFORM_MACOS));
        CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 win-x86_64", "v2.86.0",
                                   ETA_UPDATE_PLATFORM_WINDOWS) == ETA_UPDATE_INSTALL);
        CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 macos-aarch64", "v2.86.0",
                                   ETA_UPDATE_PLATFORM_MACOS) == ETA_UPDATE_INSTALL);
        /* The Mac is held to the game's version like Windows. */
        strcpy(manifest.engine, "v2.87.0");
        CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 macos-aarch64", "v2.86.0",
                                   ETA_UPDATE_PLATFORM_MACOS) == ETA_UPDATE_NEEDS_GAME);

        /* A Mac-only release is not offered to Windows. */
        CHECK(ETA_Update_ParseManifest(mac, &manifest));
        CHECK(manifest.platforms == ETA_UPDATE_PLATFORM_MACOS);
        CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 win-x86_64", "v2.86.0",
                                   ETA_UPDATE_PLATFORM_WINDOWS) == ETA_UPDATE_NONE);

        /* Only systems it does not know: for neither. */
        CHECK(ETA_Update_ParseManifest(unknown, &manifest));
        CHECK(manifest.platforms == 0);
        CHECK(ETA_Update_DecideFor(&manifest, "beta-0.02.2", "ET Legacy v2.86.0 win-x86_64", "v2.86.0",
                                   ETA_UPDATE_PLATFORM_WINDOWS) == ETA_UPDATE_NONE);
    }

    /* --- The words --- */
    ETA_Update_SpokenVersion("beta-0.02.3", words, sizeof(words));
    CHECK(strcmp(words, "beta 0.02.3") == 0);

    CHECK(ETA_Update_ParseManifest(good, &manifest));
    ETA_Update_DescribeOffer(ETA_UPDATE_INSTALL, &manifest, "beta-0.02.2", words, sizeof(words));
    CHECK(strstr(words, "beta 0.02.3") != NULL);
    CHECK(strstr(words, "beta 0.02.2") != NULL);
    CHECK(strstr(words, "Download") != NULL);
    CHECK(strchr(words, '-') == NULL);
    /* The tester asked to hear first that there is a new version. */
    CHECK(strncmp(words, "A new version is available", 26) == 0);

    strcpy(manifest.engine, "v2.87.0");
    ETA_Update_DescribeOffer(ETA_UPDATE_NEEDS_GAME, &manifest, "beta-0.02.2", words, sizeof(words));
    CHECK(strstr(words, "v2.87.0") != NULL);
    CHECK(strstr(words, "Update ET: Legacy first") != NULL);

    ETA_Update_DescribeOffer(ETA_UPDATE_NONE, &manifest, "beta-0.02.2", words, sizeof(words));
    CHECK(words[0] == '\0');

    /* A small buffer is cut, never overrun. */
    {
        char tiny[8];

        memset(tiny, 'x', sizeof(tiny));
        ETA_Update_DescribeOffer(ETA_UPDATE_INSTALL, &manifest, "beta-0.02.2", tiny, sizeof(tiny));
        CHECK(tiny[sizeof(tiny) - 1] == '\0');
    }

    /* --- The Mac's bots file --- */
    {
        const char *abc = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        const char *path = "eta_update_check_smoke_qagame.tmp";
        char        hex[ETA_UPDATE_SHA256_HEX_LENGTH + 1];
        FILE       *file = fopen(path, "wb");

        CHECK(file != NULL);
        if (file)
        {
            fputs("abc", file);
            fclose(file);
        }
        CHECK(ETA_Update_FileSha256(path, hex));
        CHECK(strcmp(hex, abc) == 0);
        /* The one built with this release, or another, or none at all. */
        CHECK(ETA_Update_CheckMacGame(path, abc) == ETA_MAC_GAME_MATCHES);
        CHECK(ETA_Update_CheckMacGame(path, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
              == ETA_MAC_GAME_OTHER);
        remove(path);
        CHECK(!ETA_Update_FileSha256(path, hex));
        CHECK(hex[0] == '\0');
        CHECK(ETA_Update_CheckMacGame(path, abc) == ETA_MAC_GAME_ABSENT);
        /* A build that made no bots file checks nothing. */
        CHECK(ETA_Update_CheckMacGame(path, "") == ETA_MAC_GAME_UNCHECKED);
        CHECK(ETA_Update_CheckMacGame(path, NULL) == ETA_MAC_GAME_UNCHECKED);
        CHECK(strcmp(ETA_Update_MacGameSha256(), "") == 0);
    }

    /* --- SHA-256, FIPS 180-2 vectors --- */
    CheckSha("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    CheckSha("abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    CheckSha("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
             "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");

    /* A million 'a's, fed in uneven pieces: the way a download arrives. */
    {
        ETA_Sha256 sha;
        char       chunk[1000];
        char       hex[ETA_UPDATE_SHA256_HEX_LENGTH + 1];
        size_t     done = 0, piece = 1;

        memset(chunk, 'a', sizeof(chunk));
        ETA_Sha256_Begin(&sha);
        while (done < 1000000)
        {
            size_t take = piece;

            if (take > 1000000 - done)
            {
                take = 1000000 - done;
            }
            ETA_Sha256_Add(&sha, chunk, take);
            done += take;
            piece = piece % 997 + 1;
        }
        ETA_Sha256_FinalHex(&sha, hex);
        CHECK(strcmp(hex, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0") == 0);
    }

    /* Lengths either side of the padding boundary (55, 56, 64 bytes). */
    CheckSha("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318");
    CheckSha("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a");
    CheckSha("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb");

    if (gSmokeFailures)
    {
        printf("[smoke] update_check: %d failure(s)\n", gSmokeFailures);
        return 1;
    }

    printf("[smoke] update_check: all checks passed\n");
    return 0;
}

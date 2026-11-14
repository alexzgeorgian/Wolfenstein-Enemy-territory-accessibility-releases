#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Finding out that there is a newer version of the mod, and whether it
 * can be put in place yet.
 *
 * Getting a new build used to be an errand: notice a release, open the
 * page, download a zip, find the pk3 inside it, and copy it into the
 * right one of two folders that are both called "legacy". Every step is
 * one more place for somebody who cannot see the screen to get stuck,
 * so the mod now asks the release page itself and offers the update
 * from a menu that talks.
 *
 * What lives here is everything about that which can be checked without
 * a network or a Windows machine: reading what the release page says,
 * deciding whether it is newer, deciding whether it would even run on
 * the game the player has, the words of the offer, and the checksum the
 * download has to match. The fetching and the file swap are the
 * platform's (platform/windows/windows_update.c).
 *
 * The release page publishes a small text file beside the pk3,
 * eta-update.txt, written by .github/workflows/release.yml:
 *
 *     version=beta-0.02.3
 *     engine=v2.86.0
 *     sha256=<64 hex digits of zzz_accessibility.pk3>
 *     size=<bytes of zzz_accessibility.pk3>
 *     platforms=windows,macos
 *
 * platforms names the systems the pk3 carries libraries for. Releases
 * before the Mac port did not write it and carried Windows alone, so a
 * file without it means Windows; a Mac takes only a release that names
 * macos, and never one that would leave it with no game code to load.
 *
 * A text file rather than GitHub's JSON, so nothing here needs a JSON
 * parser and the format is whatever this project says it is.
 */

/*
 * Where releases are published for the game to fetch. Not the project's
 * own repository: that one is private, and a private repository's
 * releases answer "not found" to anybody not signed in to GitHub, which
 * the game never is. So the release workflow copies each release - the
 * archive, the pk3 and eta-update.txt - to a public repository that
 * holds nothing else, and this is that repository.
 *
 * "latest" only ever names a full release, never one marked as a
 * pre-release, which is why the release workflow marks each one as the
 * latest.
 */
#define ETA_UPDATE_RELEASES_URL \
    "https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-releases/releases"
#define ETA_UPDATE_MANIFEST_URL ETA_UPDATE_RELEASES_URL "/latest/download/eta-update.txt"
#define ETA_UPDATE_PACKAGE_NAME "zzz_accessibility.pk3"
/* Published beside it: the Mac's game module with bots (see below). */
#define ETA_UPDATE_MAC_GAME_NAME "qagame_mac"

#define ETA_UPDATE_MAX_VERSION_LENGTH 32
#define ETA_UPDATE_MAX_ENGINE_LENGTH 32
#define ETA_UPDATE_SHA256_HEX_LENGTH 64

/* The pk3 is a few megabytes. Anything claiming to be past this is not
   a pk3 this project built, and is not downloaded. */
#define ETA_UPDATE_MAX_PACKAGE_BYTES (64L * 1024L * 1024L)

/* The systems a release carries libraries for (platforms=). */
#define ETA_UPDATE_PLATFORM_WINDOWS 1
#define ETA_UPDATE_PLATFORM_MACOS   2

/* The system this build runs on. Windows stands in everywhere else, as
   there is no updater anywhere else to ask. */
#ifdef __APPLE__
#define ETA_UPDATE_THIS_PLATFORM ETA_UPDATE_PLATFORM_MACOS
#else
#define ETA_UPDATE_THIS_PLATFORM ETA_UPDATE_PLATFORM_WINDOWS
#endif

typedef struct
{
    char version[ETA_UPDATE_MAX_VERSION_LENGTH + 1];
    char engine[ETA_UPDATE_MAX_ENGINE_LENGTH + 1];
    char sha256[ETA_UPDATE_SHA256_HEX_LENGTH + 1]; /* lower case */
    long size;
    int  platforms; /* ETA_UPDATE_PLATFORM_* bits; Windows when not said */
} ETA_UpdateManifest;

typedef enum
{
    ETA_UPDATE_NONE = 0,     /* nothing newer, or nothing usable */
    ETA_UPDATE_INSTALL,      /* newer, and built for the game being run */
    ETA_UPDATE_NEEDS_GAME    /* newer, but for a newer ET: Legacy */
} ETA_UpdateOffer;

/*
 * Reads eta-update.txt. Returns 1 only when every field is present and
 * sound: a version name made of safe characters, an engine tag, exactly
 * 64 hex digits, and a size inside ETA_UPDATE_MAX_PACKAGE_BYTES. Unknown
 * keys and comment lines are ignored, so the file can grow.
 */
int ETA_Update_ParseManifest(const char *text, ETA_UpdateManifest *out);

/*
 * A version name that is safe to put in a URL and a file path: letters,
 * digits, '.', '-' and '_', and not empty. The version also names the
 * download's address, so this is what keeps a damaged manifest from
 * pointing the download anywhere else.
 */
int ETA_Update_IsSafeVersionName(const char *version);

/* A build that came out of the release workflow, rather than "dev" or
   nothing. Only those check for updates. */
int ETA_Update_IsReleaseBuild(const char *version);

/*
 * The version of the mod that is running, and the ET: Legacy tag it was
 * built for. The release workflow passes both in when it builds
 * (ETA_RELEASE_VERSION, ETA_ENGINE_TAG); any other build is "dev", and
 * never offers to replace itself.
 */
const char *ETA_Update_InstalledVersion(void);
const char *ETA_Update_BuiltEngine(void);

/*
 * The Mac's bots. ET: Legacy builds its Mac game module without Omni-bot,
 * so the Mac download carries its own, qagame_mac, built with it, for
 * the player to put in their legacy folder. It is not in the pk3 - the
 * engine loads the game module only as a loose file - so the in-game
 * updater does not replace it, and a copy left from another version
 * could make hosting fail. The menus check it: the SHA-256 of the one
 * built with this release (empty in a build that made none), and the
 * SHA-256 of a file. A release publishes its qagame_mac beside the pk3,
 * and on a Mac set up for bots the menus fetch it, check it against
 * this, and put it in place, so the player never copies it by hand.
 */
typedef enum
{
    ETA_MAC_GAME_UNCHECKED = 0, /* this build made no qagame_mac */
    ETA_MAC_GAME_ABSENT,        /* none installed */
    ETA_MAC_GAME_MATCHES,       /* the one built with this release */
    ETA_MAC_GAME_OTHER          /* one from another version */
} ETA_MacGameState;

const char *ETA_Update_MacGameSha256(void);
int ETA_Update_FileSha256(const char *path, char out[ETA_UPDATE_SHA256_HEX_LENGTH + 1]);
ETA_MacGameState ETA_Update_CheckMacGame(const char *path, const char *expected);

/* The address of a release's pk3. 0 if version is not a safe name. */
int ETA_Update_PackageUrl(const char *version, char *out, size_t outSize);

/* The address of a release's qagame_mac, the same way. */
int ETA_Update_MacGameUrl(const char *version, char *out, size_t outSize);

/*
 * Orders two version names. The numbers decide first, each compared as
 * a number so 0.10 comes after 0.9; on equal numbers alpha < beta < rc
 * < a name with no stage. Negative, zero or positive, like strcmp.
 */
int ETA_Update_CompareVersions(const char *a, const char *b);

/*
 * Whether engineText - ET: Legacy's own description of itself, e.g.
 * "ET Legacy v2.86.0 win-x86_64 Oct  2 2026" - is the release named by
 * tag ("v2.86.0"). A development build ("v2.86.0-12-g1234abc") is not.
 */
int ETA_Update_EngineIs(const char *engineText, const char *tag);

/*
 * What to offer. installedVersion is the running mod's; engineText is
 * the game's description of itself, and builtEngine the engine tag this
 * mod was built for, used in its place when the game says nothing. A
 * release that carries nothing for this system is never offered.
 */
ETA_UpdateOffer ETA_Update_Decide(const ETA_UpdateManifest *manifest,
                                  const char *installedVersion,
                                  const char *engineText,
                                  const char *builtEngine);

/* The same, for the system named (ETA_UPDATE_PLATFORM_*), so either
   system's choice can be checked on any machine. */
ETA_UpdateOffer ETA_Update_DecideFor(const ETA_UpdateManifest *manifest,
                                     const char *installedVersion,
                                     const char *engineText,
                                     const char *builtEngine,
                                     int platform);

/* The spoken words of an offer, ready for the popup. */
void ETA_Update_DescribeOffer(ETA_UpdateOffer offer,
                              const ETA_UpdateManifest *manifest,
                              const char *installedVersion,
                              char *out, size_t outSize);

/* A version name as it should be said: "beta-0.02.3" is "beta 0.02.3",
   not "beta minus zero point zero two point three". */
void ETA_Update_SpokenVersion(const char *version, char *out, size_t outSize);

/*
 * SHA-256, so a download is checked against the checksum the release
 * published before anything is put in place. A cut-off or damaged pk3
 * fails to load with no speech at all, which would leave the player
 * with a silent game and nothing to tell them why.
 */
typedef struct
{
    unsigned int state[8];
    unsigned long long length;
    unsigned char block[64];
    size_t used;
} ETA_Sha256;

void ETA_Sha256_Begin(ETA_Sha256 *sha);
void ETA_Sha256_Add(ETA_Sha256 *sha, const void *data, size_t size);
/* Writes 64 lower case hex digits and a terminator. */
void ETA_Sha256_FinalHex(ETA_Sha256 *sha, char out[ETA_UPDATE_SHA256_HEX_LENGTH + 1]);

#ifdef __cplusplus
}
#endif

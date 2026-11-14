#include "update_check.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef ETA_RELEASE_VERSION
#define ETA_RELEASE_VERSION "dev"
#endif
#ifndef ETA_ENGINE_TAG
#define ETA_ENGINE_TAG ""
#endif
#ifndef ETA_MAC_GAME_SHA256
#define ETA_MAC_GAME_SHA256 ""
#endif

const char *ETA_Update_InstalledVersion(void)
{
    return ETA_RELEASE_VERSION;
}

const char *ETA_Update_BuiltEngine(void)
{
    return ETA_ENGINE_TAG;
}

const char *ETA_Update_MacGameSha256(void)
{
    return ETA_MAC_GAME_SHA256;
}

int ETA_Update_FileSha256(const char *path, char out[ETA_UPDATE_SHA256_HEX_LENGTH + 1])
{
    FILE         *file;
    ETA_Sha256    sha;
    unsigned char block[16384];
    size_t        got;
    int           ok;

    if (out)
    {
        out[0] = '\0';
    }
    if (!path || !out || !(file = fopen(path, "rb")))
    {
        return 0;
    }

    ETA_Sha256_Begin(&sha);
    while ((got = fread(block, 1, sizeof(block), file)) > 0)
    {
        ETA_Sha256_Add(&sha, block, got);
    }
    ok = !ferror(file);
    fclose(file);
    if (ok)
    {
        ETA_Sha256_FinalHex(&sha, out);
    }
    return ok;
}

ETA_MacGameState ETA_Update_CheckMacGame(const char *path, const char *expected)
{
    char got[ETA_UPDATE_SHA256_HEX_LENGTH + 1];

    if (!expected || strlen(expected) != ETA_UPDATE_SHA256_HEX_LENGTH)
    {
        return ETA_MAC_GAME_UNCHECKED;
    }
    if (!ETA_Update_FileSha256(path, got))
    {
        return ETA_MAC_GAME_ABSENT;
    }
    return strcmp(got, expected) == 0 ? ETA_MAC_GAME_MATCHES : ETA_MAC_GAME_OTHER;
}

static void ETA_Update_Copy(char *out, size_t outSize, const char *text, size_t length)
{
    if (length >= outSize)
    {
        length = outSize - 1;
    }

    memcpy(out, text, length);
    out[length] = '\0';
}

int ETA_Update_IsSafeVersionName(const char *version)
{
    const char *c;

    if (!version || !version[0] || strlen(version) > ETA_UPDATE_MAX_VERSION_LENGTH)
    {
        return 0;
    }

    for (c = version; *c; c++)
    {
        if (!isalnum((unsigned char)*c) && *c != '.' && *c != '-' && *c != '_')
        {
            return 0;
        }
    }

    /* "." and ".." are made of safe characters and are still a path. */
    return strcmp(version, ".") != 0 && strcmp(version, "..") != 0;
}

/* A file published with a release, by name. */
static int ETA_Update_AssetUrl(const char *version, const char *asset, char *out, size_t outSize)
{
    int written;

    if (!out || outSize == 0)
    {
        return 0;
    }

    out[0] = '\0';

    if (!ETA_Update_IsSafeVersionName(version))
    {
        return 0;
    }

    written = snprintf(out, outSize, "%s/download/%s/%s", ETA_UPDATE_RELEASES_URL, version, asset);
    if (written < 0 || (size_t)written >= outSize)
    {
        out[0] = '\0';
        return 0;
    }

    return 1;
}

int ETA_Update_PackageUrl(const char *version, char *out, size_t outSize)
{
    return ETA_Update_AssetUrl(version, ETA_UPDATE_PACKAGE_NAME, out, outSize);
}

int ETA_Update_MacGameUrl(const char *version, char *out, size_t outSize)
{
    return ETA_Update_AssetUrl(version, ETA_UPDATE_MAC_GAME_NAME, out, outSize);
}

int ETA_Update_IsReleaseBuild(const char *version)
{
    const char *c;

    if (!ETA_Update_IsSafeVersionName(version) || strcmp(version, "dev") == 0)
    {
        return 0;
    }

    for (c = version; *c; c++)
    {
        if (isdigit((unsigned char)*c))
        {
            return 1;
        }
    }

    return 0;
}

/* A comma separated list of system names; names it does not know are
   left out, so a later release can add one. */
static int ETA_Update_ParsePlatforms(const char *value, size_t length)
{
    int    platforms = 0;
    size_t start     = 0;

    while (start < length)
    {
        size_t end = start, last;

        while (end < length && value[end] != ',')
        {
            end++;
        }
        last = end;
        while (start < last && value[start] == ' ')
        {
            start++;
        }
        while (last > start && value[last - 1] == ' ')
        {
            last--;
        }
        if (last - start == 7 && !strncmp(value + start, "windows", 7))
        {
            platforms |= ETA_UPDATE_PLATFORM_WINDOWS;
        }
        else if (last - start == 5 && !strncmp(value + start, "macos", 5))
        {
            platforms |= ETA_UPDATE_PLATFORM_MACOS;
        }
        start = end + 1;
    }

    return platforms;
}

int ETA_Update_ParseManifest(const char *text, ETA_UpdateManifest *out)
{
    const char *line;
    int         haveVersion = 0, haveEngine = 0, haveSha = 0, haveSize = 0, havePlatforms = 0;

    if (!text || !out)
    {
        return 0;
    }

    memset(out, 0, sizeof(*out));

    for (line = text; *line; )
    {
        const char *end = line;
        const char *equals;
        const char *value;
        size_t      keyLength, valueLength;

        while (*end && *end != '\n')
        {
            end++;
        }

        equals = memchr(line, '=', (size_t)(end - line));

        if (equals && line[0] != '#')
        {
            keyLength = (size_t)(equals - line);
            value = equals + 1;
            valueLength = (size_t)(end - value);

            /* A file saved on Windows ends its lines with \r\n. */
            while (valueLength > 0 && (value[valueLength - 1] == '\r' || value[valueLength - 1] == ' '))
            {
                valueLength--;
            }

            if (keyLength == 7 && !strncmp(line, "version", 7) && valueLength <= ETA_UPDATE_MAX_VERSION_LENGTH)
            {
                ETA_Update_Copy(out->version, sizeof(out->version), value, valueLength);
                haveVersion = ETA_Update_IsSafeVersionName(out->version);
            }
            else if (keyLength == 6 && !strncmp(line, "engine", 6) && valueLength <= ETA_UPDATE_MAX_ENGINE_LENGTH)
            {
                ETA_Update_Copy(out->engine, sizeof(out->engine), value, valueLength);
                haveEngine = ETA_Update_IsSafeVersionName(out->engine);
            }
            else if (keyLength == 6 && !strncmp(line, "sha256", 6) && valueLength == ETA_UPDATE_SHA256_HEX_LENGTH)
            {
                size_t i;

                haveSha = 1;
                for (i = 0; i < valueLength; i++)
                {
                    if (!isxdigit((unsigned char)value[i]))
                    {
                        haveSha = 0;
                    }
                    out->sha256[i] = (char)tolower((unsigned char)value[i]);
                }
                out->sha256[valueLength] = '\0';
            }
            else if (keyLength == 4 && !strncmp(line, "size", 4) && valueLength > 0 && valueLength < 12)
            {
                char   number[12];
                char  *stop;
                long   size;

                ETA_Update_Copy(number, sizeof(number), value, valueLength);
                size = strtol(number, &stop, 10);
                haveSize = (*stop == '\0' && size > 0 && size <= ETA_UPDATE_MAX_PACKAGE_BYTES);
                out->size = haveSize ? size : 0;
            }
            else if (keyLength == 9 && !strncmp(line, "platforms", 9))
            {
                out->platforms = ETA_Update_ParsePlatforms(value, valueLength);
                havePlatforms  = 1;
            }
        }

        line = *end ? end + 1 : end;
    }

    /* Every release before the Mac port carried Windows alone, and said
       nothing. */
    if (!havePlatforms)
    {
        out->platforms = ETA_UPDATE_PLATFORM_WINDOWS;
    }

    return haveVersion && haveEngine && haveSha && haveSize;
}

/* The stage word a version starts with, ranked; a bare number ranks
   above every pre-release. */
static int ETA_Update_StageRank(const char *version)
{
    if (!strncmp(version, "alpha", 5))
    {
        return 0;
    }
    if (!strncmp(version, "beta", 4))
    {
        return 1;
    }
    if (!strncmp(version, "rc", 2))
    {
        return 2;
    }
    return 3;
}

int ETA_Update_CompareVersions(const char *a, const char *b)
{
    const char *pa = a ? a : "";
    const char *pb = b ? b : "";

    for (;;)
    {
        long na = -1, nb = -1;

        while (*pa && !isdigit((unsigned char)*pa))
        {
            pa++;
        }
        while (*pb && !isdigit((unsigned char)*pb))
        {
            pb++;
        }

        if (*pa)
        {
            na = strtol(pa, (char **)&pa, 10);
        }
        if (*pb)
        {
            nb = strtol(pb, (char **)&pb, 10);
        }

        if (na < 0 && nb < 0)
        {
            break;
        }

        /* 0.3 and 0.3.0 are the same version: a missing number is 0. */
        if ((na < 0 ? 0 : na) != (nb < 0 ? 0 : nb))
        {
            return (na < 0 ? 0 : na) < (nb < 0 ? 0 : nb) ? -1 : 1;
        }
    }

    return ETA_Update_StageRank(a ? a : "") - ETA_Update_StageRank(b ? b : "");
}

int ETA_Update_EngineIs(const char *engineText, const char *tag)
{
    const char *found;
    size_t      length;

    if (!engineText || !tag || !tag[0])
    {
        return 0;
    }

    length = strlen(tag);

    for (found = strstr(engineText, tag); found; found = strstr(found + 1, tag))
    {
        int startsWord = (found == engineText || found[-1] == ' ');
        int endsWord   = (found[length] == '\0' || found[length] == ' ');

        if (startsWord && endsWord)
        {
            return 1;
        }
    }

    return 0;
}

ETA_UpdateOffer ETA_Update_Decide(const ETA_UpdateManifest *manifest,
                                  const char *installedVersion,
                                  const char *engineText,
                                  const char *builtEngine)
{
    return ETA_Update_DecideFor(manifest, installedVersion, engineText, builtEngine, ETA_UPDATE_THIS_PLATFORM);
}

ETA_UpdateOffer ETA_Update_DecideFor(const ETA_UpdateManifest *manifest,
                                     const char *installedVersion,
                                     const char *engineText,
                                     const char *builtEngine,
                                     int platform)
{
    if (!manifest || !ETA_Update_IsReleaseBuild(installedVersion)
        || !ETA_Update_IsSafeVersionName(manifest->version))
    {
        return ETA_UPDATE_NONE;
    }

    /* A pk3 with no game code for this system would load to a silent
       game: such a release is not for this player at all. */
    if (!(manifest->platforms & platform))
    {
        return ETA_UPDATE_NONE;
    }

    if (ETA_Update_CompareVersions(manifest->version, installedVersion) <= 0)
    {
        return ETA_UPDATE_NONE;
    }

    /* The game is the judge of which engine is running: a player who has
       already updated ET: Legacy for the new mod is offered it straight
       away, even though this old mod was built for the old engine. Only
       when the game will not say does the build's own tag stand in. */
    if (engineText && engineText[0])
    {
        return ETA_Update_EngineIs(engineText, manifest->engine)
               ? ETA_UPDATE_INSTALL : ETA_UPDATE_NEEDS_GAME;
    }

    return (builtEngine && !strcmp(builtEngine, manifest->engine))
           ? ETA_UPDATE_INSTALL : ETA_UPDATE_NEEDS_GAME;
}

void ETA_Update_SpokenVersion(const char *version, char *out, size_t outSize)
{
    size_t i;

    if (!out || outSize == 0)
    {
        return;
    }

    for (i = 0; version && version[i] && i + 1 < outSize; i++)
    {
        out[i] = (version[i] == '-' || version[i] == '_') ? ' ' : version[i];
    }
    out[i] = '\0';
}

void ETA_Update_DescribeOffer(ETA_UpdateOffer offer,
                              const ETA_UpdateManifest *manifest,
                              const char *installedVersion,
                              char *out, size_t outSize)
{
    char newer[ETA_UPDATE_MAX_VERSION_LENGTH + 1];
    char older[ETA_UPDATE_MAX_VERSION_LENGTH + 1];

    if (!out || outSize == 0)
    {
        return;
    }

    out[0] = '\0';

    if (!manifest || offer == ETA_UPDATE_NONE)
    {
        return;
    }

    ETA_Update_SpokenVersion(manifest->version, newer, sizeof(newer));
    ETA_Update_SpokenVersion(installedVersion, older, sizeof(older));

    if (offer == ETA_UPDATE_INSTALL)
    {
        snprintf(out, outSize,
                 "A new version is available: accessibility mode %s. You have %s. "
                 "Download it now?",
                 newer, older);
    }
    else
    {
        snprintf(out, outSize,
                 "A new version is available: accessibility mode %s. It needs ET: Legacy %s, "
                 "which is newer than your game. Update ET: Legacy first, "
                 "and this offer comes back when you start the game again.",
                 newer, manifest->engine);
    }
}

/* SHA-256, FIPS 180-4. */

static const unsigned int ETA_Sha256_K[64] =
{
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

#define ETA_ROTR(x, n) ((((x) >> (n)) | ((x) << (32 - (n)))) & 0xffffffffu)

static void ETA_Sha256_Block(ETA_Sha256 *sha, const unsigned char *block)
{
    unsigned int w[64];
    unsigned int a, b, c, d, e, f, g, h;
    int          i;

    for (i = 0; i < 16; i++)
    {
        w[i] = ((unsigned int)block[i * 4] << 24) | ((unsigned int)block[i * 4 + 1] << 16)
               | ((unsigned int)block[i * 4 + 2] << 8) | (unsigned int)block[i * 4 + 3];
    }

    for (i = 16; i < 64; i++)
    {
        unsigned int s0 = ETA_ROTR(w[i - 15], 7) ^ ETA_ROTR(w[i - 15], 18) ^ (w[i - 15] >> 3);
        unsigned int s1 = ETA_ROTR(w[i - 2], 17) ^ ETA_ROTR(w[i - 2], 19) ^ (w[i - 2] >> 10);

        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & 0xffffffffu;
    }

    a = sha->state[0]; b = sha->state[1]; c = sha->state[2]; d = sha->state[3];
    e = sha->state[4]; f = sha->state[5]; g = sha->state[6]; h = sha->state[7];

    for (i = 0; i < 64; i++)
    {
        unsigned int s1    = ETA_ROTR(e, 6) ^ ETA_ROTR(e, 11) ^ ETA_ROTR(e, 25);
        unsigned int ch    = (e & f) ^ (~e & g);
        unsigned int temp1 = (h + s1 + ch + ETA_Sha256_K[i] + w[i]) & 0xffffffffu;
        unsigned int s0    = ETA_ROTR(a, 2) ^ ETA_ROTR(a, 13) ^ ETA_ROTR(a, 22);
        unsigned int maj   = (a & b) ^ (a & c) ^ (b & c);
        unsigned int temp2 = (s0 + maj) & 0xffffffffu;

        h = g; g = f; f = e;
        e = (d + temp1) & 0xffffffffu;
        d = c; c = b; b = a;
        a = (temp1 + temp2) & 0xffffffffu;
    }

    sha->state[0] = (sha->state[0] + a) & 0xffffffffu;
    sha->state[1] = (sha->state[1] + b) & 0xffffffffu;
    sha->state[2] = (sha->state[2] + c) & 0xffffffffu;
    sha->state[3] = (sha->state[3] + d) & 0xffffffffu;
    sha->state[4] = (sha->state[4] + e) & 0xffffffffu;
    sha->state[5] = (sha->state[5] + f) & 0xffffffffu;
    sha->state[6] = (sha->state[6] + g) & 0xffffffffu;
    sha->state[7] = (sha->state[7] + h) & 0xffffffffu;
}

void ETA_Sha256_Begin(ETA_Sha256 *sha)
{
    static const unsigned int initial[8] =
    {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
    };

    memcpy(sha->state, initial, sizeof(initial));
    sha->length = 0;
    sha->used = 0;
}

void ETA_Sha256_Add(ETA_Sha256 *sha, const void *data, size_t size)
{
    const unsigned char *bytes = (const unsigned char *)data;

    sha->length += size;

    while (size > 0)
    {
        size_t take = 64 - sha->used;

        if (take > size)
        {
            take = size;
        }

        memcpy(sha->block + sha->used, bytes, take);
        sha->used += take;
        bytes += take;
        size -= take;

        if (sha->used == 64)
        {
            ETA_Sha256_Block(sha, sha->block);
            sha->used = 0;
        }
    }
}

void ETA_Sha256_FinalHex(ETA_Sha256 *sha, char out[ETA_UPDATE_SHA256_HEX_LENGTH + 1])
{
    static const char hex[] = "0123456789abcdef";
    unsigned long long bits = sha->length * 8u;
    int                i;

    sha->block[sha->used++] = 0x80;

    if (sha->used > 56)
    {
        memset(sha->block + sha->used, 0, 64 - sha->used);
        ETA_Sha256_Block(sha, sha->block);
        sha->used = 0;
    }

    memset(sha->block + sha->used, 0, 56 - sha->used);
    for (i = 0; i < 8; i++)
    {
        sha->block[56 + i] = (unsigned char)(bits >> (56 - i * 8));
    }
    ETA_Sha256_Block(sha, sha->block);

    for (i = 0; i < 32; i++)
    {
        unsigned int byte = (sha->state[i / 4] >> (24 - (i % 4) * 8)) & 0xff;

        out[i * 2]     = hex[byte >> 4];
        out[i * 2 + 1] = hex[byte & 0xf];
    }
    out[ETA_UPDATE_SHA256_HEX_LENGTH] = '\0';
}

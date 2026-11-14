# Releases

A release is one file a player can drop into ET: Legacy and hear the
difference. Everything else in this repository is source.

**Releases are published to the repository's Releases page**, not
committed here. Two reasons: a release asset downloads in one click,
where a binary in the source tree does not; and a 2.4 MB archive that
changes wholesale every build has no business in a source repository's
history.

    release/
      build-release.sh      builds the package from source
      INSTALL.md.in         the guide, rendered into every package
      NOTES.md.in           the Releases page's text
      CHANGES.md            what changed in the version being cut
      autoexec.cfg          the ready-made config, shipped as-is
                            (installed by guide section 2, step two)
      README.md             this file

The three `.in` and `.md` texts above carry `@VERSION@`, `@ARCHIVE@`,
`@CHECKSUM_LINE@`, `@COMMIT@` and `@ENGINE_TAG@` placeholders that
`build-release.sh` fills in, so no version number is ever typed into a
document by hand. A placeholder left unreplaced fails the build rather
than shipping as literal text.

Players want the latest archive from the Releases page. It unzips into a
single folder of the same name, holding everything:

    wolfenstein-enemy-territory-accessibility-<version>-windows/   (the Mac's, -mac/, has no nvda/)
      zzz_accessibility.pk3
      autoexec.cfg
      INSTALL.md
      CHANGELOG.md
      SHA256SUMS.contents

`SHA256SUMS` is published beside the archive as a second release asset,
and lists only the archive, so `sha256sum -c SHA256SUMS` passes cleanly
on a good download.

## Version numbers

The number grows by as much as the change deserves, not by a fixed step
each time:

- **Patch** (`alpha-0.17.0` to `alpha-0.17.1`) for a fix, a document, a
  key binding, packaging - anything a player would describe as "the same
  build, tidied".
- **Minor** (`alpha-0.17.x` to `alpha-0.18.0`) for a new thing to hear,
  or a change to how something already spoken behaves.

Earlier releases stepped the minor number every time regardless of size,
which made a documentation pass and a whole new narration feature look
equally significant from the outside. They are not.

The tag carries the `alpha-` prefix and the release workflow takes it
verbatim, so the version passed to it is the whole tag.

## Cutting a release

Update `CHANGES.md` first. It is the "What changed in this build"
section of the release page *and* the body of the `CHANGELOG.md` that
ships inside the archive, and it describes the version being cut - so it
is rewritten each time rather than appended to.

Then move the *previous* version's `CHANGES.md` text into `HISTORY.md`
as a new entry at the top, trimmed to a headline and a few bullets.
`CHANGES.md` is only ever the build being cut; `HISTORY.md` is every
build before it, and the two are concatenated into the archive's
`CHANGELOG.md`. The release workflow fails if `HISTORY.md` is missing an
entry for a tag that has already been published, so forgetting this step
stops the release rather than shipping a gap.

The two documents in the archive are kept apart on purpose. `INSTALL.md`
answers "how do I run this" and `CHANGELOG.md` answers "what is
different this time"; neither should start absorbing the other. The
guide had drifted once already, still shipping notes about alpha-0.1.0
and alpha-0.4.0 that read as current long after they stopped being
true.

The changelog carries the whole history rather than pointing at the
releases page because the person reading it is using a screen reader:
opening a browser, finding the releases list and walking back through it
to see what changed since the build they had is several minutes of work
that a file in the folder answers in seconds. Every version is a
heading, so heading navigation goes straight down the list.

### Fixing the wording on a page that is already published

Run the Release workflow with **notes_only** ticked. It downloads the
published `SHA256SUMS`, reads the build commit out of the existing
notes, re-renders `NOTES.md.in` against both, and edits the release -
without touching the assets.

That distinction matters. The archive's timestamps are pinned to
`SOURCE_DATE_EPOCH`, which is this repository's last commit, so a plain
rebuild produces a different checksum even when the libraries are
byte-identical. Anyone who recorded the old one would be told a good
download is bad. A wording fix should never do that.

Push a tag and `.github/workflows/release.yml` does the rest - it builds
the package with the script below and publishes it as a release asset:

    git tag alpha-0.3.0
    git push origin alpha-0.3.0

Tags matching `alpha-*`, `beta-*` or `v*` trigger it. The same workflow
can be run from the Actions tab with a version typed in, for anyone who
would rather not push a tag.

Re-running for a version that already has a release replaces its assets
rather than failing, so a bad build can be corrected in place.

## What the package is

`zzz_accessibility.pk3` holds accessibility-enabled builds of ET:
Legacy's two client mod libraries, for 32-bit and 64-bit Windows in the
same file. It is additive: it replaces nothing, and uninstalling is
deleting it.

Three details decide whether it works at all, and every one of them
fails silently if you get it wrong. They are in the script as comments
where they apply, and repeated here because they are easy to undo by
accident:

- **The name has to sort after `legacy_*.pk3`.** ET: Legacy sorts a mod
  folder's pk3 files ascending and prepends each to the search path, so
  the last one alphabetically is searched first. Rename it earlier and
  the stock libraries load instead, with no error anywhere.
- **Loose DLLs do not work.** On release builds `Sys_LoadGameDll` always
  re-extracts the mod libraries from the pk3 into `fs_homepath` before
  loading them, so anything copied in by hand is overwritten on startup.
  The pk3 is the only reliable way in.
- **The architecture has to be in the filename.** The engine looks for
  `cgame_mp_x64.dll` / `cgame_mp_x86.dll`. Cross-compiling leaves
  `CMAKE_SYSTEM_PROCESSOR` empty, ET: Legacy's arch detection then fails,
  and the build produces `cgame_mp_.dll`, which loads nowhere.

## Building a release

    release/build-release.sh [--engine PATH] [--out DIR] [--version V]

`--version` names both the archive and the folder it unzips to, so a
package always says which release it is once it has left this
repository.

With no `--engine` it clones ET: Legacy at the revision pinned in
`.github/workflows/ci.yml` and verifies the commit before building. Give
it `--engine` to reuse a checkout you already have; it needs that tree
clean, and hands it back unmodified.

Needs `cmake`, `git`, `zip`, and both mingw-w64 cross compilers
(`x86_64-w64-mingw32-gcc`, `i686-w64-mingw32-gcc`). It refuses to
produce a package whose libraries do not export `vmMain` and `dllEntry`,
or that do not contain the NVDA speech path - that last check is what
catches a build where `FEATURE_ACCESSIBILITY` quietly did not take.

The engine revision is read out of the CI workflow rather than written
down twice, so a release can never be built against a tree different
from the one CI tests the patch series against.

## How reproducible this is

The script pins the two things that otherwise make every build unique:
source paths are mapped to fixed names with `-ffile-prefix-map`, and
`SOURCE_DATE_EPOCH` is set from the last commit so the timestamp ET:
Legacy stamps in comes from the source rather than the clock.

That takes two builds from different directories from about 120,000
differing bytes down to 237. It is **not** bit-for-bit reproducible: the
remaining bytes are non-printable padding, with no differing strings and
no functional meaning, and closing that gap was not worth the effort at
this stage. So `SHA256SUMS` identifies the artifact that was actually
shipped; treat it as a way to check your download, not as a figure you
can independently re-derive.

The checksums are split across two files on purpose. `sha256sum -c`
fails on any line naming a file it cannot find, so listing the archive's
contents alongside the archive would report four missing files and make
an intact download look corrupt.

## Releases so far

**alpha-0.2.0** - current. Brings the accessibility runtime up in both
modules, and plays the game's own sounds as cues through the engine.
Shipped as a single archive; earlier builds were loose files.

**alpha-0.1.0** - withdrawn, not kept. It could not speak: neither module
ever called an initialiser, so the speech backends were never set up and
every narration call silently did nothing. Only the audio cues worked.
It is deleted rather than archived because a build that cannot do the
one thing it exists for is not worth anyone's download.

That bug is worth remembering when adding a system here: the library's
tests call Init themselves, so a missing Init in an integration is
invisible to every check in this repository. Nothing but running the
game catches it.

## What this release is not

It has never been played. Everything in it compiles, links, passes the
test suite, and has its direction maths checked against the engine's own
code on every commit - but no part of it has been run in a real match or
spoken through a real screen reader. That is the entire point of
shipping an alpha: those are the bugs nobody here can find.

`docs/ROADMAP.md` lists what remains unverified.

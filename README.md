# Wolfenstein: Enemy Territory accessibility mode

This is the official download page for the accessibility mode of
Wolfenstein: Enemy Territory, the World War II first-person shooter. The
mode lets blind and visually impaired players play the game on their
own, with a screen reader and the keyboard, on **Windows or a Mac**.

It is built on ET: Legacy, the maintained version of the game. It reads
the menus and the match aloud, plays sounds that tell you where things
are, and every control can be reached from the keyboard. On Windows it
speaks through NVDA, or the speech built into Windows. On a Mac it
speaks through VoiceOver, or the Mac's own voice.

You do not need a GitHub account to download.

## Download

Go to the latest release:
https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-releases/releases/latest

Download the zip for your computer. Its name says which it is for:

- **On Windows:** the one ending in `-windows.zip`.
- **On a Mac:** the one ending in `-mac.zip`.

It is everything you need. Ignore the other files. (Up to 1.2.0 there
was one zip, for both.)

A release marked "Mac test build, not for players" is a build being
tried out before a release. Take the latest release instead.

## Install on Windows

1. You need **ET: Legacy 2.86.1**, from https://www.etlegacy.com/download.
   The version matters: the mode only works with the version it was
   built for. Each release says which version that is.
2. You need the original game files, `pak0.pk3`, `pak1.pk3` and
   `pak2.pk3`. The ET: Legacy installer can download them for you.
3. Download the `-windows.zip` and unzip it anywhere. It makes one
   folder.
4. In that folder, find `zzz_accessibility.pk3`. Copy it into the
   `legacy` folder where ET: Legacy is installed. For a normal install
   that is `C:\Program Files\ETLegacy\legacy`.
5. If you use NVDA, copy `nvdaControllerClient.dll` next to
   `ETLegacy.exe`. Use the one from the `nvda\x64` folder for 64-bit
   ET: Legacy, or the one from `nvda\x86` for 32-bit. Without NVDA, the
   mode uses the speech built into Windows, which needs nothing
   installed.
6. Start the game. The menus speak straight away.

## Install on a Mac

1. You need **ET: Legacy 2.86.1** for macOS, from
   https://www.etlegacy.com/download. It runs on Apple Silicon and
   Intel Macs.
2. You need the original game files, `pak0.pk3`, `pak1.pk3` and
   `pak2.pk3`. Start ET: Legacy once, so it makes its folders.
3. Download the `-mac.zip` and open it. The Mac unzips it into a
   folder.
4. In Finder, choose **Go**, then **Go to Folder** (Command Shift G).
   Type `~/Library/Application Support/etlegacy/legacy` and press
   Return.
5. Copy `zzz_accessibility.pk3` from the unzipped folder into that one.
6. Start ET: Legacy. With VoiceOver on, the game speaks through
   VoiceOver. With it off, it speaks through the Mac's own voice.

**Bots on a Mac.** ET: Legacy's Mac version comes without bot support.
Download Omni-bot from its own page and put its `omni-bot` folder in the
same `legacy` folder, as on Windows. The game then fetches the file that
adds bot support, `qagame_mac`, by itself, and keeps it up to date.
`INSTALL.md`, in the Mac zip, has the steps under "Step three: bots".

On both, do not rename `zzz_accessibility.pk3`: the name is what makes
the game load it. The folder also has `INSTALL.md`, the full guide,
which explains every key and every sound.

## Updates

On Windows and on a Mac, when the game starts you hear "Checking for
updates", then whether you have the latest version, then "Main menu".
If there is a new version, it asks you before it downloads anything. To
check yourself, go to Options, then Accessibility, then "Check for
updates".

## First steps in a match

- **L** opens the team and class choice. Move with the arrow keys or
  Tab, and choose with Enter.
- **F5** says your status. **F6** says the last thing again. **F8**
  stops the speech.
- **9** says your health, and **0** says your ammo.
- **Left and Right arrow** turn you. A tap turns to the next compass
  point; holding turns smoothly. **Up and Down arrow** look up and
  down.
- **F** turns you to the nearest thing you can use: a door, a cabinet,
  a wounded teammate, a ladder, or your dynamite. Close up, F uses it.
  **]** and **[** choose a different one.
- **F9** tells you what is around you.
- **Keypad plus** puts a marker on an objective. Press it again to move
  the marker to the next objective. Then follow the marker's ping:
  - a high ping means the marker is in front of you;
  - a lower ping means it is to your left or right;
  - a low double ping means it is behind you.
- **Keypad dot** says where the marker is. **Keypad star** clears it.

**No number pad?** Most Mac keyboards have none. Every key can be
changed: go to Options, then Accessibility, then Key Binds. Arrow to a
row, press Enter, then press the key you want.

## Settings

Go to Options, then Accessibility. There are five pages:

- **Environment**: which sounds and announcements you hear.
- **Speech**: the speech rate, pitch and volume, and how far the music
  goes down while the narrator speaks.
- **Sound**: the volume of each of the mode's sounds.
- **Key Binds**: every key the mode uses.
- **Hosting**: playing on your own with bots, or with friends.

## Help and feedback

The mode is made with, and tested by, a blind player. If something is
not said, says the wrong thing, or a sound points the wrong way, please
open an issue on this page. Say what you did, what you heard, and
whether you were on Windows or a Mac.

## Licence

The mode is built on ET: Legacy, which is free software under the GNU
General Public License, version 3. The mode is under the same licence,
and its source code is available on request. The original Wolfenstein:
Enemy Territory game files are not part of this download.

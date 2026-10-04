# Wolfenstein: Enemy Territory accessibility mode

This is the official download page for the accessibility mode of
Wolfenstein: Enemy Territory, the World War II first-person shooter. The
mode lets blind and visually impaired players play the game on their
own, with a screen reader and the keyboard.

It is built on ET: Legacy, the maintained version of the game. It reads
the menus and the match aloud through NVDA, or through the speech
built into Windows. It plays sounds that tell you where things are, and
every control can be reached from the keyboard.

You do not need a GitHub account to download.

## Download

Go to the latest release:
https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-releases/releases/latest

Download the file whose name starts with
`wolfenstein-enemy-territory-accessibility-` and ends in `.zip`. That
is everything you need. Ignore the files called "Source code".

## What you need first

1. **Windows.**
2. **ET: Legacy version 2.86.0**, from https://www.etlegacy.com/download.
   The version matters: the mode only works with the version it was
   built for. Each release says which version that is.
3. **The original game files**: `pak0.pk3`, `pak1.pk3` and `pak2.pk3`.
   The ET: Legacy installer can download them for you.
4. **Optional: NVDA.** Without it, the mode uses the speech built into
   Windows, which needs nothing installed.

## Install

1. Unzip the download anywhere. It makes one folder.
2. In that folder, find `zzz_accessibility.pk3`. Copy it into the
   `legacy` folder where ET: Legacy is installed. For a normal install
   that is `C:\Program Files\ETLegacy\legacy`.
3. If you use NVDA, copy `nvdaControllerClient.dll` next to
   `ETLegacy.exe`. Use the one from the `nvda\x64` folder for 64-bit
   ET: Legacy, or the one from `nvda\x86` for 32-bit.
4. Start the game. The menus speak straight away.

Do not rename `zzz_accessibility.pk3`: the name is what makes the game
load it. The folder also has `INSTALL.md`, the full guide, which
explains every key and every sound.

## Updates

When the game starts you hear "Checking for updates", then whether you
have the latest version, then "Main menu". If there is a new version,
it asks you before it downloads anything. To check yourself, go to Options, then
Accessibility, then "Check for updates".

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
- **F9** tells you what is around you.
- **Keypad plus** puts a marker on an objective. Press it again to move
  the marker to the next objective. Then follow the marker's ping:
  - a high ping means the marker is in front of you;
  - a lower ping means it is to your left or right;
  - a low double ping means it is behind you.
- **Keypad dot** says where the marker is. **Keypad star** clears it.

**No number pad?** Every key can be changed. Go to Options, then
Accessibility, then Key Binds. Arrow to a row, press Enter, then press
the key you want.

## Settings

Go to Options, then Accessibility. There are four pages:

- **Environment**: which sounds and announcements you hear.
- **Speech**: the speech rate, pitch and volume, and how far the music
  goes down while the narrator speaks.
- **Key Binds**: every key the mode uses.
- **Hosting**: playing on your own with bots, or with friends.

## Help and feedback

The mode is made with, and tested by, a blind player. If something is
not said, says the wrong thing, or a sound points the wrong way, please
open an issue on this page. Say what you did and what you heard.

## Licence

The mode is built on ET: Legacy, which is free software under the GNU
General Public License, version 3. The mode is under the same licence,
and its source code is available on request. The original Wolfenstein:
Enemy Territory game files are not part of this download.

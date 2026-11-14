# No Quarter integration

This wires the accessibility mode into **No Quarter**, so the classic
No Quarter mod can be played with the same speech and keys as the
ET: Legacy mode. It runs on the ET: Legacy engine, with No Quarter in
its own `nq` mod folder.

The base is **NoQuarter EoTS**, the community-maintained No Quarter
that runs on 64-bit ET: Legacy:

Base commit: [`DL-LAM/NoQuarter-EoTS@f41b59e`](https://github.com/DL-LAM/NoQuarter-EoTS/commit/f41b59e0159276e67682ddeda6728ce0792dc4c2)
(tag `NQ_EoTS_v1.0.7b`, the commit its 1.0.7b release was built from).

Like `integration/etlegacy/`, this is a series of patches rather than a
fork. Apply them in order; each depends on the ones before it.

## Licence

No Quarter is under the No Quarter Mod Team's Modified Reciprocal
Public License 1.1 (`License.txt` in its repository). It asks that the
source of any changes we hand out is public, which this repository is.
These patches and the No Quarter libraries built from them fall under
that licence.

## Why this is its own integration

No Quarter grew from the original 2.60 game code, not from ET: Legacy.
Its menus are one `src/ui/ui_shared.c`, as in
`integration/id-software/`, and its text boxes edit their cvar directly,
one byte per character. So the changes follow the ET: Legacy series in
what they say and do, but are written against No Quarter's own code.

The accessibility library (`src/accessibility/`) is used unchanged.
Every engine call the mode makes exists in No Quarter too.

## Building

The download - `zzz_accessibility_nq.pk3` with the 64-bit and 32-bit
Windows libraries, and its guide - is built by one script:

```sh
release/build-noquarter.sh --out out --version nq-test-1
```

It clones NoQuarter EoTS at the release in `base.txt`, checks the
commit, applies these patches, and cross-compiles with mingw-w64 as
`release/build-release.sh` does for ET: Legacy. The guide is
`release/INSTALL-noquarter.md.in`. `.github/workflows/noquarter-test.yml`
runs it on every change, and on a push publishes the download as a
prerelease on the public downloads page, `nq-test-N`, keeping only the
newest.

By hand, for Linux:

```sh
git clone https://github.com/DL-LAM/NoQuarter-EoTS nq
git -C nq checkout f41b59e0159276e67682ddeda6728ce0792dc4c2
for p in integration/noquarter/*.patch; do git -C nq apply "$PWD/$p"; done
cmake -S nq -B build-nq -DFEATURE_ACCESSIBILITY=ON \
      -DETA_SOURCE_DIR="$PWD" -DBUILD_SERVER_MOD=OFF -DWITH_LUA=OFF
cmake --build build-nq --target cgame ui
```

Only the client libraries change. The server's `qagame` and Omni-bot
come from the NoQuarter EoTS download as they are. The pk3 is named to
sort after No Quarter's own `nqeots_b_v1.0.7b.pk3`, so its libraries
are the ones the game loads.

## 0001: build the accessibility mode into cgame and ui

- Adds `FEATURE_ACCESSIBILITY` (off by default) and `ETA_SOURCE_DIR`,
  the checkout of this repository, to `src/CMakeLists.txt`.
- When on, builds the library once and links it into `cgame` and `ui`,
  each its own copy, as on ET: Legacy.
- Adds `-fcommon` for GCC. No Quarter's headers define globals without
  `extern`; MSVC merges them, GCC 10 and later refuse to link. No
  Quarter's own Linux build script passes the same flag.

## 0002: say the menus

All in `src/ui/`, and the same behaviour as the ET: Legacy menus:

- Each control says its name and its setting when the keyboard lands on
  it: "Fullscreen, On", a key bind with the key it is on, a list with
  the row it is on and "3 of 12".
- Changing a setting says the new value. Sliders move with the left and
  right arrows, in round steps.
- Enter, and the arrows on a slider, work on whatever the keyboard is
  on. No Quarter, like the original game, also asked that the mouse
  pointer be over the control, which the keyboard never moves.
- A pointer left still no longer takes focus away from the keyboard on
  every key press.
- Text boxes say their contents on arrival, then each character typed,
  deleted, or passed by the cursor. Password fields say only how many
  characters they hold.
- Popups are read as they open.
- Binding a key says it is listening, and then what the control is on.
- The server list reads each server in words: name, map, game type,
  players and bots, ping, and what its icons show, including whether it
  runs No Quarter. A refresh says how many servers and players it found.
- "No Quarter. Main menu" and "In-game menu" as those menus open, and
  "Console open" and "Console closed" before a match.
- F6 repeats what was last said and F8 stops speech, offered once on
  keys the stock config leaves free, and offered again after the
  controls are reset to their defaults.

## 0003: choose team, class and weapons from the keyboard

The limbo panel, as on ET: Legacy, in `src/cgame/`:

- The cgame starts its own speech first thing in `CG_Init`, since the
  panel can open before the rest of the init is done.
- Opening the panel says "Limbo menu" and how to use it. That is said
  from the `CGAME_EVENT_GAMEVIEW` case rather than from
  `CG_LimboPanel_Setup`, which No Quarter also calls on every promotion
  with the panel shut.
- Up and down walk the teams, the five classes, the primary and
  secondary weapon, and Confirm, moving the real cursor onto each and
  saying it: "Axis, selected", "Medic, full", "Primary weapon, MP40,
  1 of 2". A weapon slot with nothing to choose is stepped over.
- Enter presses the control through its own click handler. On a weapon
  it moves to the next weapon the slot offers, through the dropdown's
  own setter. No Quarter's secondaries depend on rank - akimbo pistols
  at Light Weapons 4, and for a soldier at Heavy Weapons 4 a
  submachine gun and, where the server allows it, the shotgun - so the
  list is read fresh each time. A primary the server has ruled out is
  left out of it.
- Tab swaps between the primary and secondary weapon and says which.
- F6 and F8 work in a match too: the cgame answers them, or hands them
  to the menus when a menu is open.

## 0004: say the match

Most of it is in a new file, `src/cgame/cg_accessibility.c`, built only
with `FEATURE_ACCESSIBILITY`; No Quarter's own files call into it from
marked hooks. It follows the ET: Legacy cgame in what it says:

- **Keys.** `accessibilityStatus` (F5): playing or watching, health,
  weapon and ammo, the next objective in the map's list, and the way to
  the nearest. `accessibilityHealth` (9) and `accessibilityAmmo` (0).
  `accessibilityObjectives` (O), since No Quarter has no objectives
  key: the map's mission text, the next objective, and the way to it.
  The scoreboard is read when `+scores` brings it up. The menus offer
  these keys as a second generation of binds, replacing only the dead
  `weaponbank 9` and `weaponbank 10` (bank 9 is empty in No Quarter,
  and there is no bank 10), and `weapalt` on keypad slash.
- **As it happens.** The weapon in hand with its ammo, from the same
  figures the HUD draws (`CG_PlayerAmmoValue`, through a wrapper); the
  posture; the scope and binoculars; leaning; playing, down, waiting or
  watching, and who is being watched; the player's own kills and
  deaths, in the words of No Quarter's own obituary tables and weapon
  files, before its display filters; pickups with what they gave;
  finished and failed objectives from the map script's states; the
  construction count under the pliers; chat, with team and fireteam
  brackets read as words; the console opening; the loading screen and,
  in the ui, the connection screen.
- **Respawn countdown.** Unlike ET: Legacy, only while waiting to
  respawn, every five seconds and the last three, from
  `CG_CalculateReinfTime`.
- **Sounds.** The stock game's own sounds through the engine: a hit
  from its direction, low health, and the objective changing with its
  direction. No sound files are added.
- **Objectives.** No Quarter's objective info has no `objflags` and
  sets no main objective, so the way given is to the nearest objective
  on the team's command map, kept while it stays near. No Quarter keeps
  tanks and other objective icons in two lists, `mapEntities` and
  `mapEntities2`, both static in `cg_commandmap.c`, so the search lives
  there. The order and descriptions still come from the map's own list
  in `CS_MULTI_INFO` and `CS_MULTI_OBJECTIVE`.
- **Settings**, read each frame: `eta_chatCallouts`,
  `eta_objectiveCallouts`, `eta_interactionCallouts`, `eta_musicDuck`,
  `eta_cueVolume`, `eta_speechRate`, `eta_speechPitch`,
  `eta_speechVolume`, and a `eta_cue...` sound name for each cue.

Getting around is 0007.

## 0005: build for the Mac

NoQuarter EoTS ships no Mac build, so this makes one, with
`release/build-noquarter-mac.sh` on a Mac: `cgame_mac` and `ui_mac`
with the mode, into the pk3, and No Quarter's own `qagame_mac` with
Omni-bot and without Lua, for a game the player hosts, packed into the
pk3 too and written out by the ui (below). Each holds Apple Silicon and
Intel code.

- `src/CMakeLists.txt`: on the Mac the three libraries are named
  `cgame_mac`, `ui_mac` and `qagame_mac`, with no extension, as
  ET: Legacy loads them.
- `src/game/q_shared.h`: a platform block for today's macOS. The
  `MACOS_X` and `__MACOS__` blocks are the PowerPC Macs of the original
  game, which no compiler defines now.
- `src/cgame/cg_osfile.h`: `sys/stat.h` on the Mac too.
- `Omnibot/Common/BotLoadLibrary.cpp`: on the Mac, look for
  `omnibot_et_mac.so`, the name Omni-bot and the NoQuarter EoTS release
  ship it under, in `omnibot_path`, the game's folder and `~/omni-bot`,
  and only there. No Quarter's Linux names are left out on the Mac: it
  cannot load them, and on an Intel Mac the first of them would replace
  the library just found.
- `src/game/g_client.c`: the localhost check, off by default, knows the
  Mac client's name.
- `src/cgame/cg_accessibility.c`: on the Mac the loading screen is said
  when the load is over, as in the ET: Legacy mode. The game loads
  without letting the Mac's event loop run, and VoiceOver and the
  system voice need it, so what was said during the load was lost.
- `src/cgame/cg_accessibility.c`: in a game the player hosts with
  `omnibot_enable` on, after the briefing, why the bots did not come:
  Omni-bot not found where the game module looks, or still carrying the
  Mac's quarantine mark. While it carries the mark the Mac refuses to
  load it and puts up a window over the game, and nothing else says why.
  A file the player allowed in System Settings keeps the mark, with its
  user-approved flag (0x40) set, and loads; only a mark without the flag
  counts. Nothing is said when bots are already in the game.
- `src/ui/ui_main.c`: on the Mac, when a game ends in an error, the
  error is said again a second after the menus are drawing. The menus
  are started again and the error popup opens without the Mac's event
  loop running, so its reading was lost, and the player was back at the
  main menu with no reason given.
- `src/ui/ui_main.c`: on the Mac, as the ui starts, `qagame_mac` is
  written out of the mod's pk3, where `release/build-noquarter.sh` packs
  it as `eta/qagame_mac`, into the mod's folder: when it is missing,
  different, or carries the Mac's quarantine mark. The game extracts
  `cgame_mac` and `ui_mac` from a pk3 itself, but looks for the game
  module only loose in the folder, and a copy downloaded from the web
  carries the mark, which made the Mac refuse to load it; the game then
  said the file was missing while it sat there. One the game writes
  carries no mark.
  Then the ui tries loading it, and when the Mac refuses, says so once
  the menus have settled, with the Mac's own reason: otherwise every map
  ends the game with the same "missing file" error, and the reason is
  only in the console.
- `src/ui/ui_main.c`: on the Mac the game keeps its log, `etconsole.log`
  (`logfile 2`, written line by line, so a crash does not lose the end),
  unless the player has set `logfile` themselves. When the menus next
  start after a crash or a fatal error, the end of that log is said: the
  line naming the crash or error, and the last lines before it. A crash
  on the Mac quits with nothing said and no crash log, so this is the
  only way the player hears why. The old log is kept as
  `etconsole-last.log`.

## 0006: let the server start on the Mac, and say why when it will not

No Quarter checks, as its server starts, that it runs on a game it
supports, in a folder called `nq`. Both checks stopped it on a Mac:

- ET: Legacy on the Mac calls itself `ET 2.60d OSX-universal`, the last
  Mac version of the original game. No Quarter accepts 2.60d on a Mac,
  but only under `__MACOS__`, which only the old PowerPC compilers
  defined; today's Mac compilers define `__APPLE__`, so it asked for the
  Windows and Linux 2.60b and refused. `src/game/g_main.c` now takes
  2.60d under either.
- When a check failed, No Quarter called `exit()`. On a game the player
  hosts, the server runs inside the player's own game, so that ended the
  game outright, window and all, with the reason only in the console.
  It is now an error: the server stops, the player is back at the menus,
  and the error popup says why, in a sentence per failed check - the
  game version, or the folder's name.

The folder must still be called `nq`: players joining a No Quarter
server look for its files there.

## 0007: get around

The ET: Legacy mode's getting around, carried across whole rather than
written again: three new files in `src/cgame/`, built only with
`FEATURE_ACCESSIBILITY`, from that mode's cgame as its patches through
0120 leave it.

- `cg_accessibility_world.c`, from its `cg_draw.c`, `cg_spawn.c` and
  `cg_event.c`: what is ahead and underfoot, drops, water and stairs,
  the facing and the look up and down, the place and its kind, the
  openings passed, the footing; the doors, flags, construction and
  dynamite sites, ladders, pickups and mines heard where they are, and
  the bump of walking into something; the furniture named from the map
  file; what is around (F9); the things to use and aim at, and the
  stairs; the crosshair cue; the stuck report with the way to go.
- `cg_accessibility_map.c`, from its `cg_commandmap.c`: the command map
  walked square by square while it is open, and the marker - placed on a
  square, the objective, a room, a sniper spot or the way out of a
  building - with its sound and the way to it, round walls and up
  ladders.
- `cg_accessibility_keys.c`, from its `cg_consolecmds.c`: a tap on a turn
  key stepping to the next compass point, the use key turning to the
  thing first and climbing ladders, the enemy lock (only on a game the
  player hosts, or a server that sets `eta_aimAssist`), choosing what F
  turns to, taking a uniform, and the map's keys while it is open.

The parts No Quarter already had from 0004 - the weapon, stance, scope,
lean, play state, deaths, the console, objectives finished, the building
count, pickups - were left out of the copy, and the copy calls 0004's.

Where No Quarter differs:

- **Objectives.** 0004's helpers are exported under the names the copy
  uses. No Quarter's objective info has no `objflags`, so no objective's
  number in the map's list leads to its place on the map, and
  `CG_AccessibilityObjectiveByNumber` always says so; its callers fall
  back to the nearest, as 0004 does. `CG_AccessibilityObjectiveList`
  walks both of No Quarter's command map lists.
- **The command map.** Its lists are static to `cg_commandmap.c`, so it
  hands out both as one (`CG_AccessibilityMapEntity`). There is no
  `ME_PLAYER_OBJECTIVE` and no landmine filter. A disguise is judged at
  512 units, as the stock command map draws it.
- **Skills.** No Quarter keeps them as bits: a disguise is seen through
  at Signals bit 4, by a field op or where the server keeps the award,
  and a mine close by at Battle Sense bit 4. A disguise's name is
  `disguiseName`.
- **The crosshair** is `crosshairClientNum`, current for a second, as
  `CG_DrawCrosshairNames` holds it.
- **The map key** (`+mapexpand`) is a switch while `eta_mapToggle` is on,
  and while the map is up the keys are its own (`CG_KeyEvent`).
- **The look keys.** No Quarter removed `+lookup` and `+lookdown` for
  anti-recoil scripts; they are kept, being the only way to tip the view
  without a mouse.
- **Doors and flags** are read from the map's entity list by
  `cg_spawn.c`'s spawn table, and a `misc_gamemodel`'s model file is kept
  as it spawns, for naming the furniture. The ladders and the props are
  read from the map file as it loads (`cg_main.c`).
- **The grid**: `BG_GetLocationGrid` in `bg_misc.c` gives the survey
  the grid `BG_GetLocationString` reads squares off.
- Cursor hints ET: Legacy has and No Quarter does not are given values
  no hint takes; `MIN`, `MAX` and `CH_BREAKABLE_DIST` are defined where
  missing.

`src/cgame/cg_accessibility.c` gains the settings and the looping sounds,
which `release/make-cue-sounds.py` generates into the pk3, as for the
ET: Legacy mode. The menus offer the keys as a third generation of
binds, on the ET: Legacy mode's keys.

The accessibility options pages and the announcer's volume came in
0010.

## 0008: the Tesla gun and the Snooper, from RTCW

The engine allows 64 weapons and No Quarter has 63, so there was room for
one: `WP_TESLA`, the 64th. Soldiers on both teams carry it after the
Venom. `Weapon_TeslaFire` (`g_weapon.c`) hits the nearest enemies in
front of the gun, up to three, each in sight and within 600 units, every
50 ms the trigger is held; it overheats, reloads and gains skill like the
Venom, and kills as `MOD_TESLA`. Every table sized by the weapon, means
of death or weapon-stat enum gains its row.

- **Its item** is last in `bg_itemlist`, past the team items, so every
  other item keeps the index a stock No Quarter server sends;
  `BG_WeaponItem` finds it for the weapon lookups, and it has no ammo
  item to drop.
- **Only where the server has it.** The server says so with the
  `eta_tesla` serverinfo key; `BG_OfferTesla` takes it off the soldier's
  list everywhere else. The Windows download keeps No Quarter's own
  server module, so it offers the Tesla only on a server built with the
  mode, as the Mac's is.
- **Its weapon file**, `weapons/tesla.weap` in the pk3, comes from
  `release/noquarter/weapons/`. It uses the Venom's models and animations
  (the animation scripts treat the Tesla as the Venom), and a crackle
  `release/make-noquarter-sounds.py` synthesises, looping while it fires,
  first person included.
- **RTCW's own Tesla**, its models, icons, shader and zap, comes only
  from `release/make-rtcw-sounds.py` and the player's own RTCW. That
  pack, `zzzz_rtcw.pk3`, sorts after the mode's pk3 and carries its own
  copy of the weapon file pointing at them.

**The Snooper** needs no slot: it takes the place of the Allied covert
ops' M1 Garand. `WP_GARAND` and its scope, `WP_GARAND_SCOPE`, are both
named the Snooper, and their kills say so (the engineer's Garand,
`WP_CARBINE`, keeps its name). The RTCW pack gives it the Snooper's
shot, and, with a copy of No Quarter's `m1_garand_s.weap` whose game
values are unchanged (`release/noquarter/rtcw/`), RTCW's Garand models
and icons.

## 0009: the stats, the top shots and the end of the match

- **Stats and top shots.** `+stats` and `+topshots` ask the server, and
  the answers (`CG_parseWeaponStatsGS_cmd`, `CG_topshotsParse_cmd`) are
  said as reports - totals, rank and XP, then each weapon used; or each
  weapon's best player - when they answer a key just pressed, as the
  scoreboard is. No Quarter sends hit regions and sprees rather than
  ET: Legacy's accuracy line, so those are said instead.
- **The debriefing** (`cg_debriefing.c`) is spoken page by page:
  `CG_AccessibilityDebriefingKey` takes Page Up and Down, the arrows,
  Enter, Home and End before the chat box does, and Enter only while the
  chat is empty. The map vote sends the same `mapvote` commands as its
  buttons, one choice per Enter where the server takes three. A page is
  said again when it changes by the mouse, when the map list arrives,
  and when the chosen player's weapon stats arrive.

## 0010: the accessibility pages, hosting and the announcer's volume

- **The pages.** `release/noquarter/ui` holds No Quarter's copies of the
  ET: Legacy mode's pages, written with ET 2.60's macros, and
  `eta_menudef.h` with the layout macros No Quarter's `menudef.h` lacks.
  `UI_LoadMenus` parses them after `ui/menus.txt`, so No Quarter's list
  is not copied; No Quarter's `options.menu` is (`options.menu.stock`
  beside it), with ACCESSIBILITY above BACK. No update check: No Quarter
  builds have none.
- **Hosting.** `eta_hostPlain`, `eta_hostBotCount`, `eta_hostBotSkill`
  as in the ET: Legacy mode, applied on Start Server: Omni-bot on, its
  path set to the download's `nq/omni-bot` where unset (not on a Mac,
  whose loader looks in its own places), and the count queued behind the
  map; changed during a hosted match, sent at once. And
  `eta_hostMapVote`, which No Quarter's Host Game screen does not offer:
  the game type becomes map voting.
- **The announcer's volume** (`eta_announcerVolume`) applies to the
  map's voice, buffered sound scripts and global sounds, as in the
  ET: Legacy mode: below full, a streamed line is played as an ordinary
  sound, which takes a volume.

## 0011: voice chats' own volume, and the Snooper on the ground

- `eta_voiceVolume`, as in the ET: Legacy mode's patch 0121: below 100,
  `CG_PlayVoiceChat` plays the voice from the player's own head at that
  share of full, instead of as a local sound, which takes no volume.
- A weapon lying on the ground is named by its weapon name, not its
  item's pickup name, so the covert ops' rifle is the Snooper there too.
  The pickup names stay: the animation scripts know weapons by them.


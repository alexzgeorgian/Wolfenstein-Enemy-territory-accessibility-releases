# ET: Legacy integration: menu, HUD, audio cue, and navigation narration

This wires the menu narrator (`src/accessibility/menu/menu_narrator.c`),
HUD narrator (`src/accessibility/hud/hud_narrator.c`), audio cue system
(`src/accessibility/audio/audio_cue_system.c`), and navigation system
(`src/accessibility/navigation/navigation_system.c`) into the real
ET: Legacy engine, behind a new opt-in `FEATURE_ACCESSIBILITY` CMake
option. It is kept as patches here rather than applied directly to
`etlegacy/etlegacy`, because this repository has no push access to that
project and the engine is meant to stay upstream (see
`docs/SOURCE_CODE_PLAN.md`).

Base commit: [`etlegacy/etlegacy@626020f`](https://github.com/etlegacy/etlegacy/commit/626020f38bab1bf2c9ac5b6c66bfaf921b4a4d78)
(`v2.86.1`). The pin follows what ET: Legacy's website actually hands
out, not the newest tag — those were the same thing when this project
started, diverged when 2.86.0 was tagged before it was published (which
cost a release), and were the same again once 2.86.0 was the download.
The tester has 2.86.1, the download now, so the series is on it.
Accessibility-mode pinned at commit `229ba0e` of this repo —
patches 0002-0013 don't need a newer pin, since they only call
`ETA_MenuNarrator_OnValueChanged` / `OnConfirmDialogShown` /
`ETA_HudNarrator_Speak*` / `ETA_AudioCueSystem_Play*` /
`ETA_NavigationSystem_*`, all of which already existed at that commit.

Apply the patches in order; each depends on the ones before it.

## 0001: menu focus narration

- Adds `option(FEATURE_ACCESSIBILITY ... OFF)` next to the other `(mod)`
  feature flags in the top-level `CMakeLists.txt`. Off by default, so
  existing builds are unaffected.
- In `cmake/ETLSetupFeatures.cmake`, when the feature is on: pulls this
  repository in as a CMake subdirectory and links the resulting
  `eta_accessibility` static library into `mod_libraries`, the interface
  target both the `cgame` and `ui` module targets link against. That's a
  single point of wiring because `src/ui/ui_menu.c` /
  `src/ui/ui_menuitem.c` are compiled into both modules
  (`UI_SHARED` is appended to `CGAME_SRC` in `cmake/ETLSources.cmake`).
- In `src/ui/ui_menuitem.c`, calls
  `ETA_MenuNarrator_OnFocusChanged(menuName, itemText)` from inside
  `Item_SetFocus`, right before its `return qtrue;`, guarded on
  `item->window.flags & WINDOW_HASFOCUS`. `Item_SetFocus` already
  short-circuits at its top if the item already has focus, so this fires
  exactly once per genuine focus transition — not on every mouse-move
  tick — and it's reached by both mouse hover and the keyboard-driven
  `Menu_SetPrevCursorItem` / `Menu_SetNextCursorItem` (Tab navigation),
  which covers the project's keyboard-only navigation goal.

This satisfies Milestone 2's exit condition ("a blind player can hear
which menu item is selected") for real engine menus, not just the
standalone smoke test.

## 0002: setting value narration

Hooks `Item_HandleKey` in `src/ui/ui_menuitem.c` — the single dispatcher
`Menu_HandleKey` calls with the currently focused item on every keypress
(`src/ui/ui_menu.c:1230`), which routes to per-type handlers
(`Item_CheckBox_HandleKey`, `Item_YesNo_HandleKey`, `Item_Multi_HandleKey`,
`Item_Slider_HandleKey`). Each of those only reacts to `K_ENTER` or a mouse
button, so this is reachable without a mouse: focus a setting via Tab, then
press Enter to cycle it.

For each type, after the handler reports `qtrue` (value changed), narrates
via `ETA_MenuNarrator_OnValueChanged(item->text, ...)`:

- `ITEM_TYPE_CHECKBOX` → `"On"` / `"Off"` from the cvar's value.
  `ITEM_TYPE_TRICHECKBOX` is deliberately left alone — its cvar is
  three-valued (0/1/2) with no generic label, so it's not narrated here to
  avoid announcing something misleading.
- `ITEM_TYPE_YESNO` → `"Yes"` / `"No"`.
- `ITEM_TYPE_MULTI` → `Item_Multi_Setting(item)`, the engine's own helper
  for a multi-choice item's current display label (e.g. `"Medium"`), not
  the raw cvar value.
- `ITEM_TYPE_SLIDER` → the cvar's current value formatted with `va("%.2f",
  ...)`, the engine's own `printf`-style scratch-buffer helper (already
  used elsewhere in this same file), matching project convention instead
  of introducing a local buffer.

This covers Milestone 3's setting-value-narration deliverable for the two
most common engine widget types (toggles and multi-choice/slider
settings).

## 0003: confirmation dialog narration

Hooks `Menus_ActivateByName` in `src/ui/ui_menu.c` — the function every
popup/confirm dialog actually opens through. `Menus_OpenByName` (what a
`.menu` script's `open <name>` command calls) is a thin wrapper around it,
and it's the only active caller of the lower-level `Menus_Activate`
(`Menus_ShowByName`, the other wrapper, is dead code — its own doc comment
says `@note Unused`).

Right after a menu is activated, if it has `WINDOW_POPUP` set, walks its
`items[]` and narrates every `ITEM_TYPE_TEXT` item that has literal text,
joined with spaces, via `ETA_MenuNarrator_OnConfirmDialogShown`. This
relies on a real, verified convention rather than a guess: every popup
shipped in `etmain/ui/*.menu` builds its title and body text with the
`SUBWINDOW`/`SUBWINDOWBLACK`/`LABEL`/`LABELWHITE` macros
(`etmain/ui/menumacros.h`), and all four of them always emit an
`ITEM_TYPE_TEXT` item with `decoration` set and a literal `text` string -
confirmed by reading the macro definitions and a real dialog
(`etmain/ui/ingame_disconnect.menu`, a "Do you want to disconnect from the
server?" Yes/No confirm), not assumed. For that dialog this produces
`"DISCONNECT Do you want to disconnect from the server?"` - the title
plus both body lines. A hand-rolled popup that skips those macros and sets
`item->text` some other way (e.g. `popup_errormessage.menu`'s error label,
which is cvar-bound rather than literal `text`) won't be picked up; see
follow-ups.

This satisfies Milestone 3's remaining deliverable ("confirmation dialog
narration") and the Menu Narrator's "confirmation narration"
responsibility from `docs/ACCESSIBILITY_ARCHITECTURE.md`.

## 0004: HUD status narration

Milestone 4's deliverables (health/ammo/weapon/objective/respawn speech)
aren't uniform: health and ammo change many times a second during combat,
so narrating every change automatically would be noise, not accessibility
- unlike a menu value, which only changes on a deliberate keypress. This
patch splits the two kinds of HUD state it actually implements accordingly:

- **On-demand status query** (`src/cgame/cg_consolecmds.c`): a new
  `accessibilityStatus` console command (bindable to a key, same pattern as
  the existing `+objectives`/`+scores`/etc. commands in the same file's
  `commands[]` table) that narrates health, the current weapon, and its
  ammo in one report when the player asks for it - matching Milestone 4's
  exit condition literally ("a blind player can query basic match state").
  Reads `cg.snap->ps.stats[STAT_HEALTH]` and the engine's own
  `CG_PlayerAmmoValue()` / `GetWeaponTableData(weap)->desc` helpers rather
  than re-deriving ammo/weapon-name logic - `desc` is confirmed (not
  assumed) to be the real display name by checking where it's already used
  for the on-screen weapon panel text and spawn centerprints in
  `cg_limbopanel.c`.
- **Automatic weapon-change narration** (`src/cgame/cg_playerstate.c`): in
  `CG_TransitionPlayerState`, reuses the engine's own existing
  `ps->weapon != ops->weapon` check (already there to reset smoke
  generation) to narrate the new weapon whenever it actually changes.
  This function's own file-level doc comment says it's "done after local
  prediction" in normal play and "when the snapshot transitions" during
  demo playback/follow mode, and it's the same function `CG_CheckLocalSounds`
  already uses this exact ps/ops-diffing pattern in for pain sounds - so
  this hook has the same firing characteristics as an existing, shipped
  engine feature, not a new one.

Deliberately not covered by this patch: automatic health/ammo narration
(would spam during combat - covered by the on-demand query instead),
objective status (added in 0006), and respawn-timer narration (added in
0007). See follow-ups.

## 0005: audio cues

Wires two of the audio cue system's five cues into `src/cgame/cg_playerstate.c`,
reusing existing engine change-detection rather than adding new polling:

- **Damage direction** - in `CG_DamageFeedback`, right after
  `cg.v_dmg_angle = angles[YAW]`. That `angles[YAW]` is already the damage
  bearing relative to the player's view (0 = front, 90 = right, 180 =
  behind, 270 = left), computed by the engine's own `vectoangles`
  (`vec3_to_angles`, `src/qcommon/q_math.c`) from the same
  view-relative `dir` vector the existing screen-kick effect uses - this
  patch reuses that already-computed value for
  `ETA_AudioCueSystem_PlayDamageDirectionCue` instead of re-deriving the
  direction, only wrapping it into `[0, 359]` for the accessibility
  layer's range guard. `CG_DamageFeedback` is only ever called from one
  place, gated on `ps->damageEvent != ops->damageEvent && ps->damageCount`
  - an existing one-shot-per-damage-event check, so this fires once per
  hit, not every frame. The `yawByte == 255 && pitchByte == 255` case
  (omnidirectional damage - falling, etc.) is deliberately left alone:
  there's no real direction to report there.
- **Low health** - in `CG_CheckLocalSounds`, alongside the existing pain
  sound trigger (`ps->stats[STAT_HEALTH] < ops->stats[STAT_HEALTH] - 1`),
  added an extra `<= 25` condition so the cue only fires while critically
  low, not on every routine chip of damage.

Deliberately not covered: the remaining three cues (objective, interaction,
objective direction). The interaction cue's natural hook,
`CG_CheckForCursorHints` in `cg_draw.c`, is a per-frame trace whose own doc
comment says `@note Concept in progress...`, and no clear "hint cleared"
reset was found in `cg_draw.c` for `cg.cursorHintIcon` - wiring it
correctly would need edge-detection against state whose exact lifecycle
isn't nailed down yet, so it's left as a follow-up rather than guessed at.
The objective and objective-direction cues depended on finding a real
objective-name/position source, which 0006 below does find - see its
follow-up note for why the cues themselves still aren't wired.

## 0006: objective status narration

Adds `CG_MainObjectiveNameForTeam(team_t team)` to
`src/cgame/cg_consolecmds.c` and calls it from `CG_AccessibilityStatus_f`
(the on-demand status command 0004 added), narrating the player's team's
current main objective alongside health/weapon/ammo.

0004 had left objective status open because `+objectives`/`-objectives`
turned out to only toggle a panel's *visibility*, not hold its text. This
patch traces further to the actual source: `cg_draw_hud.c`'s
`ET_EXPLOSIVE_INDICATOR` / `ET_CONSTRUCTIBLE_INDICATOR` icon-drawing code
already resolves a team's current main objective, by reading the
objective's entity number out of the `CS_MAIN_AXIS_OBJECTIVE` /
`CS_MAIN_ALLIES_OBJECTIVE` configstrings and matching it against
`cgs.oidInfo[]` (an array of objective entities parsed from configstrings
in `cg_servercmds.c`, each with a `name` field). `CG_MainObjectiveNameForTeam`
does the same two-step lookup as a standalone function instead of only
inline inside that drawing code, so `CG_AccessibilityStatus_f` can call it
directly without needing a drawn map icon/entity in hand.

This completes Milestone 4's HUD deliverables started in 0004 (health,
weapon, ammo, and now objective status), leaving only respawn-timer
narration open at this point - see 0007.

## 0007: respawn timer narration

Hooks `CG_DrawRespawnTimer` in `src/cgame/cg_draw_hud.c` - the HUD
component's own paint callback (registered in the `commands[]`-style HUD
component table alongside health/ammo/etc.). Its `s` string is exactly
what's already drawn on screen for the reinforcement countdown -
`CG_SpawnTimersText` computes it, ultimately from `CG_GetReinfTime(qfalse)`
(`cg_draw.c`), the seconds until the local player's team's next
reinforcement wave. This patch parses that same `s` (guarded the same way
the component's own existing `reinforceWarning` color logic already does:
`cgs.gamestate == GS_PLAYING && Q_isanumber(s)`) and narrates it via
`ETA_HudNarrator_SpeakRespawn`, so what's spoken always matches what's on
screen instead of a separately re-derived value.

Unlike every other engine event this integration hooks so far,
`CG_TransitionPlayerState`'s ps/ops diffing doesn't apply here - the
countdown isn't driven by a discrete state transition, it's a live clock
recomputed fresh every frame from elapsed time. So this patch adds its own
edge detection: a `static int lastNarratedSeconds` local to the function,
narrating only when the integer actually changes, so "5 seconds" doesn't
get spoken repeatedly for the ~60 frames it's on screen.

This completes all five of Milestone 4's original deliverables (health,
ammo, weapon, objective, respawn) with a real engine hook.

## 0008: tri-checkbox setting narration

0002 deliberately skipped `ITEM_TYPE_TRICHECKBOX` because its cvar is
three-valued with, it assumed, "no generic label" to narrate for the
third state. Checking the real engine source (both this base commit and
the original id Software GPL release, which already has the same
`ITEM_TYPE_TRICHECKBOX` type and 0/1/2 `Item_CheckBox_HandleKey` cycling
logic) shows that assumption was wrong: every shipped tri-checkbox
(`etmain/ui/playonline.menu`'s nine server-browser filters, all built via
the `TRICHECKBOXACTIONMULTI` macro in `menumacros.h`) already carries a
`cvarFloatList` mapping each of the three values to a label string, e.g.
`cvarFloatList { "Filter Disabled" 0 "Empty only..." 1 "Not empty..." 2 }`
- the exact same mechanism `ITEM_TYPE_MULTI` uses. `Item_CheckBox_Paint`
already calls `Item_Multi_Setting(item)` to draw a tri-checkbox's on-screen
label from that list (`src/ui/ui_menuitem.c`), so the label this patch
narrates is never invented - it's the same string already on screen.

This patch gives `ITEM_TYPE_TRICHECKBOX` its own case in `Item_HandleKey`,
mirroring 0002's `ITEM_TYPE_MULTI` case exactly: after
`Item_CheckBox_HandleKey` reports a change, narrates via
`ETA_MenuNarrator_OnValueChanged(item->text, Item_Multi_Setting(item))`.
`Item_Multi_Setting` itself already handles the case this patch doesn't
touch - a bare `TRICHECKBOXACTION` with no `cvarFloatList` (unused in any
shipped menu, but supported by the macro set) - by falling back to its
existing translated `"None Defined"` string, the same fallback `MULTI`
items without a list get.

This closes the "Tri-checkbox narration" follow-up from the original
patch set.

## 0009: non-macro (cvar-bound) popup narration

0003 deliberately left a gap: its heuristic in `ETA_NarrateConfirmDialog`
only read `ITEM_TYPE_TEXT` items with literal `item->text`, and noted that
a popup whose message comes from a cvar-bound label instead wouldn't be
narrated. Checking `etmain/ui` directly shows this isn't a hypothetical -
every shipped popup with a dynamic message body (`popup_errormessage.menu`,
`popup_errormessage_pb.menu`, `popup_hostgameerrormessage.menu`,
`popup_serverredirect.menu`'s `com_errorMessage`; `popup_autoupdate.menu`'s
`com_updatemessage`; `popup_addfavorite.menu` / `popup_removefavorite.menu`'s
`cl_currentServerIP`; `profile_create_error.menu`'s
`ui_profile_create_error`) uses the `CVARLABEL` macro
(`etmain/ui/menumacros.h`) for it, not a literal `LABEL`/`LABELWHITE`. Every
one of these is exactly the case 0003 flagged as unhandled - so the gap
covered the majority of the engine's actual error/status popups, not an
edge case.

`CVARLABEL` still emits `type ITEM_TYPE_TEXT`, but with no `text` and a
`cvar` set instead; `Item_Text_Paint` (`src/ui/ui_menuitem.c`) already
resolves that at paint time via `DC->getCVarString(item->cvar, ...)`. This
patch makes `ETA_NarrateConfirmDialog` do the same: for each
`ITEM_TYPE_TEXT` item, if `item->text` is unset and `item->cvar` is set, it
reads the cvar's current string the same way `Item_Text_Paint` does, so
what's narrated always matches what's painted. (No shipped popup pairs
`CVARLABEL` with the `WINDOW_TEXTASINT`/`WINDOW_TEXTASFLOAT` display flags
`Item_Text_Paint` also supports - those only appear on `CVARFLOATLABEL`
items in non-popup options screens - so this patch doesn't replicate that
transform; see follow-ups if that combination is ever used in a popup.)

This closes the "Non-macro popups" follow-up from the original patch set.

## 0010: interaction hint audio cue

The audio cue system has five cues; 0005 wired two (damage direction, low
health) and left the interaction cue as a follow-up because
`CG_CheckForCursorHints`'s own doc comment says `@note Concept in
progress...` and, per that follow-up note, "no clear 'hint cleared' reset
was found in `cg_draw.c` for `cg.cursorHintIcon`."

That's true as far as it goes - `CG_CheckForCursorHints` (`cg_draw.c`) only
ever *sets* `cg.cursorHintIcon`/`cg.cursorHintTime`/`cg.cursorHintFade`
when a hint condition (server-dictated hint, water, ladder, a knife
backstab opportunity) is newly true; it never resets `cg.cursorHintIcon`
back to `HINT_NONE`. But the reset the follow-up was looking for turns out
to live in a different file: `CG_DrawCursorhint` (`src/cgame/cg_newDraw.c`,
the component that actually paints the hint icon) treats a hint as
currently visible purely from a timing window - `cg.cursorHintTime &&
cg.cursorHintFade > 0 && (cg.time - cg.cursorHintTime) < cg.cursorHintFade`
- gating its own draw call on exactly that check, never on the icon value
itself. So `cg.cursorHintIcon` is deliberately allowed to go stale once the
window closes; the window, not the icon, is the real "is a hint showing"
state, and it's the same state the icon's on-screen visibility already
depends on.

This patch adds `ETA_NarrateInteractionHint` (`cg_draw.c`), called once per
frame right after the existing `CG_CheckForCursorHints()` call in
`CG_Draw2D`. It reuses that exact timing-window formula to track whether a
hint is currently active, with two `static` locals (`wasActive`, `lastIcon`)
for edge detection, and narrates via `ETA_AudioCueSystem_PlayInteractionCue()`
only on a real transition: the window opening (`!wasActive`) or the icon
changing while the window stays open (e.g. sliding the crosshair from a
door onto an MG42 without a gap) - never on every frame a hint stays up.
`HINT_COMPLETED` is explicitly excluded from counting as a new icon,
because `CG_DrawCursorhint`'s own switch comment says it deliberately
"keep[s] the last used hint icon shader" rather than indicating anything
new was found.

This closes the "Interaction cue" follow-up from the original patch set.

## 0011: objective and objective-direction audio cues

The last two of the audio cue system's five cues. 0006 had already found
the real objective source - `CG_MainObjectiveForTeam` (renamed from 0006's
`CG_MainObjectiveNameForTeam` by this patch; see below), the
`CS_MAIN_AXIS_OBJECTIVE` / `CS_MAIN_ALLIES_OBJECTIVE` + `cgs.oidInfo[]`
lookup also behind the on-screen objective icons - but left the cues
themselves unwired, needing "a per-frame or on-demand 'is the objective
newly relevant' trigger decided first," since firing on every
`/accessibilityStatus` call wouldn't fit the other cues' "ambient event"
role.

This patch defines "newly relevant" the same way 0004 already defined
"changed" for the weapon cue and 0007 for the respawn timer: a real
state transition, not a threshold or a guess. `cgs.oidInfo[]` entries
carry an `entityNum`, and the server reassigns which entity is a team's
*main* objective (via `CS_MAIN_AXIS_OBJECTIVE`/`CS_MAIN_ALLIES_OBJECTIVE`)
exactly when the old one is destroyed/captured and a new one takes its
place - so "the main objective entity number for my team changed" is an
unambiguous, already-server-driven event, not an invented one.

`ETA_NarrateObjectiveChange` (`cg_playerstate.c`) is called once per
`CG_TransitionPlayerState` (the same effectively-every-frame hook 0004's
weapon narration and 0005's audio cues already use), and narrates via
`ETA_AudioCueSystem_PlayObjectiveCue()` + `PlayObjectiveDirectionCue()`
only when the player's current team's main objective entity number
differs from what was last narrated (tracked with two `static` locals),
including the transition of joining/switching to a playing team and
picking up its objective for the first time. Switching to spectator (or
having no resolvable objective yet) resets the tracked state without
narrating, so returning to a team re-announces its objective rather than
staying silent on a stale match.

The direction math mirrors 0005's damage-direction cue exactly in
convention (0 = front, 90 = right, 180 = behind, 270 = left), but not in
source data: where 0005 reused an already-view-relative angle computed by
the game code, no equivalent exists for the objective, so this patch
computes one - `objective->origin` minus the player's own `ps->origin`,
through the engine's own `vec3_to_angles`, then made relative to
`ps->viewangles[YAW]` and wrapped with the engine's own `AngleNormalize360`
(`angle_norm_360`, `q_math.c`) rather than a hand-rolled clamp.

**The operand order was initially wrong**, which mirrored the cue: it
computed target yaw minus view yaw, which places a target on the
player's right at 270, not the 90 the convention above requires. It is
now view yaw minus target yaw. The convention itself is not a guess -
`cg_draw.c`'s own damage-indicator code brackets `cg.v_dmg_angle` as
`>= 60 && < 120` for "right" and `>= 240 && < 300` for "left", in its
own comments. Confirmed by compiling the expression against the
engine's `q_math.c` with a target at a known bearing.

Because the ambient cue and the on-demand `/accessibilityStatus` command
(0006) now need the same objective lookup with different amounts of
information (the command only ever needed the name; the cue also needs
`entityNum` and `origin`), 0006's `static const char
*CG_MainObjectiveNameForTeam(team_t)` is generalized in this patch into a
non-static `oidInfo_t *CG_MainObjectiveForTeam(team_t)` returning the
whole matched entry, declared in `cg_local.h` for cross-file use, with
`CG_AccessibilityStatus_f` updated to read `->name` from it - one lookup,
not two copies of the same loop.

This closes the "Objective and objective-direction audio cues" follow-up
from the original patch set - the accessibility audio cue system now has
all five of its cues wired to real engine hooks.

## 0012: stuck detection (Milestone 6)

The first of Milestone 6 ("Navigation Prototype")'s three deliverables not
already covered by 0011's objective-direction cue. The standalone
`ETA_NavigationSystem_UpdateMovement(distanceMovedMeters, elapsedSeconds)`
(`src/accessibility/navigation/navigation_system.c`) already implements the
whole "have I been effectively stationary for 3 seconds" state machine and
narrates "You may be stuck" itself once tripped - it just needed real
per-frame movement fed into it.

`ETA_NarrateStuckDetection` (`cg_playerstate.c`) does that from the same
`CG_TransitionPlayerState` hook 0004's weapon narration and 0011's
objective-change narration already use, computing real movement as
`Distance(ps->origin, ops->origin)` and real elapsed time as
`cg.frametime` (an existing `cg.time - cg.oldTime` field already used
throughout `cg_draw.c`/`cg_effects.c` for exactly this purpose) - both
already-computed values, not new polling. It only runs while
`ps->pm_type == PM_NORMAL` and the player is on a playing team (the same
gate `ETA_NarrateObjectiveChange` uses); outside that gate stuck detection
is reset instead, so time spent dead, spectating, or in limbo can't itself
be mistaken for standing still, and `CG_Respawn` (the engine's own existing
respawn hook) resets it directly too, so a fresh life never inherits a
stale timer.

Distance moved is converted from Quake units to the meters
`UpdateMovement` expects via `ETA_QU_TO_METERS` (new in `cg_local.h`, used
by 0013 as well): **id Tech 3's commonly cited external convention of 1
Quake unit = 1 inch. Neither this engine nor the original id Software GPL
release states a units-per-meter constant anywhere searchable in either
codebase, so this is not a value verified against real engine source the
way the rest of this integration's claims are** - it's the best available
external convention, applied consistently, and called out here rather than
presented as engine-verified fact.

## 0013: distance feedback and route correction (Milestone 6)

The remaining two Milestone 6 deliverables. Both are added to the existing
on-demand `/accessibilityStatus` command (0006) rather than narrated
ambiently: like health/ammo, a walking player's live distance and bearing
to the objective change continuously, so - consistent with 0006's own
reasoning for why status query is a query and not a stream - an ambient
version would need an invented announcement interval or hysteresis this
codebase gives no basis for, where a query-on-demand doesn't.

**Distance**: `ETA_NavigationSystem_AnnounceDistance` gets
`Distance(ps->origin, objective->origin) * ETA_QU_TO_METERS` - the same
conversion 0012 introduced, and the same objective lookup 0011 already
generalized.

**Route correction**: computes the same objective bearing
`ETA_NarrateObjectiveChange` (0011, `cg_playerstate.c`) already computes
for the objective-direction audio cue, but through `AngleSubtract` instead
of `AngleNormalize360` - the exact same helper `cg_commandmap.c`'s
`CG_DrawCompassIcon` already uses to place a compass icon relative to view
yaw, reused here rather than reinvented - since `AngleSubtract`'s signed
`[-180, 180]` result reads naturally as "turn left" / "turn right"
spoken text, instead of the 0-cue's 0-359 clock position. Within ±15
degrees narrates "Objective is ahead" instead.

**The sign of that result was initially read backwards**, so the patch
said "turn left" when the objective was on the player's right. In id
Tech 3 yaw increases counter-clockwise, so a target to the player's
right sits at a *lower* yaw than the view: `AngleSubtract(targetYaw,
viewYaw)` is **negative** on the right and positive on the left. The
patch now narrates "turn left" on a positive result. Verified by
compiling the expression against the engine's own `q_math.c` and
feeding it a target at a known bearing, not by reading the sign off
the page - see the same correction in the id Software series' 0009.

**That ±15 degree band is a judgment call, not a verified value** - unlike
0012's unit conversion, there isn't even an established external
convention to point to here; no comparable on-course tolerance exists
anywhere else in this engine to measure it against. It's a reasonable
starting point, flagged as one, not a discovered fact - see follow-ups.

This closes Milestone 6's three remaining deliverables (0011 had already
covered the objective-direction cue); all of Milestone 6 ("A blind player
can begin moving toward objectives intentionally") is now wired to real
engine hooks.

## 0014: runtime init, and cues through the engine

The patch that made the mod audible. Patches 0001-0013 placed
twenty-one narration calls and not one initialiser, and both speech
backends return immediately before their Init runs - `gVoice` is null
until `CoCreateInstance`, `gSpeakText` is null until the NVDA controller
client is loaded. Every call ran, passed its guards, and was discarded.
That is what made alpha-0.1.0 mute.

0014 brings the runtime up in `cgame` and `ui` separately, because the
two modules link their own copies of the library, and takes it down on
shutdown.

The same patch moves the audio cues off `PlaySoundW` and onto the
engine: flat cues through `trap_S_StartLocalSound`, directional ones
placed in the world for `trap_S_StartSound` so the engine spatialises
them like any other sound. The previous tones ignored the player's
volume, competed for the audio device, and faked direction with a
stereo balance. Each cue sound is an archived cvar, changeable without
a restart.

The world-placement maths is the same one that shipped mirrored twice,
so `tests/bearing_regression_test.py` now lifts it out of the patched
tree too and checks a cue for a given bearing lands on that side of the
listener.

## 0015: repeat and stop-speech commands

`ETA_MenuNarrator_RepeatCurrentItem` and `ETA_Speech_Stop` had been in
the library from the start with nothing registering a console command
for either, so no key could be bound to them. The functions existed and
could not be called.

Registering them is not two rows in a table, because the engine picks
who answers a console command and picks in an order a mod cannot
change. `Cmd_ExecuteString` (`qcommon/cmd.c`) offers every command to
cgame before ui, and `CG_ConsoleCommand` returns `qtrue` for any name in
its table - so once a snapshot exists, cgame answers first and ui never
sees it. Repeat is exactly where that is wrong: with the options menu
open mid-match, the player wants the focused menu item, not their
health.

So `cg_consolecmds.c` registers `accessibilityRepeat` and
`accessibilityStopSpeech`, and each first offers the request to ui under
a *different* name (`accessibilityRepeatMenuItem`,
`accessibilityStopSpeechMenu`) that cgame does not itself register. A
forwarded name cgame also claimed would loop inside the engine with no
output; `tests/command_wiring_test.py` guards that specific hazard.
`ui_atoms.c` registers all four names, so the menu path works whether
the request arrives directly or forwarded.

## 0016: limbo panel keyboard navigation

The first patch written in answer to an in-game report rather than a
source reading. A tester got through the menus and then could not enter
a match at all: the limbo panel (**L**), where team and class are
chosen, has no keyboard traversal whatsoever.

Narration alone would not have helped, because the panel has no notion
of a focused item to narrate. It is mouse-driven end to end: every
control is hit-tested against the cursor (`BG_CursorInRect` reads
`DC->cursorx` / `cursory`), and `BG_PanelButtonsKeyEvent` only delivers
a key to a button that a click already focused. With no cursor aimed at
a button, no key reaches anything.

So 0016 adds the traversal the panel never had. Up / Down / Tab walk a
list of stops, Enter presses one. Rather than synthesising button
presses, it moves the real cursor to the centre of the current
control's rect and then calls that control's own `onKeyDown` with
`K_MOUSE1` - the exact path a mouse click takes. Nothing here duplicates
or second-guesses the panel's logic; it only drives it from the
keyboard, so a selection made this way is indistinguishable from a
clicked one.

The stop list is deliberately short: the three team buttons, the five
class buttons, and OK. `limboPanelButtons` holds some fifty entries,
most of them frames, medals and counters that are decorative - cycling
those would bury the three that matter.

Spoken text is derived rather than read off the button, because these
buttons carry no `text`: teams from `teamOrder[data[0]]`, classes from
`BG_ClassnameForNumber(data[1])`, and OK as "Confirm and spawn". Each
stop also states what a sighted player reads from the button's colour
and what is in no string anywhere - `", full"` from
`CG_LimboPanel_TeamIsDisabled`, `", unavailable"` from
`CG_LimboPanel_ClassIsDisabled`, `", selected"` from
`CG_LimboPanel_GetTeam` / `GetClass`. Enter re-speaks the same stop
afterwards, since pressing it changes what the panel now says about it.

The hook sits in `CG_LimboPanel_KeyHandling` *after* the
`BG_PanelButtonsKeyEvent` early return and *after* the close-key check,
so it only ever sees keys nobody else wanted.

## 0017: limbo panel weapon selection

The limbo work's second half, from the same tester's second report: the
panel's team and class stops worked, but changing weapon said nothing.

The panel offers no per-weapon control to drive. Weapons live in a
dropdown that only opens under a cursor, so 0016's "move the cursor and
call the control's own handler" has nothing to aim at. Instead each slot
gets a stop of its own and **Enter cycles it** to the next option,
through `CG_LimboPanel_SetSelectedWeaponNum` - the same setter the
dropdown calls when clicked.

**How many weapons a class has is never assumed.** The engine already
works it out, per class *and* per skill level, and the secondary slot's
list additionally drops whatever duplicates the current primary pick.
`ETA_LimboPanel_WeaponOptions` walks
`CG_LimboPanel_WeaponPanel_GetSelectableWeaponOption`, which is the same
enumeration the dropdown draws from, so the spoken "2 of 3" is the
panel's own count and the spoken order is the order its 1-9 accelerator
keys count in. That helper reads `cgs.ccSelectedWeaponSlot` rather than
taking a slot, so the slot is moved for the walk and put back.

A stop with fewer than two options is skipped rather than announced: a
class with one weapon in a slot has nothing to choose there, and a
spectator has no weapons at all.

`SECONDARY_SLOT` is **0** and `PRIMARY_SLOT` is **1** (`cg_local.h`),
the opposite way round from how the names read, and `weaponLight1`
carries the secondary slot while `weaponLight2` carries the primary.
Both pairings were read out of the button definitions rather than
inferred - this is the same shape of trap as the mirrored bearings.

**0016 took Tab and should not have.** Tab already had a job in this
panel: swapping which weapon slot is shown. 0016 consumed it for
traversal and that job was silently lost. 0017 gives it back, and
narrates the result, so the swap is the engine's own and the keyboard
walk parks on the slot it switched to. Up and Down alone now traverse.

## 0018: default binds, so the config file is optional

The same tester installed the mod correctly and pressed F5 to nothing,
because the second file - `autoexec.cfg`, which is the only thing that
ever bound that key - had not been copied. The commands were registered
and reachable; no key reached them.

A mod cannot edit the engine's `default.cfg`, but `ui` has
`trap_Key_GetBindingBuf` and `trap_Key_SetBinding`, so `UI_Init` can
install the three binds itself. F5, F6 and F8 are free in the stock
`default.cfg` (it binds F1-F4, F7 and F11-F12 and leaves these alone),
so claiming them takes nothing away.

Two rules keep it from being a key thief:

- **An existing binding is never replaced**, whatever it is. A player
  who uses F5 for something else keeps it.
- **`eta_bindsInstalled`**, archived, records that this ran, so a player
  who deliberately unbinds one does not find it back next launch.

`autoexec.cfg` still ships and still works; it is now a way to *change*
the keys rather than the thing that makes them exist.

`tests/autoexec_config_test.py` grew a fifth check for this. These binds
fail exactly as silently as a misspelling in the cfg and are worse to
diagnose, because there is no file to inspect - so every command the
installer names is now checked against the real command tables, and the
check fails loudly if it can read no binds at all.

## 0019: text box narration

The last thing the first in-game report found, and the one that had been
open longest: a text box spoke its label and nothing else, so typing a
player name or a server address gave no feedback at all.

**What was wrong was not the narration, it was what it read.** 0001's
focus hook narrates `item->text`, which for a text box is the label above
it. "Player name" does not say what the name currently *is*, and there
was no other way to find out without sight.

Three hooks, all on paths that already existed:

- **`Item_SetFocus`** (0001's hook) now composes its text through
  `ETA_MenuItem_FocusText`, which for a text box returns "Player name,
  edit box, Alex" and for everything else returns the label unchanged.
  One utterance rather than two, because a second `Say` cuts the first
  off.
- **`Item_HandleTextFieldSelect`** narrates too. Tabbing from one field
  to the next moves the edit target *without changing focus*, so the
  focus hook never fires on that path and the player would be typing
  into a box that never said what it was.
- **The single `Item_TextField_HandleKey` call in `ui_menu.c`** is where
  per-keystroke echo happens. Every key that reaches a text box comes
  through that one call, so the field's contents are taken before the
  engine sees the key and compared with what it left behind.

**The echo describes what the engine did, not what the key was.** That
matters: a letter typed into a number box, or a character past the
field's limit, is refused by the engine and says nothing, which is the
honest answer. Reading the keycode instead would have announced
characters that were never entered.

`item->cvar` is deliberately not what gets read. While a field is being
edited the engine works on a scratch cvar (`EDITFIELD_TEMP_CVAR`) and
only writes back on leaving, so `item->cvar` mid-edit holds what the
field contained *before* the player started typing.

Other details that are not arbitrary:

- **Passwords are never read out.** `Item_IsPasswordField` already
  exists, because the panel draws `password` and `rconpassword` masked.
  Speech honours it: the field's length on arrival, "star" per keystroke.
  Speech that read them would say out loud, in a room, exactly what the
  screen is hiding.
- **Backspace versus Delete** is worked out from where the cursor ended
  up, not from the keycode, so a rebound key still names the right
  character. Backspace removes at `beforeCursor - 1`, Delete at
  `beforeCursor`; both were read out of the engine's own
  `Q_UTF8_Move` calls.
- **Overstrike mode** replaces rather than inserts, so the length does
  not change. Comparing lengths alone would have missed it and spoken
  the wrong character; the comparison is on the text.
- **Space, dot, dash, underscore, colon, slash, backslash and at** are
  spoken by name. A space echoed as `" "` is silence, which is
  indistinguishable from the key not registering - and the rest are what
  a server address is made of.
- **A paste is read whole**, not spelled out.
- Two announcements of the same field are collapsed, since arriving at a
  field can fire both the focus and the select path.

`tests/textfield_echo_test.py` is new and runs in CI. It lifts
`ETA_CharacterAt` out of the patched tree - lifted, not copied, so a test
carrying its own copy cannot pass while the shipped one is broken - and
compiles it against the engine's own `q_unicode.c`. The multi-byte case
is the point: assuming one byte per character is the obvious mistake and
it hands a screen reader half a character to pronounce. Mutation-tested,
and it names the failing case rather than dying on the undecodable bytes
its own failure produces.

## 0020: settings speak their value on arrival, and one more secret field

Two things found by reading `etmain/ui/hostgame.menu` against the patch
series, after a tester asked whether the host-game screen was covered.

**A setting that only speaks when it changes cannot be read, only
altered.** Arriving on "Game Type:" said the label and nothing about
where it stood, so the only way to learn the current value was to change
it first and listen. That is not a hooking gap - `ITEM_TYPE_MULTI` has
been narrated since 0002 - it is a gap in *when*. 0019 gave text boxes
their value on arrival and left every other kind of setting behind,
which made the inconsistency worse rather than better.

`ETA_MenuItem_FocusText` now covers `ITEM_TYPE_MULTI`,
`ITEM_TYPE_TRICHECKBOX`, `ITEM_TYPE_CHECKBOX`, `ITEM_TYPE_YESNO` and
`ITEM_TYPE_SLIDER` as well, so focus says "Game Type:, Campaign".

**The value text is now defined once.** `ETA_MenuItem_SettingText` holds
each type's expression, and both the arrival narration and the five
change hooks call it. The alternative was a second copy of those
expressions and a test asserting the two agreed; one function means they
cannot disagree in the first place, which is the better guarantee.

**`g_password` is now treated as secret by speech.** The host-game and
host-game-advanced screens expose the server join password on that cvar,
and the engine's own `Item_IsPasswordField` covers only `password` and
`rconpassword` - the client-side boxes - so it was being read aloud
character by character.

The fix is a separate `ETA_IsSecretField` rather than a wider
`Item_IsPasswordField`, and that separation is the point.
`Item_IsPasswordField` drives the *drawing* and is not behind the
feature flag: widening it would mask a field on screen for every player
running this mod, feature on or off. Speech gets to be more careful than
the screen without changing what the screen does. ET showing the
password in clear is arguably its own bug, but it is not this mod's to
fix, and a password read aloud in a room is a different exposure from
one shown on a monitor its owner is sitting at.

`tests/textfield_echo_test.py` needed its lift bounds tightened. It
ended the lifted block at the next function's doc comment, so inserting
`ETA_IsSecretField` between that comment and `ETA_CharacterAt` dragged
it in and the test failed to compile - for a reason with nothing to do
with what it checks. It now ends at the close of `ETA_CharacterAt`
itself.

## 0021: separate status keys, and reports spoken as one line

Three things, all from a tester's account of playing with 0.8.0.

### The bug underneath: reports were being cut off

`ETA_WindowsSpeech_Speak` calls `ISpVoice_Speak` with
**`SPF_PURGEBEFORESPEAK`**, which cancels whatever is still being spoken.
The status command made six separate `Say` calls - health, weapon, ammo,
objective, distance, route - so on the SAPI backend a player heard the
last fragment and nothing before it. NVDA queues, so the same build
behaved completely differently depending on which screen reader was
running.

This was already understood in one place: 0019's text-box narration
deliberately says "x deleted, empty" in one breath "because two
utterances in a row cut each other off". That reasoning was applied
locally and never generalised, which is how the shipped status report
kept the defect.

`ETA_Speech_BeginReport` / `EndReport` now group any number of `Say`
calls into one spoken line, joined with ", ". Between them `Say` appends
instead of speaking; `End` speaks the joined result once, and that whole
line is what F6 repeats. It sits in the speech manager rather than in any
narrator, because every module funnels through `Say` - so this needed no
API change in the narrators and covers the ones that compose across
modules, like the objective report that spans `hud_narrator` and
`navigation_system`.

`ETA_Speech_GetLastMessage` was added so the composition can be asserted
rather than taken on trust; `tests/speech_smoke_test.c` checks the
joining, the single-part case, empty reports, `End` without `Begin`, a
report left open, and an oversized part being dropped whole rather than
cut in half. Mutation-tested against both a changed separator and
batching disabled.

### Health and ammo on keys that can be reached

The tester's point was that F5 is a reach mid-fight and that one long
report is the wrong shape when the question is "am I about to die".

`accessibilityHealth` and `accessibilityAmmo` answer one thing each.
They are bound to **9** and **0**.

Every letter A-Z is bound by the stock config, so there was no free key
near the movement hand. 9 and 0 are bound - to `weaponbank 9` and
`weaponbank 10` - but **neither command can do anything**:
`CG_WeaponBank_f` rejects any bank outside `1..MAX_WEAP_BANKS_MP-1`, so
`weaponbank 10` never reaches the table, and bank 9's row in
`weapBanksMultiPlayer` is empty.

So 0018's "an existing binding is never replaced" gains exactly one
exception, and only for those exact commands. The assumption behind it
is not left as one: `tests/weapon_bank_test.py` reads both facts out of
the engine being built against and fails the build if either bank comes
alive. Mutation-tested against a weapon appearing in bank 9 and against
the bank ceiling being raised.

### Weapon changes say what is loaded

Pressing a weapon key spoke the weapon's name and stopped there, which
does not answer what the player is actually asking. It now reports the
name and the loaded rounds in one line - and nothing extra for a knife,
which has no ammo value.

### The objectives key speaks

`CG_objectivesDown_f` narrates the objective, its distance and which way
to turn. This augments the key the player already presses rather than
claiming another one, and leaves the panel behaviour untouched. The
tester suggested it; it is the better pattern and worth reusing.

The objective narration is now one function shared by that key and the
full status report, so the two cannot drift into describing the same
objective differently.

## 0022: the weapon ammo that never arrived, and the silent objectives key

Both reported from playing 0.9.0, and both are defects in 0021 rather
than missing features.

### Ammo on a weapon change was asking the wrong object

0021 narrated the weapon change from `CG_TransitionPlayerState`, where
`ps->weapon != ops->weapon` fires. The name came out right, because it
was read from `ps->weapon`. The ammo never did.

`CG_PlayerAmmoValue` does not read the playerstate's weapon. Its first
act is `weap = (weapon_t)cent->currentState.weapon` - the *player
entity's* state, which prediction has not updated at that point in the
frame. So it answered for the weapon being put away, or bailed out on an
invalid one and left `ammo` at its `-1` initialiser, which the caller
read as "nothing to say".

The fix is not better timing, it is removing the timing question.
`ETA_NarrateWeaponChange` now runs each frame from `CG_DrawActive` and
watches `cg.predictedPlayerEntity.currentState.weapon` - the same field
`CG_PlayerAmmoValue` reads. Both come from one source, so they cannot
disagree about which weapon is in hand. It also catches changes the
playerstate hook never saw: the mouse wheel, running a weapon dry, and
being handed one on spawn.

### Ammo now says what is left to reload from

Loaded rounds alone do not say whether the next reload is coming.
`ETA_HudNarrator_SpeakAmmoDetail` reports both - "8 loaded, 24 in
reserve" - and falls back to the loaded count alone for a weapon with no
reserve. Akimbo pairs add their second clip, as the HUD's own count does.
The status report and the ammo key use the same helper.

### The objectives key was reading the wrong thing entirely

0021 hooked the objectives key to the main-objective lookup, which reads
`CS_MAIN_AXIS_OBJECTIVE` / `CS_MAIN_ALLIES_OBJECTIVE`. Plenty of maps and
modes never set those, so `CG_MainObjectiveForTeam` returned NULL and the
key said **nothing at all** - indistinguishable from the feature being
broken, which is the exact failure this project keeps having to design
out.

The objectives key now reads `cg.objMapDescription_Axis` / `_Allied` /
`_Neutral`, which is the text `CG_ObjectivesDraw` itself draws and what
the player pressing that key is actually asking for. `*` is the map
text's line separator; it becomes a pause.

The main-objective lookup stays where it belongs, on the status report,
answering "which objective, how far, which way" - and now says "No
current objective" rather than going quiet when there is none.

**Neither path can be silent any more.** A map with no description says
so; a weapon with no ammo count says so; no main objective says so.

## Moving between engine versions

The pin has now moved three times: 2.86.0 to 2.85.0 when it turned out
the website was still serving 2.85.0, back to 2.86.0 once it was
published, and on to 2.86.1. Every move cost re-anchoring, and it is
worth recording how little.

**2.86.1, with 107 patches.** The series was made one commit per patch
on 2.86.0 and replayed onto 2.86.1 with `git rebase`, which merges each
patch three ways, and the patch files were made again from the commits.
Of the 107, one met a real conflict: 0016, whose include in
`cg_limbopanel.c` sits where 2.86.1 added two `extern` lines; both are
kept. The other 106 merged by themselves, in files 2.86.1 changed too
(`cg_event.c`, `cg_draw_hud.c`, `cg_weapons.c`, `cg_consolecmds.c`,
`cg_local.h`). Merging is not proof, so the tree was then built with the
feature on and off, and every check run against it.

Before that:

**Only two patches have ever needed it**, both times the same two:

- **0001**, whose CMake hook sits among the `FEATURE_*` blocks in
  `ETLSetupFeatures.cmake`. 2.86.0 has a `FEATURE_XPSAVE` block that
  2.85.0 does not, so the trailing context differs. The hook itself goes
  in the same place relative to `FEATURE_MULTIVIEW` either way.
- **0007**, whose respawn narration sits inside `CG_DrawRespawnTimer`.
  That function was reworked between the versions. The narration goes
  immediately before the `CG_DrawCompText` call in both, which is what
  matters: it reads the component's own on-screen text, so speech cannot
  drift from the display regardless of what surrounds it.

The other twenty apply unchanged to both versions, because they hook
functions and call sites that did not move.

Worth knowing for next time: 0019 and 0020 *appeared* to need
re-anchoring too, and did not. They were tested against a tree where
0001 had failed to apply, so `ui_menuitem.c` was missing 0001's changes
and every later patch to that file looked broken. Applying the series in
order and fixing the first failure first showed the other two were
fine. A patch series reports its failures cumulatively; only the first
one is trustworthy.

## 0023: tell the player the way out, not that they are stuck

From playing 0.10.0: the "You may be stuck" announcement arrived at
random, and when it did it said nothing the player could act on.

**Both halves were wrong.**

The detector asked only "has this player moved in the last three
seconds". In a shooter, not moving is ordinary - aiming, covering a
doorway, listening, waiting out a spawn wave - so it fired constantly
during normal play. Worse, it measured a *single frame's* travel against
a fixed distance, which is a speed test with the frame rate as its
hidden units: at 125fps, 0.05m per frame is 6.25m/s, so walking,
crouching and crawling all registered as motionless.

Being stuck is **wanting to move and not moving**. So the player's own
movement input now decides whether the question is asked at all
(`trap_GetUserCmd`, `forwardmove` / `rightmove`), and progress is
measured across the whole window rather than per frame, which asks the
question that was meant and answers it the same way at any frame rate.
Leaning and jumping are deliberately excluded: neither is an attempt to
get anywhere, and someone jumping to free themselves from geometry is
exactly who should still be told.

**And the announcement is now useful.** Rather than a label for the
player's predicament, the moment reports the objective, its distance and
which way to turn - the same report the objectives key gives. That was
the tester's suggestion and it is plainly right: at the moment you
cannot move, what helps is knowing where to go.

The library returns the judgement rather than speaking it, because only
the engine knows where the objective is. `CG_AccessibilityNarrateObjective`
is now shared by the status report, the objectives key and this, so all
three describe an objective the same way.

Reported once per snag, not repeatedly: staying stuck is not news.

## 0024: find an objective when the map does not name one

From playing 0.11.0: **no navigation assistance played at all**. Not a
wrong distance or a wrong direction - nothing. The only thing the
navigation system ever said was the stuck announcement 0023 replaced.

The cause is one lookup. Every distance, every "turn left toward the
objective", the objective audio cue and its direction cue all asked
`CG_MainObjectiveForTeam` where to point, and that reads
`CS_MAIN_AXIS_OBJECTIVE` / `CS_MAIN_ALLIES_OBJECTIVE`. Those two
configstrings are written in exactly one place in the entire engine -
`G_ScriptAction_SetMainObjective` in `src/game/g_script_actions.c`, the
map script command `wm_set_main_objective` - and that function bails out
quietly when a script does not call it:

```c
// for old map scripts compatibilty we don't abort
return qtrue; // important to set true!
```

Most maps never call it. On those maps the lookup returned NULL and
**every** navigation announcement in the mod was skipped. It compiled,
linked, and passed all six checks. It was wrong only to the person
listening, which is why it took a play session to find and is the third
time this project has shipped that shape of defect.

### The command map already knows

`mapEntities[]` is the list the command map draws its objective icons
from. The server pushes it to every playing client once a second whether
or not the map is open (`G_SendMapEntityInfo`, called from
`ClientThink_real`), it already contains only that client's own team's
entries, and entries drop out as objectives are completed. It needs no
map script.

So `CG_AccessibilityObjective` is now the single place that answers
"where should this player be going": the map's designated main objective
when it has one, and otherwise the nearest objective on the player's own
command map. Every announcement goes through it. Positions are resolved
exactly the way `CG_DrawMapEntity` resolves them for drawing - including
`ME_COMMANDMAP_MARKER`, which is positioned from `cgs.oidInfo[]` because
it has no entity of its own.

Two judgements sit on top of that list, both deliberate:

- **Real objectives beat construction sites.** An entry the map flags
  `IS_OBJECTIVE` (spawnflag bit 4, the bit `cg_draw_hud.c` uses to pick
  out primary objectives) wins over one it does not, before distance is
  considered. Health/ammo cabinets are skipped entirely.
- **The target is sticky.** Without that, two objectives at similar
  range swap places as the player strafes between them, re-firing the
  objective cue and changing what "the objective" means mid-approach.
  The current target is kept while it is still on the command map unless
  another is a quarter closer - a margin rather than a fixed distance,
  so it scales with how far apart a map spreads its objectives.

An objective with no `shortname` is now spoken as "Objective" rather
than silently skipped. Nothing in this path can go quiet any more.

### The check that would have caught it

`tests/objective_source_test.py` reads the server's own "only the
objectives" filter out of `g_teammapdata.c` - the engine's definition of
which `ME_*` types are objectives - and fails the build if the
narration cannot place one of them. It also fails if any function that
announces a distance, a route correction or a direction cue gets its
target from anywhere but the one resolver, which is the original bug
written down as a rule. Both properties were confirmed by breaking them
on purpose before the check was trusted.

It runs against both integrations.

## 0025: speak the player's stance

Asked for by the tester, not off the back of a play session - there has
been no release since 0.11.0, so 0024's navigation fix and this one ship
together. Nothing said whether the player was standing, crouched or
prone.

A sighted player reads that off the screen without thinking about it.
Without it, "did the crouch take" is genuinely unanswerable - and the
engine can refuse: `PM_CheckDuck` only clears `PMF_DUCKED` when a trace
finds headroom, so releasing crouch under a low ceiling leaves the
player crouched with nothing to say so. That case is the reason this
narrates the *state* rather than echoing the keypress.

`ETA_NarrateStanceChange` runs every active frame from `CG_DrawActive`,
beside 0022's weapon narration and for the same reason: it reads
`cg.predictedPlayerState`, because posture is predicted locally and the
snapshot is a round trip behind. Announcing a crouch a round trip late
is the defect 0022 had to fix after it shipped.

**Prone is tested before crouch, and that ordering is load-bearing.**
Going prone sets `PMF_DUCKED` as well - the engine's own comment on the
line is "crouched as well" - so a prone player has both flags set.
Testing crouch first would report every prone player as crouched and
never say "prone" at all. Both orders read as perfectly reasonable C;
only the engine says which is right.

A consequence worth stating because it sounds like a bug and is not:
standing up from prone is heard as "Crouched" and then "Standing",
because leaving prone also sets `PMF_DUCKED`. That is the player's
actual posture on the way up, not an artifact of the narration.

The three names live in the library as an enum
(`ETA_HudNarrator_SpeakStance`), not as strings passed in from the
engine, so the two integrations cannot word them differently. The value
indexes a name table, so an unmapped flag combination is refused by the
range guard rather than reading out of bounds and handing whatever it
finds to a screen reader.

`tests/stance_narration_test.py` derives the flag overlap from
`bg_pmove.c` itself and fails the build if the narration tests them in
the order that overlap forbids, or reads them from the snapshot. Both
mistakes, and removing the narration outright, were made on purpose to
confirm it goes red.

## 0026: name every weapon, and call out the approach

Two things from playing 0.12.0.

### Grenades announced their ammo and no name

Both grenades have an **empty `desc`** in `weaponTable`. The narration
passed that straight to `ETA_HudNarrator_SpeakWeapon`, the input guard
correctly refused an empty string, and the player was left with half a
report. Team and class made no difference because both teams' grenades
are blank.

Grenades were only the pair everybody carries. **Fifteen of the
fifty-five weapons have no `desc`**, and the rest of that list is class
signature kit: the medic's health packs, the engineer's landmines and
rifle grenades, the covert ops' scoped rifles and smoke bomb, the field
ops' smoke marker and binoculars. Every one was silent the same way,
waiting for somebody to play that class.

`CG_AccessibilityWeaponName` (`cg_weapons.c`) resolves a name in order:
the weapon table's `desc`, then a two-entry table in the mod, then the
item's `pickup_name`, then a last-resort `"Weapon"`. **The engine's own
name always wins**, so the mod can only fill a gap, never shadow or
rename anything upstream.

`pickup_name` covers almost all of them - "Grenade", "Pineapple",
"Binoculars", "Landmine", "Smoke Bomb", "M1 Garand Scope". The two the
mod names itself are the ones where the engine's only string is an
internal token: `WP_MEDKIT` is `"medicheal"` and `WP_SMOKE_MARKER` is
`"smokeGrenade"`. Both are things a player holds.

`tests/weapon_name_test.py` walks every weapon reachable from
`weapBanksMultiPlayer` and its alternates - the engine's own definition
of what the number keys can put in your hands - resolves the name
through the same three sources, and fails if any comes out empty or
token-shaped. 49 weapons: 38 named by the engine's description, 9 by
pickup name, 2 by the mod.

### The distance now announces itself

The on-demand report answers "how far is it" when asked. It does not
answer "am I getting there", which is the question a player walking
actually has - and answering it meant pressing a key, walking, pressing
again and comparing two remembered numbers. The tester could not tell
whether the distance was falling or the feature was stuck.

`ETA_NarrateObjectiveApproach` (`cg_draw.c`) feeds the live distance to
the library every frame; the library speaks only when the player crosses
**100, 50, 25 or 10 metres** inward. Four callouts is the whole cost of
an approach.

Three decisions worth recording:

- **The milestone decides when to speak, never what to say.** The
  distance announced is the real one, so arriving inside several
  milestones at once - a spawn, a new objective - reports where the
  player actually stands rather than a rounded fiction.
- **A milestone re-arms only well outside itself** (125%). Drifting
  across its edge, which is exactly what happens in a firefight near an
  objective, stays silent; genuinely leaving and coming back is news
  again.
- **Reset when the target changes.** Distance to a different objective
  is not progress toward this one, and without the reset a completed
  objective handing over to a further one would leave every milestone
  spent and the new approach silent.

Read from `cg.predictedPlayerState`, like 0025's stance and 0022's
weapon, for the same reason.

`eta_objectiveCallouts` (default 1, archived) turns it off. Near an
objective under fire, a spoken distance is one more thing competing with
the footsteps a player is listening for, so it is worth being able to
silence without giving up the on-demand report.

## 0027: speak what the player picked up

Asked for after 0.13.0, and widened in the asking: the tester's example
was an ammo pack, but the request is every item - anything on the ground
or anywhere else.

Walking over something gave a sound and nothing else. A sighted player
reads it off the popup feed. The tester knew what they had found only
because they still remembered the stock sound effects, which a player
new to the game cannot do at all.

**The hook is `CG_ItemPickup`, and that placement is the whole of why
this is correct.** Both pickup paths funnel through it -
`EV_ITEM_PICKUP` / `EV_ITEM_PICKUP_QUIET` and `EV_GLOBAL_ITEM_PICKUP` -
and it is already filtered to the local player, so there is exactly one
place a pickup has to be caught.

**The spoken line is the engine's own popup text**, built from the same
`CG_PickupItemText` call `CG_AddPMItem` is given, character for
character. A table of our own would drift from the screen and would lose
the engine's translations. So the player hears what a sighted player
reads: "Picked up a Health Pack", "Picked up an Objective".

Where the pickup changes a number the player tracks, the new total
follows - health for a health pack, loaded and reserve rounds for an
ammo pack.

**Deliberately the resulting total, not the amount gained.** How much a
pack gives depends on the receiver's class and skill and is decided
server-side, so the client would have to infer it from a playerstate
delta correlated across two code paths in the same frame. The total is
what the player actually needs - am I resupplied - and it is the same
number, from the same helper, that the health and ammo keys report, so
there is no second vocabulary to disagree with the first.

Weapons and objectives get the name alone: a weapon announces its own
ammo when it reaches the player's hands (0022), and "an Objective" is
the whole of what matters about carrying one.

`tests/pickup_narration_test.py` reads both properties out of the
patched engine - that every pickup event still reaches the funnel, and
that the narration still builds its line from the popup's own text - and
fails if either stops holding. Unhooking the narration, routing one
event past the funnel, and giving the mod its own wording were each
tried to confirm it goes red.

### Known limitation

Two pickups in the same frame are two separate messages, and the SAPI
backend cancels one message when the next arrives, so only the second
would be heard. This is the same backend behaviour 0021 had to design
around for multi-part reports, but batching across pickups needs a
frame-level flush that the report API is not re-entrant enough to give
cheaply. Recorded rather than papered over: the normal case is one
pickup at a time, and the failure is a lost line rather than a wrong
one.

## 0028: say how much a pickup gave, and when it gave nothing

0027 spoke the resulting total and deliberately not the amount gained. I
said the gain would have to be inferred fragilely; having read the
server, that was too cautious, and the tester was right to push.

**An ammo pack does not contain a number of rounds.** `BG_AddMagicAmmo`
gives one clip's worth for every weapon the player carries, scaled by
their Signals skill, capped per weapon. So there is no figure to read
off the pack - the gain exists only as the difference it makes.

That difference is visible on the client: the reserve only ever goes up
from a pickup, so summing the per-weapon *increases* is exactly what the
pack gave, across the whole kit.

**The hard part is the "before", and it is a timing problem.** A pickup
arrives with a new snapshot, and by the time `CG_ItemPickup` runs,
`cg.snap->ps` already holds what the server granted. The engine's own
before/after pair is no help either: in the ordinary predicted case
`CG_TransitionPlayerState` runs from the prediction pass, not from the
snapshot transition, so it is not a fixed distance either side of the
event.

So the mod samples the two numbers itself, once a frame, from
`CG_DrawActive` (`CG_AccessibilitySampleTotals`) - **sidestepping the
ordering question rather than trying to answer it**, which is the lesson
0022 had to learn about the weapon ammo report.

### "Already full" is the point

The tester's words: *it must be announced that you are full*. Walking
over a pack you cannot use sounds exactly like one that resupplied you,
and the pack is consumed either way. A gain of zero now says so, for
health and ammo alike.

The library refuses `SpeakGain(0)` outright rather than saying "0
rounds": the caller has to choose which of the two things happened.

### The check

`tests/pickup_narration_test.py` gains a fourth property: the totals must
be sampled once a frame from `CG_DrawActive`, and never from the event
path. Sample them inside snapshot processing and every pickup measures
itself against its own result - every gain reads zero and the mod says
"already full" every time, which is worse than silence because it is
wrong. Removing the per-frame sample and re-sampling at pickup time were
both tried to confirm it goes red.

## 0029: say what is in front of you

The tester's ask, and it turned out `bind b "+zoom"` ties three of their
points into one: **the B key is the binoculars and the scope**.

### Announcing the zoom

`cg.zoomedBinoc` and `cg.zoomed` give "Binoculars", "Scope" and "Zoom
off". Worth saying on its own, because a scope does not always come up
when asked - some weapons refuse while moving or reloading - so silence
after pressing the key is currently indistinguishable from a scope that
did engage.

### What is actually in front of you

The tester asked for the environment: *it could be in front of me, for
example, a wall, a door, something like that*, and noted it would matter
for a sniper rifle.

`ETA_DescribeLookAhead` traces from the eye along the view
(`CG_Trace`, `MASK_SHOT`, about 200 metres) and describes whatever it
runs into. **A trace is the only honest answer to "what is in front of
me"**: it reports what the engine's own collision says is there, rather
than a guess assembled from nearby entities - which would be confidently
wrong exactly when a player is lining up a shot.

What it can say:

- **A person**: their name, and teammate or enemy. First thing that
  matters at the end of a scope.
- **A door, an explosive, an item**, from the entity type.
- **World geometry**, as material plus orientation: "Wooden wall",
  "Gravel ground", "Metal ceiling", "Ladder".
- **"Open sky"** with no distance - the skybox is not somewhere you can
  walk, and a distance to it is the distance to the edge of the map.
- **"Nothing in range"** past the probe's reach.

Two choices worth recording:

- **The materials are the engine's own.** `SURF_METAL`, `SURF_WOOD`,
  `SURF_GLASS` and the rest are the flags it already uses to pick
  footstep and impact sounds, so what is spoken agrees with what the
  player hears underfoot. A table of our own would drift from it.
- **Orientation comes from the impact plane, not the surface.** A normal
  pointing up is ground, pointing down is a ceiling, anything between is
  a wall. That is what makes "wooden wall" and "gravel ground" both come
  out right with no table of special cases.

While zoomed, the view is re-read and spoken again whenever what it meets
changes - a different surface, material or entity, or a distance moved by
more than five metres - rate limited to twice a second. That is what
makes sweeping the binoculars across a scene informative rather than a
single snapshot at the moment they came up.

`tests/look_ahead_test.py` fails the build if the description stops
coming from a trace, if the materials stop being the engine's own flags,
if the skybox regains a distance, or if the plane test that separates a
wall from the ground goes away. All four were broken on purpose to
confirm it.


## 0030: name the weapons the engine labels by class

The tester's bug: *in medical class syringe should be named properly,
which currently it doesn't - it says an ammo count, which is kind of
weird given I already have a health pack I can drop.*

0026 built `CG_AccessibilityWeaponName` around a deliberate rule: **the
engine's own `desc` always wins, so the mod can only ever fill a gap,
never shadow or rename anything upstream.** That rule was right for the
problem 0026 had (fifteen weapons with no `desc` at all) and wrong for
this one. `WP_MEDIC_SYRINGE`'s `desc` is `"MEDIC"` - the *class*, which
the engine itself names that in `BG_ClassnameForNumber`. Beside an icon
of a syringe that reads fine. Spoken alone it names the class and then
reads an ammo count, and a medic carrying both the syringe and the
health pack had no way to tell them apart by ear.

`CG_AccessibilityDescriptionNamesTheWeapon` skips `desc` for that one
weapon, falling through to the item's `pickup_name` - `"Syringe"`, which
the engine already gets right. So the mod still does not invent a name;
it picks between two the engine already has.

**The rule for adding to that list is the interesting part.** The
obvious generalisation - prefer the pickup name when it is longer and
the `desc` is a prefix of it - was written, run against the weapon
table, and thrown out. It fires on thirteen weapons and most of its
answers are worse: STEN to "Sten gun", `WP_FG42_SCOPE` to "FG 42
Paratroop Rifle Scope", and dynamite to "Dynamite Weapon". The rule that
survives is narrow and checkable: skip `desc` only where it is one of
the engine's own player class names.

`tests/weapon_name_test.py` now derives that set from
`BG_ClassnameForNumber` and requires the mod's list to equal it in both
directions - a weapon the engine mislabels and the mod does not skip
fails, and a weapon the mod skips without cause fails too. Both
directions were checked by breaking them.

This is an ET: Legacy defect only. The 2010 tree has no `desc` field at
all, so it has always read `pickup_name` and has always said "Syringe".

## 0031: describe the ground and what is right ahead

The tester, after playing 0029: *in the situation that a class does not
have binoculars or a weapon with a scope, this description of the
environment would not be available... if you're stepping on gravel
ground the announcement changes if the material changes. If you're
facing towards a wall then it should pop up.* And, exactly right about
the relationship: *it's the same environment description feature, but
with binoculars and scope you can see further.*

So this is 0029 at two ranges rather than a second feature.

### The ground, from the engine's own footstep

`ETA_NarrateFooting` hangs off `EV_FOOTSTEP` in `CG_EntityEvent`, which
is the single point where the engine decides which footstep sound to
play, having already resolved the surface flags through
`BG_FootstepForSurface`. The mod speaks a word indexed by that same
footstep type, so **the word and the sound cannot disagree** - a map
that fools one fools both identically.

It is called from inside each of the event's two branches rather than
once above them, because a zero `eventParm` means "use the character's
own default", and reading the parm alone would announce every such step
as stone. Only the local player's steps are narrated: other players'
footsteps are heard, not walked on.

Spoken only on a change, which is the only time the ground is news.

`FOOTSTEP_TOTAL` never reaches the table. It is the engine's marker for
`SURF_NOSTEPS`, a surface that makes no footstep sound at all, and a
surface a sighted player cannot hear is not one to announce.

### The wall, from the same probe as the binoculars

`ETA_DescribeLookAhead` gained a range argument and an optional out
parameter for the trace itself. `ETA_NarrateObstacleAhead` calls it at
100 Quake units - about two and a half metres, roughly where a sighted
player notices they are walking into something - instead of 0029's 8192.

Two things it deliberately does not do:

- **Nothing while zoomed.** The binoculars are already answering this
  question at the range the player asked for, and both speaking would be
  the same sentence twice.
- **Nothing for the floor.** At this range, glancing down puts the
  ground in the probe every time. The trace's plane normal separates
  them, and the ground is the footstep narration's job anyway - which
  answers it from the engine's footstep type rather than from a probe.

### The setting

`eta_environmentCallouts`, archived, default on, covering both halves.

`tests/footing_test.py` reads the `footstep_t` enum, the sound file the
engine registers for each member, and the mod's word table, and requires
all three to line up. That is what pins `FOOTSTEP_NORMAL` to "Stone":
the engine loads `stone1.wav` through `stone4.wav` for it, and "Normal"
would be a word that told the player nothing.

## 0032: say which way you are facing

The tester: *another proposal is what direction you're facing. Here I
propose cardinal directions. That should help out regarding the
direction turning towards the objective as well.*

**This is the one place in the mod where being wrong is worse than being
silent.** Every other defect here has been a missing word: the player
hears nothing and knows something is off. A compass point is confident,
plausible, and wrong in the direction they then walk - and a player with
no sight has no second opinion to check it against.

So the conversion lives in the shared library
(`ETA_HudNarrator_FacingFromYaw`), where both integrations use the same
one and a test can reach it without a game running. ET puts north at yaw
90 and east at yaw 0, and yaw runs anticlockwise while a compass runs
clockwise; that is the whole of it.

`ETA_HudNarrator_UpdateFacing` owns the hysteresis. A new point is only
adopted once the view is five degrees past the boundary, because the
boundary is exactly where a player lining up on a doorway sits, and
without it the smallest movement of the mouse flips the announcement
back and forth.

`ETA_NarrateFacing` reads `cg.predictedPlayerState`, like 0025's stance,
because turning is a local action and the snapshot lags it by a round
trip. `eta_facingCallouts`, archived, default on.

### And the objective

`CG_AccessibilityNarrateObjective` now adds *"Objective lies north, you
are facing south"* after the turn instruction. The two points together
say how far round to turn, which "turn left" never has - a player who
hears those two knows to keep turning past where a vaguer instruction
would have them stop. `angles[YAW]` there is already the objective's own
world yaw, so both come out of the same conversion.

### An ET: Legacy defect found while checking this

`tests/compass_test.py` lifts the label ring and the selection
expression out of `CG_DrawSquareCompassCase` and compares them against
the mod over a full turn. They disagreed past yaw 203, and the engine
was the one that was wrong.

The engine computes `angle = fmodf(-cg.refdefViewAngles[YAW] + 180,
360)`. C's `fmodf` keeps the sign of its left operand, and view yaw is
never negative - it arrives either from the packed network angle or from
`vectoangles`, both non-negative - so for any heading past 180 the angle
is negative, every `angle < 22.5 + index * 45` test succeeds at index 0,
and **the game labels the top of its own square compass "W" for the
entire back half of a turn.**

That is upstream's bug, not a convention to imitate. The test compares
against what the engine's code *means* across all 360 degrees, and
separately against what it literally *does* over the range where `fmodf`
cannot go negative, where the two agree exactly. Both halves were broken
on purpose first: moving north to yaw 270 and swapping east with west in
the word table are each caught.

## 0033: say when you lean out and when you come back

The tester: *obviously for the keys Q and E we can add an announcement
as well.* In the stock config those are `+leanleft` and `+leanright`.

Leaning is one of the few controls **the engine silently refuses**:
`PM_UpdateLean` will not lean a player who is moving, firing, prone,
mounted on an MG42, holding a set mortar, or mid-throw with dynamite.
Nothing on screen says so either - a sighted player simply sees the view
has not moved.

So `ETA_NarrateLean` reads `ps->leanf`, which is what the lean actually
did, and never the key. Announcing the keypress would tell a player they
are peeking out from behind a wall at exactly the moment they are not,
which is a worse answer than saying nothing.

`leanf` is an offset in Quake units that eases in and out over about a
fifth of a second, so a bare sign test would fire on the way out and
again on the way back during a single quick peek; two units in is the
threshold for "this happened". The first frame is not announced, because
a player who has not leaned does not need to be told they are upright.

Positive is right and negative is left - stated here because both
engines write it in a comment and nowhere else, and it is the second
place in this integration where a reversed sign would compile, link and
be confidently wrong.


## 0034: keep keyboard focus when the cursor has not moved

The tester's second report, and the more serious of the two: *when I
pressed enter on the refresh list, I woke up that I got connected to a
server.*

The narration was right. `Menu_HandleKey` opens with

```c
Menu_HandleMouseMove(menu, DC->cursorx, DC->cursory);  // fix for focus not resetting on unhidden buttons
```

which rebuilds focus from the cursor's position **on every key press**.
With a hand on the mouse that is correct - the cursor is where the
player is looking. Played from the keyboard alone it inverts: the cursor
never moves, so it wins every time, and whatever the arrow keys selected
loses focus the instant any key is pressed.

On `playonline.menu` that is not cosmetic. The server list carries

```
onEnter { uiScript JoinServer }
```

so a player who has arrowed to "REFRESH LIST", and has just been *told*
they are on it, presses Enter, focus jumps to the list under the parked
cursor, and they connect to whichever server was highlighted.

The fix is one condition: run the focus reset only when the cursor has
actually moved since the last key. `ETA_MenuCursorMoved` compares
exactly rather than with a tolerance, because the question is whether
the player touched the mouse at all, and its first call returns qtrue so
a menu opened with the cursor already over something still picks that up
once.

**Nothing changes for a mouse user**: the first movement of the cursor
makes it current again and it resumes winning. ET: Legacy had already
carved out the same exception one line above, for listbox navigation -
this generalises it to every other item type.

## 0035: reach the weapon scope from the keyboard

The tester's first report: *when I used the scope for FG 42 the narrator
didn't announce if I being on the scope or not. Even the environment had
not been described whatsoever.*

Nothing is wrong with 0029's narration. `cg.zoomed` is set in `CG_Zoom`
whenever `cg.weaponSelect` is a `WEAPON_TYPE_SCOPED` weapon, `CG_Zoom`
runs from `CG_CalcFov` inside `CG_CalcViewValues`, and that is called at
cg_view.c:167 - well before `CG_DrawActive` at :328, where the narration
reads the flag. The ordering is sound and `WP_FG42_SCOPE` is correctly
marked scoped.

The scope was never entered. Going to it runs `weapalt`
(`CG_AltWeapon_f` → `CG_FinishWeaponChange`), and `default.cfg` contains
exactly one line for that command:

```
bind MOUSE2 "weapalt"
```

**It is the only action in the stock config with no keyboard key.**
`ui_shared.c`'s own default-bindings table says the same thing twice
over, listing `K_MOUSE2` as both of weapalt's keys. So a player without
a mouse cannot scope a rifle, set a mortar, set a machine gun, or
detonate a satchel - and the binoculars, on `b`, work fine, which is
exactly the split the tester reported.

This is the limbo panel again (0016), in a smaller place. The bind goes
into the table 0018 already installs, under the same rule: only if the
key is free.

**KP_SLASH, not F9.** F9 and F10 are free in `default.cfg` and *bound*
in `default_left.cfg`, the left-handed layout - `+stats` and
`+topshots`. Of the keys free in both, KP_SLASH, KP_STAR and KP_DEL are
what is left once the mod's own five are taken.

`tests/keyboard_reachable_test.py` guards both patches. It requires the
cursor-moved guard to still stand in front of the focus reset, every key
the mod binds to be free in *both* stock layouts, and `weapalt` to still
be mouse-only upstream - so if ET: Legacy ever gives it a key, the mod
is told to stop claiming one rather than shadowing it. All three were
broken on purpose first.


## 0036: let the scope report finish

0035 was offered as the answer to *the scope announces nothing* and was
not. The tester corrected it: they reach the scope from the weapon-bank
number keys and always could, so the scope was being entered and the
narration was still silent.

**Scoping a rifle is a weapon change in this engine.** `WP_FG42` and
`WP_FG42_SCOPE` are two different `weapon_t` values, each the other's
`weapAlts`. So:

1. The key press sets `cg.weaponSelect` to the scoped weapon at once.
2. `CG_Zoom`, from `CG_CalcFov` in `CG_CalcViewValues`, sets `cg.zoomed`
   the same frame.
3. `ETA_NarrateZoom` says *"Scope"* and describes what the view meets -
   one report, and the long one.
4. A few hundred milliseconds later, when the `WEAP_ALTSWITCHTO`
   animation finishes, `cg.predictedPlayerEntity.currentState.weapon`
   catches up.
5. `ETA_NarrateWeaponChange` fires and speaks a **second** report - and
   the speech backend delivers a new report by purging the one in
   progress (the same `SPF_PURGEBEFORESPEAK` behaviour 0021 exists for).

So the scope line was cut off mid-sentence by a weapon announcement
whose text was *"FG 42"* - the name the player already had, because
`WP_FG42_SCOPE` carries the same `desc` as `WP_FG42`.

**That is why the binoculars were fine.** `+zoom` sets `EF_ZOOMING` on
the weapon in hand and changes no weapon at all, so nothing arrives
afterwards to cut it off. The split the tester reported - binoculars
yes, scope no - is exactly this difference, and it should have been the
clue rather than the mouse.

The fix: `ETA_NarrateWeaponChange` returns silently when the new weapon
and the last spoken one are each other's `weapAlts` and either is
`WEAPON_TYPE_SCOPED`. That is right independently of the purge - raising
a scope is not picking up a different gun, and announcing the same name
twice was noise even when it did not destroy anything.

Restricted to *scoped* pairs deliberately. The other `weapAlts` pairs -
a mortar or an MG being set down, a satchel and its detonator - have no
zoom narration covering them, so there this report is the only
announcement there is.

**None of this depends on which key was used**, which is what the tester
asked for: the narration reads the engine's zoom state, never a binding,
so the number keys, `weapalt` and the mouse all behave identically.

`tests/zoom_state_test.py` fails if the guard goes away, and separately
if the zoom narration ever reads a flag the client does not assign. It
took three attempts to write - it passed while the defect was present
twice, first by finding the engine's own use of the constant elsewhere
in the file, then by finding the mod's own helper defined nearby.

## Applying it

```sh
# From the root of an etlegacy/etlegacy checkout at (or near) 626020f (v2.86.1):
git submodule add https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-mode.git accessibility-mode
git -C accessibility-mode checkout 229ba0eeb3fc86b50f264512d56597d3ca31d0dd
git apply --index 0001-wire-menu-focus-narration.patch
git apply --index 0002-wire-setting-value-narration.patch
git apply --index 0003-wire-confirmation-dialog-narration.patch
git apply --index 0004-wire-hud-status-narration.patch
git apply --index 0005-wire-audio-cues.patch
git apply --index 0006-wire-objective-status-narration.patch
git apply --index 0007-wire-respawn-timer-narration.patch
git apply --index 0008-wire-tri-checkbox-narration.patch
git apply --index 0009-wire-non-macro-popup-narration.patch
git apply --index 0010-wire-interaction-cue.patch
git apply --index 0011-wire-objective-audio-cues.patch
git apply --index 0012-wire-stuck-detection.patch
git apply --index 0013-wire-distance-route-correction.patch
git apply --index 0014-wire-runtime-init-and-engine-sound-cues.patch
git apply --index 0015-wire-repeat-and-stop-speech-commands.patch
git apply --index 0016-wire-limbo-panel-keyboard-navigation.patch
git apply --index 0017-wire-limbo-weapon-selection.patch
git apply --index 0018-wire-default-accessibility-binds.patch
git apply --index 0019-wire-text-field-narration.patch
git apply --index 0020-wire-setting-value-on-focus.patch
git apply --index 0021-wire-separate-status-keys-and-report-batching.patch
git apply --index 0022-fix-weapon-ammo-timing-and-objective-text.patch
git apply --index 0023-report-the-way-out-instead-of-stuck.patch
git apply --index 0024-find-an-objective-when-the-map-names-none.patch
git apply --index 0025-speak-the-players-stance-when-it-changes.patch
git apply --index 0026-name-every-weapon-and-call-out-the-approach.patch
git apply --index 0027-speak-what-the-player-picked-up.patch
git apply --index 0028-say-how-much-a-pickup-gave.patch
git apply --index 0029-say-what-is-in-front-of-you.patch
git apply --index 0030-name-the-weapons-the-engine-labels-by-class.patch
git apply --index 0031-describe-the-ground-and-what-is-right-ahead.patch
git apply --index 0032-say-which-way-you-are-facing.patch
git apply --index 0033-say-when-you-lean-out-and-when-you-come-back.patch
git apply --index 0034-keep-keyboard-focus-when-the-cursor-has-not-moved.patch
git apply --index 0035-reach-the-weapon-scope-from-the-keyboard.patch
git apply --index 0036-let-the-scope-report-finish.patch

# Standard ET: Legacy setup - fetch the bundled third-party libraries submodule:
git submodule update --init --depth 1 libs

# Configure with the feature on:
cmake -B build -DFEATURE_ACCESSIBILITY=ON -DBUILD_MOD=ON
cmake --build build --target ui cgame
```

## What was actually validated here

Against the real cloned engine source:

- `src/ui/ui_menuitem.c` and `src/ui/ui_menu.c` with all thirteen patches
  applied compile cleanly (`gcc -fsyntax-only -std=gnu90`, matching the
  engine's actual `C_STANDARD 90` + default GNU extensions) both with
  `-DFEATURE_ACCESSIBILITY` and without it, and under both the `ui`
  module's defines (`UIDLL=1 MODLIB=1`) and `cgame`'s (`CGAMEDLL=1
  MODLIB=1`), since both files are compiled into both — confirming the
  integration is a true no-op when the feature is off, and that
  `item->text` / `Item_Multi_Setting`'s return / `va()`'s return (all
  `const char *`) line up with the menu narrator's signatures. This
  caught one real bug during development: 0003's `ETA_NarrateConfirmDialog`
  first didn't compile because `ETA_MAX_MENU_TEXT_LENGTH` lives in
  `core/runtime_guard.h`, not `menu/menu_narrator.h` - the missing
  `#include` was added once the compiler pointed it out.
- `src/cgame/cg_consolecmds.c`, `src/cgame/cg_playerstate.c`, and
  `src/cgame/cg_draw_hud.c` (0004-0007) compile cleanly the same way,
  under `CGAMEDLL=1 MODLIB=1` (they're only ever compiled into `cgame`,
  unlike the shared `ui_*.c` files), with and without the feature flag.
  `src/cgame/cg_draw.c` (0010), the 0011 revisions to `cg_consolecmds.c` /
  `cg_playerstate.c` / `cg_local.h`, and the 0012/0013 revisions to those
  same three files were all validated the same way.
- All thirteen patches were checked to apply cleanly with `git apply --check`
  in sequence from a real clean checkout of the base commit (`git reset
  --hard`), not just eyeballed. This caught a real process bug while
  developing 0005: a `git checkout --` between generating and verifying
  the patch silently reverted the file all the way to the pristine base
  commit (past 0001-0004's changes to it) rather than to the intended
  "after 0004" state, because those earlier patches were applied without
  `--index` and so never touched the git index `checkout` restores from -
  caught by the immediate `git apply --check` failure that followed,
  fixed by resetting and cleanly reapplying 0001-0004 before 0005 (and
  avoided entirely for 0006 and 0007 by not using `checkout` between
  generating and verifying their patches). 0008 through 0013 were
  additionally verified end-to-end from separate clean clones: the full
  patch stack up to and including each one applied cumulatively with
  `git apply --index` from the pristine base commit, in one sequence,
  reproducing byte-for-byte the same files this section's compile checks
  ran against.
- The `add_subdirectory` + `INTERFACE` library propagation pattern used
  in `ETLSetupFeatures.cmake` was reproduced in an isolated CMake project
  and built successfully: a consumer target linking only `mod_libraries`
  correctly picked up `eta_accessibility`'s headers and static library
  without any additional include/link directives, which is exactly how
  `cgame`/`ui` will consume it.
- **The mod libraries actually build and link**, with all thirteen patches
  applied: `git submodule update --init --depth 1 libs` (the previously
  unfetched `etlegacy-libs` submodule - the archive is public and fetched
  cleanly once actually requested, so what earlier revisions of this
  README called a sandbox limitation wasn't one) followed by
  `cmake -B build -DBUILD_MOD=ON -DFEATURE_ACCESSIBILITY=ON -DINSTALL_EXTRA=OFF
  -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc
  -DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++ -DBUILD_SERVER=OFF
  -DBUILD_CLIENT=OFF` (`INSTALL_EXTRA=OFF` skips the GeoIP/WolfAdmin/omni-bot
  add-on downloads from `mirror.etlegacy.com`, which this sandbox's network
  policy blocks and which have nothing to do with these patches) then
  `cmake --build build --target cgame ui` produced real, linked
  `cgame_mp_.dll` and `ui_mp_.dll` - not just syntax-checked translation
  units. Repeating the same configure+build with `-DFEATURE_ACCESSIBILITY=OFF`
  also succeeded, and `x86_64-w64-mingw32-objdump -t` on the two resulting
  `cgame_mp_.dll`s confirms the no-op claim at the binary level, not just by
  reading the `#ifdef`s: 60 `ETA_*` symbols linked into the feature-on
  build (including all eight `ETA_NavigationSystem_*` functions 0012/0013
  wire up), 0 in the feature-off one. Repeated once more from a fully
  separate clean clone after 0012/0013 (this time also cloning the
  `accessibility-mode` checkout into place per "Applying it" above, rather
  than reusing one already set up) with the same result, to rule out
  anything specific to the working checkout these patches were developed
  against.

- **All thirty-six were verified against v2.86.0**, the pin these
  patches now target, after the tester updated to it. They apply cleanly
  with `git apply --index` in sequence to a pristine `9345fc8` clone with
  its `libs` submodule fetched; `cgame` and `ui` then build with `FEATURE_ACCESSIBILITY` on
  and off with no compiler warnings either way. For 0016 specifically,
  the feature-off build carries **0** of the patch's strings and the
  feature-on build carries them, so the limbo traversal is a genuine
  no-op when the flag is off, checked in the built objects rather than
  by reading the `#ifdef`s.

**The meaning-level checks do not compile the engine, and cannot catch a
patch that breaks it.** That is not a hypothetical: while preparing
0023, the patch was generated by copying three files from a 2.85.0
working tree into a 2.86.0 base, so it silently reverted `cg_local.h`
and two other files to their 2.85.0 content. All twenty-three patches
still applied, and all six checks still passed - because none of them
compiles anything. Only building the patched tree caught it, on an
unrelated symbol in `cg_debriefing.c`.

The lesson is that a green check run is not evidence the series is
sound. Build the patched tree before trusting it; CI does, which is why
this is a near miss rather than a shipped one.

Not validated by this repository: a full client/server build (needs the
genuine W:ET game asset `.pk3` files this sandbox doesn't have, and
touches none of the code these patches change).

In-game behaviour is no longer wholly unverified, but it is verified by
a tester rather than here. alpha-0.4.0 established that the main menus
narrate correctly and that the limbo panel could not be operated at all.
alpha-0.5.0 established that **0016 works**: a player reached a match
from the keyboard for the first time. The same session found the two
things 0017 and 0018 answer - weapon changes said nothing, and F5 did
nothing because `autoexec.cfg` had not been copied. Neither 0017 nor
0018 has been heard yet.

alpha-0.6.0 added weapon selection (0017) and the self-installed key
binds (0018); neither has been heard yet. 0019 closed the text-entry gap
the first report opened, and 0020 the "what does this setting say right
now" gap that 0019 exposed. Neither has been heard either.

0.11.0's session established that the O key and the weapon ammo report
both work, and that **no navigation assistance played at all** - which
0024 traces to the main-objective lookup and fixes. That report is the
only reason the defect is known: nothing in this repository could see
it, because the code was correct and its input was empty.

## Known follow-ups (not included in these patches)

- **`WINDOW_TEXTASINT`/`WINDOW_TEXTASFLOAT` popup labels**: 0009's
  cvar-bound popup narration reads a `CVARLABEL` item's raw cvar string,
  matching every popup shipped today. No shipped popup combines
  `CVARLABEL` with the `TEXTASINT`/`TEXTASFLOAT` display transform
  `Item_Text_Paint` also supports (only non-popup `CVARFLOATLABEL` options
  do), so 0009 doesn't replicate it; a future popup that does would narrate
  the untransformed string until this is added.
- **Route correction's on-course threshold**: 0013's ±15 degree
  "objective is ahead" band is a judgment call made in this round, not a
  value found in or verified against this codebase - there is no
  comparable on-course tolerance anywhere in the engine to measure it
  against. Worth real playtesting rather than treated as settled.

  The `ETA_QU_TO_METERS = 0.0254` conversion that sat alongside it is no
  longer on this list. It was taken from id Tech 3's external
  1-unit-=-1-inch convention and marked unverified, on the grounds that
  nothing in the engine states a real-world size. That was wrong: the
  engine states the size of a *person* in five independent places, and a
  person has known dimensions. Under the conversion they read 1.83 m
  standing, 1.63 m to the eye, 1.22 m crouched, 1.02 m to the eye
  crouched and 0.41 m to the eye prone - five anatomical measurements,
  all correct to a few centimetres, from constants that were never
  chosen with metres in mind. `tests/distance_scale_test.py` reads them
  out of the engine on every run and fails if any lands outside a human
  range, so a wrong conversion or an engine that rescales its players
  cannot make every spoken distance quietly wrong.

  What remains genuinely unverified is a *map's* intended real-world
  size. Nothing published states one, and the player is the only object
  in the game whose true dimensions are known independently - which is
  why the player, and not a map, is what the check measures.

## 0121: voice chats have a volume of their own

`eta_voiceVolume`, 0 to 100, on Accessibility → Sound. Asked for by the
tester: bots calling for medics and ammo drowned the marker's beacon on
the way to it. Below 100, `CG_PlayVoiceChat` plays the voice with
`trap_S_StartSoundVControl` from the player's own head at that share of
full, since a local sound takes no volume; the chat line is unchanged,
so the words are still read.


## 0122: period faces the way to the marker; the main menu says "Play online"

The tester, used to O in the RTCW mode, wanted a key that turns them
straight onto the way to the marker instead of turning by ear.
`accessibilityMarkerFace`, on **period** (bind generation 16, taken only
from the stock `mapzoomin`, a zoom of the on-screen map - N, first tried,
is the spawn-timer reset the tester keeps), takes the point the ping is placed at -
`ETA_MarkerTarget`: the open way when the straight way is walled off,
along the route when there is one, straight at the marker in plain reach
- through the new `CG_AccessibilityMarkerFacePoint`, and turns the view
there with the use key's own `ETA_AimStartSnap`, level at eye height so
the player is not left looking at the floor. It says *"Facing the way. N
meters to marker"*, or *"No marker set"* with no marker. A row on Key
Binds (*"Face The Way"*) and a `g_bindings` entry go with it.

The main menu's first button is `MSGID_MENU_MAIN_PLAY`, "PL^_AY", and
opens the Play Online screen; the tester knows it by that name. A button
whose action opens `playonline` is now said as *"Play online"*
(`ETA_MenuItem_Label`).

Checked: all of the engine checks the CI runs pass on the series with
this patch, and `cgame` and `ui` build with the feature on.

## 0123: "Play online" said for real

0122's "Play online" never reached the tester: it looked for "open
playonline" in the button's action, but the menu parser keeps an action
as it rebuilt it, each word of more than one character in quotes -
`"open" "playonline"` (`PC_Script_Parse`, ui_parse.c) - so it never
matched, and the button was still said as "Play". The label now looks
for `playonline` alone, on a button of the menu named `main`.
`play_online_label_test.py` rebuilds the stock main menu's button action
the way the parser does and holds the label code's test against it: it
fails on 0122's code and passes on this.

## 0124: Shift+N faces the marker

The tester wanted the marker's turn on a key next to the ones they
already use, and N, like U, is taken in the stock config: N is
`timerreset`. N is now bound to `accessibilityTimerReset`, which runs the
game's own `timerreset` when Shift is up - nothing is lost - and with
Shift held runs period's `accessibilityMarkerFace`, turning the player
toward the way to the marker. Period keeps doing that too. The Key Binds
page has the row *"Timer, Shift Faces Way"*; `timerreset` joins the
replaceable commands in `keyboard_reachable_test.py`, since N still does
it.

## 0125: Shift+N alone faces the marker; period given back

The tester wanted the turn toward the marker on one key, Shift+N, and
period off it. Period's row goes from the installed keys, and generation
18 gives period back to the game's `mapzoomin` - only while it is still
on `accessibilityMarkerFace`, so a key the player has set since is left
alone. The `accessibilityMarkerFace` command, its Key Binds row and its
`g_bindings` entry go: the turn is Shift+N's alone, through
`accessibilityTimerReset`. `mapzoomin` leaves the replaceable commands in
`keyboard_reachable_test.py`, since nothing takes it now.

## 0126: Shift+N turns once Shift is up, and speaks where it landed

On 1.4.4.2 the tester heard "Facing the way" from Shift+N and was not
turned. The words were said as the snap began, whether it went anywhere
or not, and the snap began with Shift still held - the one thing that
set Shift+N apart from F, whose snap turns. The turn now waits for Shift
to be let go (or a second and a half), and the words come when the snap
ends, from where the view has landed: "Facing the way. 40 meters to
marker" within 15 degrees of the way, else "Could not turn all the way:
the way to the marker is ahead left, 40 meters" - so a turn that fails
says so, and says which way to turn by hand.

## 0127: N alone turns toward the marker; Shift+N resets the timer

On a Mac the tester found Shift+N did nothing, and asked for N itself to
turn them toward the marker - N being the key they use both to hear
where it is and to be turned. N now says what the marker is on, how far
and how high, then turns toward the way to it, round the walls, and says
"Facing the way" once the turn lands (or which way to turn by hand when
it cannot); Shift+N is the game's spawn-timer reset, which the tester
does not use. The bind is the same - N on `accessibilityTimerReset` - so
nothing in the config changes.

Keypad dot, generation 6's "where is the marker", is given back in
generation 19: unbound - nothing in the stock game is on it - if it is
still on `accessibilityMarkerWhere`, since N says where the marker is
now. The command goes with its Key Binds row (every command the mod
answers has a row: `menu_override_test.py`), and N's row reads "Face
Marker, Shift Timer".

## 0128: Where Is Marker back, doing what N does

0127 took `accessibilityMarkerWhere` away with Keypad dot's bind, and
with it the Key Binds row. The tester had put the command on N
themselves, so on 1.4.4.4 N answered nothing and the marker's beep kept
telling them they faced the wrong way. The command is back, sharing N's
code (ETA_MarkerWhereAndFace): what the marker is on, how far and how
high, then the turn toward the way to it. Its row is back on the Key
Binds page as "Where Is Marker". No default key: Keypad dot stays
free, and generation 19 still frees it only where it was the mod's own
bind. A key the player set to the command keeps working.

## 0129: the way is kept while it is looked for again

On Oasis the tester could not get from the Allied camp to the Old City
Water Pump: the way there goes through the flooded caves, and the
marker's beacon kept to the road outside the Old City wall. The way
was found - on the real map, ten to twelve seconds of searching, 197
points through the caves - but it is looked for again five seconds
after it is found and whenever the player strays, and each new search
began by clearing the old one. For the ten seconds of the search the
ping pointed at the last point it had; the player walked past it, and
N turned them east, west and east again. The found way is now copied
(eta_way) and followed - its stairs, crouches and jumps told from it -
while the next search runs, and replaced only when that search has an
answer; no new search is begun while one is running. A fresh marker,
with no way yet, starts with no jump told (saidJump -1), as before.

Checked on the real Oasis: N and forward only, from the Allied camp to
the Old City Water Pump through the caves, "Crouch, low ceiling ahead"
and the ladder out said on the way, reached twice.

## 0130: N turns to a direction, turns keep the run, and the stuck report waits for no marker

Three things the tester found following the marker.

N aimed at the way's next point, a few metres on. Running while the
view turned, the player reached the point and went past, the direction
to it swung round behind them, and the turn chased it until the snap
gave up: "Could not turn all the way". N now turns to the direction to
that point from where it was pressed, carried 8192 units out, so a few
steps do not move it; and a turn that falls short is made once more
before anything is said.

The turns were sped up with the walk key, +speed, which raises the turn
keys by cl_anglespeedkey - and, with cl_run on, walks the player at half
speed for as long as it is held. Every N and every compass step slowed
the player down; the tester asked why they were slower than everyone
else. ETA_TurnBoost now raises cl_yawspeed five times instead and puts
it back when the turn ends, with the value it had kept in
eta_turnYawSaved (archived) so a game closed mid-turn has it put back
on the next turn. The walk key's number, 997, is no longer pressed.

The stuck detector read out the objective's straight line - "136 meters
to objective, turn left toward the objective" - whenever a turn of the
way held the player a moment, and it pointed elsewhere than the
marker. With a marker out it says nothing now.

Checked on the real Oasis: running with forward held and N every three
seconds, from the Allied camp to the Old City Water Pump - 24 turns,
"Facing the way" each time, no "Could not turn", no objective report.

## 0131: the host game page's checkboxes and map list, and the match's server info

Two menus the tester could not read with NVDA or VoiceOver.

On the host game page, arrowing down from the password went through
five checkboxes - Friendly Fire, Anti-Lag, Max Lives, Weapon
Restrictions, Balanced Teams - that are drawn with their words beside
them as separate labels and have no text of their own, so each was
silent; the tester, hearing nothing, took the page for dead before the
map list. A control with no text whose item name starts "label" is now
said by the rest of its name: "Friendly Fire, On". The list under them
is called what it lists: "Campaign list, Central Europe, 1 of 2", or the
map list for the other game types. The tester, wanting one map, found
only North Africa and Central Europe there: with the game type on
Campaign the list holds campaigns, so on reaching it that is said too -
"For one map, set Game Type to Single-Map Objective" - and with that set
it reads "Map list, Fuel Dump, 1 of 6".

In a match, Escape and Server Info opens a list nothing is chosen from;
the arrows only scrolled it, and after its first line nothing more was
said. The arrows, Page Up and Down, Home and End now go row by row
through such a list, the screen kept on the row, and each is said:
"Address, localhost, 2 of 43". The players at the end are said by name,
"tester, score 0, ping 0", under "Players", and a blank row as "blank".

Checked in the game: the host game page from Server Name to Advanced
and back, and the server info list on Oasis, top to bottom.

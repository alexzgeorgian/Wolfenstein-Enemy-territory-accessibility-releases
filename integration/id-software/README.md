# id Software original GPL release integration

This wires the menu narrator (`src/accessibility/menu/menu_narrator.c`),
HUD narrator (`src/accessibility/hud/hud_narrator.c`), audio cue system
(`src/accessibility/audio/audio_cue_system.c`) and navigation system
(`src/accessibility/navigation/navigation_system.c`) into the original
2010 id Software GPL release of Wolfenstein: Enemy Territory, behind an
opt-in `FEATURE_ACCESSIBILITY` compile define. It is
kept as patches here rather than applied directly to
`id-Software/Enemy-Territory`, for the same reason as the ET: Legacy
integration (`integration/etlegacy/README.md`): this repository has no
push access to that project, and the engine is meant to stay upstream (see
`docs/SOURCE_CODE_PLAN.md`).

Base commit: [`id-Software/Enemy-Territory@40342a9`](https://github.com/id-Software/Enemy-Territory/commit/40342a9)
("The Wolfenstein: Enemy Territory sources as originally released under
the GPL license on August 20, 2010") — the only commit in that
repository; there is no ongoing development to track a moving base
against, unlike ET: Legacy.

## Why this is a separate integration from `integration/etlegacy/`

ET: Legacy is a fork of this exact codebase, but by its own pinned commit
it has already diverged by over a decade of refactoring. Two differences
matter for how patches are structured here:

- **No CMake.** This release ships a Python 2 SCons build
  (`src/SConstruct`, `src/SConscript.*`) for Linux, and a Visual C++ 2008
  solution (`src/wolf.sln`) for Windows - there is no equivalent of
  ET: Legacy's `FEATURE_ACCESSIBILITY` CMake option or its
  `add_subdirectory(accessibility-mode)` wiring to reuse.
- **The UI code is one file, not several.** ET: Legacy split what was
  originally a single `src/ui/ui_shared.c` into `ui_menu.c` / `ui_menuitem.c`
  / `ui_parse.c` / `ui_script.c` / `ui_shared.c` as part of its own
  modernization. In this original release, `Item_SetFocus` and every other
  menu/item function ET: Legacy's patches hook lives in one
  `src/ui/ui_shared.c` instead - confirmed by reading this repository's
  actual source, not assumed from ET: Legacy's layout.

Despite that split, the two codebases share a very recent-enough common
ancestor that the actual hook points read as nearly identical C: this
patch set was written by re-deriving each hook fresh against this
repository's real source (not by copy-pasting the ET: Legacy patches),
but where a hook already exists in the ET: Legacy integration, the
underlying engine logic here has consistently turned out to already
support the same narration, function-for-function - `Item_SetFocus` (this
patch), for instance, has the exact same "sets `WINDOW_HASFOCUS` once per
genuine focus change, short-circuits if already focused" behavior 0001 of
the ET: Legacy integration relies on, reachable from both mouse hover and
`Menu_SetPrevCursorItem` / `Menu_SetNextCursorItem` (Tab navigation) -
confirmed by reading both call sites directly, not assumed from the fork.

Apply the patches in order; each depends on the ones before it.

## 0001: menu focus narration

Hooks `Item_SetFocus` in `src/ui/ui_shared.c` - the same function
ET: Legacy's own 0001 patch hooks, and (per above) functionally identical
in this original release: it sets `WINDOW_HASFOCUS` on `item` exactly once
per genuine focus transition (mouse hover into a widget, or
`Menu_SetPrevCursorItem`/`Menu_SetNextCursorItem` moving the Tab cursor),
and short-circuits at its own top if the item already has focus. Right
before its final `return qtrue;`, guarded on
`item->window.flags & WINDOW_HASFOCUS`, calls
`ETA_MenuNarrator_OnFocusChanged(menuName, itemText)`.

`src/ui/ui_shared.c` is compiled into both the `ui` and `cgame` shared
libraries here (see `SConscript.ui` / `SConscript.cgame`, both of which
list it - `ui_shared.c` directly for `ui`, `../ui/ui_shared.c` for
`cgame`), the same "shared file compiled into two modules" situation
`ui_menuitem.c`/`ui_menu.c` are in for ET: Legacy - so this one hook point
covers narration for both the standalone menu system and any in-game
(`cgame`) menus, matching ET: Legacy's 0001 exactly in scope.

This satisfies Milestone 2's exit condition ("a blind player can hear
which menu item is selected") for this engine's real menus.

## 0002: setting value narration

Hooks `Item_HandleKey`'s dispatch switch in `src/ui/ui_shared.c` - the
single dispatcher every settings widget's keypress routes through, exactly
as in the ET: Legacy integration's own 0002 (also `Item_HandleKey`, just
in `ui_menuitem.c` there post-split). Checked directly rather than assumed
from the fork: `Item_CheckBox_HandleKey`, `Item_YesNo_HandleKey`,
`Item_Multi_HandleKey`, `Item_Multi_Setting`, and `Item_Slider_HandleKey`
all already exist in this release with the same behavior ET: Legacy's
pre-0002 baseline had - including `Item_Multi_Setting`'s `cvarFloatList`
lookup mechanism, which is what makes narrating a `MULTI` item's setting
possible without inventing a label.

For each type, after the handler reports `qtrue` (value changed), narrates
via `ETA_MenuNarrator_OnValueChanged(item->text, ...)`:

- `ITEM_TYPE_CHECKBOX` → `"On"` / `"Off"` from the cvar's value.
  `ITEM_TYPE_TRICHECKBOX` is left alone in this patch, matching
  ET: Legacy's own original pre-tri-checkbox-follow-up scope (see
  ET: Legacy's 0008 for why tri-checkbox needed its own separate look, once
  this integration gets there).
- `ITEM_TYPE_YESNO` → `"Yes"` / `"No"`.
- `ITEM_TYPE_MULTI` → `Item_Multi_Setting(item)`, this file's own existing
  helper for a multi-choice item's current display label.
- `ITEM_TYPE_SLIDER` → the cvar's current value formatted with `va("%.2f",
  ...)`, this file's own existing `printf`-style scratch-buffer helper.

One real behavioral difference from ET: Legacy worth noting (found while
reading `Item_CheckBox_HandleKey` here, not assumed): this original
release's `ITEM_TYPE_TRICHECKBOX` cycling only increments
(`getCVarValue(item->cvar) + 1`, wrapping at 2 back to 0) - it has no
`K_MOUSE2`-decrements-instead branch the way ET: Legacy's fork later grew.
Irrelevant to this patch (narration only reads the resulting value, not
the direction it changed), but a real difference between the two
codebases at this exact hook point.

This covers Milestone 3's setting-value-narration deliverable for the
three widget types with a real handler to hook in this release
(checkboxes, yes/no toggles, and multi-choice/slider settings).

## 0003: confirmation dialog narration

Hooks `Menus_ActivateByName` in `src/ui/ui_shared.c` - the same function
ET: Legacy's own 0003 hooks, and confirmed here to have the exact same
shape: every menu activation, by name, goes through it; right after
`Menus_Activate(m)` and before the (identical) modal-stack handling, this
patch narrates via a new `ETA_NarrateConfirmDialog` when the activated
menu has `WINDOW_POPUP` set.

`ETA_NarrateConfirmDialog` walks the menu's `items[]` and narrates every
`ITEM_TYPE_TEXT` item with literal `text`, joined with spaces - relying on
the `SUBWINDOW`/`SUBWINDOWBLACK`/`LABEL`/`LABELWHITE` macros in
`etmain/ui/menumacros.h` always emitting exactly that shape, the same
convention ET: Legacy's 0003 verified against real shipped `.menu` files.
**This release doesn't ship any `.menu` scripts to check against directly**
- `etmain/ui/` here contains only `menudef.h`/`menumacros.h` (the
constants/macros themselves), not actual menu content; unlike engine
source, `.menu` files are game data, and this GPL release's own README
says game data isn't included. So this patch is verified against the real
macro *definitions* (confirmed: `SUBWINDOW`'s title itemDef and both
`LABEL`/`LABELWHITE` either explicitly set `type ITEM_TYPE_TEXT` or rely
on an omitted `type` defaulting to `0` == `ITEM_TYPE_TEXT`, matching
`Item_Init`'s `memset`-to-zero item initialization), not against a
concrete popup - a real difference from how confidently this could be
checked in the ET: Legacy integration, and worth keeping in mind if this
narration is ever found not to fire for some hand-authored popup content.

`ITEM_TYPE_TEXT` and the other item-type constants turned out to be
`#define`s in that same `etmain/ui/menudef.h`, included directly by
`ui_shared.h` (`#include "../../etmain/ui/menudef.h"`) - so the C engine
code and the `.menu` script format share one literal source of truth for
these constants in this codebase, not just a naming convention kept in
sync by hand.

This satisfies Milestone 3's remaining deliverable ("confirmation dialog
narration") for this engine's real menus.

## 0004: tri-checkbox setting narration

0002 deliberately skipped `ITEM_TYPE_TRICHECKBOX`, matching ET: Legacy's
own original scoping before its later 0008 gave tri-checkbox its own
pass. Checking this release's real source shows the same thing 0008 found
for ET: Legacy: `Item_CheckBox_Paint` (`ui_shared.c`) already calls
`Item_Multi_Setting(item)` to draw a tri-checkbox's on-screen label
whenever it has a `cvarFloatList` (`multiPtr && multiPtr->count`) - the
exact same mechanism `ITEM_TYPE_MULTI` uses - so the label this patch
narrates was never invented, it's the same string `Item_CheckBox_Paint`
already draws. `TRICHECKBOXACTIONMULTI` (`etmain/ui/menumacros.h`) also
exists here, splicing a `cvarFloatList`-style argument into `cvar` the
same way ET: Legacy's version does.

**Unlike 0001/0002, this can't be checked against a real popup or
setting menu the way ET: Legacy's 0008 was** (against
`playonline.menu`'s actual server-browser filters) - as 0003 already
found, this release ships no `.menu` scripts at all, only the
constants/macros. So this patch rests on the C-side proof
(`Item_CheckBox_Paint` calling `Item_Multi_Setting` for real, live
tri-checkboxes) and the macro's existence, not on a concrete example of
it being used in shipped game content - the same category of gap 0003
already flagged, not a new kind of uncertainty.

This patch gives `ITEM_TYPE_TRICHECKBOX` its own case in `Item_HandleKey`,
mirroring 0002's `ITEM_TYPE_CHECKBOX` case: after `Item_CheckBox_HandleKey`
reports a change, narrates via
`ETA_MenuNarrator_OnValueChanged(item->text, Item_Multi_Setting(item))`.
`Item_Multi_Setting` itself already falls back to `"None Defined"` /
`"Custom"` for a bare `TRICHECKBOXACTION` with no `cvarFloatList` (unused
by any macro caller found here, but supported), the same fallback `MULTI`
items without a list get - so this patch never narrates an invented label
even in that unconfirmed case.

This closes the "Tri-checkbox narration" follow-up, completing Milestone
3 for this codebase.

## 0005: HUD status narration (Milestone 4)

The first cgame-side patch - everything before this touched only
`src/ui/ui_shared.c`. Adds an on-demand `accessibilityStatus` console
command (`cg_consolecmds.c`) narrating health, the active weapon, and its
ammo in one report - ET: Legacy's own Milestone 4 exit condition - plus
automatic weapon-change narration (`cg_playerstate.c`).

Neither piece ported directly from ET: Legacy's own 0004, because the two
codebases have genuinely diverged here more than in the UI layer:

- **No `GetWeaponTableData`.** ET: Legacy's weapon abstraction doesn't
  exist in this release. The real, already-displayed source for a
  weapon's name here is `gitem_t.pickup_name` (`bg_public.h`) via
  `BG_FindItemForWeapon` (`bg_misc.c`) - confirmed genuinely on-screen
  already, not assumed: `cg_draw.c`'s pickup-message builder
  (`"a %s", bg_itemlist[item].pickup_name`) uses the exact same field to
  build the "you picked up a Thompson" message.
- **`BG_FindItemForWeapon` isn't safe to call with an arbitrary weapon
  value.** It `Com_Error(ERR_DROP, ...)`s - dropping the client - if the
  weapon has no matching `IT_WEAPON` entry in `bg_itemlist`. `bg_pmove.c`
  has its own inline guard before calling it
  (`weapon <= WP_NONE || weapon > WP_DYNAMITE) && !(weapon >= WP_KAR98 ...)`),
  but checking the actual `weapon_t` enum values that range excludes shows
  it's specific to that function's own reload logic, not a general
  "is this a real weapon" test - the excluded range (16-22) includes
  `WP_MEDKIT`, `WP_BINOCULARS`, `WP_PLIERS`, and `WP_SMOKE_MARKER`, all
  real, commonly-held items `CG_PlayerAmmoValue` itself already treats as
  legitimate current weapons. Reusing that guard here would have
  incorrectly refused to narrate anyone holding pliers or a medkit. Added
  `BG_FindItemForWeaponSafe` (`bg_misc.c`/`bg_public.h`, `#ifdef
  FEATURE_ACCESSIBILITY`) instead - the same `bg_itemlist` scan
  `BG_FindItemForWeapon` already does, just returning `NULL` on a miss
  instead of fatally erroring, so a narration call can never be the thing
  that drops a player from a match.
- **`CG_PlayerAmmoValue` already exists** (`cg_draw.c`, used for the
  on-screen ammo count) with the same per-weapon special-casing ET: Legacy's
  version has, but is `static` and takes 3 out-params, not ET: Legacy's 4
  (no `maxammo`). Made non-static (declared in `cg_local.h`, `#ifdef
  FEATURE_ACCESSIBILITY`) rather than duplicated, mirroring how
  ET: Legacy's own `CG_MainObjectiveForTeam` was generalized for
  cross-file reuse - same reasoning, same repo, same fix shape.
- **No automatic weapon-change hook exists in `CG_TransitionPlayerState`.**
  ET: Legacy's 0004 reused an existing `ps->weapon != ops->weapon` check
  already there (added later in that fork, for smoke-generation reset);
  this original version's `CG_TransitionPlayerState` has no such check to
  reuse. Rather than force ET: Legacy's exact shape onto code that doesn't
  have it, this patch adds a `ps->weapon != ops->weapon` diff directly -
  not an invented mechanism, since the same function already does this
  exact kind of `ps`/`ops` field diffing for `damageEvent`,
  `persistant[PERS_SPAWN_COUNT]`, and `viewheight` a few lines away in
  both directions.

This satisfies Milestone 4's exit condition ("a blind player can query
basic match state") for this engine's real HUD state, for the two pieces
covered so far (weapon name, on query and automatically; ammo, on query).
Health/ammo aren't narrated automatically, matching ET: Legacy's own
reasoning: they change too often during combat for that to be anything
but noise.

## 0006: respawn timer narration

The reinforcement countdown - a genuinely working, actively-used feature
here, unlike the objective-status deliverable (see below):
`CG_CalculateReinfTime`/`CG_CalculateReinfTime_Float` (`cg_draw.c`) are
called from multiple real, active sites - `CG_DrawLimboMessage`'s
"Reinforcements deploy in %d seconds." text (the one this patch hooks),
the limbo menu's numeric respawn-time widget (`cg_limbopanel.c`), and the
scoreboard (`cg_scoreboard.c`).

`ETA_NarrateRespawnTimer` is called from inside `CG_DrawLimboMessage`,
right after its own two early-return guards (dead, and not yet in limbo
or spectating) - so it only runs in exactly the window the on-screen text
is showing. It calls the identical `CG_CalculateReinfTime(qfalse)` the
text itself uses, so what's narrated always matches what's drawn, and
does its own edge detection with a `static int lastNarratedSeconds` local
(the countdown recomputes fresh from elapsed time every frame rather than
being driven by a discrete state transition) - the same technique
ET: Legacy's own 0007 uses for its equivalent HUD component. Stays silent
once `persistant[PERS_RESPAWNS_LEFT]` hits 0, matching the on-screen "No
more reinforcements this round." case.

**Objective status narration - Milestone 4's other remaining
deliverable - is not included, and isn't just unverified this time; it
was investigated and found to rest on genuinely dead code in this
release.** `CS_MAIN_AXIS_OBJECTIVE`/`CS_MAIN_ALLIES_OBJECTIVE` and
`oidInfo_t`/`cgs.oidInfo[]` (what ET: Legacy's own 0006 uses) do exist
here, but tracing every reference to those configstrings found: the one
cgame-side read of them (`cg_commandmap.c`) is inside a `/* ... */`
comment block, and the one place that would ever *write* one of them -
`G_ScriptAction_SetMainObjective` (`g_script_actions.c`, the
`wm_set_main_objective` map-script command) - has its entire body
commented out and unconditionally `return qtrue`s, a no-op stub. Nothing
in this codebase ever sets these configstrings to a real value, so
narrating them - correctly-written or not - would only ever report "no
objective" for the whole game. See follow-ups for what would be needed
to do this responsibly instead of shipping narration for a value that's
provably always empty.

## 0007: non-macro popup narration

0003's heuristic only narrates an `ITEM_TYPE_TEXT` item with a literal
`item->text` - true for the `SUBWINDOW`/`SUBWINDOWBLACK`/`LABEL`/`LABELWHITE`
macros, but not for `CVARLABEL` (`etmain/ui/menumacros.h`), which emits an
`ITEM_TYPE_TEXT` item with `text` left unset and a `cvar` to resolve
instead - the same gap ET: Legacy's own 0009 found and fixed there.

Checked directly against this file's own paint code rather than assumed
from ET: Legacy: `Item_Text_Paint` and `Item_Text_AutoWrapped_Paint`
(`ui_shared.c`) both already handle exactly this case when actually
drawing the item - `item->text == NULL && item->cvar != NULL` →
`DC->getCVarString(item->cvar, text, sizeof(text))` - and since
`CVARLABEL` sets `autowrapped`, every `CVARLABEL` item in practice paints
through the second of those two (which does the plain resolution, with no
`WINDOW_TEXTASINT`/`WINDOW_TEXTASFLOAT` formatting - `CVARLABEL` sets
neither flag).

`ETA_NarrateConfirmDialog` now mirrors that same resolution: for each
`ITEM_TYPE_TEXT` item, narrates `item->text` when set, otherwise resolves
`item->cvar` via `DC->getCVarString` into a local buffer and narrates that
instead - so a `CVARLABEL`-built popup line is read exactly as it will be
painted, using the engine's own existing resolution rather than a
narration-specific reimplementation of it.

This closes the "Non-macro popups" follow-up.

## 0008: audio cues (Milestone 5)

The audio cue system (`src/accessibility/audio/audio_cue_system.c`) has
five cue types. Three are wired here - low health, damage direction, and
interaction - re-derived against this release's own `cg_playerstate.c`
and `cg_newDraw.c` rather than ported from ET: Legacy's 0005/0010, which
turned out necessary: this codebase's equivalent functions have genuinely
diverged in shape, not just naming.

- **Low health.** `CG_CheckLocalSounds` (`cg_playerstate.c`) already has
  the exact pain-sound trigger ET: Legacy's own 0005 hooks - `ps->stats[STAT_HEALTH]
  < ops->stats[STAT_HEALTH] - 1` while still alive - so this patch adds
  `ETA_AudioCueSystem_PlayLowHealthCue()` right beside the existing
  `CG_PainEvent`/`cg.painTime` call, gated the same way ET: Legacy gates it
  (`stats[STAT_HEALTH] <= 25`) so routine chip damage doesn't cue every
  hit, only a genuinely critical hit.
- **Damage direction.** This release's `CG_DamageFeedback` has no
  `cg.v_dmg_angle` field the way ET: Legacy's fork does - checked directly,
  not assumed, since `cg.v_dmg_angle` doesn't exist anywhere in this
  codebase's `cg_local.h`. What it does already compute, in the
  "positional" branch (`yawByte`/`pitchByte` not both 255, i.e. a real
  attacker direction, not centered/environmental damage like falling),
  are `front`/`left` - the incoming direction dotted against
  `cg.refdef.viewaxis[0]`/`[1]`, already view-relative since `viewaxis`
  bakes in the player's current view rotation. This is the exact pair
  `CG_DamageBlendBlob` (`cg_view.c`) uses to place its on-screen
  directional blood-blob, just as a 2D screen offset rather than an
  angle - so rather than inventing a new direction computation, this patch
  runs the same `front`/`left` through `atan2(-left, front)` (negating
  `left` because `viewaxis[1]` points left, and the cue convention wants
  positive-right) and `AngleNormalize360`/`RAD2DEG` (both already used
  elsewhere in `cgame`/`q_math.c` for exactly this kind of angle-from-vector
  conversion) to get the `0 = front, 90 = right, 180 = behind, 270 = left`
  bearing `ETA_AudioCueSystem_PlayDamageDirectionCue` expects - reusing
  real, already-computed values instead of re-deriving the direction from
  scratch. No cue fires for the centered/no-direction case, matching how
  the on-screen blood-blob also has no position to show there
  (`vd->damageX = vd->damageY = 0`).
- **Interaction.** `cg.cursorHintIcon`/`cursorHintTime`/`cursorHintFade`
  exist here too, but this release's `CG_CheckForCursorHints` is called
  from inside `CG_DrawCursorhint` (`cg_newDraw.c`) - gated on the
  `cg_cursorHints` cvar being nonzero - not unconditionally from
  `CG_Draw2D` the way ET: Legacy's 0010 patch shows; and "is a hint
  currently visible" is resolved here via the existing
  `CG_FadeColor(cg.cursorHintTime, cg.cursorHintFade)` helper (returns
  `NULL` once `cg.time - cg.cursorHintTime >= cg.cursorHintFade`), not an
  inlined time-window check. `ETA_NarrateInteractionHint(active)` mirrors
  ET: Legacy's edge-detection (fires once per new icon while active, not
  every frame; resets once inactive so the same icon reappearing later
  cues again), called at each of the three points `CG_DrawCursorhint`
  already exits without showing anything (`cg_cursorHints` off, no icon
  resolved, or `CG_FadeColor` says faded out) with `active = qfalse`, and
  once with `active = qtrue` right after both a real icon and a live fade
  color are confirmed - so the cue fires exactly when, and exactly as
  often as, the on-screen hint icon would actually be visible. This
  release's hint enum also has no `HINT_COMPLETED` value (another
  ET: Legacy-only addition, checked directly against `bg_public.h`), so
  unlike ET: Legacy's 0010 there's no icon value to special-case out of
  counting as "new".

**Objective and objective-direction cues are not included - the same
root cause 0006 already found blocks them, confirmed again here rather
than assumed.** ET: Legacy's own 0011 derives both from the identical
`CS_MAIN_AXIS_OBJECTIVE`/`CS_MAIN_ALLIES_OBJECTIVE` + `cgs.oidInfo[]`
lookup 0006 already traced end-to-end in this codebase: the one cgame-side
read of those configstrings (`cg_commandmap.c`) is inside a `/* ... */`
comment block, and the one server-side write
(`G_ScriptAction_SetMainObjective`, `g_script_actions.c`) is a
commented-out no-op. Nothing has changed since 0006's finding - these two
cues would rest on the same provably-always-empty data, so they're left
out rather than shipped as narration that could never say anything. See
0006 above and "Known follow-ups" below for what would need to happen
first.

This closes 3 of Milestone 5's 5 cues for this codebase; the remaining 2
share 0006's objective-status blocker.

## 0009: navigation assistance (Milestone 6)

Milestone 6's three deliverables - stuck detection, distance feedback, and
route correction - all of which turned out implementable here, including
the two that need an objective position. That last part needed a real
finding rather than a workaround, described below.

**Stuck detection** feeds per-frame movement into
`ETA_NavigationSystem_UpdateMovement` from `CG_TransitionPlayerState`
(`cg_playerstate.c`), which narrates "You may be stuck" on its own once
the player stays under its movement threshold long enough. Gated on being
on a playing team and on `ps->pm_type == PM_NORMAL` - checked against this
release's real `pm_type` enum rather than assumed: `PM_NORMAL` is the only
value a live, unfrozen, self-controlled player moves in, with `PM_DEAD`,
`PM_SPECTATOR`, `PM_NOCLIP`, `PM_FREEZE` and `PM_INTERMISSION` covering
everything else. Outside that gate the detector is reset rather than fed
zero movement, so time spent dead or spectating can't itself register as
stuck; `CG_Respawn` resets it too, so a fresh spawn never inherits a stale
timer.

**Distance and route correction** are the interesting half. 0006 and 0008
both found the `CS_MAIN_AXIS_OBJECTIVE`/`CS_MAIN_ALLIES_OBJECTIVE` +
`cgs.oidInfo[]` path that ET: Legacy's own 0011/0013 use to be dead code
here, and 0006's follow-up left open whether "some entirely different
mechanism this release actually uses to designate a 'main' objective"
existed, noting it hadn't been searched for. It has now, and the answer is
twofold:

- There is still **no "main objective" concept** anywhere in this release -
  nothing revives the dead configstrings.
- But there **is** a completely separate, fully live per-team objective
  pipeline that the dead path is unrelated to: the server builds a list of
  `ME_CONSTRUCT`/`ME_DESTRUCT`/`ME_DESTRUCT_2`/`ME_TANK`/`ME_TANK_DEAD`
  map entities per team and sends it as the `entnfo` command
  (`g_teammapdata.c`); `CG_ServerCommand` handles `entnfo` and
  `CG_ParseMapEntityInfo` (`cg_commandmap.c`) parses it into
  `mapEntities[]`; and `CG_DrawMap` draws exactly those entries, filtered
  by `mEnt->team != CG_LimboPanel_GetRealTeam()`, as the command map's
  objective icons. Traced end to end - server writer, wire command, client
  parser, and the drawing code that consumes it - so this is live data,
  not another stub.

So this patch adds `ETA_NearestObjectiveOrigin` (`cg_commandmap.c`, where
that file-static list lives; declared in `cg_local.h`), which walks that
same list with that same team filter and returns the nearest objective's
world origin. Positions are resolved exactly the way `CG_DrawMapEntity`
already resolves them for drawing - `ME_CONSTRUCT`/`ME_DESTRUCT`/
`ME_DESTRUCT_2` through `cg_entities[mEnt->data].lerpOrigin`, and
`ME_TANK`/`ME_TANK_DEAD` through the `ET_OID_TRIGGER` entity in the
current snapshot whose `teamNum` matches `mEnt->data`. `mEnt->x`/`y` are
deliberately not used: `CG_ParseMapEntity` only fills those in for tanks
and players (leaving them stale for the constructible/destructible types)
and quantizes them to 128-unit steps even then. One thing this patch does
*not* copy from the engine: `mEnt->data` arrives from the server and
`CG_DrawMapEntity` indexes `cg_entities[]` with it unchecked, so the new
lookup range-checks it against `MAX_GENTITIES` first.

`CG_AccessibilityStatus_f` (`cg_consolecmds.c`, from 0005) then announces
the distance to that objective and a turn-left/right/ahead correction
toward it, using `AngleSubtract` - the same helper `cg_draw.c`'s mortar
reticle already uses to express one yaw relative to another.

> **Corrected after 0014.** As first written, this patch had the
> left/right test backwards: it told the player to turn *left* when the
> objective was on their right, and vice versa. The sign was carried over
> from ET: Legacy's own 0013 without being checked against this codebase's
> yaw convention, and nothing in the toolchain here could catch it - a
> mirrored comparison compiles and links perfectly. It surfaced while
> deriving 0014's cue bearing, when the convention was finally tested
> numerically against the engine's own `q_math.c` (see 0014). The patch
> file has been fixed in place rather than corrected by a later patch, so
> that nobody applying 0001-0009 gets a navigation aid that confidently
> points the wrong way. Yaw increases counterclockwise here, so a target
> to the player's left sits at a *higher* yaw: `relativeYaw > 0` means
> turn left.

Both stay
**on-demand only**, on the same bindable command as the rest of the status
report: a walking player's bearing to an objective changes continuously,
so announcing it automatically would be noise. The +-15 degree "ahead"
band is a judgment call, not a value found in this engine - no comparable
on-course tolerance exists here to match it against.

`ETA_QU_TO_METERS` (`cg_local.h`) started out the same way: no
units-per-meter constant exists in this codebase, so the conversion took
id Tech 3's commonly cited 1 unit = 1 inch convention on faith. It is no
longer on faith. The engine states the size of a human being in five
independent places - the player bounding box and the standing, crouched
and prone view heights - and under this conversion they come out 1.83 m
standing, 1.63 m to the eye, 1.22 m crouched, 1.02 m to the eye crouched
and 0.41 m to the eye prone. Five anatomical measurements, all right to
a few centimetres, from constants never chosen with metres in mind.
`tests/distance_scale_test.py` reads them out of this tree on every run
(the values are identical to ET: Legacy's) and fails if any lands
outside a human range.

**"Nearest" is this integration's own choice of navigation target**, and
worth being explicit about: the engine ranks these objectives in no way at
all, so nearest-first is a navigation-aid decision, not an engine concept
being surfaced. For the distance/route-correction deliverables that reads
naturally - a player asking "where do I go" wants the closest thing they
can act on. It would read much less naturally for the *objective status*
and *objective audio cue* deliverables still outstanding from 0006/0008,
which want a stable "this is your objective, and it just changed" event
rather than something that changes as you walk past things - so those are
deliberately still not implemented off this data. See the follow-ups.

This closes Milestone 6 for this codebase.

## 0010: SCons build-system wiring

Adds an `ACCESSIBILITY` build option to the Linux/SCons build, so the
modules can actually be built with the feature on rather than by hand.
`ACCESSIBILITY=1` makes `SConscript.cgame` and `SConscript.ui` define
`FEATURE_ACCESSIBILITY`, add `accessibility-mode/src/accessibility` to
`CPPPATH`, and append the layer's thirteen sources to that module's source
list. Default is `0`, and the option is added to `SConstruct`'s
`serialized` list so it persists in `site.conf` like `TARGET_CGAME` and
the rest.

Two decisions worth naming:

- **The sources are compiled into the module rather than linked from the
  `eta_accessibility` static library** that `accessibility-mode`'s own
  CMake builds. Linking the prebuilt library would mean the user has to
  match this build's architecture by hand - `SConstruct` defaults to
  `gcc -m32`, and a default CMake build is 64-bit, so the two would not
  link and the failure would be confusing. Compiling the sources in the
  module's own environment makes that mismatch impossible. It is also the
  configuration actually verified here (below). All thirteen sources were
  confirmed to compile under the engine's own `-std=gnu90` - the
  accessibility library's CMake asks for C99, but nothing in it needs C99,
  and the two `platform/windows/` files are `#ifdef _WIN32`-guarded, so
  they become empty translation units on Linux rather than failing.
- **The new block guards on `ACCESSIBILITY` with `try:`/`except:`**, which
  copies `SConscript.cgame`'s existing `GAMERANGER` block verbatim in
  shape - that option has the same "isn't exported in all usage paths"
  problem, and the same fix. Paths are resolved to absolutes with
  `os.path.abspath` (both SConscripts already `import os`) because
  `accessibility-mode` sits *beside* `src/` rather than under it, and the
  relative source entries in these files go through `BuildDir` remapping
  that an out-of-tree path would interact with in ways that could not be
  tested here. Absolute paths sidestep that question entirely.

**What is and isn't verified matters more than usual for this patch**, so
plainly: the SCons scripts have still never been executed. This release's
`SConstruct` is hard Python 2 (it imports `commands`, `StringIO` and
`popen2`, and calls `EnsureSConsVersion(0, 96)`), Python 2 has been
end-of-life since 2020, and it is not available here. What *was* done
instead, in place of hand-waving:

- All three edited files parse under the **Python 2 grammar** (via
  `lib2to3`, which still ships a Py2 parser), so the added code is at
  least syntactically valid for the interpreter that would run it.
- The SConscripts' own logic was **executed in isolation** with SCons
  stubbed out, in all three states - `ACCESSIBILITY` set to `1`, set to
  `0`, and not defined at all (the `except:` path). Off and absent produce
  a byte-identical source list and `CPPDEFINES` to the unpatched files; on
  produces exactly twelve extra sources, all of which resolve to files
  that exist, plus the one define and one include path.
- Those exact inputs were then **really compiled and linked** - see below.

What that leaves genuinely unverified is SCons's own behaviour: whether
`SharedLibrary` and `BuildDir` do what is intended with these inputs.
`build-modules.py` in this directory exists to cover that gap - see the
next section.

## 0011: MSVC project wiring

Adds the thirteen accessibility sources to `cgame/cgame.vcproj` and
`ui/ui.vcproj`, in their own `accessibility` filter under Source Files,
plus a `src/accessibility.vsprops` property sheet carrying the define,
include directory and Windows libraries.

The shape of this patch is dictated by one constraint: **a VC++ 2008
project cannot be validated here at all** - there is no MSVC, and unlike
the SCons scripts there is no way to execute the logic in isolation. So it
is built to be incapable of breaking anything it isn't explicitly turned
on for:

- The added `<File>` entries are `ExcludedFromBuild="true"` in **both**
  shipped configurations, copying `..\game\bg_lib.c`, which both projects
  already carry that way. Verified structurally: every added entry's XML
  shape is identical to the `bg_lib.c` entry's, and the `<Configuration>`
  blocks are byte-identical to upstream's after patching - so a default
  Release or Debug build compiles and links exactly what it did before.
- `accessibility.vsprops` is a **new file that nothing references**. It is
  attached through the IDE's Property Manager when wanted, so it cannot
  affect a build that doesn't opt in.

Excluded-by-default is not a stylistic choice. The accessibility sources
are not themselves guarded by `FEATURE_ACCESSIBILITY` - that guard is in
the engine files - so building them unconditionally would compile and link
thirteen files into every build and drag in the SAPI code's `ole32` /
`oleaut32` / `winmm` dependencies, breaking the default link for everyone.

### Enabling it in Visual Studio

Two steps per project, both in the IDE:

1. **Property Manager** (View → Property Manager) → right-click the
   configuration → *Add Existing Property Sheet* → `src\accessibility.vsprops`.
2. **Solution Explorer** → select the thirteen files under Source Files →
   `accessibility` → Properties → *Excluded From Build* → **No**.

If the property sheet doesn't take, the same three settings entered
directly on the project (with *All Configurations* selected) are exactly
equivalent:

- C/C++ → Preprocessor → Preprocessor Definitions: add `FEATURE_ACCESSIBILITY`
- C/C++ → General → Additional Include Directories: add
  `$(ProjectDir)..\..\accessibility-mode\src\accessibility`
- Linker → Input → Additional Dependencies: add
  `ole32.lib oleaut32.lib winmm.lib`

**Neither path has been run.** The property sheet's format, and whether
VC++ 2008 merges its `PreprocessorDefinitions` into the project's rather
than replacing them, are both written from knowledge of the format and are
unverified here - which is why the manual settings are documented beside
it rather than instead of it. What *is* checked is that both `.vcproj`
files and the `.vsprops` are well-formed XML, that the twelve
`RelativePath` values resolve to real files in the layout the submodule
instructions produce, that tabs/LF/ASCII formatting is unchanged so the
files stay round-trippable by the IDE, and that the file list matches the
SCons wiring and the library's own CMake exactly - all four agree on the
same thirteen sources.

0011 leaves enabling as two IDE steps. Patch 0012 below turns that into a
configuration dropdown; 0011 still stands on its own if you would rather
not add configurations, and its property sheet remains the documented
alternative.

## 0012: dedicated MSVC configurations

Adds `Release Accessibility|Win32` and `Debug Accessibility|Win32` to
`cgame.vcproj` and `ui.vcproj`, and the matching solution configurations
to `wolf.sln`. Selecting one from the Visual Studio configuration dropdown
builds both modules with the accessibility layer - no property sheet, no
per-file changes.

It turns out this release already contains the exact pattern this needs.
The solution ships **four** configurations, not two: alongside
`Debug|Win32` and `Release|Win32` there are `Debug Dedicated|Win32` and
`Release Dedicated|Win32`, and only the `wolf` project actually defines
Dedicated configurations of its own - every other project maps those
solution configurations to its plain `Debug|Win32`/`Release|Win32`. That
is precisely the shape needed here: two projects carry real new
configurations, the other six fall back. So this is following an existing
convention in the file rather than inventing one.

Each new project configuration is a clone of the shipped `Release`/`Debug`
block with four changes and nothing else:

- `FEATURE_ACCESSIBILITY` appended to the compiler's
  `PreprocessorDefinitions`,
- `AdditionalIncludeDirectories` pointing at the accessibility headers,
- `ole32.lib oleaut32.lib winmm.lib` appended to the linker's
  `AdditionalDependencies`,
- every output path retargeted from `Release`/`Debug` to
  `ReleaseAccessibility`/`DebugAccessibility`, so objects, PDBs, map files
  and the DLL land beside the normal build instead of overwriting it. The
  DLLs keep their required names (`cgame_mp_x86.dll`, `ui_mp_x86.dll`),
  just in their own directory.

Two details that would have broken the build if missed, both caught by
checking rather than assumed:

- **`..\game\bg_lib.c` is `ExcludedFromBuild` in the shipped
  configurations**, and a new configuration with no `FileConfiguration`
  entry for it would have compiled it for the first time. It is excluded
  in the new configurations too.
- **cgame and ui are not built in the solution's plain `Debug`
  configuration** (they have `ActiveCfg` but no `Build.0` there). The new
  configurations deliberately diverge and set `Build.0` for both -
  building them is the entire point of selecting one. Every other project
  mirrors its plain configuration exactly, including the projects that are
  deliberately not built (`extractfuncs` in all configurations, `game` in
  Debug).

### What was checked

Still no Visual Studio, so this remains structural - but a solution file
supports rather more structural checking than a lone project does:

- Both `.vcproj` files and the `.sln` parse; the `.sln` mapping section
  was rebuilt from parsed data only after confirming the ordering model
  reproduced the original section **byte-for-byte**, which is what makes
  "nothing was silently reordered or dropped" a checked claim.
- **Every (project, solution configuration) pair - all 8 projects across
  all 6 configurations - maps to a project configuration that actually
  exists in that project's `.vcproj`.** A dangling mapping here is the
  classic way a solution breaks, and there are none.
- No pre-existing mapping was dropped or altered; 29 were added, all for
  the two new configurations. Everything in the `.sln` outside the two
  edited sections is byte-identical.
- The shipped `Release|Win32` and `Debug|Win32` project configurations are
  byte-identical to upstream's, attribute by attribute, tools included -
  so an existing build is provably unaffected.
- Each new configuration was diffed attribute-by-attribute against the
  block it was cloned from, confirming *only* the four intended changes.
  In particular the `VCMIDLTool` and `VCResourceCompilerTool`
  `PreprocessorDefinitions` (which also carry `NDEBUG`/`_DEBUG`) are
  untouched - the edits are tool-scoped, not a global search-and-replace.
- Tabs, LF endings and ASCII-only content preserved in all three files, so
  the IDE can round-trip them.
- The Linux build is unaffected, re-confirmed with `build-modules.py`
  after applying 0012.

What is still unverified is the same thing as in 0011, and it is the
important one: **no Visual Studio has opened any of this.** The checks
above establish internal consistency, not that VC++ 2008 accepts the
result.

## 0013: objective status narration

Milestone 4's last HUD deliverable. The `accessibilityStatus` command now
also speaks the player's team's objectives by name:
`"Objectives: Command Post, Main Gate"`.

0006 and 0008 both had to defer this because the
`CS_MAIN_AXIS_OBJECTIVE`/`CS_MAIN_ALLIES_OBJECTIVE` path ET: Legacy's own
0011 uses is dead code here. 0009 then found the live replacement - the
`entnfo`/`mapEntities[]`/command-map pipeline - and left one question
open: what should be narrated, given this release designates no "main"
objective. That question is now answered, and the answer came from
reading the data rather than from picking a preference.

**What the client can and cannot know.** The open question in 0009's
follow-up was whether completion state is available, so that the narration
could report only *outstanding* objectives. Traced, and it is not:

- Objectives stop being refreshed into the team list once their entity
  leaves `STATE_DEFAULT` (`G_UpdateTeamMapData`'s
  `ET_CONSTRUCTIBLE_INDICATOR`/`ET_EXPLOSIVE_INDICATOR` cases,
  `g_teammapdata.c`) - but they are **not** removed. Every
  `G_FreeMapEntityData` call in the game module is about landmines, not
  objectives, and the staleness sweep in `G_SendMapEntityInfo` only frees
  `ME_PLAYER`/`ME_PLAYER_DISGUISED` entries.
- That sweep does set `mEnt->status` (1 for stale, 2 for fresh), which is
  exactly the signal that would be wanted - but `status` is never sent to
  the client. It is commented out of the client's own `mapEntityData_t`
  (`cg_local.h`) and `CG_ParseMapEntity` does not parse it.
- `oidInfo`'s two candidate fields don't carry it either, contrary to what
  0009's follow-up guessed: `objflags` is parsed into `cgs.oidInfo[]` and
  then never read anywhere in cgame, and `spawnflags` is a category
  bitfield (`1<<4` objective, `1<<5` HA cabinet, `1<<6` command post) that
  `CG_DrawMapEntity` uses for its filter checkboxes, not a state.

So a completed objective keeps being sent, with nothing marking it
completed. **The command map has the same blind spot** - it draws these
entries without any liveness test - which settles the design question:
narrating the full list is not a compromise, it is exactly parity with
what a sighted player sees on their command map. Reporting "outstanding
objectives" would be claiming knowledge the client doesn't have.

`ETA_TeamObjectiveNames` (`cg_commandmap.c`, where the file-static list
lives) therefore returns every objective name for the team, resolved the
way `CG_DrawMapEntity` resolves the command map's own hover label
(`name = oidInfo->name`). One subtlety mirrored rather than unified: that
function indexes `cgs.oidInfo[]` through the entity's `modelindex2` for
the constructible/destructible types but through `mEnt->data` directly for
tanks. Indices are range-checked against `MAX_OID_TRIGGERS` and
`MAX_GENTITIES` before use, since both come from the server, and entries
whose `oidInfo` has no name yet are skipped.

Reading the whole list is reasonable only because this stays **on demand**,
on the same bindable command as the rest of the status report - it is the
spoken equivalent of glancing at the command map, not a running
commentary.

**One lead left for whoever takes the objective audio cues.** The
indicator entities are spawned `SVF_BROADCAST` (`g_trigger.c`), so they
reach every client regardless of PVS, which makes
`cg_entities[mEnt->data].currentValid` a *candidate* completion test -
`cg_commandmap.c` already uses `currentValid` that way for players. It is
deliberately not used here: the command map doesn't apply it to
objectives, so narration that did would diverge from what's drawn, and
whether the indicator entity actually disappears on completion could not
be tested. Worth confirming in a running game before building the cues on
it.

This completes Milestone 4.

## 0014: objective audio cues (completing Milestone 5)

The last two of the audio cue system's five cues. Both fire in two
places: on the `accessibilityStatus` request, alongside the spoken report,
and once on respawn.

**Why those triggers, and not an objective change.** ET: Legacy's own 0011
fires these when the team's main objective changes. That event does not
exist here: there is no "main objective" (checked four times now), and
0013 established that objective *completion* state never reaches the
client at all - so nothing in this codebase fires when an objective
becomes, or stops being, the one to head for. Cueing off the *nearest*
objective changing instead would chatter as the player walks past things.
What this release does offer is two real moments when a player actually
wants objective orientation:

- **On request.** The status command already speaks distance and a
  turn-left/right instruction; the directional cue adds a sound the player
  can simply turn toward, which is a different and more direct thing than
  parsing "turn left". This needs no event at all.
- **On respawn**, hooked in `CG_TransitionPlayerState` right after the
  existing `CG_Respawn` call, where `ps` is already in scope (the same
  spot 0008/0009 hook). Respawn is discrete, happens once per life so it
  cannot chatter, and is precisely when a blind player has no idea which
  way they are facing. It stays silent when the client has no objective
  list yet, or when the player is not on a playing team.

**The bearing convention was tested, not reasoned about** - and it is just
as well. Both cues use `AngleNormalize360( viewYaw - targetYaw )`, which
is the *opposite* order from ET: Legacy's 0011. Compiling a throwaway
harness against this engine's own `q_math.c` and placing a target to the
player's right showed why: `targetYaw - viewYaw` yields 270 for something
on the right, while `viewYaw - targetYaw` yields 90 - and 90 = right is
the convention 0008's damage-direction cue already established here.
Porting ET: Legacy's expression verbatim would have produced cues
mirrored left-for-right, which is worse than no cue at all for a player
relying on them.

That same harness is what exposed the mirrored turn instruction in 0009
(see the note there). Two sign errors in the same area, one shipped and
one caught before shipping, is a fair summary of how easy this particular
mistake is: nothing about a mirrored direction fails to compile, fails to
link, or looks wrong in a diff.

This completes Milestone 5, and with it every deliverable defined for
this integration.

## 0016: tell the player the way out, not that they are stuck

The mirror of ET: Legacy 0023, and it had to be: the stuck detector lives
in the shared accessibility library, and
`ETA_NavigationSystem_UpdateMovement` gained a parameter there.

Both halves of the old behaviour were wrong. It asked only whether the
player had moved recently - ordinary in a shooter, so it fired during
normal play - and it measured a single frame's travel against a fixed
distance, which is a speed test with the frame rate as its hidden units,
so walking and crawling read as motionless.

The player's own movement input now gates the question
(`trap_GetUserCmd`), and what gets said is the objective, its distance
and which way to turn, rather than a label for the predicament.

`CG_AccessibilityNarrateObjective` is hoisted out of
`CG_AccessibilityStatus_f` and shared with the stuck detector, so both
describe an objective identically - and it now says "No current
objective" rather than going quiet when there is none.

## 0017: find an objective on every kind of map

The mirror of ET: Legacy 0024, for the part of it that applies here.

The ET: Legacy defect itself cannot happen in this tree: this release
designates no main objective at all, so the navigation here has always
read the command map's own `mapEntities[]` list. But finding it exposed
three holes in that reading, each of which goes quiet in exactly the same
way - fine on the maps that happen not to hit it, silent on the ones that
do.

- **`ME_COMMANDMAP_MARKER` was never placed.** `G_UpdateTeamMapData_CommandmapMarker`
  emits one for every objective trigger flagged `AXIS_OBJECTIVE` or
  `ALLIED_OBJECTIVE`, and `CG_DrawMapEntity` positions it from
  `cgs.oidInfo[]` because it has no entity of its own. The navigation
  skipped the type entirely, so a map whose objectives are all markers
  had nothing to point at.
- **Health and ammo cabinets counted as objectives.** They ride in the
  same list, marked by spawnflag bit 5 - the bit `CG_DrawMapEntity`
  filters them by. A cabinet is somewhere to go; it is never the
  objective.
- **A constructible that had left the snapshot was still read.**
  `CG_DrawMapEntity` reaches that type only from inside `CG_DrawMap`'s
  own `currentValid` check; nothing guarded this path. `lerpOrigin` on a
  stale entity is wherever it was last seen, which is a confident wrong
  direction rather than a missing one.

Position resolution now lives in one helper both the navigation target
and the spoken objective list go through, so the three cannot drift
apart again. On top of it, matching 0024: entries the map flags
`IS_OBJECTIVE` win over ones it does not before distance is considered,
the chosen target is sticky unless another is a quarter closer, and an
objective with no `shortname` is spoken as "Objective" rather than
skipped.

`tests/objective_source_test.py` runs against this tree too. It reads the
server's own "only the objectives" filter out of `g_teammapdata.c` and
fails the build if the narration cannot place one of the types it names.

## 0018: speak the player's stance

The mirror of ET: Legacy 0025, and a straight one: this tree carries the
same `PMF_DUCKED` / `EF_PRONE` flags, sets `PMF_DUCKED` on the way into
prone in the same place with the same comment, and predicts posture
locally the same way.

`ETA_NarrateStanceChange` is added to `CG_DrawActive`, reading
`cg.predictedPlayerState` (`CG_PredictPlayerState` runs before it in
`CG_DrawActiveFrame`), testing `EF_PRONE` before `PMF_DUCKED` because
prone sets both, and speaking through the library's
`ETA_HudNarrator_SpeakStance` enum so both integrations use the same
three words.

`tests/stance_narration_test.py` runs against this tree too, reading the
flag overlap out of this tree's own `bg_pmove.c`.

## 0019: name every weapon, and call out the approach

The mirror of ET: Legacy 0026.

**Weapon names.** This release has no weapon description field at all, so
the narration already read `pickup_name` and grenades were never silent
here. But two of its pickup names are internal tokens rather than
anything to say aloud - `WP_MEDKIT` is `"medicheal"` and
`WP_SMOKE_MARKER` is `"smokeGrenade"` - and both are things a player
holds and switches to. `CG_AccessibilityWeaponName` (`cg_weapons.c`)
names those two and falls through to `pickup_name` for everything else,
so both integrations say the same words for the same kit.

**Approach callouts.** `ETA_NarrateObjectiveApproach` (`cg_draw.c`)
feeds the live distance to the shared library every frame, which speaks
only on crossing 100, 50, 25 or 10 metres inward. The milestones, the
re-arm margin and the "announce the real distance, not the milestone"
rule all live in the library, so the two integrations cannot drift into
announcing at different points. `eta_objectiveCallouts` (default 1) turns
it off, registered through this tree's `cvarTable`.

## 0020: speak what the player picked up

The mirror of ET: Legacy 0027, and a close one: this tree has the same
`CG_ItemPickup` funnel, reached by the same two pickup event paths and
already filtered to the local player, and the same `CG_PickupItemText`
behind its popup.

The differences are local: the popup here is not run through a
translation layer, the item type comes from `bg_itemlist[itemNum]`
directly, `giTag` stands in for `giWeapon`, and this tree's
`CG_PlayerAmmoValue` takes three arguments rather than five.

`tests/pickup_narration_test.py` runs against this tree too.

## 0021: say how much a pickup gave, and when it gave nothing

The mirror of ET: Legacy 0028, and a straight one: the same per-frame
sample of reserve and health from `CG_DrawActive`, the same
positive-deltas-only sum, and the same "already full" when a pack gave
nothing. This tree's `CG_PlayerAmmoValue` still takes three arguments
and the item type still comes from `bg_itemlist[itemNum]`.

`tests/pickup_narration_test.py` checks the sampling placement here too.

## 0022: say what is in front of you

The mirror of ET: Legacy 0029. This tree carries the same `cg.zoomed` and
`cg.zoomedBinoc`, the same `CG_Trace` and `MASK_SHOT`, and the same
surface flags, so the probe and its wording are the same.

One difference caught by the build rather than by reading: this tree's
`cg_draw.c` did not include `speech/speech_manager.h`, and the
report-batching calls compiled as implicit declarations. The
warning-set comparison in `build-modules.py` is what found it - the
feature-on build had two warnings the feature-off build did not.

`tests/look_ahead_test.py` runs against this tree too.

## 0023: describe the ground and what is right ahead

The mirror of ET: Legacy 0031, and the shapes line up closely.

`EV_FOOTSTEP` in this tree carries the same `eventParm` and the same
zero-means-the-character's-default branch, so `ETA_NarrateFooting` sits
inside both arms for the same reason. The `footstep_t` enum has the same
nine members in the same order - checked by `tests/footing_test.py`
rather than assumed - and `cg_main.c` registers the same
`sound/player/footsteps/*.wav` set, which is what the word table is
matched against.

The only real difference is that this tree plays the sound through
`CG_StartFootStepSound( classInfo, ... )` rather than
`trap_S_StartSound` directly, which does not change where the narration
hangs.

`ETA_DescribeLookAhead` took the same range and out-trace parameters,
and `ETA_NarrateObstacleAhead` is the same function with this tree's
brace style. `eta_environmentCallouts` joins the cvar table rather than
a `trap_Cvar_Register` call, as everything else here does.

## 0024: say which way you are facing

The mirror of ET: Legacy 0032, sharing the conversion itself - it lives
in `hud_narrator.c`, not in either integration, precisely so the two
engines cannot drift apart on which way north is.

**What this tree cannot do is check it as strongly.** The ring of
cardinal points around the square compass is an ET: Legacy addition, so
there is no in-engine answer here to compare against.
`tests/compass_test.py` falls back to the convention that ring rests on
- the engine's own axes put yaw 0 along +x and yaw 90 along +y, so east
and north respectively - plus that the mod's eight points are evenly
spaced and walk the ring in one direction. That is weaker, stated
plainly in the test, and acceptable only because the strong form runs on
the other engine over exactly the same shared code.

`CG_AccessibilityNarrateObjective` gains the same *"Objective lies
north, you are facing south"* line.

## 0025: say when you lean out and when you come back

The mirror of ET: Legacy 0033. `ps->leanf` exists here with the same
meaning and the same sign convention - positive right, negative left,
written in a comment in `PM_UpdateLean` and nowhere else - and this
tree's `PM_UpdateLean` refuses a lean in the same situations, so reading
the state rather than the key is right here for the same reason.

## 0026: keep keyboard focus when the cursor has not moved

The mirror of ET: Legacy 0034, and this tree has the defect in its older
form. `Menu_HandleKey` in `ui_shared.c` opens with the same unconditional

```c
Menu_HandleMouseMove( menu, DC->cursorx, DC->cursory );  // NERVE - SMF - fix for focus not resetting on unhidden buttons
```

without even the listbox exception ET: Legacy grew later, so a parked
cursor takes focus back on every key press here too. Same one-condition
fix, same helper, same rule that the cursor wins again as soon as it
moves.

There is no counterpart to 0035 in this tree: the default binds are an
ET: Legacy-only patch (0018), so there is no table here to add `weapalt`
to.

## 0027: let the scope report finish

The mirror of ET: Legacy 0036, plus a defect this tree had on its own.

**The flag nothing writes.** `cg_local.h` declares both `cg.zoomed`
(line 847) and `cg.zoomedScope` (line 849), and the client assigns only
the second - `CG_SetSniperZoom` sets it for `WP_FG42SCOPE`,
`WP_GARAND_SCOPE` and `WP_K43_SCOPE` and clears it otherwise.
`cg.zoomed` appears nowhere on the left of an assignment in the whole
client; the only reader was this mod. So the scope branch of
`ETA_NarrateZoom` could never be taken here and this tree has never
announced a scope at all. It compiled, linked and passed every check.

**And the same purge.** Scoping is a weapon change here too, so the
announcement in `CG_TransitionPlayerState` arrived after the scope line
and cut it off. `ETA_IsScopeToggle` stands it down, deriving the three
scoped weapons from the ones `CG_SetSniperZoom` itself switches on
rather than from a list invented here.

`tests/zoom_state_test.py` covers both: it resolves which `cg.*` flag
the scope branch reads and fails if nothing in the client assigns it.

## Applying it

```sh
# From the root of an id-Software/Enemy-Territory checkout at 40342a9:
git submodule add https://github.com/alexzgeorgian/Wolfenstein-Enemy-territory-accessibility-mode.git accessibility-mode
git -C accessibility-mode checkout 229ba0eeb3fc86b50f264512d56597d3ca31d0dd
git apply --index integration/id-software/0001-wire-menu-focus-narration.patch
git apply --index integration/id-software/0002-wire-setting-value-narration.patch
git apply --index integration/id-software/0003-wire-confirmation-dialog-narration.patch
git apply --index integration/id-software/0004-wire-tri-checkbox-narration.patch
git apply --index integration/id-software/0005-wire-hud-status-narration.patch
git apply --index integration/id-software/0006-wire-respawn-timer-narration.patch
git apply --index integration/id-software/0007-wire-non-macro-popup-narration.patch
git apply --index integration/id-software/0008-wire-audio-cues.patch
git apply --index integration/id-software/0009-wire-navigation-assistance.patch
git apply --index integration/id-software/0010-wire-scons-build-system.patch
git apply --index integration/id-software/0011-wire-msvc-projects.patch
git apply --index integration/id-software/0012-wire-msvc-configurations.patch
git apply --index integration/id-software/0013-wire-objective-status-narration.patch
git apply --index integration/id-software/0014-wire-objective-audio-cues.patch
git apply --index integration/id-software/0015-wire-runtime-init-and-repeat-stop-commands.patch
git apply --index integration/id-software/0016-report-the-way-out-instead-of-stuck.patch
git apply --index integration/id-software/0017-find-an-objective-on-every-kind-of-map.patch
git apply --index integration/id-software/0018-speak-the-players-stance-when-it-changes.patch
git apply --index integration/id-software/0019-name-every-weapon-and-call-out-the-approach.patch
git apply --index integration/id-software/0020-speak-what-the-player-picked-up.patch
git apply --index integration/id-software/0021-say-how-much-a-pickup-gave.patch
git apply --index integration/id-software/0022-say-what-is-in-front-of-you.patch
git apply --index integration/id-software/0023-describe-the-ground-and-what-is-right-ahead.patch
git apply --index integration/id-software/0024-say-which-way-you-are-facing.patch
git apply --index integration/id-software/0025-say-when-you-lean-out-and-when-you-come-back.patch
git apply --index integration/id-software/0026-keep-keyboard-focus-when-the-cursor-has-not-moved.patch
git apply --index integration/id-software/0027-let-the-scope-report-finish.patch
```

### Building it

With 0010 applied, the SCons build takes an `ACCESSIBILITY` option:

```sh
cd src
scons ACCESSIBILITY=1 TARGET_CGAME=1 TARGET_UI=1
```

That needs **Python 2 and a SCons old enough to run this release's build
scripts**, which is the same requirement the unmodified release has always
had - 0010 doesn't add it. If you don't have that (it was not available
where this was developed, so those scripts have never actually been run -
see 0010), `build-modules.py` in this directory builds the two modules
directly with no SCons at all:

```sh
integration/id-software/build-modules.py path/to/enemy-territory/src
```

It reads the source lists - including the accessibility list patch 0010
adds - straight out of `SConscript.cgame`/`SConscript.ui`, so it builds
exactly what the SCons wiring specifies, with `SConstruct`'s own release
flags. It builds each module with the feature off and on, links both with
`--no-undefined`, and fails if the two configurations produce different
compiler warnings. It builds 64-bit by default (pass `--m32` to match
`SConstruct`'s `gcc -m32`, if you have 32-bit libc installed).

It is a verification harness and a fallback, not a replacement build
system: it builds `cgame` and `ui` only - not the engine, game module,
bspc or curl - and has no dependency tracking.

For Windows, open `src/wolf.sln` and pick **Release Accessibility** (or
**Debug Accessibility**) from the configuration dropdown - patch 0012 adds
those, and they build `cgame` and `ui` with the layer compiled in, into
their own `ReleaseAccessibility`/`DebugAccessibility` output directories.
The plain Release and Debug configurations are untouched and build exactly
what they did before. 0011 alone (files plus a property sheet, enabled by
hand) remains a workable alternative if you would rather not use the extra
configurations. Neither has been run through Visual Studio - see 0011 and
0012 for exactly how far each was verified.

## What was actually validated here

Against the real cloned engine source (`id-Software/Enemy-Territory@40342a9`):

- `src/ui/ui_shared.c` with all five UI-layer patches applied (0001-0004,
  0007) compiles cleanly (`gcc -fsyntax-only -std=gnu90`) both with
  `-DFEATURE_ACCESSIBILITY` and without it, and under both `-DUIDLL` and
  `-DCGAMEDLL` (the two `CPPDEFINES` values `SConscript.ui`/`SConscript.cgame`
  actually pass) - confirming the integration is a true no-op when the
  feature is off, and that `item->text` (`const char *`) and
  `parent->window.name` (`const char *`) line up with
  `ETA_MenuNarrator_OnFocusChanged`'s signature, `Item_Multi_Setting`'s
  return / `va()`'s return (both `const char *`) line up with
  `ETA_MenuNarrator_OnValueChanged`'s, and the `char[]` buffer
  `ETA_NarrateConfirmDialog` builds lines up with
  `ETA_MenuNarrator_OnConfirmDialogShown`'s, including 0007's added
  `DC->getCVarString` resolution path. `src/game/bg_misc.c`,
  `src/cgame/cg_draw.c`, `src/cgame/cg_consolecmds.c`, and
  `src/cgame/cg_playerstate.c` (0005), and 0006's further revisions to
  `cg_draw.c`, were all compiled the same way under `-DCGAMEDLL` (and
  `bg_misc.c`/`bg_public.h`, shared into all three modules, also under
  `-DGAMEDLL` and `-DUIDLL`), confirming `gitem_t.pickup_name`
  (`const char *`) lines up with `ETA_HudNarrator_SpeakWeapon`'s
  signature and `CG_CalculateReinfTime`'s `int` return lines up with
  `ETA_HudNarrator_SpeakRespawn`'s. The baseline files (before any patch)
  were compiled the same way first, to confirm any warnings seen are
  pre-existing in the original 2010 release (three real bugs:
  `Item_TextField_Paint` and `BG_PanelButton_RenderEdit` each compare a
  pointer against `'\0'` instead of dereferencing it first; `CG_DrawFollow`
  passes a translated string straight to `sprintf` as the format argument)
  and not something these patches introduced.
- `src/cgame/cg_playerstate.c` (0008's low-health and damage-direction
  cues) and `src/cgame/cg_newDraw.c` (0008's interaction cue) were also
  compiled under `-DCGAMEDLL`, both with and without
  `-DFEATURE_ACCESSIBILITY`, confirming `atan2`/`AngleNormalize360`/
  `RAD2DEG`'s `float`/`double` results narrow to
  `ETA_AudioCueSystem_PlayDamageDirectionCue`'s `int` parameter as
  intended and that `cg_newDraw.c`'s new `ETA_NarrateInteractionHint`
  static (referencing `cg.cursorHintIcon`, `HINT_NONE`) compiles cleanly
  against this file's own real cursor-hint state.
- 0009's four touched files (`cg_local.h`, `cg_commandmap.c`,
  `cg_consolecmds.c`, `cg_playerstate.c`) were compiled under `-DCGAMEDLL`
  with and without `-DFEATURE_ACCESSIBILITY`, as were the other cgame
  files that include the modified `cg_local.h` (`cg_draw.c`,
  `cg_newDraw.c`, `cg_main.c`, `cg_limbopanel.c`) - every one produced an
  identical diagnostic count both ways, which is what makes "true no-op
  when the feature is off" a checked claim rather than an assumed one.
- All fourteen patches were checked to apply cleanly with
  `git apply --check` (then applied for real, 0001 through 0014 in
  sequence) against a completely fresh clone of the base commit, not just
  the working checkout they were developed against. With all of them
  applied the modules still build and link via `build-modules.py`, warning
  sets still identical with the feature off and on, and `nm` shows the
  objective narration and cue symbols only in the enabled build.
- **The direction convention was checked numerically**, by compiling a
  throwaway harness against this engine's own `q_math.c` and asking it
  what bearing a target to the player's right produces. That is what
  established `viewYaw - targetYaw` as the correct order for 0014's cues,
  and what exposed the mirrored turn instruction in 0009. It is the one
  class of defect in this integration that no amount of compiling,
  linking or diff-reading would have caught.
- Both `Item_SetFocus` call sites reachable via keyboard (inside
  `Menu_SetPrevCursorItem` and `Menu_SetNextCursorItem`, `ui_shared.c`)
  were read directly to confirm Tab-navigation reachability, matching the
  ET: Legacy integration's stated scope, rather than assumed from the
  fork's behavior. Likewise, `Item_CheckBox_HandleKey`,
  `Item_YesNo_HandleKey`, `Item_Multi_HandleKey`/`Item_Multi_Setting`, and
  `Item_Slider_HandleKey` were all read directly in this file before 0002
  assumed their behavior matched ET: Legacy's baseline, and the
  `SUBWINDOW`/`SUBWINDOWBLACK`/`LABEL`/`LABELWHITE` and
  `TRICHECKBOXACTIONMULTI` macro *definitions* (`etmain/ui/menumacros.h`)
  were read directly before 0003/0004 relied on them, as was
  `Item_CheckBox_Paint`'s existing `Item_Multi_Setting(item)` call for
  0004 - though, unlike 0001/0002, without a concrete shipped `.menu` file
  in this repository to also check any of that against (see 0003/0004
  above). For 0005, `bg_pmove.c`'s own weapon-validity guard was read and
  its excluded range (16-22) cross-checked against the real `weapon_t`
  enum and `CG_PlayerAmmoValue`'s own per-weapon handling before
  concluding that guard wasn't the right one to reuse (it would have
  wrongly excluded pliers/medkit/binoculars/smoke-marker) - not assumed
  from its name. For 0006, `CG_CalculateReinfTime`'s three other real call
  sites (`cg_limbopanel.c`, `cg_scoreboard.c`, and `CG_DrawLimboMessage`
  itself) were read to confirm it's a genuinely live, actively-used value
  before narrating it - and, going the other direction, every reference
  to `CS_MAIN_AXIS_OBJECTIVE`/`CS_MAIN_ALLIES_OBJECTIVE` in this
  repository was read and traced to conclude objective-status narration
  isn't implementable here at all yet (see 0006 above and follow-ups
  below), rather than skipped without checking. For 0007,
  `Item_Text_Paint` and `Item_Text_AutoWrapped_Paint` were both read to
  confirm their existing `item->text == NULL && item->cvar != NULL` →
  `DC->getCVarString` resolution before `ETA_NarrateConfirmDialog` was
  extended to reuse the identical logic, and `CVARLABEL`
  (`etmain/ui/menumacros.h`) was read to confirm it sets neither
  `WINDOW_TEXTASINT` nor `WINDOW_TEXTASFLOAT`, so the plain
  (non-numeric-formatting) resolution is the correct one to mirror. For
  0008, `cg_local.h` was searched and confirmed to have no `v_dmg_angle`
  field before deriving the damage-direction bearing from `front`/`left`
  instead of assuming ET: Legacy's field carried over; `CG_DamageBlendBlob`
  (`cg_view.c`) was read to confirm `front`/`left` are the same real
  values already driving the on-screen directional blood-blob; and
  `CG_DrawCursorhint`/`CG_CheckForCursorHints` (`cg_newDraw.c`) and
  `CG_FadeColor` (`cg_drawtools.c`) were all read directly to confirm
  where and how a cursor hint's visibility is actually gated in this
  release, rather than assuming ET: Legacy's unconditional
  `CG_Draw2D`-based placement applied here - it doesn't, since hints are
  only ever checked from inside `CG_DrawCursorhint` itself. `bg_public.h`'s
  hint enum was also checked and confirmed to have no `HINT_COMPLETED`
  value to special-case, unlike ET: Legacy's fork. For 0009, the `entnfo`
  objective pipeline was traced end to end before anything was built on
  it - the server-side writer (`g_teammapdata.c`, confirmed live code, not
  another commented-out stub), the `entnfo` handler in `CG_ServerCommand`
  (`cg_servercmds.c`), `CG_ParseMapEntity`/`CG_ParseMapEntityInfo`, and
  `CG_DrawMap`/`CG_DrawMapEntity` as the real consumers - and
  `CG_ParseMapEntity` in particular was read closely enough to establish
  that `mEnt->x`/`y` are *not* a usable position source for the
  constructible/destructible types (it skips filling them in for exactly
  those), which is why the new lookup mirrors `CG_DrawMapEntity`'s
  per-type resolution instead of reading the simpler-looking fields.
  `pm_type`'s real enum values and `AngleSubtract`'s existing use in
  `cg_draw.c` were likewise confirmed directly, and the absence of any
  units-per-meter constant was established by searching for one rather
  than by carrying ET: Legacy's note across.
- **A real build, as of 0010** - this supersedes what earlier revisions of
  this file said. Every patch up to 0009 was checked only with
  `gcc -fsyntax-only` on individual files, which cannot catch a linker
  error. Both modules are now built for real, from a fresh clone with
  0001-0010 applied, via `build-modules.py`:
  - `cgame` links from 52 objects with the feature off and 64 with it on;
    `ui` from 13 and 25. The +12 in each case is the accessibility layer,
    so the SCons wiring's source list is not just syntactically present
    but actually compiles as part of each module.
  - Both link with `-Wl,--no-undefined` in all four configurations, so
    nothing the accessibility layer calls is left unresolved - the first
    check in this integration that could have caught a missing or
    mismatched symbol, and it passes.
  - `nm` on the results: zero `ETA_*` symbols with the feature off, 65
    (cgame) and 64 (ui) with it on - so the toggle genuinely toggles.
  - The compiler warning sets are **byte-identical** with the feature off
    and on (106 warnings for cgame, 35 for ui, all pre-existing 2010-release
    ones). "True no-op when the feature is off" is now checked at whole-module
    level, not just per file.

Still not validated:

- **This codebase's own build systems.** `build-modules.py` reproduces
  what the SCons wiring specifies, but SCons itself was never run (no
  Python 2 available - see 0010), so SCons's own `SharedLibrary`/`BuildDir`
  behaviour with these inputs is unconfirmed. The MSVC projects and
  solution (0011, 0012) are wired but never opened or built - there is no
  Visual Studio here, and project files offer nothing runnable to check
  against, so both patches rest on structural checks rather than on a
  build: well-formed XML, added file entries shaped exactly like the
  existing `bg_lib.c` exclusion, shipped `<Configuration>` blocks provably
  unchanged, new configurations differing from their base only in the
  four intended ways, every solution mapping resolving to a project
  configuration that exists, paths resolving, and the file list matching
  the other two build definitions. The real build above is also
  64-bit, where
  `SConstruct` defaults to `gcc -m32`; 32-bit libc wasn't available here.
  The 2010 code has known 64-bit issues (`cg_main.c`'s syscall trampoline
  casts a pointer through an `int`), so the 64-bit result is a valid
  compile-and-link check, not a runnable game module.
- Runtime behavior in-game.

## Known follow-ups (not included in this patch)

- **Running the SCons build once.** 0010 adds the `ACCESSIBILITY=1` option
  to `SConstruct`/`SConscript.cgame`/`SConscript.ui`, and everything about
  it that could be checked without SCons has been (Python 2 grammar, the
  SConscripts' own logic executed with SCons stubbed, and a real build of
  exactly the inputs it specifies - see 0010 and the validation section).
  What's left is running `scons ACCESSIBILITY=1` on a machine that has
  Python 2 and a period-appropriate SCons, to confirm SCons's
  `SharedLibrary`/`BuildDir` handling is happy with sources that live
  outside `src/`. If it isn't, the likely fix is local to the new block -
  the source list and flags themselves are already proven correct.
- **Opening the MSVC solution once.** 0011 and 0012 wire it, but nothing
  about either has been run - there is no Visual Studio here (see those
  two patches and the validation section). Worth checking on a machine
  with VC++ 2008, in this order, easiest and most important first:
  1. The solution still opens and all 8 projects load. 0012 rewrote
     `wolf.sln`'s mapping section, so this is the check that matters most.
  2. A plain **Release** build is byte-for-byte what it was. Both patches
     are built so this is hard to break - the shipped configurations are
     provably untouched - but it is the regression that would hurt others.
  3. **Release Accessibility** builds and links `cgame`/`ui` into
     `ReleaseAccessibility/`. If the link fails on the SAPI code, the
     `ole32`/`oleaut32`/`winmm` dependencies are the thing to check first.
  4. Only if using 0011's property-sheet route instead: whether VC++ 2008
     merges the sheet's `PreprocessorDefinitions` into the project's
     rather than replacing them. If it doesn't, the manual settings
     documented in 0011 are the fallback and the sheet can be dropped.
- **An objective-change trigger for the two objective cues, if one ever
  exists.** 0014 fires them on request and on respawn, because this
  release gives no "objective became current" event to hang them on:
  there is no "main objective" (checked four times - 0006, 0008, 0009,
  0013), and objective *completion* state never reaches the client (0013
  traced the full path). If completion state were ever recoverable - the
  one untested lead is whether the `SVF_BROADCAST` indicator entity
  disappearing (`currentValid`) tracks it, see 0013 - these two cues could
  become ambient, firing when an objective is actually finished rather
  than on the player's schedule. Worth confirming in a running game
  before rewiring them.
- **Everything past Milestone 6.** Milestones 2-6 are now complete here -
  every deliverable defined for this integration is implemented, and
  nothing further is defined in `docs/SOURCE_CODE_PLAN.md`. What stands
  between this patch set and something a player can actually use is no
  longer code: a 32-bit build on a machine with this release's real
  toolchain, and then testing in-game with a screen reader. 0009's
  mirrored turn instruction is a good argument for the latter - it was a
  live defect that only a numeric check caught, and there may be others
  that only playing will surface.

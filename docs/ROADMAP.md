# Roadmap

Every milestone below is implemented. The library in `src/accessibility/`
provides each system, and both engine integrations
(`integration/etlegacy/` and `integration/id-software/`) wire it into the
menu, HUD, audio and navigation code of their respective engines.

What that does *not* mean is that any of it has been heard by a player.
Nothing here has been verified at runtime — see
"What is still unverified" at the end, which is the part that matters most
when reading the ticks above it.

Per-deliverable notation:

Every deliverable below is marked **done**, meaning implemented in the
library and wired into both engines.

Patch numbers refer to the patch series in each integration directory;
the two series were developed separately and their numbering differs.

## Milestone 1 — Speech Smoke Test — done

Build the smallest possible Windows speech path.

Deliverables:
- speech manager interface — done
  (`src/accessibility/speech/speech_manager.c`)
- Windows speech backend stub — done, and no longer a stub: an NVDA
  backend (`platform/windows/windows_nvda.c`, via the NVDA Controller
  Client DLL) with the SAPI backend
  (`platform/windows/windows_speech.c`) as fallback when NVDA is not
  running
- test message function — done
  (`ETA_AccessibilityRuntime_RunSpeechSmokeTest`)

Exit condition: *A test call can produce spoken output.*
Code-complete. Unverified: the speech path has never been run on Windows
with a screen reader or SAPI voice present.

## Milestone 2 — Menu Reader Prototype — done

Make menu focus changes speak.

Deliverables:
- menu focus event interface — done (ET:L 0001, id 0001)
- current item storage — done
- repeat current item command — done (ET:L 0015, id 0015), bound to F6
- stop speech command — done (ET:L 0015, id 0015), bound to F8

These last two were marked done for a long time while being unreachable.
The library had `ETA_MenuNarrator_RepeatCurrentItem` and
`ETA_Speech_Stop` from the beginning, but nothing in either engine
exposed them, so no key could reach either one: the functions existed
and could not be called. ET:L 0015 and id 0015 register the console commands
that close that gap, in both trees.

Wiring them turned out not to be a table entry. The engine offers every
console command to cgame before ui (`Cmd_ExecuteString`, qcommon/cmd.c),
and `CG_ConsoleCommand` answers finally for any name in its table — so a
repeat key pressed with the options menu open mid-match would repeat the
last health report rather than the focused item, because cgame answered
and ui never saw it. cgame therefore checks the key catcher and hands
the request to ui under a name only ui registers. That name must differ
from the one cgame registers, or the forward returns to cgame and loops
inside the engine with no output at all; `tests/command_wiring_test.py`
exists to keep that true, and runs against both trees. The two ui
modules answer commands differently — ET: Legacy has a table like
cgame's, the 2010 release has a chain of `Q_stricmp` comparisons — so
the test reads both shapes rather than assuming one.

Exit condition: *A blind player can hear which menu item is selected.*
Hooked at item focus in `src/ui/ui_menuitem.c` on ET: Legacy and in
`src/ui/ui_shared.c` on the id Software tree — the two trees having split
that file differently is why the series are not interchangeable.

## Milestone 3 — Spoken Settings — done

Make configurable values understandable without sight.

Deliverables:
- setting name narration — done (ET:L 0001, id 0001)
- setting value narration — done (ET:L 0002, id 0002), including
  tri-state checkboxes (ET:L 0008, id 0004)
- confirmation dialog narration — done (ET:L 0003, id 0003) for
  macro-built dialogs, extended to cvar-bound popup text
  (ET:L 0009, id 0007)

Exit condition: *A blind player can change options without guessing.*

## Milestone 4 — Spoken HUD Prototype — done

Expose the most important gameplay state.

Deliverables:
- health speech — done (ET:L 0004, id 0005)
- ammo speech — done
- weapon speech — done, from `gitem_t.pickup_name`
- respawn speech — done (ET:L 0007, id 0006), from
  `CG_CalculateReinfTime`
- objective status speech — done (ET:L 0006, id 0013), from the live
  `entnfo` command-map pipeline

The objective report lists every objective on the map rather than only
the incomplete ones, because completion state never reaches the client in
either engine. That is parity with what the command map itself can show,
not a shortcut.

Exit condition: *A blind player can query basic match state.*

## Milestone 5 — First Audio Cues — done

Add non-speech cues for fast gameplay feedback.

Deliverables:
- low health cue — done (ET:L 0005, id 0008), gated at 25 health
- objective cue — done (ET:L 0011, id 0014)
- interaction cue — done (ET:L 0010, id 0008), from the cursor hint
- damage direction cue prototype — done (ET:L 0005, id 0008), bearing
  derived from the pain event's `front`/`left` components

Also added beyond the original list: an objective direction cue, played
on respawn and on an objective status request (ET:L 0011, id 0014).

Exit condition: *Important events are not dependent on speech alone.*

## Milestone 6 — Navigation Prototype — done

Create the first movement assistance system.

Deliverables:
- objective direction cue — done (ET:L 0011, id 0014), bearing to the
  nearest objective from the command-map entity list
- distance feedback — done (ET:L 0013, id 0009), in metres, converting at
  the commonly cited 1 quake unit = 1 inch. Neither engine defines a
  units-per-metre constant, so that figure comes from outside the source
  and is worth checking by ear once distances can be heard
- route correction cue — done (ET:L 0013, id 0009), spoken rather than
  tonal: "turn left/right toward the objective", or "objective is ahead"
  within 15 degrees. That 15-degree band is a judgment call, not a value
  measured against anything in either engine
- stuck detection concept — done (ET:L 0012, id 0009), on the movement
  the player state already reports

Exit condition: *A blind player can begin moving toward objectives
intentionally.*

Bearings use 0 = ahead, 90 = right, 180 = behind, 270 = left — not an
invented convention, but the one ET: Legacy's own damage-indicator code
documents in `cg_draw.c`, where `>= 60 && < 120` is labelled "right".

Both integrations got that sign wrong at first, in both the spoken route
correction and the directional cue, and told the player to turn left
when the objective was on their right. In id Tech 3 yaw increases
counter-clockwise, so a target on the player's right sits at a *lower*
yaw than the view — the opposite of what reading the expression casually
suggests. Both are fixed, in the patch files themselves rather than in a
follow-up patch, so applying the series in order never produces a
mirrored navigation aid.

This is the single most useful thing on this page. A mirrored direction
cue compiles, links, and reads correctly to a sighted reviewer — it is
only wrong to the person relying on it.

It was the first runtime-meaning defect CI could catch:
`tests/bearing_regression_test.py` lifts the real bearing expressions out
of each patched engine tree, compiles them against that engine's own
`q_math.c`, and checks that a target on the player's right reads as
right. Both original bugs were reintroduced by hand to confirm it goes
red on each.

Three more have joined it since, listed under "Continuous integration"
below. What none of them touch is timing and judgement — whether a cue
fires at the right moment, or often enough to help without drowning the
match — which is still the whole of what is unverified.

## Beyond the original milestones

Work that was not on this roadmap but was needed to make the above
buildable, or reachable by a player:

- **Build wiring.** ET: Legacy builds through its own CMake feature flag
  (`-DFEATURE_ACCESSIBILITY=ON`). The id Software tree had no such hook,
  so the SCons build (id 0010) and the VC++ 2008 projects, property sheet
  and dedicated configurations (id 0011, 0012) were added.
- **Compile and link verification.** Both integrations have been built as
  real linked mod libraries — not just syntax-checked — with and without
  `FEATURE_ACCESSIBILITY`, and the warning sets compared to confirm the
  feature is a genuine no-op when off.
- **Test coverage.** The five smoke tests in `tests/` were rewritten to
  assert through a macro that survives `NDEBUG`. Previously every
  assertion was compiled out of Release builds, so the suite could not
  fail.
- **Continuous integration.** `.github/workflows/ci.yml` runs the smoke
  tests in Release, Debug and under sanitizers, applies both patch series
  to pinned pristine engine checkouts, builds both integrations with the
  feature on and off, and runs the meaning-level checks against each
  patched tree.

  Three run on both: the bearing regression test, the runtime init test
  and the command wiring test. The fourth, `autoexec_config_test.py`,
  runs on ET: Legacy alone, because the shipped config belongs to that
  package - the id Software tree has no release to configure.

  Each exists because of a defect that reached a release or would have:
  a mirrored "turn left", narration wired to an uninitialised backend, a
  command loop that would hang the game, and a bind naming a command the
  engine does not have.
- **Limbo panel keyboard navigation** (ET:L 0016). None of the in-match
  milestones can be reached by a player who cannot aim a cursor, because
  the team/class panel that stands between the menus and a spawn is
  mouse-driven and has no keyboard traversal of its own. Up / Down / Tab
  walk the teams, classes and OK; Enter moves the real cursor onto the
  control and calls its own handler, so a keyboard selection takes the
  same path a click does. Each stop is spoken with its state - "full",
  "unavailable", "selected" - which a sighted player reads from the
  button's colour and which appears in no string in the panel.

  0017 adds weapon selection to the same walk: each slot is a stop and
  Enter cycles it, since the panel's weapons live in a dropdown that
  only opens under a cursor. How many a class has is the engine's own
  count, per class and per skill level, never a number assumed here.

  The id Software series has no equivalent yet.
- **Text box narration** (ET:L 0019). Everything else in the menus is
  chosen from a set the mod can read; a text box is the one place the
  player produces the content, and their only feedback is the echo. So
  arriving at a box reads "Player name, edit box, Alex", each keystroke
  is echoed as it lands, and the cursor keys read the field back
  character by character.

  The echo reports what the engine did rather than what the key was, so
  a key the engine refuses says nothing. Passwords are spoken as a
  length and never read, honouring the masking the panel already does.
  `tests/textfield_echo_test.py` guards the character extraction against
  the engine's own UTF-8 code.
- **Stuck detection reports the way out** (ET:L 0023, id 0016). The old detector
  asked only whether the player had moved recently, which in a shooter
  is normal behaviour, so it fired at random; and it compared a single
  frame's travel against a fixed distance, making walking and crawling
  read as motionless. It now requires movement *input* before asking the
  question, and measures progress across the window rather than per
  frame. The announcement is the objective, its distance and which way
  to turn, rather than a label for the predicament.

  Both integrations, because the detector lives in the shared library and
  its signature changed. CI caught the id side: a local build of one
  engine is not evidence for the other when the change is in code they
  both link.
- **Weapon ammo, actually delivered** (ET:L 0022). 0021's weapon-change
  narration asked `CG_PlayerAmmoValue` for ammo from inside the
  playerstate transition, but that function reads the weapon from the
  player *entity's* state, which prediction has not updated yet - so the
  name was right and the ammo was absent. The narration now runs per
  frame off the same field that function reads, which removes the timing
  question instead of trying to answer it. Ammo also reports what is
  left in reserve, not only what is loaded.
- **The objectives key reads the map's objective text** (ET:L 0022). It
  had been wired to the main-objective configstring, which many maps
  never set, so the key was silent in testing. It now reads what the
  objectives panel itself draws. Nothing on either path can be silent
  now: no description, no ammo count and no main objective each say so.
- **Navigation assistance can find an objective at all** (ET:L 0024,
  id 0017). 0022 fixed the objectives *key* by moving it off the
  main-objective configstring. It did not occur to anyone - including
  the author of that patch - that everything *else* about where to go
  read the same dead source: the distance, the turn direction, the
  objective cue and its direction cue. Playing 0.11.0 found what that
  meant in practice: no navigation audio whatsoever, on any map.

  One lookup now answers "where should this player be going", and it
  falls back to the nearest objective on the player's own command map -
  a list the server pushes once a second, that needs no map script, and
  that objectives leave as they are completed. Real objectives beat
  construction sites, cabinets are excluded, and the chosen target is
  sticky so it does not swap as the player strafes.

  `tests/objective_source_test.py` reads the engine's own list of
  objective types and fails if the narration cannot place one, or if
  anything announces a direction it did not get from that one lookup.

  The lesson recorded: **fixing one symptom of a bad data source is not
  fixing the source.** 0022 found the configstring was empty on most
  maps and moved a single caller off it, leaving four others behind.
- **The binoculars and scope say what they are pointed at**
  (ET:L 0029, id 0022). `bind b "+zoom"` turned out to tie three of the
  tester's points into one: the B key is the binoculars and the scope.

  The zoom itself is announced because a scope does not always engage
  when asked, so silence is otherwise ambiguous. Then a trace along the
  view says what it meets: a person with their side, a door, an
  explosive, or world geometry as material plus orientation - "Wooden
  wall", "Gravel ground". The skybox gets no distance; past the probe's
  reach it says so.

  Two things are load-bearing. The answer comes from `CG_Trace`, because
  the engine's own collision is the only honest source for "what is in
  front of me" - a guess would be wrong exactly when a player is lining
  up a shot. And the materials are the engine's own surface flags, the
  ones it uses for footsteps and impacts, so speech agrees with what the
  player hears underfoot.

  `tests/look_ahead_test.py` guards all of it.

- **The ground and the wall ahead, without binoculars**
  (ET:L 0031, id 0023). The tester, after playing the zoom build, was
  exactly right about the relationship: it is the same feature, and the
  binoculars only see further. Most classes carry neither binoculars nor
  a scope and had nothing told to them about their surroundings at all.

  The ground hangs off `EV_FOOTSTEP`, which is where the engine has
  already resolved the surface into a footstep type to pick a sound.
  Speaking a word indexed by that same type means **the word and the
  sound cannot disagree.** Only on a change, which is the only time the
  ground is news.

  The wall is 0029's probe at 100 units instead of 8192. It stands down
  while zoomed - the binoculars are already answering it - and ignores
  the floor, which is the footstep narration's job.

  `tests/footing_test.py` reads the footstep enum, the sound the engine
  registers for each member, and the mod's word table, and requires all
  three to line up.

- **A compass** (ET:L 0032, id 0024). The tester asked for cardinal
  directions, and noted they would help with turning toward the
  objective too. Both: the heading is announced when it changes, and the
  status key now says *"Objective lies north, you are facing south"*,
  which tells a player how far round to turn in a way "turn left" never
  has.

  **This is the one place in the mod where being wrong beats being
  silent.** Every other defect here has been a missing word - the player
  hears nothing and knows something is off. A compass point is
  confident, plausible, and wrong in the direction they then walk, and a
  player with no sight has no second opinion.

  So the conversion lives in the shared library, where both integrations
  use one copy, and `tests/compass_test.py` checks it against the ring
  of cardinal points ET: Legacy draws on its own compass. Writing that
  check turned up a defect in the engine: its selection expression uses
  `fmodf` on a value that goes negative past yaw 180, so the game labels
  the top of its own square compass "W" for the entire back half of a
  turn. The mod wraps properly and does not imitate it.

- **Leaning is announced** (ET:L 0033, id 0025). Q and E are
  `+leanleft` and `+leanright`, and leaning is one of the few controls
  the engine silently refuses - while moving, firing, prone or mounted.
  So the narration reads `ps->leanf`, which is what the lean actually
  did, never the key: telling a player they are peeking out from cover
  when they are not is worse than saying nothing.

- **Doors creak, the crosshair ticks, and the map says where you are**
  (ET:L 0038, 0039). The tester's own reasoning drove these: a spoken
  line that gets interrupted takes its information with it, so a thing
  that is still *there* - a door - deserves a sound that is still there
  too. Doors within about ten metres carry a looping creak positioned in
  the world; a locked one creaks duller and slower.

  Doors are identified by `s.dmgFlags`, the hint type the server already
  stamps on the entity and replicates, behind an `eType == ET_MOVER`
  guard because that field carries damage information on players and a
  sound range on speakers. I had told the tester an entity-type test was
  the best available and that lifts would occasionally be called doors.
  That was wrong, and being wrong made the feature better.

  The beacon tones built for doors turned out to suit the crosshair
  instead, which the tester spotted: a tick under the crosshair works
  for a scoped rifle as well as an iron sight. Bright for an enemy, low
  and soft for a teammate. It rides `cg.crosshairEntNum` so it cannot
  see through a wall, and a disguised covert operative reads as a
  teammate - the stock HUD deceives a sighted player there on purpose,
  and a cue that saw through it would be an advantage no player has ever
  had. The one exception is the Field Ops skill the engine itself
  reveals disguises to.

  Locations come from `CG_GetLocationMsg`, the same lookup that fills in
  a sighted player's position in team chat, with `BG_GetLocationString`'s
  command-map grid as the fallback so a map with no location file is
  never met with silence. Writing the check for it found a real defect:
  a place name longer than the buffer was stored truncated and compared
  in full, so it never matched what had been kept, restarted its settle
  clock every frame, and could never be announced at all.

  These four sounds are the first this mod brings with it. Nothing in
  ET's sound set loops without grating - it is all one-shot transients -
  so they are synthesised by `release/make-cue-sounds.py`, which ships as
  readable source rather than as four opaque files, and the release build
  refuses to package if any sound the mod registers was not produced.
  The tester auditioned three of each and chose.

- **"Wall, 0 metres" while walking on** (ET:L 0040, id 0029). Reported,
  and wrong two ways. The narration traced a ray from the eye, which
  answers "what am I looking at" rather than "what is stopping me" -
  and every stair riser is an upright face, so it found a wall on every
  staircase in the game while the player climbed it. The distance was an
  `int`, so anything under a metre read as nought.

  The probe is now a trace of the player's own bounding box, lifted at
  the base by the engine's `STEPSIZE`, which is exactly what makes a
  stair pass underneath it as the player's feet do. No distance is
  spoken, because against something you are up against it is always
  nought.

  The same report noted it cutting off an objective distance. It was,
  and the cause is invisible at either call site: a backend that
  delivers a new report by purging the one in progress leaves whichever
  spoke *last*, so two reports in one frame means the later wins.
  Scenery now runs first. `tests/obstacle_blocking_test.py` fails if the
  order is ever swapped back.

- **Stairs, and the icons under the crosshair** (ET:L 0041, id 0030).
  Two requests, and the first of them is a debt the entry above ran up:
  lifting the probe over a stair riser is what stopped stairs being
  called walls, and it also made them silent. Before the fix a player
  heard about staircases, wrongly; after it they heard nothing, which is
  what the mod says about an empty corridor.

  So the ground ahead is measured rather than looked at: a point trace
  down at half a stride and again at a stride, each inside a window one
  `STEPSIZE` either side of the reference height - because ground inside
  that window is somewhere the player can walk to, and ground outside it
  is a wall or a drop, both of which already have narration. The second
  reading is taken from the first, not from the feet: three steps up is
  well outside a window measured from the boots, and measuring both
  against the feet would report every staircase in the game as a single
  step.

  A tread is required flat to 0.99 - far stricter than the engine's own
  `MIN_WALK_NORMAL` of 0.7, which only asks whether a surface can be
  walked on at all. A ramp therefore says nothing rather than being
  called stairs: sending a player to feel for treads that are not there,
  on a surface they might walk off, is worse than silence.

  The cursor hint is the other half. ET shows a sighted player an icon
  when they are close enough to use something - pliers on a
  construction, dynamite where a charge goes, a syringe over a body
  still worth reviving - and this mod answered all of it with one
  undifferentiated click. It now speaks the icon, with the progress
  figure where the HUD draws a bar beside it.

  The mapping switches on hint *names*, never numbers, and that is not
  fastidiousness: ET: Legacy has struck a dozen hints out as unused
  without renumbering what was left, so `HINT_ACTIVATE` is 3,
  `HINT_HEALTH` 13 and `HINT_BUILD` 38, while the 2010 tree still
  carries the whole contiguous Wolfenstein list. A table indexed by
  position is right in one engine and announces the wrong thing in the
  other. `tests/interaction_hint_test.py` reads the engine's own drawing
  switch for the list of icons that reach the screen and fails both on a
  hint the mod cannot name and on a numeric case.

  The click was kept and the words made to wait a quarter of a second
  behind it. The sound is the sighted player's flicker at the edge of
  the eye and should be immediate; the words are not, because turning
  through a supply room puts four or five hints under the crosshair
  inside a second.

- **Drops and water** (ET:L 0037, id 0028). The tester asked for empty
  space you can fall into and water you can swim in to be described like
  the rest of the scenery. Both are now part of the environment
  narration.

  The drop probes one stride ahead - along the direction of travel when
  moving, along the view when standing still - and traces down. What
  makes it safe to say *"deadly"* is that the word is not ours: ET works
  out falling damage in `PM_CrashLand` from the speed you land at, and
  its own ladder has a first damaging step and a fatal one. Those two
  numbers, run back through `h = delta * 10000 / (2g)` with the gravity
  actually in play, are the bands. A server that changes gravity moves
  the warning with it, and no map has to be measured by hand.

  Water at the bottom of a drop is reported *only* when the drop could
  not have hurt anyway. The engine does cancel falling damage for a
  player who lands submerged, but a point-contents probe cannot tell
  deep water from a puddle on the floor of a shaft, and this is the one
  feature where an over-confident answer gets someone killed.

  The waterlevel is a harder case than it looks: the engine computes it
  every movement frame in `PM_SetWaterLevel` and keeps it in `pmove_t`,
  where the cgame cannot reach it. So `ETA_WaterLevel` asks the same
  question again - the same three sample points up the player's own
  bounding box, the same `MASK_WATER`. That is a transcription, and the
  words rest on it: *"deep water"* is the level at which a jump becomes
  a swim, *"swimming"* is where `PM_WaterMove` takes over and falling
  damage stops. `tests/water_level_test.py` compares the copy against
  the original line for line, and `tests/fall_hazard_test.py` reads the
  damage ladder out of the engine and checks both the thresholds and the
  physics that converts them.

- **The compass could not keep up with the mouse** (ET:L 0037, id 0028).
  Reported as the narrator being slow. It was not slow, it was *behind*:
  a sweep across half the compass crosses four sectors in a few frames,
  each one was announced, and speech cannot deliver four reports in the
  time a hand takes to move. A backend that queues reads them out one
  behind the other, so the narration trails the view by seconds; one
  that interrupts destroys each with the next. Both sound like a
  narrator that cannot keep up.

  A heading now has to be *held* for 350 ms before it is spoken. A sweep
  says where it ended up, once. A slow deliberate turn dwells in each
  sector far longer than that and is unaffected.

  The test for it had to be rewritten: the first version sampled once
  per sector, which is not how the game calls it, and passed with the
  settle time set to zero. It now simulates frames and catches both that
  and a pending clock that is not restarted when the sector changes.

- **Only the scope toggle is silenced** (`tests/weapon_switch_test.py`).
  The tester asked whether number-key weapon switching still worked
  after 0036. It does, and this is now checked rather than asserted:
  `weapAlts` also pairs a mortar and a machine gun with their set-down
  forms, a rifle with its grenade, and a pistol with its silenced twin,
  and none of those have zoom narration to speak in their place. The
  check walks the weapon table, splits the mutual pairs by the engine's
  own scoped flag, and fails if the suppression reaches any pair the
  zoom narration does not cover - or if leaving a scope ever stops being
  announced, which would turn the fix for a silent scope into a silent
  unscope.

- **The scope said nothing, and the cause was not what it looked like**
  (ET:L 0036, id 0027). Reported twice. The first diagnosis - that the
  scope was unreachable without a mouse - was wrong, and the tester said
  so: they reach it from the weapon-bank number keys.

  Scoping a rifle *is* a weapon change here; WP_FG42 and WP_FG42_SCOPE
  are different weapons. The zoom flag flips on the key press, so the
  scope line goes out at once - then the playerstate's weapon catches up
  a few hundred milliseconds later, the weapon narration speaks a second
  report, and the backend delivers it by purging the first. The scope
  line is the long one, and the name replacing it is identical before
  and after, because a scoped weapon carries its parent's description.
  The binoculars were fine throughout because `+zoom` changes no weapon.

  A scope toggle is now not announced as a weapon change on either
  engine. And on the 2010 tree the branch could never have fired anyway:
  it read `cg.zoomed`, which that client declares and never assigns -
  `cg.zoomedScope` is the live one.

  **The lesson: a wrong diagnosis that produces a plausible fix is worse
  than no fix**, because it closes the question. `weapalt` really is
  mouse-only, the reasoning really did hold together, and it was still
  not the answer. `tests/zoom_state_test.py` now fails if the narration
  reads a flag nothing writes, or if the weapon report stops standing
  down on a scope toggle - and it took three tries to write, passing
  wrongly twice before it caught anything.

- **The mouse is no longer required** (ET:L 0034/0035, id 0026). Two
  reports from one session. One was the join-server trap below; the
  other looked like the scope and was not.

  *Menu focus.* `Menu_HandleKey` rebuilt focus from the cursor on every
  key press. From the keyboard the cursor never moves, so it won every
  time. On the join-server screen the list carries
  `onEnter { uiScript JoinServer }`, so arrowing to "REFRESH LIST",
  hearing it announced, and pressing Enter connected the tester to a
  server. The focus reset now waits for the cursor to actually move.

  *`weapalt`.* Bound in the stock config to MOUSE2 and to nothing else -
  the only action in it with no keyboard key. It sets a mortar and an MG
  down and detonates a satchel, none of which the number keys reach
  reliably. The mod now binds KP_SLASH, free in both stock layouts where
  F9 and F10 are not. This was *not* the scope fix, though it was
  offered as one.

  `tests/keyboard_reachable_test.py` checks both fixes survive, and
  fails if upstream ever gives `weapalt` a key of its own.

- **The medic's syringe is called a syringe** (ET:L 0030). It announced
  itself as "MEDIC" - the engine's own label, which is the player's
  class rather than the weapon - and a medic carrying both it and the
  health pack could not tell them apart by ear.

  0026's rule was that the engine's own name always wins, so the mod
  could only fill gaps. That was right for fifteen nameless weapons and
  wrong here. The replacement rule is narrow: skip the engine's
  description only where it is one of the engine's own player class
  names, falling through to the pickup name it already has.

  The obvious generalisation - prefer the longer pickup name - was
  written, run against the weapon table, and discarded: it renames the
  Sten to "Sten gun" and dynamite to "Dynamite Weapon".
  `tests/weapon_name_test.py` derives the narrow list from the engine
  and fails if the mod's and the engine's disagree in either direction.

  ET: Legacy only. The 2010 tree has no description field and has always
  said "Syringe".

- **A pickup says how much it gave, and when it gave nothing**
  (ET:L 0028, id 0021). 0027 spoke the resulting total and deliberately
  not the gain; the reasoning given was that the gain would have to be
  inferred fragilely. Having read the server that was too cautious, and
  the tester was right to push.

  An ammo pack holds no number of rounds - `BG_AddMagicAmmo` gives a
  clip's worth per carried weapon, scaled by skill - so the gain exists
  only as the difference it makes, and the reserve only rises from a
  pickup, so summing the per-weapon increases is exactly it.

  The "before" is the timing problem: by the time the event runs,
  cg.snap->ps already holds the grant, and the engine's own before/after
  pair runs from the prediction pass rather than the snapshot
  transition. The mod samples the totals itself once a frame from
  CG_DrawActive - sidestepping the ordering question rather than
  answering it, which is 0022's lesson again.

  "Already full" is the part the tester actually wanted: a pack you
  cannot use is consumed either way and otherwise sounds identical to
  one that helped. The library refuses SpeakGain(0) rather than saying
  "0 rounds", so the caller must choose which happened.

- **Pickups are spoken** (ET:L 0027, id 0020). Walking over something
  gave a sound and nothing else; the tester knew what they had found
  only because they still remembered the stock sound effects. Asked for
  as "ammo pickup feedback" and widened in the asking to every item.

  Hung on `CG_ItemPickup`, which both pickup event paths funnel through
  and which is already filtered to the local player, and speaking the
  engine's own popup text so what is heard is what is drawn - including
  its translations. Health and ammo packs add the resulting total, not
  the amount gained: the gain is decided server-side from class and
  skill, while the total is what the player needs and is the same number
  the health and ammo keys already report.

  `tests/pickup_narration_test.py` guards both properties. Its own first
  draft reported a false failure by reading each switch arm up to the
  first `break` - the guard's early exit, not the end of the arm - which
  is recorded in the parser.

- **Every weapon has a name, and the approach announces itself**
  (ET:L 0026, id 0019). Playing 0.12.0 found grenades announcing their
  ammo and no name: both have an empty `desc`, the guard refused the
  empty string, and half the report was lost. Fifteen weapons were in
  that state, nearly all of them class signature kit, so the tester had
  found the universal case and the rest were queued behind it. Names now
  resolve `desc` → a two-entry mod table → `pickup_name`, engine first
  so the mod can only fill gaps, and `tests/weapon_name_test.py` walks
  every weapon the bank table can reach.

  The same session could not tell whether the objective distance was
  falling as the player walked - answering that took two key presses and
  two remembered numbers. The distance now calls itself out at 100, 50,
  25 and 10 metres. The milestone decides *when*, never *what*: the real
  distance is spoken, so arriving inside several at once reports where
  the player stands rather than a rounded fiction.

  The lesson recorded: **an empty string from the engine is data, not an
  accident to pass along.** The guard did its job; the caller should have
  had somewhere else to go.

- **The player's stance is spoken** (ET:L 0025, id 0018). Standing,
  crouched and prone were never announced, so the one thing a sighted
  player reads off the screen without thinking - what posture am I in -
  was unavailable. It matters more than it sounds: `PM_CheckDuck` only
  clears `PMF_DUCKED` when a trace finds headroom, so releasing crouch
  under a low ceiling leaves the player crouched and silent.

  Narrated per frame from `cg.predictedPlayerState`, beside 0022's
  weapon narration and for the same timing reason. The flag order is
  load-bearing: going prone sets `PMF_DUCKED` too, so testing crouch
  first would report every prone player as crouched and never say
  "prone". `tests/stance_narration_test.py` reads that overlap out of
  `bg_pmove.c` and fails the build on the wrong order or the wrong
  source.

- **The metres are real metres** (both engines). `ETA_QU_TO_METERS` had
  been carried since Milestone 6 as an external convention taken on
  faith, on the stated grounds that nothing in either engine says what a
  Quake unit is worth. That was the wrong thing to look for. Neither
  engine states a distance, but both state the size of a *person* - the
  player bounding box and three view heights - and a person has known
  dimensions. Under the conversion they read 1.83 m standing, 1.63 m to
  the eye, 1.22 m crouched, 1.02 m to the eye crouched, 0.41 m to the
  eye prone: five anatomical measurements, all right to a few
  centimetres, from constants never chosen with metres in mind.

  `tests/distance_scale_test.py` reads them out of the engine on every
  run. Two wrong conversions were tried to confirm it goes red, and it
  found its own first defect immediately - it had matched a
  commented-out player box sitting above the live one, which it exposed
  only because it prints what it read rather than just a verdict.
- **Reports spoken as one line** (ET:L 0021). The SAPI backend speaks
  with `SPF_PURGEBEFORESPEAK`, so each message cancelled the one still
  being spoken and a six-part status report was audible only as its last
  fragment. NVDA queues, so the same build behaved differently depending
  on the screen reader. `ETA_Speech_BeginReport` / `EndReport` compose a
  report into one message before any backend sees it.

  The reasoning already existed in 0019, which joins "x deleted, empty"
  into one breath for exactly this reason. It was applied locally and
  never generalised, which is how the status report kept the defect
  through six releases.
- **Health and ammo on their own keys** (ET:L 0021). One long report is
  the wrong shape for "am I about to die". Bound to 9 and 0, the only
  keys within reach of the movement hand that cost nothing: every letter
  A-Z is taken by the stock config, and those two are bound to weapon
  bank commands the engine cannot execute. `tests/weapon_bank_test.py`
  fails the build if either bank ever comes alive.
- **Weapon changes report their ammo**, and **the objectives key speaks**
  (ET:L 0021). The second augments a key the player already presses
  rather than claiming one - a pattern worth reusing.
- **Setting values on arrival** (ET:L 0020). 0019 gave text boxes their
  contents on focus and left every other kind of setting announcing only
  its label, which made the inconsistency worse rather than better.
  Multi-option rows, checkboxes, yes/no rows and sliders now say where
  they stand when focus reaches them.

  The value text is defined once, in `ETA_MenuItem_SettingText`, called
  by both the arrival narration and the five change hooks - one function
  rather than two copies and a test asserting they agree.

  It also widened what speech treats as secret. `g_password`, the server
  join password on the host-game screens, was being read aloud: ET does
  not mask it and the engine's own password check covers only the
  client-side boxes. The accessibility check is deliberately separate
  from the engine's, which drives the drawing and is not behind the
  feature flag - speech can be more careful than the screen without
  changing what the screen does.
- **Default key binds** (ET:L 0018). The status, repeat and stop
  commands were only ever reachable through `autoexec.cfg`, a second
  file copied by hand into a second folder. A tester who skipped it got
  a correctly installed mod with a dead status key. `UI_Init` now
  installs the three binds itself through `trap_Key_SetBinding`, never
  replacing a key the player has already used, and only once - so
  unbinding one makes it stay unbound. The config file still ships as a
  way to change the keys rather than as the thing that creates them.

## What the in-game tests found

### alpha-0.4.0 - the first build anyone played

Three findings, in the order they matter:

- **The main menus narrate.** Focus narration (Milestone 2) works in a
  real client with a real screen reader - the first confirmation that any
  of this is audible outside a test harness. That also retires "no screen
  reader has heard any of it" for the menu path.
- **Text-entry fields say their label, not their value.** Typing a player
  name or a server address is narrated as the field's label and nothing
  else. This is not a bug in a wired path: the focus hook narrates
  `item->text`, and no patch hooks `ITEM_TYPE_EDITFIELD` /
  `ITEM_TYPE_NUMERICFIELD` content at all. Unwired, not broken.

  **Closed by ET:L 0019**, and confirmed by the tester with a screen
  reader. Arriving at a box now reads its contents, every keystroke is
  echoed, and passwords are spoken as a length rather than read out.
- **The limbo panel could not be operated at all**, so the tester never
  reached a match. Pressing **L** opens the team/class panel, and the
  panel is mouse-driven with no keyboard traversal anywhere in it. ET:L
  patch 0016 adds that traversal; it has not yet been played.

The same report mentioned game type and player count not being spoken.
**Both are now explained**, from reading `etmain/ui/hostgame.menu`:

- *Maximum Players* is a `NUMERICFIELD`, genuinely unwired until 0019.
- *Game Type* is a `MULTIACTION`, which expands to `ITEM_TYPE_MULTI` -
  hooked since 0002, but only on *change*. Arriving on it said the
  label and nothing about where it stood, so there was no way to learn
  the value without altering it first. Closed by 0020.

### alpha-0.5.0 - the first spawn

**The limbo panel works.** A player reached a match from the keyboard,
which is the first time anything past the menus has been exercised at
all. Two further findings:

- **Changing weapon said nothing.** Team and class spoke; weapons did
  not. Not an oversight in the narration so much as a missing stop -
  0016 walked controls, and the panel's weapons are not controls, they
  are a dropdown that only opens under a cursor. ET:L 0017 gives each
  slot a stop that Enter cycles.
- **F5 did nothing**, because `autoexec.cfg` had not been copied. The
  tester guessed the cause correctly, which is itself the problem: a
  correctly installed mod with a dead key is indistinguishable from a
  broken one. ET:L 0018 makes the mod install its own binds so the
  config file is optional.

Neither 0017 nor 0018 has been heard in a match yet. 0019, which closes
the text box gap from the first report, has: the tester confirmed text
boxes read back with a screen reader, and the release notes list them
as confirmed working.

## What is still unverified

None of the following has happened. Each is blocked on an environment
this project has not had access to, not on missing code.

- **The id Software integration could not speak at all until id 0015.**
  Not a missing feature: nothing in that series called any `_Init`, so
  both speech backends returned immediately on every narration call —
  the NVDA path checks the controller client's `speakText` entry point
  and the SAPI path checks its voice, and neither exists before Init
  runs. Thirteen patches of narration were being discarded in silence.
  ET: Legacy had the identical bug until its own 0014, which is what
  made alpha-0.1.0 mute. Finding it twice, the same way, in two
  independently written series is what prompted
  `tests/runtime_init_test.py`, which now runs against both trees in CI.

  It follows the library's own call graph rather than a list: a module
  that narrates health reaches Speech through HudNarrator without ever
  naming it, so the report points at the missing `ETA_Speech_Init`
  instead of at a symptom three layers up. Both historical failures were
  reconstructed to confirm it — ET: Legacy at patches 0001-0013 and the
  id tree at 0001-0014, the exact states that shipped and were silent —
  and it names the root cause in both.

- **Almost nothing here has been exercised in a running match.** Every
  "done" above means the code is written, compiles, links, and was read
  against the engine source it hooks into. The mirrored bearings
  described under Milestone 6 are what that gap costs: they survived
  review in both integrations.

  The exceptions are alpha-0.4.0 and alpha-0.5.0, which a tester ran.
  What those reports established is recorded under "What the in-game
  tests found" below.
- **The SCons build has never been executed.** `SConstruct` is Python 2
  and no Python 2 interpreter was available; the wiring was verified by
  parsing the build scripts, not by running them.
- **The MSVC projects have never been opened.** The `.vcproj`/`.sln`
  changes were written to the VC++ 2008 file format by hand and validated
  by inspection.
- **No 32-bit build on the real toolchain.** The Windows libraries that
  were produced came from a mingw cross-compiler.

Closing any one of these is worth more than adding another milestone.

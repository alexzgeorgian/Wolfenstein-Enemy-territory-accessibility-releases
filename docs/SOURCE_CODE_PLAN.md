# Source Code References

This document exists only to track the upstream engine sources related to this project.

## ET: Legacy

Primary modern engine foundation:

https://github.com/etlegacy/etlegacy

## Original Enemy Territory Source Release

Original GPL source release:

https://github.com/id-Software/Enemy-Territory

## Repository Responsibility

This repository is intended to contain:

- accessibility systems
- speech systems
- menu accessibility
- HUD accessibility
- navigation assistance
- audio accessibility features

The upstream engine source code should remain upstream unless direct integration becomes necessary.

## Engine Integration

Direct integration has started: `integration/etlegacy/` contains patches
that wire the menu narrator (focus, setting-value including tri-checkboxes,
and confirmation dialog narration, both macro-built and cvar-bound), all
five of Milestone 4's HUD deliverables (health, weapon, ammo, objective,
and respawn-timer speech, on-demand or automatic as fits each), all five
of the audio cue system's cues (damage direction, low health, interaction,
objective, and objective direction), and all three of Milestone 6's
remaining navigation deliverables (stuck detection, distance feedback, and
route correction, alongside the on-demand status command) into
ET: Legacy's real menu/cgame code behind an opt-in `FEATURE_ACCESSIBILITY`
CMake option, plus notes on what they cover and what's still open. See
`integration/etlegacy/README.md`.

A second, separate integration has also started against the original 2010
id Software GPL release: `integration/id-software/` contains fourteen patches
wiring menu narration (focus, setting values including tri-checkboxes, and
confirmation dialogs both macro-built and cvar-bound), all five of
Milestone 4's HUD deliverables (health, weapon, ammo, respawn-timer and
objective speech), all five audio cues (low health, damage direction,
interaction, objective and objective direction), and all three of
Milestone 6's navigation deliverables (stuck detection, distance feedback
and route correction) into that
codebase's own menu and cgame code behind the same `FEATURE_ACCESSIBILITY`
define. Every hook was re-derived against that release's real source
rather than ported from the ET: Legacy patches, since the two have
diverged significantly - several ET: Legacy hook points turn out not to
exist here at all.

Every deliverable defined for that integration is now implemented. The
objective-related ones took the longest: this release has no "main
objective" concept - the script action that would set one is a
commented-out stub - so patch 0009 found the live per-team objective list
behind the command map, 0013 narrates it, and 0014 cues from it on
request and on respawn, since 0013 also established that objective
completion state never reaches the client and there is therefore no
objective-change event to cue on. What remains is not code: a 32-bit
build on this release's real toolchain, and testing in-game.

This release has no CMake - it ships a Python 2 SCons build and a Visual
C++ 2008 project - so its build wiring took a different shape from
ET: Legacy's CMake option: patch 0010 adds an `ACCESSIBILITY=1` option to
the SCons scripts, and `integration/id-software/build-modules.py` builds
the two modules directly from those same source lists for anyone without a
Python 2 environment. Patches 0011 and 0012 wire the Visual C++ side:
the accessibility sources are added to the cgame and ui projects, and
dedicated "Release Accessibility"/"Debug Accessibility" configurations -
plus matching solution configurations in `wolf.sln` - build them with the
layer compiled in, leaving the shipped Release and Debug configurations
untouched. Both `cgame` and `ui` now compile and link
for real with the feature on and off, with identical warnings either way.
Neither this release's own build systems has actually been run, though -
no Python 2 for SCons, no Visual Studio for the MSVC projects - so both
wiring patches rest on checks short of a build, documented in
`integration/id-software/README.md`.

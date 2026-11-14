# Accessibility Architecture

## Purpose

This document defines the high-level architecture of the accessibility runtime.

The document establishes:

- subsystem ownership
- runtime responsibilities
- engine intersections
- event flow
- timing responsibilities
- platform boundaries

The architecture is intended for the C-based structure used by Enemy Territory and ET: Legacy.

## Engine Boundary

The engine remains responsible for:

- rendering
- networking
- gameplay simulation
- audio playback
- UI rendering
- input processing

The accessibility runtime consumes engine state and exposes accessible feedback.

## High-Level Structure

```text
Engine
│
├── Game State
├── Renderer
├── Input
├── Audio
├── UI/Menu System
│
└── Accessibility Runtime
       │
       ├── Speech Manager
       ├── Event Router
       ├── Menu Narrator
       ├── HUD Narrator
       ├── Navigation System
       ├── Audio Cue System
       ├── Accessibility Commands
       └── Diagnostics
```

## Runtime Rules

The accessibility runtime should:

- observe engine state
- process accessibility events
- expose accessible feedback
- remain modular
- remain isolated from rendering implementation

The accessibility runtime should avoid:

- direct gameplay modification
- renderer replacement
- networking replacement

## Subsystem Responsibilities

### Speech Manager

Responsibilities:

- speech output
- speech queue management
- interrupt speech
- speech priority
- repeat-last-message support
- backend selection (NVDA when running, SAPI otherwise)

The speech manager only processes speech requests.

It owns which backend speaks. On Windows it tries the NVDA controller
client first and falls back to SAPI when NVDA did not take the message -
per message, so NVDA starting or stopping mid-session needs no polling and
no restart. Platform backends live under `platform/windows/`; every one of
them compiles to no-ops elsewhere, so the manager's logic is the same on
all platforms.

### Event Router

Responsibilities:

- runtime event distribution
- menu events
- gameplay state events
- accessibility command events
- system notifications

### Menu Narrator

Responsibilities:

- focused menu item narration
- setting narration
- confirmation narration
- server browser narration

### HUD Narrator

Responsibilities:

- health narration
- ammo narration
- weapon narration
- objective narration
- respawn narration

### Navigation System

Responsibilities:

- directional guidance
- objective direction
- route correction
- orientation assistance

### Audio Cue System

Responsibilities:

- non-speech audio cues
- warning sounds
- interaction sounds
- directional cues
- priority-based feedback

### Diagnostics

Responsibilities:

- runtime logs
- accessibility state validation
- event tracing
- debugging support

## Timing Model

Some systems operate through events.

Some systems operate through polling.

Example:

```text
Menu focus change
→ event-driven narration

Health query command
→ polling-driven request
```

Timing responsibility should remain explicit.

## Platform Separation

Platform-specific code remains isolated.

Example:

```text
src/accessibility/platform/windows
```

Core accessibility logic should remain platform-neutral whenever possible.

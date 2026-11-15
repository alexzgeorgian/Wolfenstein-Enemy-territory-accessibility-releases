**Shift+N now really turns you toward the marker, and period is the game's again.**

- **Shift+N** turns you once you let go of Shift, and says *"Facing the
  way. 40 meters to marker"* only after you have turned. If the turn
  does not land, it says *"Could not turn all the way"* and which way the
  marker is, so you can turn yourself.
- **Period** no longer turns you: it is back to the game's own zoom of
  the small map, unless you had set it to something else. Shift+N is the
  one key for the turn, and the Key Binds page has no separate *"Face The
  Way"* row.
- **N** by itself still resets the spawn timer.

## What went wrong

In 1.4.4.2, Shift+N said *"Facing the way"* as soon as it was pressed,
whether or not you were turned, and began the turn with Shift still
held. Now the turn waits for Shift, and the words wait for the turn.

## Checked

- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.
- Not tried in the game before release: Enemy Territory's game files
  cannot be fetched where it is built.

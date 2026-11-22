**N says where the marker is and turns you toward it; Keypad dot is free again.**

- **N** says what the marker is on, how far it is and how high, then
  turns you toward the way to it and says *"Facing the way"*. If the turn
  does not land, it says which way the marker is, so you can turn
  yourself. You use N both to hear where the marker is and to face it.
- **Shift+N** resets the spawn timer, the game's own N.
- **Keypad dot** no longer says where the marker is, since N does: it is
  unbound, unless you had set it to something else. The Key Binds page
  has no *"Where Is Marker"* row.
- On a Mac, **if ET: Legacy stops answering** when it starts, the guide
  now says what fixed it for a tester: clearing the downloaded files'
  marks with `xattr -cr` in Terminal.

## What went wrong

In 1.4.4.2 and 1.4.4.3, Shift+N was the key for the turn, and on a Mac
it did nothing for the tester.

## Checked

- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.
- Not tried in the game before release: Enemy Territory's game files
  cannot be fetched where it is built.

**"Where Is Marker" is back on the Key Binds page, and a key you set to it works again.**

- **Where Is Marker** does the same as N: it says what the marker is on,
  how far it is and how high, then turns you toward the way to it and
  says *"Facing the way"*. Put it on any key you like on the Key Binds
  page.
- **N** is unchanged: it says where the marker is and turns you toward
  it. **Shift+N** resets the spawn timer.
- **Keypad dot** stays free.

## What went wrong

1.4.4.4 took away the Where Is Marker command along with Keypad dot's
bind. A key you had set to it yourself, such as N, then did nothing,
and the marker's beep kept saying you faced the wrong way.

## Checked

- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.
- Not tried in the game before release: Enemy Territory's game files
  cannot be fetched where it is built.

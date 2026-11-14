**The main menu's first button is said as "Play online" - this time it works.**

- 1.4.4 meant to say *"Play online"* for the main menu's first button,
  but it still said *"Play"*. It now says *"Play online"*.

## What went wrong

1.4.4 looked for the words "open playonline" in what the button does,
but the game stores each of those words in quotation marks, so the two
never matched. It now looks for the name of the screen alone, on the
main menu's button. A new check rebuilds the button the way the game
does, and fails if the name would not be found.

## Checked

- `play_online_label_test.py`: fails on 1.4.4's code, passes on this.
- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.

**The host page and the in-match server info read out properly, and the campaign list says how to pick one map.**

- **Host page**: the checkboxes around Password now say their names and
  whether they are on, and moving up or down into the list of maps or
  campaigns says which list it is and the row you are on. Up, Down,
  Page Up, Page Down, Home and End move through it, a row at a time or a
  page at a time, and each row is read. An empty row is said as
  *"blank"*.
- **Choosing one map**: when Game Type is set to campaigns, the list
  says *"Campaign list"*, and adds *"For one map, set Game Type to
  Single-Map Objective"*. Set that, and the list becomes the map list.
- **Server info during a match** (Escape, then Server Info): the player
  list reads row by row, each player as name, score and ping, after a
  *"Players"* heading.

## What went wrong

The host page's checkboxes had no text of their own, so the screen
reader had nothing to say for them, and the map list could not take
focus from the keyboard, so moving into it went silent. The server info
list was read as one run of columns with no names.

## Checked

- On the host page, from Password down: each checkbox said its name and
  state, the list said its name and each row as Up and Down moved, and
  switching Game Type swapped the campaign list for the map list.
- In a match, Server Info read each player's name, score and ping.
- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.

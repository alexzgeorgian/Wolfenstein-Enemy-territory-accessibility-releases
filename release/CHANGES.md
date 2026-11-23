**N turns you even while you run, turning no longer slows you down, and the old objective report is quiet while a marker is out.**

- **N** turns you to face the way, then says *"Facing the way"*, even
  while you are running. If the turn falls short, it turns again by
  itself instead of saying *"Could not turn all the way"*.
- **Turning keeps you running.** N's turn, and the compass steps of the
  turn keys, used to hold the game's walk key to turn faster, which
  slowed you to a walk for every turn. They now turn just as fast
  without it, so you keep your full speed.
- **With a marker out**, getting stuck against a wall no longer reads
  out the objective's straight line (*"136 meters to objective, turn
  left toward the objective"*). The marker's sound and N lead the way.
  Without a marker, it still does.

## What went wrong

N turned you toward a point on the way a few metres ahead. If you were
running, you reached that point while the view was still turning, the
direction to it swung round behind you, and the turn gave up. N now
turns you to a fixed direction, taken when you press it.

## Checked

- On the real Oasis, running with forward held and pressing N every
  three seconds, from the Allied camp to the Old City Water Pump: turned
  every time, *"Facing the way"* each time, never *"Could not turn"*,
  and no objective report on the way.
- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.

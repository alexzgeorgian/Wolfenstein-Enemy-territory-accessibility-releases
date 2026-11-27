**Axis lets you in when you host: a team limit the match runs with is lifted and said; the team list says why a team is closed; the end of a match is read out; the intro movie is described.**

- **Why a team is closed**: in the limbo menu's team list, each team is
  said with how many players are on it, and, when the menu calls it
  closed, why, with the numbers - for example *"Axis, 3 players, closed
  by the menu: Axis has 3 players, and this match allows 3 a team"*.
  Before, it only said "full", whatever the reason.
- **Picking a closed team anyway**: Enter on it takes it all the same.
  Confirm then asks the match itself, and the match's answer is said. If
  the menu's own count was wrong, you are in; if not, you hear the
  match's reason.
- **"The Axis team is full!" in a game you host**: the match you host
  was running with a limit of players per team, though Host Game showed
  0. As it is your own server, the mod now lifts the limit, tells you
  what it was, and joins you to the team you chose.
- **The end of a match**: when the results screen comes up, you hear who
  won, where you came and with how many XP, the best three players, and
  the seconds to the next map.

- **The intro movie, described**: while the game's intro plays, you
  hear what it shows, a line per scene - the logos, the war map of
  Europe with its three targets, the attack on the Würzburg radar, the
  tank at the fuel dump, the rail gun, and the burning emblem. It now
  plays at every start, as the game used to - Escape skips it. Before,
  the game played it only the very first time, so with the mod it was
  never heard. To watch it again: Options, Accessibility, **Watch the
  intro, described**.

## What went wrong

On a Mac hosting with bots, Axis said "full" and picking it did nothing,
with fewer bots and with Max Players Per Team at 0, while Allies let you
in: the match answered "The Axis team is full!".
The menu turned the team down by its own count before the match was
ever asked, and gave one word for three different checks. The note in
1.4.4.10 put it down to the Public Settings preset keeping the teams
even; that was not it.

## Checked

- On Oasis with every class limit at 0: Axis was said closed for that
  reason, picked, and on Confirm the match's "Soldier is not available!"
  was said.
- On Oasis, a match ended by its time limit said "Match over: Axis win.
  You came 1 of 1, with 0 XP. Best: ..., Next map in about 59 seconds".
- On Oasis with a team limit of 3, "The Axis team is full!" lifted the
  limit to none, said so, and joined Axis.
- The intro, played from the console, said all sixteen lines in turn,
  then the main menu came up.
- The mod libraries build with the feature on and off.

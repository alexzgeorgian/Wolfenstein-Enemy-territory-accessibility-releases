**Settings, team, class and weapons are chosen from lists that Enter opens, Custom can be picked again, and lists no longer trap the arrow keys.**

- **Settings with several choices** - Game Type, Auto-Configure Server,
  Dedicated Server and the rest - now say *"list"* after their value.
  Press **Enter** to open the list: it says how many choices there are
  and which one is set. **Up** and **Down** go through them, **Enter**
  picks one, and **Escape** closes the list without changing anything.
  A mouse click still steps the setting on, as before.
- **Custom comes back.** Auto-Configure Server reads *"Custom"* until
  you pick something else; Custom now stays in its list, first, so you
  can pick it again.
- **Lists let you out.** Up at the top of a list, or Down at the
  bottom, moves on to the control before or after it. On the host page,
  Down past the last campaign or map reaches **Back**, **Advanced** and
  **Start Server**, and Up from the first goes back to the settings.
- **The limbo menu** (L) now has five stops: **Team**, **Class**,
  **Primary weapon**, **Secondary weapon** and **Confirm and spawn**.
  Each of the first four says what is set, such as *"Class, Soldier, 1
  of 5, list"*. **Enter** opens its list, Up and Down go through the
  choices, each said with whether it is selected, full or unavailable,
  **Enter** picks one, and **Backspace** closes the list unchanged.
  Escape still closes the whole limbo menu. A weapon slot with only one
  weapon is skipped.
- **Updating on the Mac**: when a new version was offered at start-up
  on a Mac set up for bots, the game began updating its bots file at the
  same moment, and **Download** was refused. The bots file now waits, so
  the update downloads.

## What went wrong

Enter stepped a setting on to its next choice, so to reach one you had
to listen to each in turn, and a value that was none of the choices,
like Custom, could not be got back once you stepped past it. A list
kept Up and Down at its ends, so on the host page you could not move
past the campaign list. The limbo menu listed every team and class as
its own stop, and stepped the weapons on one at a time.

## Checked

- On the host page: Game Type changed from Campaign to Single-Map
  Objective from its list; Auto-Configure Server set to Public Settings
  and back to Custom; Escape closed a list without a change; Down
  through the campaign list to Start Server, and Up back to Balanced
  Teams.
- On Oasis, from spectator: Allies, Medic, then Confirm and spawn put
  the player in play as an Allied medic; Allies, Soldier, with the
  Flamethrower and then the Bazooka picked from the primary weapon list.
- Every engine check the CI runs passes, and the mod libraries build
  with the feature on and off.

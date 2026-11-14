#!/usr/bin/env python3
"""Build zzzz_rtcw.pk3: No Quarter with Return to Castle Wolfenstein's
sounds, and its Tesla gun.

The sounds and models belong to id Software and are not ours to hand out,
so nothing here ships them. This reads them from the player's own copy of
RTCW (the pak0.pk3 and mp_pak0.pk3 in its main folder) and writes a pk3
that puts each sound under the name No Quarter plays for the same thing:
the weapons, explosions, bullet hits, voice chats, footsteps and a few
player sounds. It also gives the Tesla gun the mode adds RTCW's models,
icons and zap, in place of the stand-ins the mode ships, and the Allied
covert ops' Snooper RTCW's Garand.

Put the result in the nq folder. Its name sorts after No Quarter's pk3s
and after the mode's zzz_accessibility_nq.pk3, so what it carries wins.

    python3 make-rtcw-sounds.py /path/to/RTCW/main zzzz_rtcw.pk3

What RTCW never had keeps its No Quarter sound: weapons such as the
shotgun, BAR, Browning and StG44, most distant echoes, and the newer
voice chats.
"""

import os
import sys
import zipfile

# No Quarter's name <- RTCW's name, both under sound/
SOUNDS = {
    # Pistols
    "weapons/colt/colt_fire.wav": "weapons/colt/coltf1.wav",
    "weapons/colt/colt_reload.wav": "weapons/colt/colt_reload.wav",
    "weapons/colt/colt_reload_fast.wav": "weapons/colt/colt_reload.wav",
    "weapons/colt/colt_reload_akimbo.wav": "weapons/colt/colt_reload2.wav",
    "weapons/colt/colt_silence.wav": "weapons/luger/silencerf1.wav",
    "weapons/luger/luger_fire.wav": "weapons/luger/lugerf1.wav",
    "weapons/luger/luger_reload.wav": "weapons/luger/luger_reload.wav",
    "weapons/luger/luger_reload_fast.wav": "weapons/luger/luger_reload.wav",
    "weapons/luger/luger_reload_akimbo.wav": "weapons/luger/luger_reload.wav",
    "weapons/luger/luger_silence.wav": "weapons/luger/silencerf1.wav",
    "weapons/misc/silence_on.wav": "weapons/luger/silencerattatch.wav",
    "weapons/misc/silence_off.wav": "weapons/luger/silencerremove.wav",
    # Submachine guns
    "weapons/mp40/mp40_fire.wav": "weapons/mp40/mp40f1.wav",
    "weapons/mp40/mp40_reload.wav": "weapons/mp40/mp40_reload.wav",
    "weapons/mp40/mp40_reload_fast.wav": "weapons/mp40/mp40_reload.wav",
    "weapons/thompson/thompson_fire.wav": "weapons/thompson/thompson.wav",
    "weapons/thompson/thompson_reload.wav": "weapons/thompson/thompson_reload.wav",
    "weapons/thompson/thompson_reload_fast.wav": "weapons/thompson/thompson_reload.wav",
    "weapons/sten/sten_fire.wav": "weapons/sten/stenf1.wav",
    "weapons/sten/sten_reload.wav": "weapons/sten/sten_reload.wav",
    "weapons/sten/sten_reload_fast.wav": "weapons/sten/sten_reload.wav",
    "weapons/sten/sten_heat.wav": "weapons/sten/sten_overheat.wav",
    # Rifles: the K43 and Kar98 take the Mauser's, the Garand its own;
    # the covert ops' scoped rifles take RTCW's sniper rifle and Snooper
    "weapons/k43/k43_fire.wav": "weapons/mauser/mauserf1.wav",
    "weapons/k43/k43_reload.wav": "weapons/mauser/mauser_reload.wav",
    "weapons/k43/k43_fire_silence.wav": "weapons/mauser/sniperf1.wav",
    "weapons/garand/m1_fire.wav": "weapons/garand/garandf1.wav",
    "weapons/garand/m1_reload.wav": "weapons/garand/garand_reload.wav",
    "weapons/garand/m1_fire_silence.wav": "weapons/garand/snooperf1.wav",
    "weapons/fg42/fg42_fire.wav": "weapons/fg42/fg42f1.wav",
    "weapons/fg42/fg42_reload.wav": "weapons/fg42/fg42_reload.wav",
    "weapons/fg42/fg42_reload_fast.wav": "weapons/fg42/fg42_reload.wav",
    # Venom: No Quarter already uses RTCW's names
    "weapons/venom/venomf1.wav": "weapons/venom/venomf1.wav",
    "weapons/venom/venomsu1.wav": "weapons/venom/venomsu1.wav",
    "weapons/venom/venomsd1.wav": "weapons/venom/venomsd1.wav",
    "weapons/venom/venom_overheat.wav": "weapons/venom/venom_overheat.wav",
    "weapons/venom/venom_reload.wav": "weapons/venom/venom_reload.wav",
    "weapons/venom/venom_reload_fast.wav": "weapons/venom/venom_reload.wav",
    # Heavy weapons
    "weapons/rocket/rocket_fire.wav": "weapons/rocket/rocklf1a.wav",
    "weapons/rocket/rocket_fly.wav": "weapons/rocket/rockfly.wav",
    "weapons/rocket/rocket_expl.wav": "weapons/rocket/rocklx1a.wav",
    "weapons/flamethrower/flame_burn.wav": "weapons/flamethrower/fl_fire.wav",
    "weapons/flamethrower/flame_pilot.wav": "weapons/flamethrower/fl_blow.wav",
    "weapons/flamethrower/flame_up.wav": "weapons/flamethrower/fl_start.wav",
    "weapons/flamethrower/flame_fire.wav": "weapons/flamethrower/fl_stream.wav",
    "weapons/mortar/mortar_fire.wav": "weapons/mortar/mortarf1.wav",
    "weapons/mortar/mortar_fire_alt.wav": "weapons/mortar/mortarf1.wav",
    # Explosives: RTCW's grenades blew up with the rocket's sound
    "weapons/grenade/gren_expl.wav": "weapons/rocket/rocklx1a.wav",
    "weapons/grenade/bounce_hard1.wav": "weapons/grenade/hgrenb1a.wav",
    "weapons/grenade/bounce_hard2.wav": "weapons/grenade/hgrenb2a.wav",
    "weapons/grenade/bounce_soft1.wav": "weapons/grenade/hg_dirt1a.wav",
    "weapons/grenade/bounce_soft2.wav": "weapons/grenade/hg_dirt2a.wav",
    "weapons/grenade/bounce_metal1.wav": "weapons/grenade/hg_metal1a.wav",
    "weapons/grenade/bounce_metal2.wav": "weapons/grenade/hg_metal2a.wav",
    "weapons/grenade/bounce_wood1.wav": "weapons/grenade/hg_wood1a.wav",
    "weapons/grenade/bounce_wood2.wav": "weapons/grenade/hg_wood2a.wav",
    "weapons/dynamite/dynamite_expl.wav": "weapons/dynamite/dynamite_exp.wav",
    "weapons/dynamite/dynamite_expl_far.wav": "weapons/dynamite/dynamite_exp_dist.wav",
    "weapons/dynamite/dynamite_bounce.wav": "weapons/dynamite/dynamite_bounce.wav",
    # Knife and fists
    "weapons/knife/knife_slash1.wav": "weapons/knife/knife_slash1.wav",
    "weapons/knife/knife_slash2.wav": "weapons/knife/knife_slash2.wav",
    "weapons/knife/knife_slash3.wav": "weapons/knife/knife_slash1.wav",
    "weapons/knife/knife_hit1.wav": "weapons/knife/knife_hit1.wav",
    "weapons/knife/knife_hit2.wav": "weapons/knife/knife_hit2.wav",
    "weapons/knife/knife_hit3.wav": "weapons/knife/knife_hit3.wav",
    "weapons/knife/knife_hit4.wav": "weapons/knife/knife_hit4.wav",
    "weapons/knife/knife_hitwall1.wav": "weapons/knife/knife_hitwall1.wav",
    "weapons/melee/fstatck.wav": "weapons/melee/fstatck.wav",
    "weapons/melee/fstmiss.wav": "weapons/melee/fstmiss.wav",
    # Switching, the empty click, firing under water
    "weapons/misc/change.wav": "weapons/change.wav",
    "weapons/misc/fire_dry.wav": "weapons/noammo.wav",
    "weapons/misc/fire_water.wav": "weapons/underwaterfire.wav",
}

# Bullet hits: No Quarter picks one of five; RTCW had fewer, so they repeat
for n in range(5):
    SOUNDS["weapons/impact/metal%d.wav" % (n + 1)] = "weapons/bullethit_metal%d.wav" % (n % 3 + 1)
    SOUNDS["weapons/impact/wood%d.wav" % (n + 1)] = "weapons/bullethit_wood%d.wav" % (n % 3 + 1)
    SOUNDS["weapons/impact/glass%d.wav" % (n + 1)] = "weapons/bullethit_glass1.wav"
    SOUNDS["weapons/impact/stone%d.wav" % (n + 1)] = "weapons/ric%d.wav" % (n % 4 + 1)
    SOUNDS["weapons/impact/whizz%d.wav" % (n + 1)] = "weapons/machinegun/buletby1.wav"


# Voice chats, matched by their names in the two games' chat scripts;
# where No Quarter has more takes of a line than RTCW, they repeat.
# Hold your fire and I'm a lieutenant were renamed in Enemy Territory.
# Its newer chats (field ops, covert ops, vehicles, mines) stay as they are.
SOUNDS.update({
    "chat/allies/41a.wav": "multiplayer/allies/a-affirmative.wav",
    "chat/allies/41b.wav": "multiplayer/allies/a-affirmative.wav",
    "chat/allies/41c.wav": "multiplayer/allies/a-affirmative.wav",
    "chat/allies/13a.wav": "multiplayer/allies/a-all_clear.wav",
    "chat/allies/13b.wav": "multiplayer/allies/a-all_clear.wav",
    "chat/allies/55a.wav": "multiplayer/allies/a-bye1.WAV",
    "chat/allies/55b.wav": "multiplayer/allies/a-bye2.WAV",
    "chat/allies/55c.wav": "multiplayer/allies/a-bye1.WAV",
    "chat/allies/55d.wav": "multiplayer/allies/a-bye2.WAV",
    "chat/allies/55e.wav": "multiplayer/allies/a-bye1.WAV",
    "chat/allies/57a.wav": "multiplayer/allies/a-yeah1.WAV",
    "chat/allies/57b.wav": "multiplayer/allies/a-yeah2.WAV",
    "chat/allies/57c.wav": "multiplayer/allies/a-yeah3.WAV",
    "chat/allies/57d.wav": "multiplayer/allies/a-yeah4.WAV",
    "chat/allies/57e.wav": "multiplayer/allies/a-yeah5.WAV",
    "chat/allies/57f.wav": "multiplayer/allies/a-yeah1.WAV",
    "chat/allies/57g.wav": "multiplayer/allies/a-yeah2.WAV",
    "chat/allies/57h.wav": "multiplayer/allies/a-yeah3.WAV",
    "chat/allies/57i.wav": "multiplayer/allies/a-yeah4.WAV",
    "chat/allies/57j.wav": "multiplayer/allies/a-yeah5.WAV",
    "chat/allies/57k.wav": "multiplayer/allies/a-yeah1.WAV",
    "chat/allies/57l.wav": "multiplayer/allies/a-yeah2.WAV",
    "chat/allies/34a.wav": "multiplayer/allies/a-clearpath1.WAV",
    "chat/allies/34b.wav": "multiplayer/allies/a-clearpath1.WAV",
    "chat/allies/25a.wav": "multiplayer/allies/a-cover_me.wav",
    "chat/allies/25b.wav": "multiplayer/allies/a-cover_me.wav",
    "chat/allies/25c.wav": "multiplayer/allies/a-cover_me.wav",
    "chat/allies/25d.wav": "multiplayer/allies/a-cover_me.wav",
    "chat/allies/35a.wav": "multiplayer/allies/a-defendobj1.WAV",
    "chat/allies/35b.wav": "multiplayer/allies/a-defendobj1.WAV",
    "chat/allies/36a.wav": "multiplayer/allies/a-disarm1.WAV",
    "chat/allies/36b.wav": "multiplayer/allies/a-disarm1.WAV",
    "chat/allies/12a.wav": "multiplayer/allies/a-enemyweak1.WAV",
    "chat/allies/12b.wav": "multiplayer/allies/a-enemyweak1.WAV",
    "chat/allies/15a.wav": "multiplayer/allies/a-fire_in_the_hole.wav",
    "chat/allies/15b.wav": "multiplayer/allies/a-fire_in_the_hole.wav",
    "chat/allies/31a.wav": "multiplayer/allies/a-followme1.WAV",
    "chat/allies/31b.wav": "multiplayer/allies/a-followme1.WAV",
    "chat/allies/586a.wav": "multiplayer/allies/a-goodgame1.WAV",
    "chat/allies/586b.wav": "multiplayer/allies/a-goodgame1.WAV",
    "chat/allies/586c.wav": "multiplayer/allies/a-goodgame1.WAV",
    "chat/allies/56a.wav": "multiplayer/allies/a-greatshot1.WAV",
    "chat/allies/56b.wav": "multiplayer/allies/a-greatshot1.WAV",
    "chat/allies/54a.wav": "multiplayer/allies/a-hi1.WAV",
    "chat/allies/54b.wav": "multiplayer/allies/a-hi2.WAV",
    "chat/allies/54c.wav": "multiplayer/allies/a-hi3.WAV",
    "chat/allies/54d.wav": "multiplayer/allies/a-hi1.WAV",
    "chat/allies/54e.wav": "multiplayer/allies/a-hi2.WAV",
    "chat/allies/26a.wav": "multiplayer/allies/a-hold_fire.wav",
    "chat/allies/26b.wav": "multiplayer/allies/a-hold_fire.wav",
    "chat/allies/63a.wav": "multiplayer/allies/a-engineer.wav",
    "chat/allies/63b.wav": "multiplayer/allies/a-engineer.wav",
    "chat/allies/64a.wav": "multiplayer/allies/a-lt.wav",
    "chat/allies/62a.wav": "multiplayer/allies/a-medic.wav",
    "chat/allies/62b.wav": "multiplayer/allies/a-medic.wav",
    "chat/allies/61a.wav": "multiplayer/allies/a-soldier.wav",
    "chat/allies/61b.wav": "multiplayer/allies/a-soldier.wav",
    "chat/allies/14a.wav": "multiplayer/allies/a-incoming.wav",
    "chat/allies/14b.wav": "multiplayer/allies/a-incoming.wav",
    "chat/allies/32a.wav": "multiplayer/allies/a-lets_go.wav",
    "chat/allies/32b.wav": "multiplayer/allies/a-lets_go.wav",
    "chat/allies/21a.wav": "multiplayer/allies/a-medic1.wav",
    "chat/allies/21b.wav": "multiplayer/allies/a-medic1.wav",
    "chat/allies/33a.wav": "multiplayer/allies/a-move1.WAV",
    "chat/allies/33b.wav": "multiplayer/allies/a-move1.WAV",
    "chat/allies/22a.wav": "multiplayer/allies/a-ammo.wav",
    "chat/allies/23a.wav": "multiplayer/allies/a-backup.wav",
    "chat/allies/23b.wav": "multiplayer/allies/a-backup.wav",
    "chat/allies/24a.wav": "multiplayer/allies/a-needeng1.WAV",
    "chat/allies/24b.wav": "multiplayer/allies/a-needeng1.WAV",
    "chat/allies/42a.wav": "multiplayer/allies/a-negative.wav",
    "chat/allies/42b.wav": "multiplayer/allies/a-negative.wav",
    "chat/allies/42c.wav": "multiplayer/allies/a-negative.wav",
    "chat/allies/42d.wav": "multiplayer/allies/a-negative.wav",
    "chat/allies/16a.wav": "multiplayer/allies/a-on_defense.wav",
    "chat/allies/16b.wav": "multiplayer/allies/a-on_defense.wav",
    "chat/allies/17a.wav": "multiplayer/allies/a-on_offense.wav",
    "chat/allies/17b.wav": "multiplayer/allies/a-on_offense.wav",
    "chat/allies/46a.wav": "multiplayer/allies/a-oops1.WAV",
    "chat/allies/46b.wav": "multiplayer/allies/a-oops1.WAV",
    "chat/allies/46c.wav": "multiplayer/allies/a-oops1.WAV",
    "chat/allies/11a.wav": "multiplayer/allies/a-pathclear1.WAV",
    "chat/allies/11b.wav": "multiplayer/allies/a-pathclear1.WAV",
    "chat/allies/45a.wav": "multiplayer/allies/a-sorry1.WAV",
    "chat/allies/45b.wav": "multiplayer/allies/a-sorry1.WAV",
    "chat/allies/45c.wav": "multiplayer/allies/a-sorry1.WAV",
    "chat/allies/18a.wav": "multiplayer/allies/a-takingfire1.WAV",
    "chat/allies/18b.wav": "multiplayer/allies/a-takingfire1.WAV",
    "chat/allies/43a.wav": "multiplayer/allies/a-thanks1.WAV",
    "chat/allies/43b.wav": "multiplayer/allies/a-thanks1.WAV",
    "chat/allies/43c.wav": "multiplayer/allies/a-thanks1.WAV",
    "chat/allies/43d.wav": "multiplayer/allies/a-thanks1.WAV",
    "chat/allies/44c.wav": "multiplayer/allies/a-welcome1.WAV",
    "chat/allies/44d.wav": "multiplayer/allies/a-welcome1.WAV",
    "chat/allies/27a.wav": "multiplayer/allies/a-whereto1.WAV",
    "chat/allies/27b.wav": "multiplayer/allies/a-whereto1.WAV",
    "chat/axis/41a.wav": "multiplayer/axis/g-affirmative.wav",
    "chat/axis/41b.wav": "multiplayer/axis/g-affirmative.wav",
    "chat/axis/41c.wav": "multiplayer/axis/g-affirmative.wav",
    "chat/axis/13a.wav": "multiplayer/axis/g-all_clear.wav",
    "chat/axis/13b.wav": "multiplayer/axis/g-all_clear.wav",
    "chat/axis/55a.wav": "multiplayer/axis/g-bye1.wav",
    "chat/axis/55b.wav": "multiplayer/axis/g-bye1.wav",
    "chat/axis/55c.wav": "multiplayer/axis/g-bye1.wav",
    "chat/axis/57a.wav": "multiplayer/axis/g-yeah1.wav",
    "chat/axis/57b.wav": "multiplayer/axis/g-yeah2.wav",
    "chat/axis/57c.wav": "multiplayer/axis/g-yeah3.wav",
    "chat/axis/57d.wav": "multiplayer/axis/g-yeah1.wav",
    "chat/axis/57e.wav": "multiplayer/axis/g-yeah2.wav",
    "chat/axis/57f.wav": "multiplayer/axis/g-yeah3.wav",
    "chat/axis/57g.wav": "multiplayer/axis/g-yeah1.wav",
    "chat/axis/57h.wav": "multiplayer/axis/g-yeah2.wav",
    "chat/axis/34a.wav": "multiplayer/axis/g-clearpath1.wav",
    "chat/axis/34b.wav": "multiplayer/axis/g-clearpath1.wav",
    "chat/axis/25a.wav": "multiplayer/axis/g-cover_me.wav",
    "chat/axis/25b.wav": "multiplayer/axis/g-cover_me.wav",
    "chat/axis/25c.wav": "multiplayer/axis/g-cover_me.wav",
    "chat/axis/25d.wav": "multiplayer/axis/g-cover_me.wav",
    "chat/axis/35a.wav": "multiplayer/axis/g-defendobj1.wav",
    "chat/axis/35b.wav": "multiplayer/axis/g-defendobj1.wav",
    "chat/axis/36a.wav": "multiplayer/axis/g-disarm1.wav",
    "chat/axis/36b.wav": "multiplayer/axis/g-disarm1.wav",
    "chat/axis/12a.wav": "multiplayer/axis/g-enemyweak1.wav",
    "chat/axis/12b.wav": "multiplayer/axis/g-enemyweak1.wav",
    "chat/axis/15a.wav": "multiplayer/axis/g-fire_in_the_hole.wav",
    "chat/axis/15b.wav": "multiplayer/axis/g-fire_in_the_hole.wav",
    "chat/axis/31a.wav": "multiplayer/axis/g-followme1.wav",
    "chat/axis/31b.wav": "multiplayer/axis/g-followme1.wav",
    "chat/axis/586a.wav": "multiplayer/axis/g-goodgame1.wav",
    "chat/axis/586b.wav": "multiplayer/axis/g-goodgame1.wav",
    "chat/axis/56a.wav": "multiplayer/axis/g-greatshot1.wav",
    "chat/axis/56b.wav": "multiplayer/axis/g-greatshot1.wav",
    "chat/axis/54a.wav": "multiplayer/axis/g-hi1.wav",
    "chat/axis/54b.wav": "multiplayer/axis/g-hi3.wav",
    "chat/axis/54c.wav": "multiplayer/axis/g-hi2.wav",
    "chat/axis/26a.wav": "multiplayer/axis/g-hold_fire.wav",
    "chat/axis/26b.wav": "multiplayer/axis/g-hold_fire.wav",
    "chat/axis/63a.wav": "multiplayer/axis/g-engineer.wav",
    "chat/axis/63b.wav": "multiplayer/axis/g-engineer.wav",
    "chat/axis/64a.wav": "multiplayer/axis/g-lt.wav",
    "chat/axis/64b.wav": "multiplayer/axis/g-lt.wav",
    "chat/axis/62a.wav": "multiplayer/axis/g-medic.wav",
    "chat/axis/62b.wav": "multiplayer/axis/g-medic.wav",
    "chat/axis/61a.wav": "multiplayer/axis/g-soldier.wav",
    "chat/axis/61b.wav": "multiplayer/axis/g-soldier.wav",
    "chat/axis/14a.wav": "multiplayer/axis/g-incoming.wav",
    "chat/axis/14b.wav": "multiplayer/axis/g-incoming.wav",
    "chat/axis/32a.wav": "multiplayer/axis/g-lets_go.wav",
    "chat/axis/32b.wav": "multiplayer/axis/g-lets_go.wav",
    "chat/axis/21a.wav": "multiplayer/axis/g-medic1.wav",
    "chat/axis/21b.wav": "multiplayer/axis/g-medic1.wav",
    "chat/axis/33a.wav": "multiplayer/axis/g-move1.wav",
    "chat/axis/33b.wav": "multiplayer/axis/g-move1.wav",
    "chat/axis/22a.wav": "multiplayer/axis/g-ammo.wav",
    "chat/axis/23a.wav": "multiplayer/axis/g-backup.wav",
    "chat/axis/23b.wav": "multiplayer/axis/g-backup.wav",
    "chat/axis/24a.wav": "multiplayer/axis/g-needeng1.wav",
    "chat/axis/24b.wav": "multiplayer/axis/g-needeng1.wav",
    "chat/axis/42a.wav": "multiplayer/axis/g-negative.wav",
    "chat/axis/42b.wav": "multiplayer/axis/g-negative.wav",
    "chat/axis/42c.wav": "multiplayer/axis/g-negative.wav",
    "chat/axis/16a.wav": "multiplayer/axis/g-on_defense.wav",
    "chat/axis/16b.wav": "multiplayer/axis/g-on_defense.wav",
    "chat/axis/17a.wav": "multiplayer/axis/g-on_offense.wav",
    "chat/axis/17b.wav": "multiplayer/axis/g-on_offense.wav",
    "chat/axis/46a.wav": "multiplayer/axis/g-oops1.wav",
    "chat/axis/46b.wav": "multiplayer/axis/g-oops1.wav",
    "chat/axis/11a.wav": "multiplayer/axis/g-pathclear1.wav",
    "chat/axis/11b.wav": "multiplayer/axis/g-pathclear1.wav",
    "chat/axis/45a.wav": "multiplayer/axis/g-sorry1.wav",
    "chat/axis/45b.wav": "multiplayer/axis/g-sorry1.wav",
    "chat/axis/18a.wav": "multiplayer/axis/g-takingfire1.wav",
    "chat/axis/18b.wav": "multiplayer/axis/g-takingfire1.wav",
    "chat/axis/43a.wav": "multiplayer/axis/g-thanks1.wav",
    "chat/axis/43b.wav": "multiplayer/axis/g-thanks1.wav",
    "chat/axis/43c.wav": "multiplayer/axis/g-thanks1.wav",
    "chat/axis/44c.wav": "multiplayer/axis/g-welcome1.wav",
    "chat/axis/27a.wav": "multiplayer/axis/g-whereto1.wav",
    "chat/axis/27b.wav": "multiplayer/axis/g-whereto1.wav",
    "chat/allies/medic.wav": "multiplayer/allies/a-medic.wav",
    "chat/axis/medic.wav": "multiplayer/axis/g-medic.wav",
})

SOUNDS.update({
    # Distant gunfire
    "weapons/thompson/thompson_far.wav": "multiplayer/thompson_far.wav",
    "weapons/venom/venom_far.wav": "multiplayer/venom_far.wav",
    "weapons/mg42/mg42_far.wav": "multiplayer/mg42_far.wav",
    # Artillery, air strikes, mortars, the Panzerfaust's charge
    "weapons/airstrike/airstrike_plane.wav": "multiplayer/airstrike_01.wav",
    "weapons/artillery/artillery_fly_1.wav": "multiplayer/artillery_01.wav",
    "weapons/artillery/artillery_fly_2.wav": "multiplayer/artillery_01.wav",
    "weapons/artillery/artillery_fly_3.wav": "multiplayer/artillery_01.wav",
    "weapons/artillery/artillery_expl_1.wav": "multiplayer/artillery_exp01.wav",
    "weapons/artillery/artillery_expl_2.wav": "multiplayer/artillery_exp01.wav",
    "weapons/artillery/artillery_expl_3.wav": "multiplayer/artillery_exp01.wav",
    "weapons/airstrike/airstrike_expl_1.wav": "multiplayer/artillery_exp01.wav",
    "weapons/airstrike/airstrike_expl_2.wav": "multiplayer/artillery_exp01.wav",
    "weapons/airstrike/airstrike_expl_3.wav": "multiplayer/artillery_exp01.wav",
    "weapons/mortar/mortar_expl.wav": "multiplayer/mortar_exp03.wav",
    "weapons/mortar/mortar_expl1.wav": "multiplayer/mortar_exp03.wav",
    "weapons/mortar/mortar_expl2.wav": "multiplayer/mortar_exp04.wav",
    "weapons/mortar/mortar_expl3.wav": "multiplayer/mortar_exp03.wav",
    "weapons/rocket/rocket_charge.wav": "multiplayer/p_charge1.wav",
    # Health, packs, revives, getting hurt
    "misc/health_pickup.wav": "multiplayer/health_pickup.wav",
    "items/n_health.wav": "multiplayer/health_pickup.wav",
    "misc/bag_toss.wav": "multiplayer/bag_toss.wav",
    "misc/vo_revive.wav": "multiplayer/vo_revive.wav",
    "player/hurt_barbwire.wav": "multiplayer/hurt_barbwire.wav",
    "player/land_hurt.wav": "multiplayer/land_hurt.wav",
    # Water and gibs
    "player/gasp.wav": "player/bj2/gasp.wav",
    "player/gibsplit1.wav": "player/gibsplt1.wav",
    "player/gurp1.wav": "player/gurp1.wav",
    "player/gurp2.wav": "player/gurp2.wav",
    "player/water_in.wav": "player/watr_in.wav",
    "player/water_out.wav": "player/watr_out.wav",
    "player/water_un.wav": "player/watr_un.wav",
})

# Footsteps: RTCW called stone "step", metal "clank" and water "splash"
for n in range(1, 5):
    for nq, r in (("stone", "step"), ("metal", "clank"), ("water", "splash"),
                  ("wood", "wood"), ("grass", "grass"), ("gravel", "gravel"),
                  ("roof", "roof"), ("snow", "snow"), ("carpet", "carpet")):
        SOUNDS["player/footsteps/%s%d.wav" % (nq, n)] = \
            "player/footsteps/%s%d.wav" % (r, n)

# The Tesla gun: RTCW's crackle in place of the mode's stand-in
SOUNDS["weapons/tesla/tesla_fire.wav"] = "weapons/tesla/zap2.wav"

# The Tesla gun's models, skins and icons, copied as they are
TESLA_FILES = ("models/weapons2/tesla/", "icons/iconw_tesla_1",
               # and the Garand's, for the Snooper
               "models/weapons2/garand/", "icons/iconw_garand_1")

# The mode's weapon file for the Tesla, which this pack replaces with one
# that points at RTCW's models; everything the game side reads stays the same
TESLA_WEAP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "noquarter", "weapons", "tesla.weap")
TESLA_MODELS = (
    ('"models/weapons2/venom/venom_stand.mdc"', '"models/weapons2/tesla/pu_tesla.mdc"'),
    ('"models/weapons2/venom/pu_venom.mdc"', '"models/weapons2/tesla/pu_tesla.mdc"'),
    ('"models/weapons2/venom/weapon.cfg"', '"models/weapons2/tesla/weapon.cfg"'),
    ('"models/weapons2/venom/v_venom_hand.md3"', '"models/weapons2/tesla/v_tesla_hand.mdc"'),
    ('"icons/iconw_venom"', '"icons/iconw_tesla_1"'),
    ('"icons/iconw_venom_1_select"', '"icons/iconw_tesla_1_select"'),
    ('"models/weapons2/venom/venom.mdc"', '"models/weapons2/tesla/tesla.mdc"'),
    ('model\t\t\t\t"models/weapons2/venom/v_venom.md3"',
     'model\t\t\t\t"models/weapons2/tesla/v_tesla.mdc"\n\n'
     '\t\t\tweaponLink\n\t\t\t{\n'
     '\t\t\t\tpart 0\n\t\t\t\t{\n\t\t\t\t\ttag\t\t\t"tag_barrel"\n'
     '\t\t\t\t\tmodel\t\t"models/weapons2/tesla/v_tesla_barrel.mdc"\n\t\t\t\t}\n'
     '\t\t\t\tpart 1\n\t\t\t\t{\n\t\t\t\t\ttag\t\t\t"tag_barrel2"\n'
     '\t\t\t\t\tmodel\t\t"models/weapons2/tesla/v_tesla_barrel2.mdc"\n\t\t\t\t}\n'
     '\t\t\t}'),
)
# The covert ops' M1 Garand as the Snooper, with RTCW's Garand models
SNOOPER_WEAP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "noquarter", "rtcw", "m1_garand_s.weap")
# The one shader the Tesla's arc needs, taken out of RTCW's models.shader
# alone, so nothing of Enemy Territory's own shaders is touched
TESLA_SHADER = "models/weapons2/tesla/zap_scroll2b"

# RTCW's own pk3s, in the order RTCW loads them: a later one wins
PAKS = ("pak0.pk3", "mp_pak0.pk3")


def tesla_weap():
    text = open(TESLA_WEAP).read()
    for venom, tesla in TESLA_MODELS:
        if venom not in text:
            sys.exit("%s no longer has %s; update TESLA_MODELS" % (TESLA_WEAP, venom))
        text = text.replace(venom, tesla)
    return text


def shader_block(text, name):
    """One shader's whole definition, by name, from a .shader file."""
    lines = text.replace("\r", "").split("\n")
    for i, line in enumerate(lines):
        if line.strip().lower() == name:
            depth, block = 0, []
            for line in lines[i:]:
                block.append(line)
                depth += line.count("{") - line.count("}")
                if depth == 0 and "}" in line:
                    return "\n".join(block) + "\n"
    sys.exit("No shader %s in RTCW's models.shader" % name)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    folder, target = sys.argv[1], sys.argv[2]
    found = {}
    for pak in PAKS:
        path = os.path.join(folder, pak)
        if not os.path.exists(path):
            sys.exit("No %s in %s: give RTCW's main folder" % (pak, folder))
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                found[n.lower()] = (path, n)
    missing = sorted({r for r in SOUNDS.values()
                      if "sound/" + r.lower() not in found})
    if missing:
        sys.exit("Not in RTCW's files: %s" % ", ".join(missing))
    opened = {}

    def read(key):
        path, name = found[key]
        if path not in opened:
            opened[path] = zipfile.ZipFile(path)
        return opened[path].read(name)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for nq, r in sorted(SOUNDS.items()):
            out.writestr("sound/" + nq, read("sound/" + r.lower()))
        copied = 0
        for key in sorted(found):
            if key.startswith(TESLA_FILES) and not key.endswith("/"):
                out.writestr(found[key][1], read(key))
                copied += 1
        if not copied:
            sys.exit("No Tesla models in RTCW's files")
        out.writestr("weapons/tesla.weap", tesla_weap())
        out.writestr("weapons/m1_garand_s.weap", open(SNOOPER_WEAP).read())
        out.writestr("scripts/rtcw_tesla.shader",
                     shader_block(read("scripts/models.shader").decode("latin-1"),
                                  TESLA_SHADER))
    for z in opened.values():
        z.close()
    print("Wrote %s: %d sounds, %d model and icon files" % (target, len(SOUNDS), copied))

if __name__ == "__main__":
    main()

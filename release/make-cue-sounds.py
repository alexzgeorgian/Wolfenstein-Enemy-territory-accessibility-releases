#!/usr/bin/env python3
"""Generate the mod's own cue sounds into a directory.

Why these are generated rather than shipped as files
----------------------------------------------------
Every other sound this mod plays is one the game already owns, chosen by
a cvar, so a player can read the path and know exactly what they are
hearing. These cannot work that way: ET's sound set is combat and
world effects, almost all of it one-shot transients with sharp onsets,
and a beacon that loops needs the opposite - sustained or sparse, soft
at the edges, and seamless at the loop point. Nothing in the game fits.

So they are synthesised, and the synthesis lives here as source rather
than as opaque binaries in the repository. Anyone can read what
each sound is made of, change a number and hear the difference.

What the constraints actually are
---------------------------------
  * Mono, 22050 Hz, 16-bit. The engine positions a mono source in 3D
    itself; a stereo file throws that away and the cue stops pointing
    anywhere.
  * Seamless. Each file is one whole loop cycle and both ends sit at
    zero, so the repeat is inaudible.
  * Localisable. A pure low tone is heard but not placed - the ear needs
    high-frequency content to tell front from back. Every tone here
    carries harmonics for that reason alone.
  * Bearable. These run continuously. Sparse duty cycles, soft onsets,
    nothing percussive.

Deterministic: same input, same bytes. The build checks that.

Usage
-----
    ./make-cue-sounds.py <output-directory>
    ./make-cue-sounds.py --preview <output-directory>

--preview writes each sound looped end to end for about six seconds,
the way the game plays it, for listening to outside the game. One loop
of the crosshair tick is a fifth of a second - too short to judge.
"""

import math
import os
import random
import struct
import sys
import wave

RATE = 22050
LEVEL = 0.7


def write(path, samples):
    peak = max(abs(v) for v in samples) or 1.0
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, v / peak)) * LEVEL * 32767))
            for v in samples))


def envelope(i, n, attack, release):
    """Raised cosine at both ends: no click on attack, none at the seam."""
    a, r = int(n * attack), int(n * release)
    if a and i < a:
        return 0.5 - 0.5 * math.cos(math.pi * i / a)
    if r and i > n - r:
        return 0.5 + 0.5 * math.cos(math.pi * (i - (n - r)) / r)
    return 1.0


def tone(f0, duration, cycle, harmonics, attack=0.3, release=0.5):
    """One shaped pulse, padded with silence to a whole loop cycle."""
    n = int(RATE * duration)
    body, phase = [], 0.0
    for i in range(n):
        phase += 2.0 * math.pi * f0 / RATE
        body.append(sum(a * math.sin(m * phase) for m, a in harmonics)
                    * envelope(i, n, attack, release))
    return body + [0.0] * max(0, int(RATE * cycle) - n)


def creak(duration, rate_hz, jitter, modes, seed):
    """Stick-slip friction: irregular impulses ringing a resonant body.

    A creak is not a tone. Surfaces grip, release, grip again, and each
    release rings the door. Regular spacing sounds like machinery, so
    the interval jitters - from a seeded generator, so the file is the
    same every time it is built.
    """
    n = int(RATE * duration)
    out = [0.0] * n
    rng = random.Random(seed)
    i = 0
    while i < n:
        amplitude = 0.55 + 0.45 * rng.random()
        for frequency, decay, weight in modes:
            tail = min(int(RATE * decay * 4), n - i)
            for k in range(tail):
                t = k / RATE
                out[i + k] += (amplitude * weight * math.exp(-t / decay)
                               * math.sin(2.0 * math.pi * frequency * t))
        step = RATE / (rate_hz * (1.0 + jitter * (rng.random() - 0.5)))
        i += max(1, int(step))

    # Swell to silence at both ends. Hides the seam, and is what a real
    # creak does anyway.
    for k in range(n):
        out[k] *= 0.5 - 0.5 * math.cos(2.0 * math.pi * k / n)
    return out


def strikes(hits, cycle, modes):
    """Struck metal: each hit rings a few modes and dies away.

    A hammer on a girder, which is what building in this game sounds
    like. Each hit gets a 3 ms rise so the onset is a tap rather than a
    click, and the last one has rung out well before the loop comes
    round.
    """
    n = int(RATE * cycle)
    out = [0.0] * n
    rise = int(RATE * 0.003)
    for start, amplitude in hits:
        i = int(RATE * start)
        for frequency, decay, weight in modes:
            tail = min(int(RATE * decay * 7), n - i)
            for k in range(tail):
                t = k / RATE
                attack = min(1.0, k / rise) if rise else 1.0
                out[i + k] += (amplitude * weight * attack * math.exp(-t / decay)
                               * math.sin(2.0 * math.pi * frequency * t))
    return out


def fuse(duration, cycle, hum_hz, seed):
    """A burning fuse over a low hum: something here is meant to go up.

    The hiss is softened noise - noise carries every frequency, which is
    what lets the ear place it, front from back as well as left from
    right. The hum under it gives it weight, so it reads as a warning
    rather than as steam. Seeded, so the file is the same every build.
    """
    n = int(RATE * duration)
    rng = random.Random(seed)
    out, smooth, phase = [], 0.0, 0.0
    for i in range(n):
        smooth += 0.35 * ((rng.random() * 2.0 - 1.0) - smooth)
        phase += 2.0 * math.pi * hum_hz / RATE
        hum = 0.55 * math.sin(phase) + 0.25 * math.sin(2.0 * phase) + 0.12 * math.sin(3.0 * phase)
        out.append((0.75 * smooth + hum) * envelope(i, n, 0.25, 0.55))
    return out + [0.0] * max(0, int(RATE * cycle) - n)


def chime(notes, cycle, partials):
    """A small bell: each note rings inharmonic partials and fades.

    Bells are the oldest rallying signal there is, and nothing else in
    this set rings, so a chime cannot be taken for a door, a target or
    the marker. The partials of a real bell are not whole multiples of
    the note, which is what makes it sound like a bell and not an organ.
    """
    n = int(RATE * cycle)
    out = [0.0] * n
    rise = int(RATE * 0.004)
    for start, f0, amplitude in notes:
        i = int(RATE * start)
        for ratio, decay, weight in partials:
            tail = min(int(RATE * decay * 7), n - i)
            for k in range(tail):
                t = k / RATE
                attack = min(1.0, k / rise)
                out[i + k] += (amplitude * weight * attack * math.exp(-t / decay)
                               * math.sin(2.0 * math.pi * f0 * ratio * t))
    return out


def engine(cycle, rumble_hz, chug_hz, seed):
    """An engine idling, and its treads: the tank.

    A low rumble, chugging at the engine's beat, with the dry rattle of
    tread links over it - the rattle is noise, which is what lets the
    ear place a sound this low, front from back. The whole cycle swells
    up and dies away, so the seam is silent and it pulses like an engine
    labouring. Seeded, so the file is the same every build.
    """
    n = int(RATE * cycle)
    rng = random.Random(seed)
    out, smooth = [], 0.0
    for i in range(n):
        t = i / RATE
        chug = 0.6 + 0.4 * math.sin(2.0 * math.pi * chug_hz * t) ** 2
        rumble = (math.sin(2.0 * math.pi * rumble_hz * t) + 0.6 * math.sin(4.0 * math.pi * rumble_hz * t)
                  + 0.35 * math.sin(6.0 * math.pi * rumble_hz * t))
        smooth += 0.5 * ((rng.random() * 2.0 - 1.0) - smooth)
        rattle = smooth * (1.0 if (i // int(RATE / 16)) % 2 == 0 else 0.25)
        out.append((0.8 * rumble * chug + 0.35 * rattle) * (0.5 - 0.5 * math.cos(2.0 * math.pi * i / n)))
    return out


def thud(cycle, low_hz, decay, seed):
    """Walking into a wall: a dull, heavy thud.

    A low tone that drops in pitch as it dies, the way a blow on
    something massive sounds, under a short burst of muffled noise for the
    impact - the noise is what lets the ear place it. Over in a tenth of
    a second, then silence to the end of the file.
    """
    n = int(RATE * cycle)
    rng = random.Random(seed)
    out, smooth, phase = [], 0.0, 0.0
    rise = int(RATE * 0.002)
    for i in range(n):
        t = i / RATE
        phase += 2.0 * math.pi * low_hz * (1.0 - 0.35 * min(1.0, t / decay)) / RATE
        smooth += 0.08 * ((rng.random() * 2.0 - 1.0) - smooth)
        attack = min(1.0, i / rise)
        body = math.sin(phase) * math.exp(-t / decay)
        hit = 2.5 * smooth * math.exp(-t / (decay * 0.3))
        out.append(attack * (body + hit) * envelope(i, n, 0.0, 0.9))
    return out


# A small hand bell: the hum, the fundamental, and the bright minor
# third and fifth partials that make a bell a bell.
BELL = [(0.5, 0.180, 0.45), (1.0, 0.150, 1.0), (1.19, 0.090, 0.40),
        (1.50, 0.070, 0.30), (2.0, 0.050, 0.25)]

# A wooden rung under a boot: the bar's own partials, which for a bar
# of wood are not whole multiples either, dying fast.
RUNG = [(1.0, 0.045, 1.0), (2.76, 0.022, 0.45), (5.40, 0.012, 0.25)]

# Steel rings high and long; a light tap on it, not a forge.
METAL = [(1320, 0.050, 1.0), (2970, 0.025, 0.40), (660, 0.070, 0.30)]

# Wood rings low and dies fast. The locked door is duller and slower
# still: no ring, because nothing is moving.
WOOD = [(165, 0.030, 1.0), (410, 0.018, 0.55), (880, 0.010, 0.25)]
LOCKED = [(110, 0.020, 1.0), (240, 0.012, 0.40)]

# Things on the ground. A health pack is soft, round and warm; an
# ammo pack's cartridges click, bright and dry; a gun is heavier metal,
# one clank.
SOFT = [(1.0, 0.120, 1.0), (2.0, 0.060, 0.30), (3.0, 0.030, 0.12)]
CLICK = [(2400, 0.006, 1.0), (4700, 0.004, 0.45), (1150, 0.010, 0.30)]
GUNMETAL = [(520, 0.060, 1.0), (1240, 0.030, 0.55), (2650, 0.016, 0.35)]

# A hollow box knocked on: a wooden thing with air in it, its partials
# ringing a little longer than the rungs of a ladder.
HOLLOW = [(330, 0.045, 1.0), (790, 0.028, 0.55), (1580, 0.014, 0.30), (2900, 0.006, 0.15)]

# Bright enough to be placed, and to be heard over gunfire.
BRIGHT = [(1, 1.0), (2, 0.5), (3, 0.28), (4, 0.15)]
WARM = [(1, 1.0), (2, 0.3), (3, 0.1)]

SOUNDS = {
    # Doors. Slow and unhurried: this is scenery you navigate by, not an
    # alarm. Chosen by the tester from three candidates.
    "door_creak.wav": lambda: creak(2.40, 14, 0.8, WOOD, 7),
    "door_creak_locked.wav": lambda: creak(2.20, 6, 0.6, LOCKED, 5),

    # The crosshair. These repeat about six times a second, far faster
    # than a navigation beacon, because sweeping across a target may put
    # it under the crosshair for only a fraction of a second - a cue
    # that repeated once a second would simply be missed.
    "crosshair_enemy.wav": lambda: tone(880, 0.035, 0.18, BRIGHT),
    # Low and soft. "Hold fire" must never sound like "shoot".
    "crosshair_teammate.wav": lambda: tone(330, 0.050, 0.22, WARM),

    # The player's own marker. A beacon, so it is slow: one ping a
    # second is enough to steer by and sparse enough to play under
    # everything else for a whole walk. Bright, because a sound with
    # overtones is far easier to place left or right than a pure tone,
    # and pitched between the two crosshair cues so it is mistaken for
    # neither.
    "marker_beacon.wav": lambda: tone(587, 0.160, 1.00, BRIGHT, 0.08, 0.85),
    # The same marker, where the game's stereo alone cannot say. Left
    # and right it can; in front and behind it cannot, and the tester
    # could not tell a marker behind from one ahead - with gunfire ahead
    # too. So the ping drops as the marker goes round: a fourth lower
    # off to either side, and behind an octave lower and twice - "turn
    # round". Same speed and the same bright overtones, so it is still
    # the marker and still easy to place.
    "marker_side.wav": lambda: tone(440, 0.160, 1.00, BRIGHT, 0.08, 0.85),
    "marker_behind.wav": lambda: (tone(294, 0.120, 0.24, BRIGHT, 0.08, 0.85)
                                  + tone(294, 0.120, 0.76, BRIGHT, 0.08, 0.85)),

    # Objectives. A construction site your team can build taps like a
    # hammer on steel - two light taps and a rest. An enemy objective
    # you can blow up hisses like a lit fuse over a low hum. Both slower
    # than the marker, because there can be two or three of them in
    # earshot at once, and unlike anything else here so neither is
    # mistaken for a door, the crosshair or the marker.
    "build_site.wav": lambda: strikes([(0.020, 1.0), (0.290, 0.75)], 1.40, METAL),
    "demolition_target.wav": lambda: fuse(0.55, 1.70, 98, 11),

    # A flag that can be captured: a two-note bell, high then low - a
    # call to come and take it. Slower still than the others: a flag
    # is a place to go, not something about to happen.
    "flag_capture.wav": lambda: chime([(0.020, 784, 1.0), (0.300, 659, 0.85)], 1.80, BELL),

    # A ladder: three knocks on wooden rungs, each a step higher - the
    # sound of somebody going up. Wood, like the doors, because a ladder
    # is part of the building, but struck rather than creaking, so the
    # two are never confused. Its own speed, between the marker and the
    # sites.
    "ladder.wav": lambda: chime([(0.020, 392, 1.0), (0.200, 494, 0.9), (0.380, 587, 0.8)], 1.50, RUNG),

    # Things to pick up, heard from where they lie, so a player can walk
    # to them. Each its own kind of sound, so which is which is heard
    # before it is said: a health pack, two soft notes rising - getting
    # better; an ammo pack, three quick dry clicks - cartridges; a gun,
    # one heavy clank. Slower than the marker and softer than the
    # objectives, because they are things on the way, not where to go.
    "health_pack.wav": lambda: chime([(0.020, 523, 0.9), (0.220, 659, 1.0)], 1.30, SOFT),
    "ammo_pack.wav": lambda: strikes([(0.020, 1.0), (0.110, 0.8), (0.200, 0.65)], 1.30, CLICK),
    "weapon_ground.wav": lambda: strikes([(0.020, 1.0)], 1.50, GUNMETAL),

    # The tank to escort: an engine labouring, low, with its treads
    # rattling - the one big thing on the map that moves.
    "tank.wav": lambda: engine(1.20, 55.0, 5.0, 13),

    # A landmine close by: two fast high beeps and a short rest, over and
    # over - the one alarm in the set. Higher and quicker than the enemy
    # under the crosshair, so "mine here" is never taken for "shoot".
    "landmine.wav": lambda: (tone(1397, 0.045, 0.11, BRIGHT, 0.15, 0.5)
                             + tone(1397, 0.045, 0.31, BRIGHT, 0.15, 0.5)),

    # Walking into something: played once, from where the player hit.
    # The tester asked for what audio games do - a sound when the way is
    # shut. A wall is a dull low thud, heavy and over at once; a thing -
    # a door, a crate, a vehicle - a hollow wooden knock, higher and
    # ringing a moment, so the two are never mistaken for each other.
    "bump_wall.wav": lambda: thud(0.30, 70.0, 0.060, 17),
    "bump_object.wav": lambda: strikes([(0.004, 1.0)], 0.30, HOLLOW),
}


PREVIEW_SECONDS = 6.0


def main():
    args = sys.argv[1:]
    preview = bool(args) and args[0] == "--preview"
    if preview:
        args = args[1:]
    if len(args) != 1:
        sys.exit("usage: make-cue-sounds.py [--preview] <output-directory>")

    outdir = args[0]
    os.makedirs(outdir, exist_ok=True)

    for name, build in sorted(SOUNDS.items()):
        samples = build()
        if preview:
            samples = samples * max(1, int(math.ceil(PREVIEW_SECONDS * RATE / len(samples))))
        path = os.path.join(outdir, name)
        write(path, samples)
        print("  %-24s %5.2fs" % (name, len(samples) / RATE))

    return 0


if __name__ == "__main__":
    sys.exit(main())

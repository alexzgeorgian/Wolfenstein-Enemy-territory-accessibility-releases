#!/usr/bin/env python3
"""Generate the sounds No Quarter's added weapons need, into a pk3 stage.

The Tesla gun is RTCW's, and so is its sound - but RTCW's sounds are not
ours to ship. Without one, the gun would fire in silence, which for a
player who cannot see it is the same as not firing at all. So the mode
ships this stand-in: an electric crackle over a mains hum, synthesised
here as source like the cue sounds. A player who builds the RTCW pack
(make-rtcw-sounds.py) gets RTCW's own zap in its place, because that pk3
sorts after the mode's and so wins.

Mono, 22050 Hz, 16-bit, seamless: it loops for as long as the trigger is
held. Deterministic: same input, same bytes.

    ./make-noquarter-sounds.py <pk3-stage-directory>
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, v / peak)) * LEVEL * 32767))
            for v in samples))


def crackle(cycle, hum_hz, sparks_per_second, seed):
    """Arcing electricity: a buzzing hum broken by sharp sparks.

    The hum is a whole number of cycles long, so the loop meets itself;
    the sparks are bright noise bursts that die in a few milliseconds,
    and none starts too near the end to ring out before the seam.
    """
    n = int(RATE * cycle)
    cycles = round(hum_hz * cycle)
    rng = random.Random(seed)
    out = []
    for i in range(n):
        phase = 2.0 * math.pi * cycles * i / n
        buzz = (0.45 * math.sin(phase) + 0.30 * math.sin(2.0 * phase)
                + 0.20 * math.sin(3.0 * phase) + 0.15 * math.sin(5.0 * phase))
        out.append(0.35 * buzz * (0.75 + 0.25 * math.sin(4.0 * math.pi * i / n)))
    tail = int(RATE * 0.012)
    for _ in range(int(sparks_per_second * cycle)):
        start = rng.randrange(0, n - tail)
        amplitude = 0.5 + 0.5 * rng.random()
        for k in range(tail):
            out[start + k] += amplitude * (rng.random() * 2.0 - 1.0) * math.exp(-k / (RATE * 0.002))
    # both ends at zero, so the repeat is inaudible
    edge = int(RATE * 0.004)
    for k in range(edge):
        fade = k / edge
        out[k] *= fade
        out[n - 1 - k] *= fade
    return out


SOUNDS = {
    "sound/weapons/tesla/tesla_fire.wav": lambda: crackle(0.50, 120.0, 40, 23),
}


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: make-noquarter-sounds.py <pk3-stage-directory>")
    for name, build in sorted(SOUNDS.items()):
        write(os.path.join(sys.argv[1], name), build())
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

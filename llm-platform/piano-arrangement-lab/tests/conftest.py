"""Shared corpus.

Real progressions rather than invented ones, because the awkward cases in
piano writing are the ones real music produces: the half-diminished chord in
Autumn Leaves, the chromatic bass in a Canon, the rapid key centres in
Coltrane changes.
"""

import pytest

CORPUS = {
    "I-V-vi-IV": "C G Am F C G Am F",
    "ii-V-I": "Dm7 G7 Cmaj7 Cmaj7 Em7 A7 Dm7 G7",
    "Coltrane changes": "Cmaj7 Eb7 Abmaj7 B7 Emaj7 G7 Cmaj7",
    "Autumn Leaves": "Cm7 F7 Bbmaj7 Ebmaj7 Am7b5 D7 Gm Gm",
    "Canon in D": "D A Bm F#m G D G A",
    "blues in F": "F7 Bb7 F7 F7 Bb7 Bb7 F7 D7 Gm7 C7 F7 C7",
    "slash bass": "C G/B Am Am/G F C/E Dm7 G7",
    "chromatic": "Cmaj7 C#dim7 Dm7 D#dim7 Em7 A7 Dm7 G7",
}

LEVEL_NAMES = ["beginner", "intermediate", "advanced"]
STYLE_NAMES = ["plain", "jazzy", "sparse", "lush", "hymn"]


@pytest.fixture(params=sorted(CORPUS), ids=lambda n: n.replace(" ", "-"))
def progression(request):
    return CORPUS[request.param]

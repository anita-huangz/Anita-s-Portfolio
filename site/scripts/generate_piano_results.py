"""Piano arranger: a golden fixture the TypeScript port is checked against.

The site runs the solver in the browser so a visitor can type any chords they
like, which means the engine exists twice -- once in Python, once in
TypeScript. This writes down what the Python says for a spread of
progressions, levels and styles, and `arranger.test.ts` asserts the port
agrees: every pitch, every cost, every reported rule violation.

Nothing here is used to *draw* the demo. It exists only so the two
implementations cannot drift apart unnoticed.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai-platform-projects/piano-arrangement-lab/src"))

from arranger.arrange import arrange, arrange_greedy
from arranger.difficulty import LEVELS
from arranger.intent import STYLES, parse_intent

OUT = ROOT / "site/src/data/demos"

#: Chosen to exercise the awkward cases, not the easy ones: a half-diminished
#: chord, a chromatic bass, slash chords, rapid key centres, extensions a
#: beginner cannot play.
PROGRESSIONS = {
    "I-V-vi-IV": "C G Am F",
    "ii-V-I": "Dm7 G7 Cmaj7",
    "Autumn Leaves": "Cm7 F7 Bbmaj7 Ebmaj7 Am7b5 D7 Gm",
    "Coltrane changes": "Cmaj7 Eb7 Abmaj7 B7 Emaj7 G7 Cmaj7",
    "slash bass": "C G/B Am Am/G F",
    "extensions": "Cmaj9 Dm11 G13 Cmaj7",
    "blues in F": "F7 Bb7 F7 C7 Bb7 F7",
    "chromatic": "Cmaj7 C#dim7 Dm7 G7",
}

#: Phrases the browser's keyword parser must read the same way Python does.
PHRASES = [
    "make it easier", "an advanced jazzy version", "sparse and quiet",
    "like a bach chorale", "lush and romantic, 140 bpm", "a sad slow ballad",
    "jazzy but gentle", "gentle but jazzy", "easy but actually advanced",
    "make it sound like Debussy underwater",
]


#: Costs are stored to twelve decimals, not the six that reads nicely. The
#: TypeScript port computes the same sums in the same order, so the two agree
#: to floating-point noise -- and a fixture rounded to six forces a tolerance
#: loose enough to hide a real disagreement in the third decimal.
PRECISION = 12


def dump(result) -> dict:
    return {
        "total_cost": round(result.total_cost, PRECISION),
        "total_motion": result.total_motion,
        "max_span": result.max_span,
        "steps": [
            {
                "chord": s.chord.symbol,
                "left": list(s.voicing.left),
                "right": list(s.voicing.right),
                "static": round(s.static, PRECISION),
                "transition": round(s.transition, PRECISION),
                "notes": list(s.notes),
                "violations": [
                    {"rule": v.rule, "penalty": round(v.penalty, PRECISION)}
                    for v in s.violations
                ],
            }
            for s in result.steps
        ],
    }


cases = []
for name, progression in PROGRESSIONS.items():
    for level in sorted(LEVELS):
        for style in sorted(STYLES):
            cases.append({
                "name": name,
                "progression": progression,
                "level": level,
                "style": style,
                "optimal": dump(arrange(progression, level, style)),
                "greedy": dump(arrange_greedy(progression, level, style)),
            })

payload = {
    "generated": str(date.today()),
    "levels": {
        name: {
            "max_span": level.max_span,
            "max_right_notes": level.max_right_notes,
            "max_left_notes": level.max_left_notes,
            "description": level.description,
        }
        for name, level in LEVELS.items()
    },
    "styles": {name: style.description for name, style in STYLES.items()},
    "progressions": PROGRESSIONS,
    "cases": cases,
    "intents": [
        {
            "text": phrase,
            "level": (i := parse_intent(phrase)).level,
            "style": i.style,
            "bpm": i.bpm,
            "unhandled": i.unhandled,
        }
        for phrase in PHRASES
    ],
}

path = OUT / "piano-golden.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  piano-golden.json  {path.stat().st_size / 1024:.1f} KB  "
      f"({len(cases)} cases, {len(PHRASES)} phrases)")

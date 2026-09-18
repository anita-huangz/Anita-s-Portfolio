"""Turning "make it jazzy and easy" into constraints the solver understands.

This is the seam the language model plugs into, and it is deliberately narrow.
The model never writes music. It reads a sentence and fills in a small,
validated struct — level, style, tempo — which the deterministic engine then
acts on. Everything the model can influence is enumerable and checkable, so a
bad or hallucinated answer is caught by the validator instead of turning into a
wrong chord.

Narrowing it this far is also what makes the whole thing work with no API key
at all. Most of what people actually type is keyword-shaped ("jazzy", "easier",
"slower"), and a deterministic parser handles it. The model earns its place on
the sentences the parser misses, not on the ones it gets right.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .difficulty import LEVELS, Level


@dataclass(frozen=True)
class Style:
    """A way of voicing, expressed as adjustments to the level's constraints."""

    name: str
    description: str
    #: Multipliers and deltas applied to the chosen level.
    motion_weight: float = 1.0
    rule_weight: float = 1.0
    prefer_extensions: bool | None = None
    #: What it costs to leave an available 9th, 11th or 13th unsounded. This is
    #: what makes a jazz voicing sound like one: not extra notes, but colour
    #: tones preferred over the plain ones.
    extension_penalty: float = 0.3
    #: What it costs to omit the fifth. The default of 0.6 is a mild
    #: preference for completeness; a jazz voicing sets it to zero, because
    #: dropping the fifth is the entire idea of a shell voicing.
    fifth_penalty: float = 0.6
    #: How many notes the right hand should ideally hold, and how hard to
    #: insist. Expressed as a distance from a target rather than a per-note
    #: reward: rewarding notes linearly makes a denser voicing always cheaper,
    #: which drives the total cost negative and stops it meaning anything.
    target_density: int = 3
    density_weight: float = 0.0


STYLES: dict[str, Style] = {
    "plain": Style(
        "plain", "Straight block chords, nothing added.",
    ),
    "jazzy": Style(
        "jazzy",
        "Extensions where the level allows them, and the fifth dropped in "
        "favour of colour tones — the shell voicing a jazz pianist reaches for.",
        rule_weight=0.4,
        prefer_extensions=True,
        fifth_penalty=0.0,
        extension_penalty=1.4,
        target_density=4,
        density_weight=0.4,
    ),
    "sparse": Style(
        "sparse",
        "As few notes as carry the harmony. Open, quiet, easy to play.",
        fifth_penalty=0.0,
        extension_penalty=0.0,
        target_density=2,
        density_weight=0.9,
        motion_weight=1.2,
    ),
    "lush": Style(
        "lush",
        "Full, closely spaced chords with every available tone sounding.",
        fifth_penalty=1.2,
        extension_penalty=0.8,
        target_density=5,
        density_weight=0.7,
        prefer_extensions=True,
    ),
    "hymn": Style(
        "hymn",
        "Four-part writing with strict voice leading and minimal motion — "
        "parallel fifths are punished hard, as in a chorale.",
        rule_weight=2.5,
        motion_weight=1.6,
        fifth_penalty=1.0,
        target_density=3,
        density_weight=1.0,
    ),
}


@dataclass(frozen=True)
class Intent:
    """Everything a request can ask for, and nothing it cannot."""

    level: str = "intermediate"
    style: str = "plain"
    bpm: float = 90.0
    beats_per_chord: float = 2.0
    #: Free text the parser could not account for. Surfaced rather than
    #: discarded, so "make it sound like Debussy" is visibly not honoured
    #: instead of silently ignored.
    unhandled: str = ""

    def validated(self) -> Intent:
        if self.level not in LEVELS:
            raise ValueError(f"unknown level {self.level!r}")
        if self.style not in STYLES:
            raise ValueError(f"unknown style {self.style!r}")
        if not 20 <= self.bpm <= 300:
            raise ValueError(f"bpm {self.bpm} outside 20-300")
        if not 0.25 <= self.beats_per_chord <= 16:
            raise ValueError(f"beats_per_chord {self.beats_per_chord} outside 0.25-16")
        return self


#: Phrases the deterministic parser recognises.
#:
#: When two phrases in the same category match, the one later *in the sentence*
#: wins, so "easy but actually advanced" is advanced. An earlier version let
#: whichever entry came later in this dictionary win, which meant "jazzy and
#: gentle" resolved by dictionary order rather than by what was written.
_LEVEL_WORDS = {
    "beginner": ("beginner", "easy", "easier", "simple", "simpler", "starter",
                 "first year", "child", "kid", "novice", "basic"),
    "intermediate": ("intermediate", "medium", "moderate", "normal", "standard"),
    "advanced": ("advanced", "hard", "harder", "difficult", "virtuoso",
                 "professional", "complex", "pro"),
}

_STYLE_WORDS = {
    "jazzy": ("jazz", "jazzy", "bluesy", "swing", "smoky", "lounge"),
    "sparse": ("sparse", "minimal", "quiet", "bare", "open", "spare", "thin",
               "gentle", "soft"),
    "lush": ("lush", "rich", "full", "thick", "dense", "warm", "romantic",
             "cinematic"),
    "hymn": ("hymn", "chorale", "church", "bach", "classical", "four part",
             "four-part", "sacred"),
    "plain": ("plain", "simple chords", "block", "straight", "basic chords"),
}

_TEMPO_WORDS = {
    "slow": 66.0, "slower": 70.0, "ballad": 68.0, "relaxed": 76.0, "calm": 72.0,
    "sad": 66.0, "mournful": 60.0, "fast": 132.0, "faster": 120.0,
    "quick": 126.0, "upbeat": 128.0, "lively": 120.0, "bright": 116.0,
    "energetic": 138.0,
}


def parse_intent(text: str, default: Intent | None = None) -> Intent:
    """Read a request without a language model.

    Handles the keyword-shaped majority of what people type. What it cannot
    account for is returned in `unhandled` rather than dropped, which is both
    honest to the user and the signal for when the model is worth calling.
    """
    intent = default or Intent()
    lowered = f" {text.lower()} "
    consumed: list[str] = []

    def last_match(table: dict[str, tuple[str, ...]]) -> tuple[str, int] | None:
        """The category whose phrase appears latest in the sentence."""
        best: tuple[str, int] | None = None
        for key, words in table.items():
            for word in words:
                for found in re.finditer(rf"\b{re.escape(word)}\b", lowered):
                    consumed.append(word)
                    if best is None or found.start() > best[1]:
                        best = (key, found.start())
        return best

    level = last_match(_LEVEL_WORDS)
    if level:
        intent = replace(intent, level=level[0])

    style = last_match(_STYLE_WORDS)
    if style:
        intent = replace(intent, style=style[0])

    tempo = last_match({word: (word,) for word in _TEMPO_WORDS})
    if tempo:
        intent = replace(intent, bpm=_TEMPO_WORDS[tempo[0]])

    # An explicit number always wins over a mood word.
    match = re.search(r"\b(\d{2,3})\s*(?:bpm|beats per minute)\b", lowered)
    if match:
        intent = replace(intent, bpm=float(match.group(1)))
        consumed.append(match.group(0))

    leftover = lowered
    for word in consumed:
        leftover = leftover.replace(word, " ")
    leftover = re.sub(
        r"\b(make|it|a|an|the|please|can|you|i|want|would|like|to|be|more|less|"
        r"and|but|with|sound|sounds|version|arrangement|play|this|that|my|of|in)\b",
        " ", leftover,
    )
    leftover = " ".join(leftover.split())
    return replace(intent, unhandled=leftover).validated()


def apply_style(level: Level, style: Style) -> Level:
    """The level, adjusted by the style.

    Weights move; the physical limits do not. A difficulty level is a promise
    about what a player's hands will be asked to do, and a style is a
    preference about sound — letting the second override the first would make
    the promise worthless, and an earlier version of this did exactly that,
    buying a "jazzy" beginner a fourth right-hand note.

    Styles cannot tighten the limits either, even though that sounds harmless.
    Capping "sparse" at two right-hand notes made Dm7 unvoiceable, because its
    root, third and seventh are three tones and none of them is optional. A
    preference expressed as cost degrades gracefully where a hard cap fails:
    it takes two notes when two will do and three when the chord needs three.
    """
    return replace(
        level,
        motion_weight=level.motion_weight * style.motion_weight,
        rule_weight=level.rule_weight * style.rule_weight,

        allow_extensions=(
            level.allow_extensions if style.prefer_extensions is None
            # A style may ask for extensions, but only a level that permits
            # them can grant it: "jazzy" must not smuggle 13ths into a
            # beginner arrangement.
            else level.allow_extensions and style.prefer_extensions
        ),
    )

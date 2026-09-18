"""`arrange "C Am F G7" --level beginner`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .arrange import arrange, arrange_greedy
from .difficulty import LEVELS
from .intent import STYLES, Intent
from .llm import PROVIDERS, interpret
from .midi import to_midi
from .theory import ChordError, note_name


def _keyboard(pitches: tuple[int, ...], low: int = 48, high: int = 84) -> str:
    """A one-line piano, with the sounding notes filled in.

    Crude, and much more use than a list of numbers when the question is
    "can my hand do that".
    """
    black = {1, 3, 6, 8, 10}
    out = []
    for pitch in range(low, high + 1):
        if pitch in pitches:
            out.append("#" if pitch % 12 in black else "|")
        else:
            out.append("." if pitch % 12 in black else " ")
    return "".join(out)


def render(result, show_keyboard: bool = True) -> str:
    lines = []
    level = result.level
    lines.append(f"{level.name.upper()}  —  {level.description}")
    if result.style is not None and result.style.name != "plain":
        lines.append(f"{result.style.name}: {result.style.description}")
    lines.append("")
    header = f"  {'chord':<9} {'left hand':<20} {'right hand':<30} {'span':>4} {'cost':>6}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for step in result.steps:
        left = " ".join(note_name(p) for p in step.voicing.left)
        right = " ".join(note_name(p) for p in step.voicing.right)
        lines.append(
            f"  {step.chord.symbol:<9} {left:<20} {right:<30} "
            f"{step.voicing.span:>4} {step.cost:>6.2f}"
        )
        if show_keyboard:
            lines.append(f"  {'':<9} {_keyboard(step.voicing.pitches)}")
    lines.append("")
    lines.append(
        f"  total cost {result.total_cost:.2f}   "
        f"hand travel {result.total_motion} semitones   "
        f"widest stretch {result.max_span} semitones"
    )
    if result.searched:
        lines.append(f"  {result.searched:,} transitions evaluated (exact, not greedy)")

    if result.simplifications:
        lines.append("")
        lines.append("  simplified for this level:")
        for symbol, note in result.simplifications:
            lines.append(f"    {symbol}: {note}")

    if result.violations:
        lines.append("")
        lines.append("  voice-leading notes:")
        for step in result.steps:
            for violation in step.violations:
                lines.append(f"    {step.chord.symbol}: {violation.rule} — {violation.detail}")
    else:
        lines.append("")
        lines.append("  no voice-leading rules broken")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arrange",
        description="Turn a chord chart into a playable piano arrangement.",
    )
    parser.add_argument("chords", help='e.g. "C Am F G7" or "Dm7 G7 Cmaj7"')
    parser.add_argument(
        "--level", default="intermediate", choices=sorted(LEVELS),
        help="how hard the result may be to play",
    )
    parser.add_argument(
        "--style", default="plain", choices=sorted(STYLES),
        help="how to voice it",
    )
    parser.add_argument(
        "--describe", metavar="TEXT",
        help='plain English instead of flags, e.g. "an easy jazzy version, slow"',
    )
    parser.add_argument(
        "--provider", choices=sorted(PROVIDERS),
        help="use a language model to read --describe; without this, keywords do",
    )
    parser.add_argument("--midi", type=Path, help="also write a MIDI file here")
    parser.add_argument("--bpm", type=float, default=90.0)
    parser.add_argument("--beats", type=float, default=2.0, help="beats per chord")
    parser.add_argument(
        "--greedy", action="store_true",
        help="use the greedy baseline instead of the solver, for comparison",
    )
    parser.add_argument("--no-keyboard", action="store_true")
    parser.add_argument(
        "--compare", action="store_true",
        help="arrange at all three levels and print them together",
    )
    args = parser.parse_args(argv)

    try:
        style = args.style
        level = args.level
        bpm, beats = args.bpm, args.beats
        if args.describe:
            reading = interpret(
                args.describe,
                provider=args.provider,
                default=Intent(level=level, style=style, bpm=bpm, beats_per_chord=beats),
            )
            level, style = reading.intent.level, reading.intent.style
            bpm, beats = reading.intent.bpm, reading.intent.beats_per_chord
            print(f'read "{args.describe}" as: {level}, {style}, {bpm:g} bpm  [{reading.source}]')
            if reading.note:
                print(f"  {reading.note}")
            if reading.fallback_reason:
                print(f"  (fell back to keywords: {reading.fallback_reason})")
            if reading.intent.unhandled:
                print(f"  (not understood, and ignored: {reading.intent.unhandled!r})")
            print()

        levels = sorted(LEVELS) if args.compare else [level]
        solver = arrange_greedy if args.greedy else arrange
        for i, level in enumerate(levels):
            if i:
                print()
            result = solver(args.chords, level, style)
            print(render(result, show_keyboard=not args.no_keyboard))
        if args.midi:
            args.midi.write_bytes(to_midi(result, bpm=bpm, beats_per_chord=beats))
            print(f"\n  wrote {args.midi} ({args.midi.stat().st_size} bytes)")
    except (ChordError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

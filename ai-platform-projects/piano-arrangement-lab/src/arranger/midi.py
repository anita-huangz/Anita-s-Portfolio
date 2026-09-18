"""A standard MIDI file, written by hand.

Eighty lines of `struct.pack` against a published format, rather than a
dependency. The format is genuinely small -- a header chunk, one track chunk,
and a list of delta-timed events -- and writing it directly means the project
installs with no third-party code at all, which is the difference between
"clone and run" and "clone, resolve a dependency tree, then run".

Reference: Standard MIDI File 1.0 specification, format 1.
"""

from __future__ import annotations

import struct

from .arrange import Arrangement

TICKS_PER_BEAT = 480
NOTE_ON = 0x90
NOTE_OFF = 0x80
#: Two tracks so the hands land on separate staves when imported into notation
#: software. Format 1 means "several tracks, played together".
FORMAT_MULTI_TRACK = 1


def _variable_length(value: int) -> bytes:
    """MIDI's 7-bits-per-byte integer, high bit set on all but the last."""
    if value < 0:
        raise ValueError("delta times cannot be negative")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _event(delta: int, status: int, data1: int, data2: int) -> bytes:
    return _variable_length(delta) + bytes([status, data1, data2])


def _track(events: bytes) -> bytes:
    end = _variable_length(0) + b"\xff\x2f\x00"  # end-of-track meta event
    body = events + end
    return b"MTrk" + struct.pack(">I", len(body)) + body


def _tempo_event(bpm: float) -> bytes:
    microseconds = int(60_000_000 / bpm)
    return _variable_length(0) + b"\xff\x51\x03" + microseconds.to_bytes(3, "big")


def _hand_track(
    chords: list[tuple[int, ...]], beats: float, velocity: int, channel: int
) -> bytes:
    """One staff: every chord struck together, held for `beats`, then released.

    A rest carries its duration forward into the next event's delta rather than
    emitting a silent note. Sounding a dummy note to advance the clock works in
    most players and produces a stray pitch-0 event in the ones that honour it.
    """
    ticks = int(beats * TICKS_PER_BEAT)
    events = bytearray()
    pending = 0
    for pitches in chords:
        if not pitches:
            pending += ticks
            continue
        for i, pitch in enumerate(pitches):
            events += _event(pending if i == 0 else 0, NOTE_ON | channel, pitch, velocity)
        pending = 0
        for i, pitch in enumerate(pitches):
            events += _event(ticks if i == 0 else 0, NOTE_OFF | channel, pitch, 0)
    return _track(bytes(events))


def to_midi(arrangement: Arrangement, bpm: float = 90.0, beats_per_chord: float = 2.0) -> bytes:
    """The arrangement as a two-track MIDI file, left hand and right hand."""
    if bpm <= 0:
        raise ValueError("bpm must be positive")
    if beats_per_chord <= 0:
        raise ValueError("beats_per_chord must be positive")

    # MThd carries its own 4-byte length before the six bytes of data. Omitting
    # it produces a file that looks right and no parser will read.
    header = b"MThd" + struct.pack(">IHHH", 6, FORMAT_MULTI_TRACK, 3, TICKS_PER_BEAT)
    tempo = _track(_tempo_event(bpm))
    left = _hand_track(
        [s.voicing.left for s in arrangement.steps], beats_per_chord, 70, 0
    )
    right = _hand_track(
        [s.voicing.right for s in arrangement.steps], beats_per_chord, 85, 0
    )
    return header + tempo + left + right

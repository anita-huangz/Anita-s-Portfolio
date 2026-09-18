"""The MIDI writer, parsed back rather than merely produced.

A file that is the right length and unreadable is the failure mode worth
guarding against -- an early version omitted the four-byte length field from
the header chunk, which no test of "did it write some bytes" would catch.
"""

import struct

import pytest

from arranger.arrange import arrange
from arranger.midi import TICKS_PER_BEAT, to_midi
from conftest import LEVEL_NAMES


def chunks(data: bytes):
    """Walk the file as the format defines it, yielding (tag, body)."""
    assert data[:4] == b"MThd", "no header chunk"
    length = struct.unpack(">I", data[4:8])[0]
    yield b"MThd", data[8:8 + length]
    pos = 8 + length
    while pos < len(data):
        tag = data[pos:pos + 4]
        size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        yield tag, data[pos + 8:pos + 8 + size]
        pos += 8 + size


def events(body: bytes):
    """Decode one track's event list."""
    i = 0
    while i < len(body):
        delta = 0
        while True:
            byte = body[i]
            i += 1
            delta = (delta << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
        status = body[i]
        if status == 0xFF:
            i += 1
            meta = body[i]
            i += 1
            size = 0
            while True:
                byte = body[i]
                i += 1
                size = (size << 7) | (byte & 0x7F)
                if not byte & 0x80:
                    break
            yield delta, "meta", meta, body[i:i + size]
            i += size
            if meta == 0x2F:
                return
        else:
            yield delta, "note", status, body[i + 1:i + 3]
            i += 3


def test_the_header_declares_its_own_length():
    data = to_midi(arrange("C Am F G7", "intermediate"))
    tag, body = next(iter(chunks(data)))
    assert tag == b"MThd"
    fmt, tracks, division = struct.unpack(">HHH", body)
    assert fmt == 1
    assert tracks == 3
    assert division == TICKS_PER_BEAT


def test_the_track_count_in_the_header_matches_the_file():
    data = to_midi(arrange("C Am F G7", "intermediate"))
    found = list(chunks(data))
    declared = struct.unpack(">HHH", found[0][1])[1]
    assert sum(1 for tag, _ in found if tag == b"MTrk") == declared


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_every_note_started_is_stopped(level_name):
    data = to_midi(arrange("Dm7 G7 Cmaj7 Am7", level_name))
    for tag, body in chunks(data):
        if tag != b"MTrk":
            continue
        on = off = 0
        for _, kind, status, payload in events(body):
            if kind != "note":
                continue
            if status & 0xF0 == 0x90 and payload[1] > 0:
                on += 1
            elif status & 0xF0 == 0x80:
                off += 1
        assert on == off


def test_the_notes_written_are_the_notes_arranged():
    result = arrange("C Am F", "beginner")
    data = to_midi(result)
    written = []
    for tag, body in chunks(data):
        if tag != b"MTrk":
            continue
        for _, kind, status, payload in events(body):
            if kind == "note" and status & 0xF0 == 0x90 and payload[1] > 0:
                written.append(payload[0])
    expected = [p for step in result.steps for p in step.voicing.pitches]
    assert sorted(written) == sorted(expected)


def test_a_rest_advances_the_clock_without_sounding_a_note():
    """Pitch 0 in the output would mean a rest was faked with a silent note."""
    data = to_midi(arrange("C Am F G7", "beginner"))
    for tag, body in chunks(data):
        if tag != b"MTrk":
            continue
        for _, kind, _status, payload in events(body):
            if kind == "note":
                assert payload[0] != 0, "a pitch-0 event is a faked rest"


def test_tempo_is_written_as_microseconds_per_beat():
    data = to_midi(arrange("C", "beginner"), bpm=120)
    for tag, body in chunks(data):
        if tag != b"MTrk":
            continue
        for _, kind, meta, payload in events(body):
            if kind == "meta" and meta == 0x51:
                assert int.from_bytes(payload, "big") == 500_000  # 120 bpm
                return
    pytest.fail("no tempo event")


@pytest.mark.parametrize(("bpm", "beats"), [(0, 2), (-5, 2), (90, 0), (90, -1)])
def test_nonsense_timings_are_rejected(bpm, beats):
    with pytest.raises(ValueError):
        to_midi(arrange("C", "beginner"), bpm=bpm, beats_per_chord=beats)

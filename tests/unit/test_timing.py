import pytest

from patternity.simfile.timing import TimingEngine


def test_constant_bpm_converts_beats_to_seconds() -> None:
    timing = TimingEngine(bpms={0.0: 120.0}, stops=None)
    assert [timing.convert_beat_to_seconds(beat) for beat in (0.0, 1.0, 4.5)] == [0.0, 0.5, 2.25]


def test_each_bpm_segment_runs_at_its_own_tempo() -> None:
    # Listed out of order on purpose: segments are sorted by beat.
    timing = TimingEngine(bpms={8.0: 240.0, 0.0: 120.0, 4.0: 60.0}, stops=None)

    assert timing.convert_beat_to_seconds(4.0) == pytest.approx(2.0)
    assert timing.convert_beat_to_seconds(6.0) == pytest.approx(2.0 + 2.0)
    assert timing.convert_beat_to_seconds(8.0) == pytest.approx(2.0 + 4.0)
    assert timing.convert_beat_to_seconds(10.0) == pytest.approx(2.0 + 4.0 + 0.5)


def test_stop_delays_only_the_beats_after_it() -> None:
    timing = TimingEngine(bpms={0.0: 120.0}, stops={4.0: 0.75})

    # The note on the stop's own beat is hit before the pause.
    assert timing.convert_beat_to_seconds(4.0) == pytest.approx(2.0)
    assert timing.convert_beat_to_seconds(4.5) == pytest.approx(2.25 + 0.75)


def test_stops_accumulate() -> None:
    timing = TimingEngine(bpms={0.0: 60.0}, stops={2.0: 0.5, 1.0: 0.25})
    assert timing.convert_beat_to_seconds(3.0) == pytest.approx(3.0 + 0.25 + 0.5)


def test_stop_and_bpm_change_combine() -> None:
    timing = TimingEngine(bpms={0.0: 120.0, 2.0: 60.0}, stops={1.0: 1.0})
    assert timing.convert_beat_to_seconds(3.0) == pytest.approx(1.0 + 1.0 + 1.0)

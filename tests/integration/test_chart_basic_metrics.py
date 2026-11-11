"""Full-chart basic metrics (simfile / ITG summary semantics)."""

from pathlib import Path

import pytest

from patternity import StepmaniaFileParser, analyze_chart, read_simfile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.regression
def test_burger_challenge_file_basic_metrics() -> None:
    path = FIXTURES / "charts" / "burger.ssc"
    song = StepmaniaFileParser.parse(read_simfile(path))
    chart = song.charts[0]
    assert chart.metadata.rating == 10.0

    result = analyze_chart(chart).basic.to_dict()
    assert result == {
        "taps": 587,
        "jumps": 14,
        "hands": 14,
        "holds": 135,
        "rolls": 5,
        "mines": 20,
        "lifts": 0,
        "fakes": 0,
        "steps": 601,
    }


@pytest.mark.regression
@pytest.mark.parametrize(
    "chart_index,expected_rating",
    [(0, 17.0), (1, 15.0)],
    ids=["Challenge", "Hard"],
)
def test_fots_basic_metrics_match_groove_radar(chart_index: int, expected_rating: float) -> None:
    """Jumps/hands match ITGMania groove radar (independent jump + anchored-hand rules)."""
    path = FIXTURES / "charts" / "fots.sm"
    song = StepmaniaFileParser.parse(read_simfile(path))
    chart = song.charts[chart_index]
    assert chart.metadata.rating == expected_rating

    basic = analyze_chart(chart).basic.to_dict()
    radar = chart.metadata.radar
    assert radar is not None
    assert basic["taps"] == radar.taps
    assert basic["steps"] == radar.steps
    assert basic["jumps"] == radar.jumps
    assert basic["holds"] == radar.holds
    assert basic["hands"] == radar.hands
    assert basic["mines"] == radar.mines


@pytest.mark.regression
def test_senpai_hands_count_a_press_on_a_roll_tail_row() -> None:
    """ITGMania counts 5 hands; one is a hold head and a tap on the row a roll ends."""
    path = FIXTURES / "charts" / "senpai_notice_me.ssc"
    chart = StepmaniaFileParser.parse(read_simfile(path)).charts[0]
    radar = chart.metadata.radar
    assert radar is not None

    assert analyze_chart(chart).basic.hands == radar.hands == 5

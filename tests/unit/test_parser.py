import pytest

from patternity.simfile import Difficulty, MissingTimingError, SimfileError
from patternity.simfile.parser import StepmaniaFileParser, parse_simfile_with_notes


def test_multiline_header_values_are_parsed() -> None:
    data = (
        "#TITLE:t;\n"
        "#BPMS:0.000=128.000\n,4.000=64.000\n;\n"
        "#NOTES:\n     dance-single:\n     t:\n     Challenge:\n     1:\n"
        "     0,0,0,0,0:\n1000\n0000\n0000\n0000\n,\n1000\n0000\n0000\n0000\n;\n"
    )
    song = StepmaniaFileParser.parse(data)
    assert song.header.bpms == {0.0: 128.0, 4.0: 64.0}
    second = song.charts[0].notes[1]
    assert abs(second.timestamp - 4 * 60 / 128) < 1e-9


def _sm_chart(mode: str, difficulty: str, row: str) -> str:
    return (
        f"#NOTES:\n     {mode}:\n     t:\n     {difficulty}:\n     1:\n"
        f"     0,0,0,0,0:\n{row}\n,\n;\n"
    )


_HEADER = "#TITLE:t;\n#BPMS:0.000=120.000;\n"


def test_edit_difficulty_is_parsed() -> None:
    song = StepmaniaFileParser.parse(_HEADER + _sm_chart("dance-single", "Edit", "1000"))
    assert [chart.metadata.difficulty for chart in song.charts] == [Difficulty.EDIT]
    assert song.skipped_charts == []


@pytest.mark.parametrize(
    ("mode", "difficulty", "row", "reason"),
    [
        ("dance-double", "Hard", "10000000", "only dance-single"),
        ("dance-single", "Hard", "1K00", "unsupported note character"),
        ("dance-single", "Hard", "100", "expected 4 columns"),
        ("dance-single", "Impossible", "1000", "unknown difficulty"),
    ],
)
def test_unsupported_chart_is_skipped_without_losing_the_others(
    mode: str, difficulty: str, row: str, reason: str
) -> None:
    data = (
        _HEADER
        + _sm_chart(mode, difficulty, row)
        + _sm_chart("dance-single", "Challenge", "0100")
    )
    song = StepmaniaFileParser.parse(data)

    assert [chart.metadata.difficulty for chart in song.charts] == [Difficulty.CHALLENGE]
    (skipped,) = song.skipped_charts
    assert (skipped.mode, skipped.difficulty) == (mode, difficulty)
    assert reason in skipped.reason


def test_chart_without_bpms_raises() -> None:
    with pytest.raises(MissingTimingError):
        StepmaniaFileParser.parse("#TITLE:t;\n" + _sm_chart("dance-single", "Hard", "1000"))


def test_header_only_file_needs_no_bpms() -> None:
    assert StepmaniaFileParser.parse("#TITLE:t;\n").charts == []


def test_header_tags_are_converted_by_field() -> None:
    data = (
        "#TITLE:Song;\n#OFFSET:-0.5;\n#SAMPLESTART:12.5;\n#SELECTABLE:YES;\n"
        "#DISPLAYBPM:150;\n#STOPS:4=0.25;\n#NOTAREALTAG:x;\n"
    )
    header = StepmaniaFileParser.parse(data).header

    assert (header.title, header.offset, header.samplestart) == ("Song", -0.5, 12.5)
    assert header.selectable is True
    assert header.displaybpm == 150.0
    assert header.stops == {4.0: 0.25}


def test_display_bpm_that_is_not_a_number_stays_text() -> None:
    assert StepmaniaFileParser.parse("#DISPLAYBPM:120:180;\n").header.displaybpm == "120:180"


def _file_line(data: str, text: str) -> int:
    return data[: data.index(text)].count("\n") + 1


def test_notes_body_of_an_sm_chart_starts_at_its_first_row() -> None:
    data = (
        "// preamble\n;\n" + _HEADER + "//--- dance-single ---\n"
        + _sm_chart("dance-single", "Hard", "1000 // first\n0100")
    )
    song, bodies = parse_simfile_with_notes(data)

    assert len(song.charts) == len(bodies) == 1
    assert bodies[0].text.splitlines()[0] == "1000 // first"
    assert bodies[0].first_line == _file_line(data, "1000 // first")


def test_notes_body_of_an_ssc_chart_starts_on_the_notes_line() -> None:
    data = (
        _HEADER
        + "#NOTEDATA:;\n#STEPSTYPE:dance-single;\n#DIFFICULTY:Hard;\n#METER:9;\n"
        + "#NOTES:\n// measure 0\n1000 // first\n0100\n,\n;\n"
    )
    song, bodies = parse_simfile_with_notes(data)

    assert song.charts[0].metadata.rating == 9.0
    lines = bodies[0].text.splitlines()
    row = lines.index("1000 // first")
    assert bodies[0].first_line + row == _file_line(data, "1000 // first")


def test_notes_bodies_line_up_with_parsed_charts_when_one_is_skipped() -> None:
    data = (
        _HEADER
        + _sm_chart("dance-double", "Hard", "10000000")
        + _sm_chart("dance-single", "Hard", "0100")
    )
    song, bodies = parse_simfile_with_notes(data)

    assert len(song.charts) == len(bodies) == 1
    assert bodies[0].text.splitlines()[0] == "0100"


def test_sm_notes_section_with_missing_fields_raises() -> None:
    with pytest.raises(SimfileError, match="malformed #NOTES"):
        StepmaniaFileParser.parse(_HEADER + "#NOTES:\n dance-single:\n Hard:\n1000\n;\n")

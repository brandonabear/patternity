import pytest

from patternity.simfile import Difficulty, MissingTimingError, NoteRow, Panel, SimfileError
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
        _HEADER + _sm_chart(mode, difficulty, row) + _sm_chart("dance-single", "Challenge", "0100")
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
        "// preamble\n;\n"
        + _HEADER
        + "//--- dance-single ---\n"
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


def _sm(notes: str, *, header: str = _HEADER, radar: str = "0,0,0,0,0") -> str:
    """A one-chart ``.sm`` whose note data is ``notes`` exactly as written."""
    return (
        f"{header}#NOTES:\n     dance-single:\n     t:\n     Hard:\n     1:\n"
        f"     {radar}:\n{notes}\n;\n"
    )


def _rows(data: str) -> list[NoteRow]:
    return StepmaniaFileParser.parse(data).charts[0].notes


def test_empty_rows_are_skipped_but_keep_their_place_in_the_measure() -> None:
    eighths = "1000\n0000\n0000\n0100\n0000\n0000\n0000\n0010"
    quarters = "0000\n0001\n0000\n0000"
    rows = _rows(_sm(f"{eighths}\n,\n{quarters}"))

    assert [(row.measure, row.quantization, row.beat) for row in rows] == [
        (0, 8, 0.0),
        (0, 8, 1.5),
        (0, 8, 3.5),
        (1, 4, 5.0),
    ]
    # 120 BPM: half a second per beat.
    assert [row.timestamp for row in rows] == pytest.approx([0.0, 0.75, 1.75, 2.5])


def test_bpm_change_in_the_middle_of_a_measure() -> None:
    header = "#TITLE:t;\n#BPMS:0.000=120.000,2.000=240.000;\n"
    rows = _rows(_sm("1000\n0100\n0010\n0001", header=header))
    assert [row.timestamp for row in rows] == pytest.approx([0.0, 0.5, 1.0, 1.25])


def test_stop_shifts_the_rows_after_it() -> None:
    header = "#TITLE:t;\n#BPMS:0.000=120.000;\n#STOPS:1.000=0.250;\n"
    rows = _rows(_sm("1000\n0100\n0010\n0001", header=header))
    assert [row.timestamp for row in rows] == pytest.approx([0.0, 0.5, 1.25, 1.75])


def test_holds_and_rolls_are_active_from_head_through_tail() -> None:
    rows = _rows(_sm("2004\n0100\n3000\n0013"))

    assert [row.holds_active for row in rows] == [Panel.L, Panel.L, Panel.L, Panel.NONE]
    assert [row.rolls_active for row in rows] == [Panel.R] * 4
    assert rows[0].pressed == Panel.L | Panel.R
    assert rows[3].pressed == Panel.U


def test_back_to_back_holds_on_one_panel_are_each_active() -> None:
    rows = _rows(_sm("2000\n3000\n2000\n3000"))
    assert [row.holds_active for row in rows] == [Panel.L] * 4


def test_comments_are_stripped_from_note_data() -> None:
    notes = (
        "// measure 0\n"
        "1000 // @foot=L\n"
        "   // a comment-only line is not a row\n"
        "0100// no space before the comment\n"
        ",  // measure 1\n"
        "0010\n"
        "0001"
    )
    rows = _rows(_sm(notes))

    assert [row.pressed for row in rows] == [Panel.L, Panel.D, Panel.U, Panel.R]
    assert [(row.measure, row.quantization) for row in rows] == [(0, 2), (0, 2), (1, 2), (1, 2)]


def test_comment_inside_a_header_tag_is_dropped() -> None:
    header = StepmaniaFileParser.parse("#TITLE:Song // not part of the title\n;\n").header
    assert header.title == "Song"


def test_groove_radar_values_are_parsed_in_order() -> None:
    data = _sm("1000", radar="0.5,0.25,0.125,0,1,10,8,2,3,4,1")
    radar = StepmaniaFileParser.parse(data).charts[0].metadata.radar

    assert (radar.stream, radar.voltage, radar.air, radar.freeze, radar.chaos) == (
        0.5,
        0.25,
        0.125,
        0.0,
        1.0,
    )
    assert (radar.steps, radar.taps, radar.jumps, radar.holds, radar.mines, radar.hands) == (
        10,
        8,
        2,
        3,
        4,
        1,
    )


def test_missing_groove_radar_values_stay_unset() -> None:
    radar = StepmaniaFileParser.parse(_sm("1000", radar="0.5,,")).charts[0].metadata.radar
    assert (radar.stream, radar.voltage, radar.hands) == (0.5, None, None)


def _ssc_chart(tags: str, notes: str) -> str:
    return (
        "#NOTEDATA:;\n#STEPSTYPE:dance-single;\n#DIFFICULTY:Challenge;\n#METER:12;\n"
        f"{tags}#NOTES:\n{notes}\n;\n"
    )


def test_ssc_chart_reads_its_metadata_from_tags() -> None:
    tags = (
        "#CREDIT:someone;\n#DESCRIPTION:ignored when there is a credit;\n"
        # .ssc files list each value twice (player 1, then player 2).
        "#RADARVALUES:0.5,0,0,0,0,4,4,0,0,0,0,0.5,0,0,0,0,9,9,9,9,9,9;\n"
    )
    chart = StepmaniaFileParser.parse(_HEADER + _ssc_chart(tags, "1000\n0100")).charts[0]
    metadata = chart.metadata

    assert (metadata.mode, metadata.difficulty, metadata.rating) == (
        "dance-single",
        Difficulty.CHALLENGE,
        12.0,
    )
    assert metadata.credit == "someone"
    assert (metadata.radar.stream, metadata.radar.steps, metadata.radar.hands) == (0.5, 4, 0)
    assert [row.pressed for row in chart.notes] == [Panel.L, Panel.D]


def test_ssc_chart_falls_back_to_its_description_for_credit() -> None:
    data = _HEADER + _ssc_chart("#DESCRIPTION:described;\n", "1000")
    assert StepmaniaFileParser.parse(data).charts[0].metadata.credit == "described"


def test_ssc_chart_timing_overrides_the_header() -> None:
    # Split timing: the second chart has its own #BPMS and #STOPS.
    data = (
        _HEADER
        + _ssc_chart("", "1000\n0100\n0010\n0001")
        + _ssc_chart("#BPMS:0.000=60.000;\n#STOPS:1.000=0.500;\n", "1000\n0100\n0010\n0001")
    )
    shared, split = StepmaniaFileParser.parse(data).charts

    assert [row.timestamp for row in shared.notes] == pytest.approx([0.0, 0.5, 1.0, 1.5])
    assert [row.timestamp for row in split.notes] == pytest.approx([0.0, 1.0, 2.5, 3.5])


def test_ssc_chart_with_only_its_own_bpms_needs_none_in_the_header() -> None:
    data = "#TITLE:t;\n" + _ssc_chart("#BPMS:0.000=120.000;\n", "1000\n0100")
    assert [row.timestamp for row in _rows(data)] == pytest.approx([0.0, 1.0])

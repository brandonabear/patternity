import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from patternity.simfile.notes import AnchorTracker, InvalidNoteRow, NoteRow, parse_columns
from patternity.simfile.song import (
    Chart,
    ChartMetadata,
    Difficulty,
    GrooveRadar,
    Header,
    SkippedChart,
    Song,
    parse_beat_value_map,
)
from patternity.simfile.timing import TimingEngine

_SSC_CHART_TAGS = frozenset(
    {
        "#STEPSTYPE",
        "#DESCRIPTION",
        "#CREDIT",
        "#DIFFICULTY",
        "#METER",
        "#RADARVALUES",
        "#BPMS",  # SSC split-timing
        "#STOPS",  # SSC split-timing
    }
)

# The only chart mode the footing model covers (4-panel singles).
SUPPORTED_MODE = "dance-single"


class SimfileError(ValueError):
    """The simfile text can't be parsed into a song."""


class MissingTimingError(SimfileError):
    """A chart has no ``#BPMS``, so its rows cannot be given timestamps."""


@dataclass(frozen=True, slots=True)
class SourceText:
    """A piece of the simfile, such as a section or a chart's note data, and where it sits.

    ``first_line`` is the 1-based file line of ``text``'s first line, so line
    ``i`` of ``text.splitlines()`` is file line ``first_line + i``.
    """

    text: str
    first_line: int


def _leading_comment_lines(lines: list[str]) -> int:
    """How many blank or comment-only lines come before the first line of content."""
    for idx, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("//"):
            return idx
    return len(lines)


def _sections(data: str) -> Iterator[SourceText]:
    """The non-empty ``;``-terminated sections of a simfile, in order.

    Leading comments are stripped; there is often a decorative one before a
    chart's note data:
    ```sm
    #HEADER:;
    //------ dance-single -------
    #NOTES:;
    ```
    """
    line = 1
    for raw in data.split(";"):
        lines = raw.splitlines()
        skipped = _leading_comment_lines(lines)
        text = "\n".join(lines[skipped:]).strip()
        if text:
            yield SourceText(text, line + skipped)
        line += raw.count("\n")


_TAG_RE = re.compile(r"^(#[A-Z][A-Z0-9]*)\s*:\s*(.*)$", re.DOTALL)


def _parse_tag(raw: str) -> tuple[str, str]:
    """Split a ``#KEY:value`` section into its key and value (empty strings if it isn't one)."""
    fallback = ("", "")
    if not raw:
        return fallback

    cleaned = "\n".join(_strip_comment(line) for line in raw.splitlines()).strip()
    m = _TAG_RE.match(cleaned)
    return (m.group(1), m.group(2).strip()) if m else fallback


def _strip_comment(line: str) -> str:
    return line.split("//", 1)[0].strip()


@dataclass(frozen=True)
class SourceRow:
    """A non-empty note row as written, with its position in the chart.

    ``line_index`` is the 0-based line within the notes text passed to
    ``source_rows``.
    """

    text: str
    line_index: int
    measure: int
    quantization: int
    beat: float


class LineKind(Enum):
    BLANK = auto()  # empty or comment-only
    SEPARATOR = auto()  # starts with "," or ";"
    ROW = auto()  # note row, empty "0000" rows included


@dataclass(frozen=True, slots=True)
class NotesLine:
    """One line of a chart's notes text, classified the way the parser reads it."""

    index: int  # 0-based line within the notes text
    kind: LineKind
    notes: str  # text before "//", stripped
    comment: str  # text after the first "//", stripped ("" if none)


def _line_kind(notes: str) -> LineKind:
    if not notes:
        return LineKind.BLANK
    if notes.startswith((",", ";")):
        return LineKind.SEPARATOR
    return LineKind.ROW


def notes_lines(notes: str) -> list[NotesLine]:
    """Every line of ``notes``, so callers that need comments or positions agree with the parser."""
    lines: list[NotesLine] = []
    for index, raw in enumerate(notes.splitlines()):
        note_text, _, comment = raw.partition("//")
        note_text = note_text.strip()
        lines.append(NotesLine(index, _line_kind(note_text), note_text, comment.strip()))
    return lines


def _split_measures(notes: str) -> list[list[NotesLine]]:
    """Group note rows into measures separated by ',' lines."""
    measures: list[list[NotesLine]] = []
    current: list[NotesLine] = []
    for line in notes_lines(notes):
        if line.kind is LineKind.SEPARATOR:
            if current:
                measures.append(current)
                current = []
        elif line.kind is LineKind.ROW:
            current.append(line)
    # The chart-closing ";" is treated as the section delimiter, so the last
    # measure may have no trailing ",".
    if current:
        measures.append(current)
    return measures


def source_rows(notes: str) -> list[SourceRow]:
    """The rows that become ``NoteRow``s, in chart order (empty ``0000`` rows skipped)."""
    rows: list[SourceRow] = []
    for measure_idx, measure in enumerate(_split_measures(notes)):
        quantization = len(measure)
        for slot, line in enumerate(measure):
            if line.notes == "0000":
                continue
            rows.append(
                SourceRow(
                    text=line.notes,
                    line_index=line.index,
                    measure=measure_idx,
                    quantization=quantization,
                    beat=round(measure_idx * 4 + slot * 4 / quantization, 4),
                )
            )
    return rows


def _parse_notedata(notes: str, timing: TimingEngine) -> list[NoteRow]:
    """Build NoteRows with timing and hold/roll anchor state."""
    anchor_tracker = AnchorTracker()
    note_rows: list[NoteRow] = []
    for source in source_rows(notes):
        columns = parse_columns(source.text)
        holds_active, rolls_active = anchor_tracker.advance(columns)
        note_rows.append(
            NoteRow(
                notes=columns,
                measure=source.measure,
                quantization=source.quantization,
                beat=source.beat,
                timestamp=timing.convert_beat_to_seconds(source.beat),
                holds_active=holds_active,
                rolls_active=rolls_active,
            )
        )
    return note_rows


def _parse_groove_radar(raw: str) -> GrooveRadar:
    """Parse comma-separated groove radar values into GrooveRadar.

    Uses the first 11 values when present. SSC may supply more (e.g. P1+P2);
    extras are ignored. Missing or blank fields stay None.
    """
    parts = [p.strip() for p in raw.split(",")]

    def fget(i: int) -> float | None:
        if i >= len(parts) or parts[i] == "":
            return None
        return float(parts[i])

    def iget(i: int) -> int | None:
        value = fget(i)
        return None if value is None else int(value)

    return GrooveRadar(
        stream=fget(0),
        voltage=fget(1),
        air=fget(2),
        freeze=fget(3),
        chaos=fget(4),
        steps=iget(5),
        taps=iget(6),
        jumps=iget(7),
        holds=iget(8),
        mines=iget(9),
        hands=iget(10),
    )


def _build_chart(
    *,
    mode: str,
    credit: str,
    difficulty: str,
    rating: float,
    radar_raw: str,
    notes: str,
    timing: TimingEngine,
) -> Chart | SkippedChart:
    """Build one chart, or say why it can't be modeled.

    One unsupported chart (doubles, an unknown note character) must not hide the
    other charts in the file, so it is reported rather than raised.
    """

    def skipped(reason: str) -> SkippedChart:
        return SkippedChart(mode=mode, difficulty=difficulty, reason=reason)

    if mode != SUPPORTED_MODE:
        return skipped(f"only {SUPPORTED_MODE} charts are supported")
    try:
        parsed_difficulty = Difficulty.from_sm(difficulty)
    except ValueError:
        return skipped(f"unknown difficulty {difficulty!r}")
    try:
        note_rows = _parse_notedata(notes, timing)
    except InvalidNoteRow as exc:
        return skipped(str(exc))

    metadata = ChartMetadata(
        mode=mode,
        credit=credit,
        difficulty=parsed_difficulty,
        rating=rating,
        radar=_parse_groove_radar(radar_raw),
    )
    return Chart(metadata, note_rows)


def _timing(header: Header, chart_tags: dict[str, str] | None = None) -> TimingEngine:
    """Timing from the chart's own ``#BPMS`` / ``#STOPS`` (.ssc split timing), else the header's."""
    bpms = header.bpms
    stops = header.stops

    if chart_tags:
        if chart_tags.get("#BPMS"):
            bpms = parse_beat_value_map(chart_tags["#BPMS"])
        if chart_tags.get("#STOPS"):
            stops = parse_beat_value_map(chart_tags["#STOPS"])

    if not bpms:
        raise MissingTimingError("simfile has charts but no #BPMS")
    return TimingEngine(bpms=bpms, stops=stops)


def _sm_chart(section: SourceText, header: Header) -> tuple[Chart | SkippedChart, SourceText]:
    """A chart from a .sm ``#NOTES:`` section, which packs metadata and notes into
    colon-separated fields: ``#NOTES:mode:credit:difficulty:meter:radar:notes``."""
    pieces = section.text.split(":", 6)
    if len(pieces) != 7:
        raise SimfileError(f"line {section.first_line}: malformed #NOTES section")
    _, mode, credit, difficulty, meter, radar, raw_notes = pieces

    # The notes start after the last colon and any whitespace that follows it.
    before_notes = section.text[: len(section.text) - len(raw_notes.lstrip())]
    notes = SourceText(raw_notes.strip(), section.first_line + before_notes.count("\n"))

    chart = _build_chart(
        mode=mode.strip(),
        credit=credit.strip(),
        difficulty=difficulty.strip(),
        rating=float(meter.strip()),
        radar_raw=radar.strip(),
        notes=notes.text,
        timing=_timing(header),
    )
    return chart, notes


def _ssc_chart(
    tags: dict[str, str], section: SourceText, header: Header
) -> tuple[Chart | SkippedChart, SourceText]:
    """A chart from an .ssc ``#NOTEDATA`` block: its tags, then the ``#NOTES:`` section."""
    notes = SourceText(section.text.split(":", 1)[1], section.first_line)
    chart = _build_chart(
        mode=tags.get("#STEPSTYPE", ""),
        credit=tags.get("#CREDIT") or tags.get("#DESCRIPTION") or "",
        difficulty=tags.get("#DIFFICULTY", ""),
        rating=float(tags.get("#METER", 0)),
        radar_raw=tags.get("#RADARVALUES", ""),
        notes=notes.text,
        timing=_timing(header, tags),
    )
    return chart, notes


def parse_simfile_with_notes(data: str) -> tuple[Song, list[SourceText]]:
    """Parse a .sm or .ssc file, also returning each chart's note data as written.

    The second value lines up with ``song.charts``. It is for tools that read
    what the parser discards (comments, source line numbers).
    """
    song = Song(header=Header())
    bodies: list[SourceText] = []
    # Tags of the #NOTEDATA block being read (.ssc only); None outside one.
    ssc_tags: dict[str, str] | None = None

    def add(chart: Chart | SkippedChart, notes: SourceText) -> None:
        if isinstance(chart, Chart):
            song.charts.append(chart)
            bodies.append(notes)
        else:
            song.skipped_charts.append(chart)

    for section in _sections(data):
        head = section.text.upper()
        if head.startswith("#NOTEDATA"):
            ssc_tags = {}
        elif ssc_tags is not None:
            if head.startswith(("#NOTES:", "#NOTES2:")):
                add(*_ssc_chart(ssc_tags, section, song.header))
                ssc_tags = None
            else:
                key, value = _parse_tag(section.text)
                if key in _SSC_CHART_TAGS:
                    ssc_tags[key] = value
        elif head.startswith("#NOTES:"):
            add(*_sm_chart(section, song.header))
        else:
            song.header.set_tag(*_parse_tag(section.text))

    return song, bodies


def parse_simfile(data: str) -> Song:
    """Parse a .sm or .ssc file."""
    song, _ = parse_simfile_with_notes(data)
    return song

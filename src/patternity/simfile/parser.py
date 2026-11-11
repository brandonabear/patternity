import re
from dataclasses import dataclass

from patternity.simfile.notes import AnchorTracker, InvalidNoteRow, NoteRow, parse_columns
from patternity.simfile.song import (
    HEADER_SETTERS,
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


class MissingTimingError(ValueError):
    """A chart has no ``#BPMS``, so its rows cannot be given timestamps."""


def strip_leading_comments(section: str) -> str:
    """Strip leading comments from a section.

    There is often a decorative comment before the note data section.
    ```sm
    #HEADER:;
    //------ dance-single -------
    #NOTES:;
    ```
    """
    lines = section.splitlines()
    for idx, line in enumerate(lines):
        stripped_line = line.strip()
        # Keep only non-comment lines
        if stripped_line and not stripped_line.startswith("//"):
            return "\n".join(lines[idx:]).strip()
    return ""


_HEADER_RE = re.compile(r"^(#[A-Z][A-Z0-9]*)\s*:\s*(.*)$", re.DOTALL)


def _parse_header(raw: str) -> tuple[str, str]:
    """Extract the key/value pair as a tuple using regex."""
    fallback = ("", "")
    if not raw:
        return fallback

    cleaned = "\n".join(_strip_comment(line) for line in raw.splitlines()).strip()
    m = _HEADER_RE.match(cleaned)
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


def _split_measures(notes: str) -> list[list[tuple[int, str]]]:
    """Group ``(line_index, row_text)`` into measures separated by ',' lines."""
    measures: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for line_index, raw in enumerate(notes.splitlines()):
        line = _strip_comment(raw)
        if not line:
            continue
        if line.startswith((",", ";")):
            if current:
                measures.append(current)
                current = []
        else:
            current.append((line_index, line))
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
        for slot, (line_index, text) in enumerate(measure):
            if text == "0000":
                continue
            rows.append(
                SourceRow(
                    text=text,
                    line_index=line_index,
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


class StepmaniaFileParser:
    """Parses StepMania .sm and .ssc files."""

    @classmethod
    def _build_timing(
        cls, song: Song, chart_fields: dict[str, str] | None = None
    ) -> TimingEngine:
        """Build TimingEngine using chart-level split timing if present, else song header."""
        bpms = song.header.bpms
        stops = song.header.stops

        if chart_fields:
            if chart_fields.get("#BPMS"):
                bpms = parse_beat_value_map(chart_fields["#BPMS"])
            if chart_fields.get("#STOPS"):
                stops = parse_beat_value_map(chart_fields["#STOPS"])

        if not bpms:
            raise MissingTimingError("simfile has charts but no #BPMS")
        return TimingEngine(bpms=bpms, stops=stops)

    @classmethod
    def parse(cls, data: str) -> Song:
        """Parse a .sm or .ssc file."""
        song = Song(header=Header())
        chart_fields: dict[str, str] | None = None

        for raw_section in data.split(";"):
            section = strip_leading_comments(raw_section)
            if not section:
                continue
            head = section.upper()

            # Instantiate dictionary for chart metadata (SSC only).
            if head.startswith("#NOTEDATA"):
                chart_fields = {}
                continue

            # Read chart metadata from SSC.
            if chart_fields is not None:
                if head.startswith(("#NOTES:", "#NOTES2:")):
                    timing = cls._build_timing(song, chart_fields)
                    cls._add_chart(song, cls._chart_from_fields(chart_fields, section, timing))
                    chart_fields = None
                    continue

                key, value = _parse_header(section)
                if key in _SSC_CHART_TAGS:
                    chart_fields[key] = value
                continue

            if head.startswith("#NOTES:"):
                timing = cls._build_timing(song)
                cls._add_chart(song, cls._chart_from_packed_notes(section, timing))
                continue

            key, value = _parse_header(section)
            if key in HEADER_SETTERS:
                getattr(song.header, HEADER_SETTERS[key])(value)

        return song

    @staticmethod
    def _add_chart(song: Song, chart: Chart | SkippedChart) -> None:
        if isinstance(chart, Chart):
            song.charts.append(chart)
        else:
            song.skipped_charts.append(chart)

    @classmethod
    def _chart_from_fields(
        cls, fields: dict[str, str], section: str, timing: TimingEngine
    ) -> Chart | SkippedChart:
        """Build a chart from .ssc ``#NOTEDATA:`` tags."""
        return _build_chart(
            mode=fields.get("#STEPSTYPE", ""),
            credit=fields.get("#CREDIT") or fields.get("#DESCRIPTION") or "",
            difficulty=fields.get("#DIFFICULTY", ""),
            rating=float(fields.get("#METER", 0)),
            radar_raw=fields.get("#RADARVALUES", ""),
            notes=section.split(":", 1)[1],
            timing=timing,
        )

    @classmethod
    def _chart_from_packed_notes(cls, section: str, timing: TimingEngine
    ) -> Chart | SkippedChart:
        """Build a chart from a .sm ``#NOTES:`` value."""
        parts = [part.strip() for part in section.split(":", 6)][1:]
        return _build_chart(
            mode=parts[0],
            credit=parts[1],
            difficulty=parts[2],
            rating=float(parts[3]),
            radar_raw=parts[4],
            notes=parts[5],
            timing=timing,
        )

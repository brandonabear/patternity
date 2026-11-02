import re
from collections.abc import Iterator

from patternity.simfile.notes import AnchorTracker, NoteRow
from patternity.simfile.song import (
    HEADER_SETTERS,
    Chart,
    ChartMetadata,
    Difficulty,
    GrooveRadar,
    Header,
    Song,
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


def _split_measures(notes: str) -> list[list[str]]:
    """Group note rows into measures. Measures are separated by ',' lines."""
    measures: list[list[str]] = []
    current: list[str] = []
    for raw in notes.splitlines():
        line = _strip_comment(raw)
        if not line:
            continue
        if line.startswith((",", ";")):
            if current:
                measures.append(current)
                current = []
        else:
            current.append(line)
    # The chart-closing ";" is treated as the section delimiter, so the last
    # measure may have no trailing ",".
    if current:
        measures.append(current)
    return measures


def _rows_from_measures(
    measures: list[list[str]], timing: TimingEngine
) -> Iterator[NoteRow]:
    """Extract NoteRow and anchor state information."""
    anchor_tracker = AnchorTracker()
    for measure_idx, rows in enumerate(measures):
        quantization = len(rows)
        for row_idx, row in enumerate(rows):
            # Skip empty rows
            if row == "0000":
                continue

            # Build row timing information
            beat = round(measure_idx * 4 + row_idx * 4 / quantization, 4)
            note_row = NoteRow.from_str(
                row,
                quantization=quantization,
                beat=beat,
                measure=measure_idx,
                timestamp=timing.convert_beat_to_seconds(beat),
            )

            # Apply hold/roll tracking
            anchor_tracker.apply_heads(note_row)
            hold_mask, roll_mask = anchor_tracker.snapshot()
            note_row.hold_active_mask = hold_mask
            note_row.roll_active_mask = roll_mask
            anchor_tracker.apply_tails(note_row)
            yield note_row


def _parse_notedata(notes: str, timing: TimingEngine) -> list[NoteRow]:
    return list(_rows_from_measures(_split_measures(notes), timing))


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


def _build_chart_metadata(
    *,
    mode: str,
    credit: str,
    difficulty: str,
    rating: float,
    radar_raw: str,
) -> ChartMetadata:
    return ChartMetadata(
        mode=mode,
        credit=credit,
        difficulty=Difficulty.from_sm(difficulty),
        rating=rating,
        radar=_parse_groove_radar(radar_raw),
    )


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
                temp_header = Header()
                getattr(temp_header, HEADER_SETTERS["#BPMS"])(chart_fields["#BPMS"])
                bpms = temp_header.bpms
            if chart_fields.get("#STOPS"):
                temp_header = Header()
                getattr(temp_header, HEADER_SETTERS["#STOPS"])(chart_fields["#STOPS"])
                stops = temp_header.stops

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
                    song.charts.append(
                        cls._chart_from_fields(chart_fields, section, timing)
                    )
                    chart_fields = None
                    continue

                key, value = _parse_header(section)
                if key in _SSC_CHART_TAGS:
                    chart_fields[key] = value
                continue

            if head.startswith("#NOTES:"):
                timing = cls._build_timing(song)
                song.charts.append(cls._chart_from_packed_notes(section, timing))
                continue

            key, value = _parse_header(section)
            if key in HEADER_SETTERS:
                getattr(song.header, HEADER_SETTERS[key])(value)

        return song

    @classmethod
    def _chart_from_fields(
        cls, fields: dict[str, str], section: str, timing: TimingEngine
    ) -> Chart:
        """Build a chart from .ssc ``#NOTEDATA:`` tags."""
        return Chart(
            _build_chart_metadata(
                mode=fields.get("#STEPSTYPE", ""),
                credit=fields.get("#CREDIT") or fields.get("#DESCRIPTION") or "",
                difficulty=fields.get("#DIFFICULTY", ""),
                rating=float(fields.get("#METER", 0)),
                radar_raw=fields.get("#RADARVALUES", ""),
            ),
            _parse_notedata(section.split(":", 1)[1], timing),
        )

    @classmethod
    def _chart_from_packed_notes(cls, section: str, timing: TimingEngine) -> Chart:
        """Build a chart from a .sm ``#NOTES:`` value."""
        parts = [part.strip() for part in section.split(":", 6)][1:]
        return Chart(
            _build_chart_metadata(
                mode=parts[0],
                credit=parts[1],
                difficulty=parts[2],
                rating=float(parts[3]),
                radar_raw=parts[4],
            ),
            _parse_notedata(parts[5], timing),
        )

import re
from collections.abc import Iterator

from patternity.models.engine import NoteRow
from patternity.models.song import (
    HEADER_SETTERS,
    Chart,
    ChartMetadata,
    Difficulty,
    GrooveRadar,
    Header,
    Song,
)

_HEADER_RE = re.compile(r"^(#[A-Z][A-Z0-9]*)\s*:\s*(.*)$")
_SSC_CHART_TAGS = frozenset(
    {
        "#STEPSTYPE",
        "#DESCRIPTION",
        "#CREDIT",
        "#DIFFICULTY",
        "#METER",
        "#RADARVALUES",
    }
)


def _strip_leading_comments(section: str) -> str:
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
        if stripped_line and not stripped_line.startswith("//"):
            return "\n".join(lines[idx:]).strip()
    return ""


def _parse_header(raw: str) -> tuple[str, str]:
    # Headers are single-line; take the first line so trailing blanks are ok.
    first = raw.splitlines()[0] if raw else ""
    m = _HEADER_RE.match(first.strip())
    return (m.group(1), m.group(2)) if m else ("", "")


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
    # The chart-closing ";" is consumed as the section delimiter, so the last
    # measure may have no trailing ",".
    if current:
        measures.append(current)
    return measures


def _rows_from_measures(measures: list[list[str]]) -> Iterator[NoteRow]:
    """First row of measure N is at beat N*4; rows are evenly spaced."""
    for measure_idx, rows in enumerate(measures):
        quantization = len(rows)
        for row_idx, row in enumerate(rows):
            yield NoteRow.from_str(
                row,
                quantization=quantization,
                beat=round(measure_idx * 4 + row_idx * 4 / quantization, 4),
                measure=measure_idx,
            )


def _parse_notedata(notes: str) -> list[NoteRow]:
    return list(_rows_from_measures(_split_measures(notes)))


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
    def parse(cls, data: str) -> Song:
        """Parse a .sm or .ssc file."""
        song = Song(header=Header())
        chart_fields: dict[str, str] | None = None

        for raw_section in data.split(";"):
            section = _strip_leading_comments(raw_section)
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
                    song.charts.append(cls._chart_from_fields(chart_fields, section))
                    chart_fields = None
                    continue

                key, value = _parse_header(section)
                if key in _SSC_CHART_TAGS:
                    chart_fields[key] = value
                continue

            if head.startswith("#NOTES:"):
                song.charts.append(cls._chart_from_packed_notes(section))
                continue

            key, value = _parse_header(section)
            if key in HEADER_SETTERS:
                getattr(song.header, HEADER_SETTERS[key])(value)

        return song

    @classmethod
    def _chart_from_fields(cls, fields: dict[str, str], section: str) -> Chart:
        """Build a chart from tags collected after #NOTEDATA."""
        return Chart(
            _build_chart_metadata(
                mode=fields.get("#STEPSTYPE", ""),
                credit=fields.get("#CREDIT") or fields.get("#DESCRIPTION") or "",
                difficulty=fields.get("#DIFFICULTY", ""),
                rating=float(fields.get("#METER", 0)),
                radar_raw=fields.get("#RADARVALUES", ""),
            ),
            _parse_notedata(section.split(":", 1)[1]),
        )

    @classmethod
    def _chart_from_packed_notes(cls, section: str) -> Chart:
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
            _parse_notedata(parts[5]),
        )

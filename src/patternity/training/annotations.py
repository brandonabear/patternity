"""Inline corpus annotations for pattern fixtures (evaluation only).

Annotations are read from simfile comments and aligned to ``Chart.notes`` indices
produced by ``StepmaniaFileParser`` (including skipped ``0000`` rows).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from patternity.footing.stance import FootMove
from patternity.simfile.notes import NoteRow, NoteType
from patternity.simfile.parser import StepmaniaFileParser, strip_leading_comments
from patternity.simfile.song import Chart, Song

_NOTE_ROW_RE = re.compile(r"^[0-4MFL]{4}", re.IGNORECASE)

_FOOT_RE = re.compile(r"(?:^|\s)@foot=([LR])(?:\s|$)")
_FEET_RE = re.compile(r"(?:^|\s)@feet=([LR](?:,[LR])*)(?:\s|$)")
_PATTERN_RE = re.compile(r"(?:^|\s)@pattern=([a-z0-9_-]+(?:,[a-z0-9_-]+)*)(?:\s|$)")
_SECTION_RE = re.compile(r"(?:^|\s)@section=([a-z0-9_-]+)(?:\s|$)")

_PRESSABLE = {
    NoteType.TAP,
    NoteType.HOLD,
    NoteType.ROLL,
    NoteType.LIFT,
}


class AnnotationError(ValueError):
    """Raised when corpus comments do not align with chart rows."""


@dataclass(frozen=True)
class AnnotatedRow:
    index: int
    line_number: int
    measure: int
    beat: float
    row: NoteRow
    feet: tuple[str, ...] = ()
    patterns: frozenset[str] = frozenset()
    section: str = "default"

    @property
    def pressable_cols(self) -> tuple[int, ...]:
        notes = (self.row.left, self.row.down, self.row.up, self.row.right)
        return tuple(col for col, note in enumerate(notes) if note in _PRESSABLE)

    def expected_foot_move(self) -> FootMove | None:
        """Map ``@foot`` / ``@feet`` to ``FootMove`` for regression checks."""
        if len(self.feet) == 1:
            return FootMove.LEFT if self.feet[0] == "L" else FootMove.RIGHT
        if len(self.feet) == 2:
            if self.feet[0] == self.feet[1]:
                return FootMove.LEFT if self.feet[0] == "L" else FootMove.RIGHT
            return FootMove.BOTH
        return None


@dataclass(frozen=True)
class AnnotatedChart:
    song: Song
    rows: tuple[AnnotatedRow, ...]

    @property
    def chart(self) -> Chart:
        return self.song.charts[0]

    @property
    def tagged_assignments(self) -> dict[int, FootMove]:
        """Chart note indices with explicit ``@foot`` / ``@feet`` tags."""
        return {
            row.index: move
            for row in self.rows
            if (move := row.expected_foot_move()) is not None
        }


@dataclass(frozen=True)
class _RawRow:
    text: str
    comment: str
    line_number: int
    section: str


def _is_flat_notes_section(lines: list[str]) -> bool:
    """True when note rows follow ``#NOTES:`` directly (``.ssc`` flat body)."""
    for line in lines[1:]:
        note_text = line.split("//", 1)[0].strip()
        if not note_text or note_text.startswith("//"):
            continue
        if note_text.startswith((",", ";")):
            return True
        return bool(_NOTE_ROW_RE.match(note_text))
    return False


def _notes_body(data: str) -> tuple[str, int]:
    for raw_section in data.split(";"):
        section_text = strip_leading_comments(raw_section)
        if not section_text.lstrip().startswith("#NOTES:"):
            continue

        lines = section_text.splitlines()
        first = lines[0].strip() if lines else ""
        if first in ("#NOTES:", "#NOTES2:") and _is_flat_notes_section(lines):
            body = "\n".join(lines[1:])
            notes_idx = data.find(first)
            if notes_idx < 0:
                notes_idx = data.find("#NOTES:")
            line_end = data.find("\n", notes_idx)
            body_line = data[: line_end + 1].count("\n") + 1
            return body, body_line

        parts = [part.strip() for part in section_text.split(":", 6)][1:]
        if len(parts) < 6:
            raise AnnotationError("malformed #NOTES section")
        body = parts[5]
        prefix = data[: data.find(body)]
        return body, prefix.count("\n") + 1
    raise AnnotationError("no #NOTES chart found")


def _parse_tags(
    comment: str, *, line_number: int
) -> tuple[tuple[str, ...], frozenset[str]]:
    foot_match = _FOOT_RE.search(comment)
    feet_match = _FEET_RE.search(comment)
    if foot_match and feet_match:
        raise AnnotationError(
            f"line {line_number}: use either @foot or @feet, not both"
        )
    feet: tuple[str, ...]
    if foot_match:
        feet = (foot_match.group(1),)
    elif feet_match:
        feet = tuple(feet_match.group(1).split(","))
    else:
        feet = ()

    pattern_match = _PATTERN_RE.search(comment)
    patterns = (
        frozenset(pattern_match.group(1).split(",")) if pattern_match else frozenset()
    )
    return feet, patterns


def parse_annotated_sm(data: str, *, require_complete: bool = False) -> AnnotatedChart:
    """Parse the first chart and align inline comments to parsed note rows."""
    song = StepmaniaFileParser.parse(data)
    if not song.charts:
        raise AnnotationError("simfile has no parsed chart")

    body, body_line = _notes_body(data)
    measures: list[list[_RawRow]] = []
    current: list[_RawRow] = []
    section_name = "default"

    for offset, raw_line in enumerate(body.splitlines()):
        line_number = body_line + offset
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            match = _SECTION_RE.search(stripped[2:].strip())
            if match:
                section_name = match.group(1)
            continue

        note_text, marker, comment = stripped.partition("//")
        note_text = note_text.strip()
        comment = comment.strip() if marker else ""
        if note_text.startswith((",", ";")):
            if current:
                measures.append(current)
                current = []
            match = _SECTION_RE.search(comment)
            if match:
                section_name = match.group(1)
            continue
        if note_text:
            current.append(_RawRow(note_text, comment, line_number, section_name))
    if current:
        measures.append(current)

    annotated: list[AnnotatedRow] = []
    row_index = 0
    for measure_index, measure in enumerate(measures):
        quantization = len(measure)
        if quantization == 0:
            continue
        beat_step = 4.0 / quantization
        for slot, raw in enumerate(measure):
            if raw.text == "0000":
                continue
            try:
                note_row = NoteRow.from_str(
                    raw.text,
                    quantization=quantization,
                    beat=round(measure_index * 4.0 + slot * beat_step, 4),
                    measure=measure_index,
                )
            except (TypeError, ValueError) as error:
                raise AnnotationError(
                    f"line {raw.line_number}: invalid note row {raw.text!r}"
                ) from error
            feet, patterns = _parse_tags(raw.comment, line_number=raw.line_number)
            item = AnnotatedRow(
                index=row_index,
                line_number=raw.line_number,
                measure=measure_index,
                beat=note_row.beat or 0.0,
                row=note_row,
                feet=feet,
                patterns=patterns,
                section=raw.section,
            )
            press_count = len(item.pressable_cols)
            if feet and len(feet) == 2 and press_count != 2:
                raise AnnotationError(
                    f"line {raw.line_number}: @feet expects two panels but row has "
                    f"{press_count} pressable notes"
                )
            if feet and len(feet) > 2:
                raise AnnotationError(
                    f"line {raw.line_number}: too many @feet entries ({len(feet)})"
                )
            if patterns and press_count == 0:
                raise AnnotationError(
                    f"line {raw.line_number}: pattern anchor has no pressable note"
                )
            if require_complete and press_count and not feet:
                raise AnnotationError(
                    f"line {raw.line_number}: pressable row is missing @foot/@feet"
                )
            annotated.append(item)
            row_index += 1

    if len(annotated) != len(song.charts[0].notes):
        raise AnnotationError(
            "annotation row alignment differs from parser: "
            f"{len(annotated)} annotated vs {len(song.charts[0].notes)} parsed"
        )
    return AnnotatedChart(song=song, rows=tuple(annotated))

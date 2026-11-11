"""Inline annotations in fixture charts, used for training and evaluation.

Annotations are read from the comments on note rows and aligned to the indices
of ``Chart.notes``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from patternity.footing.stance import FootMove
from patternity.patterns.spans import PatternKind
from patternity.simfile.notes import NoteRow
from patternity.simfile.parser import parse_simfile_with_notes, source_rows
from patternity.simfile.song import Chart, Song

# Legal values of the tags read from a note row's comment.
_TAG_VALUE_RES = {
    "@foot": re.compile(r"[LR]"),
    "@feet": re.compile(r"[LR](?:,[LR])*"),
    "@pattern": re.compile(r"[a-z0-9_-]+(?:,[a-z0-9_-]+)*"),
}
_SECTION_RE = re.compile(r"(?:^|\s)@section=([a-z0-9_-]+)(?:\s|$)")

# ``@pattern`` tags that are scored, and the detector kind each is compared against.
PATTERN_TAGS: dict[str, PatternKind] = {
    "jack": PatternKind.JACK,
    "footswitch": PatternKind.FOOTSWITCH,
    "holdswitch": PatternKind.FOOTSWITCH,
    "sideswitch": PatternKind.SIDESWITCH,
    "doublestep": PatternKind.DOUBLESTEP,
    "bracket": PatternKind.BRACKET,
    "candle": PatternKind.CANDLE,
}
# Tags a chart may carry for the reader's benefit; evaluation ignores them.
UNSCORED_PATTERN_TAGS = frozenset({"crossover", "jump"})


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
            row.index: move for row in self.rows if (move := row.expected_foot_move()) is not None
        }


def _tag_values(comment: str, *, line_number: int) -> dict[str, str]:
    """The value of each ``@foot`` / ``@feet`` / ``@pattern`` tag in a row comment.

    A tag with a malformed value raises rather than being skipped: a typo would
    otherwise drop the row from training and scoring without a trace. When a
    tag repeats, the first one wins.
    """
    values: dict[str, str] = {}
    for token in comment.split():
        key, has_value, value = token.partition("=")
        if not has_value or key not in _TAG_VALUE_RES:
            continue
        if not _TAG_VALUE_RES[key].fullmatch(value):
            raise AnnotationError(f"line {line_number}: malformed tag {token!r}")
        values.setdefault(key, value)
    return values


def _parse_tags(comment: str, *, line_number: int) -> tuple[tuple[str, ...], frozenset[str]]:
    values = _tag_values(comment, line_number=line_number)
    if "@foot" in values and "@feet" in values:
        raise AnnotationError(f"line {line_number}: use either @foot or @feet, not both")
    foot_value = values.get("@foot") or values.get("@feet")
    feet = tuple(foot_value.split(",")) if foot_value else ()

    pattern_value = values.get("@pattern")
    patterns = frozenset(pattern_value.split(",")) if pattern_value else frozenset()
    unknown = patterns - PATTERN_TAGS.keys() - UNSCORED_PATTERN_TAGS
    if unknown:
        raise AnnotationError(
            f"line {line_number}: unknown @pattern tag(s) {', '.join(sorted(unknown))}"
        )
    return feet, patterns


def _sections_by_line(lines: list[str]) -> list[str]:
    """The active ``@section`` name at each body line.

    A section is set by a comment-only line or a comment on a measure separator,
    and applies to the rows that follow.
    """
    section = "default"
    sections: list[str] = []
    for line in lines:
        note_text, _, comment = line.partition("//")
        note_text = note_text.strip()
        if not note_text or note_text.startswith((",", ";")):
            match = _SECTION_RE.search(comment.strip())
            if match:
                section = match.group(1)
        sections.append(section)
    return sections


def _validate_row(item: AnnotatedRow, *, require_complete: bool) -> None:
    line, feet = item.line_number, item.feet
    press_count = len(item.row.pressed)
    if len(feet) == 2 and press_count != 2:
        raise AnnotationError(
            f"line {line}: @feet expects two panels but row has {press_count} pressable notes"
        )
    if len(feet) > 2:
        raise AnnotationError(f"line {line}: too many @feet entries ({len(feet)})")
    if item.patterns and press_count == 0:
        raise AnnotationError(f"line {line}: pattern anchor has no pressable note")
    if require_complete and press_count and not feet:
        raise AnnotationError(f"line {line}: pressable row is missing @foot/@feet")


def parse_annotated_sm(data: str, *, require_complete: bool = False) -> AnnotatedChart:
    """Parse the first chart and align inline comments to its parsed note rows.

    Row positions come from the parser's ``source_rows``; this function only adds
    what the parser discards: comments, source line numbers, and sections.
    """
    song, bodies = parse_simfile_with_notes(data)
    if not song.charts:
        raise AnnotationError("simfile has no parsed chart")
    notes = song.charts[0].notes
    body = bodies[0]

    lines = body.text.splitlines()
    sources = source_rows(body.text)
    sections = _sections_by_line(lines)

    annotated: list[AnnotatedRow] = []
    for index, (source, note_row) in enumerate(zip(sources, notes, strict=True)):
        line_number = body.first_line + source.line_index
        _, _, comment = lines[source.line_index].partition("//")
        feet, patterns = _parse_tags(comment.strip(), line_number=line_number)
        item = AnnotatedRow(
            index=index,
            line_number=line_number,
            measure=source.measure,
            beat=source.beat,
            row=note_row,
            feet=feet,
            patterns=patterns,
            section=sections[source.line_index],
        )
        _validate_row(item, require_complete=require_complete)
        annotated.append(item)
    return AnnotatedChart(song=song, rows=tuple(annotated))

#!/usr/bin/env python3
"""Write model footing and pattern suggestions into a chart for human review.

Foot suggestions (``@suggest_foot=`` / ``@suggest_feet=``) go on rows with no
``@foot``/``@feet`` tag and on rows where the model disagrees with the existing
tag. Pattern suggestions (``@suggest_pattern=``) go on rows where the patterns
detected on the decoded path differ from the row's recognized ``@pattern`` tags;
``@suggest_pattern=none`` means the decoder found nothing on a tagged row.
Existing tags are never changed. ``@margin=`` is the model's confidence (cost
gap to the best alternative foot); review low margins first, then drop the
``suggest_`` prefix to accept. When the whole output is already correct, a
find/replace of ``@suggest_`` with ``@`` accepts everything. Rerunning replaces
previous suggestions, including legacy ``@suggest=`` tags.

Also writes 0-based ``// measure N`` markers: a ``// measure 0`` line before the
first note row, and ``// measure N`` on each comma (``N`` is the measure that
starts after that comma), matching the StepMania editor convention.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from patternity.footing import FootingModel, FootingResult, FootMove, ResolvedStep, resolve_chart
from patternity.patterns import PatternKind
from patternity.simfile.parser import LineKind, notes_lines, parse_simfile_with_notes
from patternity.training.annotations import PATTERN_TAGS, AnnotatedChart, parse_annotated_sm
from patternity.training.evaluation import pattern_anchors

_SUGGEST_RE = re.compile(r"@suggest(?:_\w+)?=\S+", re.IGNORECASE)
_MARGIN_RE = re.compile(r"@margin=\S+", re.IGNORECASE)
_MEASURE_IN_COMMENT_RE = re.compile(r"measure\s+\d+", re.IGNORECASE)
_MEASURE_LINE_RE = re.compile(r"^\s*//\s*measure\s+(\d+)\s*$", re.IGNORECASE)


def _kind_tag(kind: PatternKind) -> str:
    """The ``@pattern`` tag for a detected kind; charts tag inverted crossovers as crossovers."""
    return PatternKind.CROSSOVER.value if kind is PatternKind.INVERTED_CROSSOVER else kind.value


_TAG_ORDER = tuple(dict.fromkeys(_kind_tag(kind) for kind in PatternKind))


def _tagged_patterns(patterns: frozenset[str]) -> set[str]:
    """A row's ``@pattern`` tags as detector tags (``holdswitch`` is a footswitch).

    Tags no detector kind produces, such as ``jump``, are dropped.
    """
    tags = {_kind_tag(PATTERN_TAGS[tag]) if tag in PATTERN_TAGS else tag for tag in patterns}
    return tags & set(_TAG_ORDER)


def _tag(move: FootMove) -> str:
    return {
        FootMove.LEFT: "@suggest_foot=L",
        FootMove.RIGHT: "@suggest_foot=R",
        FootMove.BOTH: "@suggest_feet=L,R",
    }[move]


def _ordered(tags: set[str]) -> list[str]:
    return [tag for tag in _TAG_ORDER if tag in tags]


def _decoded_patterns(steps: Sequence[ResolvedStep]) -> dict[int, set[str]]:
    """Pattern tags per row index, anchored on the last step of each span."""
    decoded: dict[int, set[str]] = {}
    for kind, rows in pattern_anchors(steps).items():
        for index in rows:
            decoded.setdefault(index, set()).add(_kind_tag(kind))
    return decoded


def _strip_suggestion_suffix(body: str) -> str:
    if "//" not in body or "@suggest" not in body.lower():
        return body
    left, _, comment = body.partition("//")
    comment = _MEASURE_IN_COMMENT_RE.sub("", comment)
    comment = _SUGGEST_RE.sub("", comment)
    comment = _MARGIN_RE.sub("", comment)
    comment = " ".join(comment.split())
    if comment:
        return f"{left.rstrip()} // {comment}"
    return left.rstrip()


@dataclass
class _ChartLines:
    """A chart file as editable lines, each keeping its original line ending."""

    lines: list[str]
    endings: list[str]

    @classmethod
    def read(cls, path: Path) -> _ChartLines:
        raw_lines = path.read_text(encoding="utf-8", newline="").splitlines(keepends=True)
        lines = [raw.rstrip("\r\n") for raw in raw_lines]
        endings = [raw[len(line) :] for raw, line in zip(raw_lines, lines, strict=True)]
        return cls(lines, endings)

    def text(self) -> str:
        return "".join(line + end for line, end in zip(self.lines, self.endings, strict=True))

    def write(self, path: Path) -> None:
        path.write_text(self.text(), encoding="utf-8", newline="")

    def insert(self, index: int, line: str) -> None:
        """Insert ``line`` before ``index``, with the ending of the line it displaces."""
        self.endings.insert(index, self.endings[index] if index < len(self.endings) else "\n")
        self.lines.insert(index, line)

    def append_comment(self, line_number: int, text: str) -> None:
        """Add ``text`` to the comment on 1-based ``line_number``, starting one if needed."""
        line = self.lines[line_number - 1]
        self.lines[line_number - 1] = f"{line} {text}" if "//" in line else f"{line} // {text}"


@dataclass(frozen=True, slots=True)
class _Suggestion:
    line_number: int
    measure: int
    tag: str  # Written into the chart's comment.
    detail: str  # Printed after the line and measure.
    margin: float = math.inf  # Model confidence; low margins are listed first.


def _add_measure_markers(chart: _ChartLines) -> None:
    """Label ``// measure 0`` and comma lines in the first chart's note body."""
    _, bodies = parse_simfile_with_notes(chart.text())
    if not bodies:
        return
    notes = bodies[0]
    body_start = notes.first_line - 1

    body_lines = notes_lines(notes.text)
    first_row = next((line for line in body_lines if line.kind is LineKind.ROW), None)
    if first_row is None:
        return
    separators = [line for line in body_lines if line.kind is LineKind.SEPARATOR]

    # Label commas before inserting the measure 0 line, so body indices still match.
    for measure, separator in enumerate(separators, start=1):
        if separator.notes.startswith(","):
            chart.lines[body_start + separator.index] = f"{separator.notes}  // measure {measure}"

    insert_at = body_start + first_row.index
    prev_i = insert_at - 1
    if prev_i >= 0 and _MEASURE_LINE_RE.match(chart.lines[prev_i]):
        chart.lines[prev_i] = "// measure 0"
    else:
        chart.insert(insert_at, "// measure 0")


def _foot_suggestions(annotated: AnnotatedChart, result: FootingResult) -> list[_Suggestion]:
    """Pressed rows where the decoded feet are untagged or differ from the tag."""
    gold = annotated.tagged_assignments
    suggestions: list[_Suggestion] = []
    for row in annotated.rows:
        step = result.steps[row.index]
        move, expected = step.foot_row.moved, gold.get(row.index)
        if not step.note_row.pressed or expected == move:
            continue
        margin = math.inf if step.confidence is None else step.confidence
        margin_text = "inf" if margin == math.inf else f"{margin:.1f}"
        tag = f"{_tag(move)} @margin={margin_text}"
        label = "DISAGREES" if expected is not None else "untagged"
        measure = row.note_row.measure
        suggestions.append(
            _Suggestion(row.line_number, measure, tag, f"{label} m{measure} {tag}", margin)
        )
    return sorted(suggestions, key=lambda s: (s.margin, s.line_number))


def _pattern_suggestions(annotated: AnnotatedChart, result: FootingResult) -> list[_Suggestion]:
    """Pressed rows where the patterns detected on the decoded path differ from the tags."""
    decoded = _decoded_patterns(result.steps)
    suggestions: list[_Suggestion] = []
    for row in annotated.rows:
        tagged = _tagged_patterns(row.patterns)
        found = decoded.get(row.index, set())
        if not result.steps[row.index].note_row.pressed or found == tagged:
            continue
        tag = "@suggest_pattern=" + (",".join(_ordered(found)) or "none")
        was = ",".join(_ordered(tagged)) or "untagged"
        suggestions.append(
            _Suggestion(row.line_number, row.note_row.measure, tag, f"{tag} (was {was})")
        )
    return suggestions


def _report(
    console: Console, feet: list[_Suggestion], patterns: list[_Suggestion], list_rows: int
) -> None:
    def show(suggestion: _Suggestion) -> None:
        line, measure = suggestion.line_number, suggestion.measure
        console.print(f"  line {line:5d} m{measure}: {suggestion.detail}")

    for suggestion in feet[:list_rows]:
        show(suggestion)
    if patterns:
        console.print("Pattern suggestions:")
        for suggestion in patterns[:list_rows]:
            show(suggestion)


def suggest_file(
    console: Console, path: Path, model: FootingModel, *, list_rows: int
) -> tuple[int, int]:
    """Write suggestions in place; return (foot suggestions, pattern suggestions)."""
    original = _ChartLines.read(path)
    chart = _ChartLines(
        [_strip_suggestion_suffix(line) for line in original.lines], original.endings
    )
    _add_measure_markers(chart)

    annotated = parse_annotated_sm(chart.text())
    result = resolve_chart(annotated.chart.notes, model)
    feet = _foot_suggestions(annotated, result)
    patterns = _pattern_suggestions(annotated, result)

    # Foot tags go first, so a row with both reads "// @suggest_foot=... @suggest_pattern=...".
    for suggestion in feet + patterns:
        chart.append_comment(suggestion.line_number, suggestion.tag)
    chart.write(path)
    _report(console, feet, patterns, list_rows)
    return len(feet), len(patterns)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chart", type=Path)
    parser.add_argument("--weights", type=Path, help="weights JSON (default: packaged)")
    parser.add_argument("--list", type=int, default=25, help="lowest-margin rows to print")
    return parser


def main(argv: list[str] | None = None) -> int:
    console = Console()
    parser = build_parser()
    args = parser.parse_args(args=argv)
    if args.chart.suffix not in (".sm", ".ssc"):
        parser.error(f"{args.chart} is not a .sm or .ssc file")

    model = FootingModel.load(args.weights)
    feet, patterns = suggest_file(console, args.chart.resolve(), model, list_rows=args.list)
    console.print(f"Wrote {feet} foot and {patterns} pattern suggestions to {args.chart}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
from pathlib import Path

from rich.console import Console

from patternity.footing import FootingModel, FootMove, ResolvedStep, resolve_chart
from patternity.patterns import PatternKind, detect_tech_patterns
from patternity.simfile import read_simfile
from patternity.simfile.parser import parse_simfile_with_notes
from patternity.training.annotations import parse_annotated_sm
from patternity.training.evaluation import PATTERN_TAGS

_NOTE_ROW_RE = re.compile(r"^[0-4MFL]{4}", re.IGNORECASE)
_SUGGEST_RE = re.compile(r"@suggest(?:_\w+)?=\S+", re.IGNORECASE)
_MARGIN_RE = re.compile(r"@margin=\S+", re.IGNORECASE)
_MEASURE_IN_COMMENT_RE = re.compile(r"measure\s+\d+", re.IGNORECASE)
_MEASURE_LINE_RE = re.compile(r"^\s*//\s*measure\s+(\d+)\s*$", re.IGNORECASE)


_KIND_TAG: dict[PatternKind, str] = {
    PatternKind.JACK: "jack",
    PatternKind.DOUBLESTEP: "doublestep",
    PatternKind.FOOTSWITCH: "footswitch",
    PatternKind.SIDESWITCH: "sideswitch",
    PatternKind.BRACKET: "bracket",
    PatternKind.CROSSOVER: "crossover",
    PatternKind.INVERTED_CROSSOVER: "crossover",
    PatternKind.CANDLE: "candle",
}
_TAG_ORDER = tuple(dict.fromkeys(_KIND_TAG.values()))
_TAG_ALIASES: dict[str, str] = {
    **{tag: _KIND_TAG[kind] for tag, kind in PATTERN_TAGS.items()},
    "crossover": "crossover",
}


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
    for span in detect_tech_patterns(steps).spans:
        decoded.setdefault(span.steps[-1].index, set()).add(_KIND_TAG[span.kind])
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


def _format_comma_measure(line: str, measure: int) -> str:
    note = line.split("//", 1)[0].rstrip()
    token = note.strip()
    if not token.startswith(","):
        return line
    return f"{token}  // measure {measure}"


def _add_measure_markers(lines: list[str], endings: list[str]) -> None:
    """Label ``// measure 0`` and comma lines in the first chart's note body."""
    text = "".join(body + end for body, end in zip(lines, endings, strict=True))
    _, bodies = parse_simfile_with_notes(text)
    if not bodies:
        return
    notes = bodies[0]
    body_start = notes.first_line - 1

    first_note_offset: int | None = None
    comma_updates: list[tuple[int, int]] = []

    for offset, raw_line in enumerate(notes.text.splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            continue
        note_text, _, _ = stripped.partition("//")
        note_text = note_text.strip()
        if note_text.startswith((",", ";")):
            comma_updates.append((body_start + offset, len(comma_updates) + 1))
            continue
        if note_text and _NOTE_ROW_RE.match(note_text) and first_note_offset is None:
            first_note_offset = offset

    if first_note_offset is None:
        return

    insert_at = body_start + first_note_offset
    prev_i = insert_at - 1
    if prev_i >= 0 and _MEASURE_LINE_RE.match(lines[prev_i]):
        lines[prev_i] = "// measure 0"
    else:
        ending = endings[insert_at] if insert_at < len(endings) else "\n"
        lines.insert(insert_at, "// measure 0")
        endings.insert(insert_at, ending)

    for line_i, measure in comma_updates:
        if line_i >= insert_at:
            line_i += 1
        lines[line_i] = _format_comma_measure(lines[line_i], measure)


def suggest_file(
    console: Console, path: Path, model: FootingModel, *, list_rows: int
) -> tuple[int, int]:
    """Write suggestions in place; return (foot suggestions, pattern suggestions)."""
    data = read_simfile(path)
    raw_lines = path.read_text(encoding="utf-8", newline="").splitlines(keepends=True)
    lines: list[str] = []
    endings: list[str] = []
    for raw in raw_lines:
        body = raw.rstrip("\r\n")
        endings.append(raw[len(body) :])
        lines.append(_strip_suggestion_suffix(body))

    _add_measure_markers(lines, endings)
    data = "".join(body + end for body, end in zip(lines, endings, strict=True))

    annotated = parse_annotated_sm(data)
    result = resolve_chart(annotated.chart.notes, model)
    gold = annotated.tagged_assignments
    decoded = _decoded_patterns(result.steps)

    suggestions: list[tuple[float, int, int, str]] = []
    pattern_suggestions: list[str] = []
    for row in annotated.rows:
        step = result.steps[row.index]
        if not step.note_row.pressed:
            continue
        parts: list[str] = []

        move = step.foot_row.moved
        expected = gold.get(row.index)
        if expected != move:
            margin = math.inf if step.confidence is None else step.confidence
            margin_text = "inf" if margin == math.inf else f"{margin:.1f}"
            foot_suffix = f"{_tag(move)} @margin={margin_text}"
            parts.append(foot_suffix)
            label = "DISAGREES" if expected is not None else "untagged"
            suggestions.append(
                (
                    margin,
                    row.line_number,
                    row.measure,
                    f"{label} m{row.measure} {foot_suffix}",
                )
            )

        tagged = {_TAG_ALIASES[tag] for tag in row.patterns if tag in _TAG_ALIASES}
        found = decoded.get(row.index, set())
        if found != tagged:
            pattern_tag = "@suggest_pattern=" + (",".join(_ordered(found)) or "none")
            parts.append(pattern_tag)
            was = ",".join(_ordered(tagged)) or "untagged"
            pattern_suggestions.append(
                f"  line {row.line_number:5d} m{row.measure}: {pattern_tag} (was {was})"
            )

        if parts:
            line_i = row.line_number - 1
            text = lines[line_i]
            suffix = " ".join(parts)
            lines[line_i] = f"{text} {suffix}" if "//" in text else f"{text} // {suffix}"

    with path.open("w", encoding="utf-8", newline="") as out:
        out.writelines(body + end for body, end in zip(lines, endings, strict=True))
    suggestions.sort()
    for _margin, line_number, measure, text in suggestions[:list_rows]:
        console.print(f"  line {line_number:5d} m{measure}: {text}")
    if pattern_suggestions:
        console.print("Pattern suggestions:")
        for text in pattern_suggestions[:list_rows]:
            console.print(text)
    return len(suggestions), len(pattern_suggestions)


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

    model = FootingModel.load(args.weights) if args.weights else FootingModel.default()
    feet, patterns = suggest_file(console, args.chart.resolve(), model, list_rows=args.list)
    console.print(f"Wrote {feet} foot and {patterns} pattern suggestions to {args.chart}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

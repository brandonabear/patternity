#!/usr/bin/env python3
"""Write model footing suggestions into a chart as ``@suggest=`` tags for human review.

Suggestions go on rows with no ``@foot``/``@feet`` tag and on rows where the
model disagrees with the existing tag; existing tags are never changed.
``@margin=`` is the model's confidence (cost gap to the best alternative foot);
review low margins first, then rename ``@suggest`` to ``@foot`` / ``@feet`` to
accept. Rerunning replaces previous suggestions.

Also writes 0-based ``// measure N`` markers: a ``// measure 0`` line before the
first note row, and ``// measure N`` on each comma (``N`` is the measure that
starts after that comma), matching the StepMania editor convention.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from patternity.footing import FootingModel, FootMove, resolve_chart
from patternity.simfile import read_simfile
from patternity.training.annotations import _notes_body, parse_annotated_sm

_NOTE_ROW_RE = re.compile(r"^[0-4MFL]{4}", re.IGNORECASE)
_SUGGEST_RE = re.compile(r"@suggest=\S+", re.IGNORECASE)
_MARGIN_RE = re.compile(r"@margin=\S+", re.IGNORECASE)
_MEASURE_IN_COMMENT_RE = re.compile(r"measure\s+\d+", re.IGNORECASE)
_MEASURE_LINE_RE = re.compile(r"^\s*//\s*measure\s+(\d+)\s*$", re.IGNORECASE)


def _tag(move: FootMove) -> str:
    return {
        FootMove.LEFT: "@suggest=L",
        FootMove.RIGHT: "@suggest=R",
        FootMove.BOTH: "@suggest=L,R",
    }[move]


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
    body, body_line = _notes_body(text)
    body_start = body_line - 1

    first_note_offset: int | None = None
    comma_updates: list[tuple[int, int]] = []

    for offset, raw_line in enumerate(body.splitlines()):
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
        if note_text and _NOTE_ROW_RE.match(note_text):
            if first_note_offset is None:
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




def suggest_file(path: Path, model: FootingModel, *, list_rows: int) -> int:
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

    suggestions: list[tuple[float, int, int, str]] = []
    for row in annotated.rows:
        step = result.steps[row.index]
        if not step.note_row.press_mask:
            continue
        move = step.foot_row.moved
        expected = gold.get(row.index)
        if expected == move:
            continue
        margin = math.inf if step.confidence is None else step.confidence
        margin_text = "inf" if margin == math.inf else f"{margin:.1f}"
        line_i = row.line_number - 1
        text = lines[line_i]
        suffix = f"{_tag(move)} @margin={margin_text}"
        lines[line_i] = f"{text} {suffix}" if "//" in text else f"{text} // {suffix}"
        label = "DISAGREES" if expected is not None else "untagged"
        suggestions.append(
            (margin, row.line_number, row.measure, f"{label} m{row.measure} {suffix}")
        )

    with path.open("w", encoding="utf-8", newline="") as out:
        out.writelines(body + end for body, end in zip(lines, endings, strict=True))
    suggestions.sort()
    for margin, line_number, measure, text in suggestions[:list_rows]:
        print(f"  line {line_number:5d} m{measure}: {text}")
    return len(suggestions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chart", type=Path)
    parser.add_argument("--weights", type=Path, help="weights JSON (default: packaged)")
    parser.add_argument("--list", type=int, default=25, help="lowest-margin rows to print")
    args = parser.parse_args()
    model = FootingModel.load(args.weights) if args.weights else FootingModel.default()
    count = suggest_file(args.chart.resolve(), model, list_rows=args.list)
    print(f"Wrote {count} suggestions to {args.chart}")


if __name__ == "__main__":
    main()

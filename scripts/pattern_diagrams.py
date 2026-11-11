"""Render gameplay-style SVG examples of tech patterns for ``docs/patterns.md``.

Each example is a short phrase written as ``.sm`` note rows. Rows may pin their
footing with training tags (``// @foot=L``); untagged rows are decoded with the
packaged weights. The real pattern detector then runs on that path, so a
highlighted span is exactly what patternity would count.

    uv run python scripts/pattern_diagrams.py            # writes docs/images/pattern_*.svg
"""

import argparse
import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from patternity import FootingModel, detect_tech_patterns
from patternity.footing import ResolvedStep
from patternity.footing.search import build_trellis, viterbi
from patternity.footing.stance import FootMove
from patternity.patterns.detector import column_foot
from patternity.patterns.spans import PatternKind, PatternSpan
from patternity.simfile.notes import PANELS, PRESSABLE_NOTES, NoteType, Panel
from patternity.training import parse_annotated_sm

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "images"

# Palette shared with the trellis diagrams in docs/footing-model.md.
BACKGROUND = "#1f2023"
TEXT = "#ececec"
MUTED = "#9a9a9a"
LANE = "#2a2b2f"
BEAT_LINE = "#3a3b40"
MEASURE_LINE = "#6a6b70"
RECEPTOR = "#5a5b60"
HIGHLIGHT = "#f5c542"
HOLD_BODY = "#9fb8a8"
ROLL_BODY = "#d9a441"

# Note color by quantization (StepMania "note" colors).
QUANT_COLORS: dict[int, tuple[str, str]] = {
    4: ("#ff4d4d", "4th"),
    8: ("#3b82f6", "8th"),
    12: ("#a855f7", "12th"),
    16: ("#3ddc84", "16th"),
    24: ("#ec4899", "24th"),
    32: ("#f59e0b", "32nd"),
}
OTHER_QUANT = ("#9ca3af", "finer")

ARROW = "0,-13 12,0 5,0 5,12 -5,12 -5,0 -12,0"
ROTATION = {Panel.L: 270, Panel.D: 180, Panel.U: 0, Panel.R: 90}
FOOT_LABEL = {FootMove.LEFT: "L", FootMove.RIGHT: "R"}

LANE_WIDTH = 52
PLAYFIELD_WIDTH = LANE_WIDTH * len(PANELS)
PX_PER_BEAT = 200
# Gap between the receptors and beat 0, so the first note doesn't cover its receptor.
LEAD_IN = 64
# Width of one column of span markers; overlapping spans get their own column.
SPAN_COLUMN = 150
MARGIN = 28
HEADER = 76
LEGEND = 44


@dataclass(frozen=True, slots=True)
class Example:
    """A short phrase at one tempo that demonstrates ``kind``."""

    name: str
    title: str
    kind: PatternKind
    bpm: float
    rows: tuple[str, ...]  # one measure of .sm rows, e.g. 16 rows for a 16th grid
    label: str = ""  # span marker text when it differs from ``kind`` (e.g. holdswitch)


@dataclass(frozen=True, slots=True)
class Decoded:
    example: Example
    steps: tuple[ResolvedStep, ...]
    spans: tuple[PatternSpan, ...]


EXAMPLES = (
    # Left (L) on the beat, then Right (R) on the 8th and again on the 16th.
    Example(
        name="jack",
        title="Jack",
        kind=PatternKind.JACK,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0000", "0001 // @foot=R", "0001 // @foot=R",
            "0000", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Left (L), Up (R), then a Left/Up jump (L/R) whose Left is jacked on the next 16th.
    Example(
        name="jack_from_jump",
        title="Jack out of a jump",
        kind=PatternKind.JACK,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0000", "0010 // @foot=R", "0000",
            "1010 // @feet=L,R", "1000 // @foot=L", "0000", "0000",
            "0000", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Left hold (L) anchors the left foot, so the right foot takes Down then Right.
    Example(
        name="doublestep_hold",
        title="Doublestep around a hold",
        kind=PatternKind.DOUBLESTEP,
        bpm=120,
        rows=(
            "2000 // @foot=L", "0000", "0100 // @foot=R", "0000",
            "0001 // @foot=R", "0000", "3000", "0000",
            "0000", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Left, Down, Right, Up: a mine on Down drives the right foot off it onto Right.
    Example(
        name="doublestep_mine",
        title="Doublestep cued by a mine",
        kind=PatternKind.DOUBLESTEP,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0000", "0100 // @foot=R", "0M00",
            "0001 // @foot=R", "0000", "0010 // @foot=L", "0000",
            "0000", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Left, Down, Down, Right on 12ths: a mine on Left moves the left foot onto Down.
    Example(
        name="footswitch",
        title="Footswitch",
        kind=PatternKind.FOOTSWITCH,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0100 // @foot=R", "M100 // @foot=L",
            "0001 // @foot=R", "0000", "0000",
            "0000", "0000", "0000",
            "0000", "0000", "0000",
        ),
    ),
    # The left foot releases an Up hold; a mine on Right sends the right foot onto Up.
    Example(
        name="holdswitch",
        title="Holdswitch",
        kind=PatternKind.FOOTSWITCH,
        label="holdswitch",
        bpm=120,
        rows=(
            "0020 // @foot=L", "0000", "0001 // @foot=R", "0000",
            "0030", "000M", "0010 // @foot=R", "0000",
            "1000 // @foot=L", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Left, Down, Right, Right, Left on 8ths: the left foot crosses over to Right, a mine on
    # Down cues the right foot off Down to take Right, and the left foot returns to Left.
    Example(
        name="sideswitch",
        title="Sideswitch",
        kind=PatternKind.SIDESWITCH,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=L", "0M01 // @foot=R",
            "1000 // @foot=L", "0000", "0000", "0000",
        ),
    ),
    # Left, Right, then Left+Up with the left foot alone, then Right.
    Example(
        name="bracket",
        title="Bracket",
        kind=PatternKind.BRACKET,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0001 // @foot=R", "1010 // @feet=L,L", "0001 // @foot=R",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Right, Down, Left+Up, Down, Right on 16ths: the right foot brackets across the left.
    Example(
        name="crossover_bracket",
        title="Crossover bracket",
        kind=PatternKind.BRACKET,
        bpm=150,
        rows=(
            "0001 // @foot=R", "0100 // @foot=L", "1010 // @feet=R,R", "0100 // @foot=L",
            "0001 // @foot=R", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # Left, Down, Right, Down, Left: the left foot crosses in front of the right foot on Down
    # and returns to Left.
    Example(
        name="crossover",
        title="Crossover",
        kind=PatternKind.CROSSOVER,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=L", "0100 // @foot=R",
            "1000 // @foot=L", "0000", "0000", "0000",
        ),
    ),
    # Left, Up, Right, Up, Left: the left foot crosses behind the right foot on Up and
    # returns to Left.
    Example(
        name="crossunder",
        title="Crossunder",
        kind=PatternKind.CROSSOVER,
        label="crossunder",
        bpm=120,
        rows=(
            "1000 // @foot=L", "0010 // @foot=R", "0001 // @foot=L", "0010 // @foot=R",
            "1000 // @foot=L", "0000", "0000", "0000",
        ),
    ),
    # Left, Down, Right, Left, Up, Right lateral: the player spins through facing backward
    # (right foot on Left, left foot on Right) and back to facing forward.
    Example(
        name="inverted_crossover",
        title="Inverted crossover",
        kind=PatternKind.INVERTED_CROSSOVER,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=L", "1000 // @foot=R",
            "0010 // @foot=L", "0001 // @foot=R", "0000", "0000",
        ),
    ),
    # Left, Down, Left, Up, Down, Right, Up, Down, Left on 16ths, alternating feet: the right
    # foot goes Down to Up, and later the left foot goes Down to Up.
    Example(
        name="candle_run",
        title="Candles in a 16th run",
        kind=PatternKind.CANDLE,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0100 // @foot=R", "1000 // @foot=L", "0010 // @foot=R",
            "0100 // @foot=L", "0001 // @foot=R", "0010 // @foot=L", "0100 // @foot=R",
            "1000 // @foot=L", "0000", "0000", "0000",
            "0000", "0000", "0000", "0000",
        ),
    ),
    # The 5-arrow crossover: the crossing left foot moves Left to Right and back.
    Example(
        name="candle_crossover",
        title="Candles in a crossover",
        kind=PatternKind.CANDLE,
        bpm=120,
        rows=(
            "1000 // @foot=L", "0100 // @foot=R", "0001 // @foot=L", "0100 // @foot=R",
            "1000 // @foot=L", "0000", "0000", "0000",
        ),
    ),
)  # fmt: skip


def decode(example: Example) -> Decoded:
    """Footing (tags first, model otherwise) and detected spans of the example's kind."""
    annotated = parse_annotated_sm(_chart_text(example))
    trellis = build_trellis(annotated.chart.notes)
    path = viterbi(trellis, FootingModel.default().vector(), allowed=annotated.tagged_assignments)
    steps = tuple(
        ResolvedStep(index=i, note_row=row, foot_row=state)
        for i, (row, state) in enumerate(zip(trellis.rows, path.states(trellis), strict=True))
    )
    spans = tuple(s for s in detect_tech_patterns(steps).spans if s.kind == example.kind)
    if not spans:
        raise ValueError(f"{example.name}: no {example.kind.value} detected in the phrase")
    return Decoded(example=example, steps=steps, spans=spans)


def _chart_text(example: Example) -> str:
    body = "\n".join(example.rows)
    return (
        f"#TITLE:example;\n#BPMS:0.000={example.bpm};\n#STOPS:;\n#NOTES:\n"
        "     dance-single:\n     example:\n     Challenge:\n     1:\n"
        f"     0,0,0,0,0:\n{body}\n;\n"
    )


def quantization(beat: float) -> int:
    """Smallest note division that places ``beat`` on its grid (4 = quarter notes)."""
    denominator = Fraction(beat).limit_denominator(48).denominator
    return 4 * denominator


def render(example: Example) -> str:
    """The full SVG document for one example."""
    decoded = decode(example)
    pressed = [s for s in decoded.steps if _pressed(s)]
    # Whole beats through the last row (tails and mines included), plus one of headroom.
    beats = math.floor(_beat(decoded.steps[-1])) + 1
    columns = max(_span_columns(decoded.spans)) + 1
    width = 2 * MARGIN + PLAYFIELD_WIDTH + columns * SPAN_COLUMN
    height = HEADER + LEAD_IN + beats * PX_PER_BEAT + LANE_WIDTH + LEGEND + MARGIN
    quants = sorted({quantization(_beat(s)) for s in pressed})

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" '
        'font-family="-apple-system, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="14">',
        f"<title>{example.title} example</title>",
        f"<desc>{_description(decoded)}</desc>",
        "<style>.title{font-size:20px;font-weight:700} .cap{font-weight:600} "
        ".lbl{font-size:12px} .foot{font-size:17px;font-weight:700;fill:#fff;"
        "stroke:#000;stroke-width:0.6;paint-order:stroke}</style>",
        f'<rect width="{width}" height="{height}" fill="{BACKGROUND}"/>',
        f'<text x="{MARGIN}" y="{MARGIN + 10}" class="title" fill="{TEXT}">{example.title}</text>',
        f'<text x="{MARGIN}" y="{MARGIN + 30}" class="lbl" fill="{MUTED}">'
        f"{example.bpm:g} BPM</text>",
    ]
    parts.extend(_playfield(decoded, MARGIN, HEADER + LANE_WIDTH / 2, beats))
    parts.extend(_legend(quants, MARGIN, height - MARGIN))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _playfield(d: Decoded, x: float, top: float, beats: int) -> list[str]:
    """Lanes, receptors, notes, and span markers; ``top`` is the receptor row center."""
    receptors = top
    top += LEAD_IN  # beat 0
    bottom = top + beats * PX_PER_BEAT + LANE_WIDTH / 2
    parts = [
        f'<rect x="{x}" y="{receptors - LANE_WIDTH / 2}" width="{PLAYFIELD_WIDTH}" '
        f'height="{bottom - receptors + LANE_WIDTH / 2}" rx="6" fill="{LANE}"/>',
    ]
    for beat in range(beats + 1):
        line_y = top + beat * PX_PER_BEAT
        is_measure = beat % 4 == 0
        parts.append(
            f'<line x1="{x}" y1="{line_y}" x2="{x + PLAYFIELD_WIDTH}" y2="{line_y}" '
            f'stroke="{MEASURE_LINE if is_measure else BEAT_LINE}" '
            f'stroke-width="{2 if is_measure else 1}"/>'
        )
    for column, panel in enumerate(PANELS):
        parts.append(_arrow(_lane_x(x, column), receptors, panel, fill="none", stroke=RECEPTOR))
    label = d.example.label or d.example.kind.value.replace("_", " ")
    for span, column in zip(d.spans, _span_columns(d.spans), strict=True):
        parts.extend(
            _span_marker(span, x + PLAYFIELD_WIDTH + 10 + column * SPAN_COLUMN, top, label)
        )
    parts.extend(_hold_bodies(d.steps, x, top))
    for step in d.steps:
        parts.extend(_notes(step, x, top))
    return parts


def _hold_bodies(steps: Sequence[ResolvedStep], x: float, top: float) -> list[str]:
    """A body from each hold/roll head down to its tail, drawn beneath the heads."""
    parts = []
    open_heads: dict[Panel, tuple[float, NoteType]] = {}
    for step in steps:
        for column, (panel, note) in enumerate(zip(PANELS, step.note_row.notes, strict=True)):
            if note in (NoteType.HOLD, NoteType.ROLL):
                open_heads[panel] = (_beat(step), note)
            elif note == NoteType.TAIL and panel in open_heads:
                head_beat, kind = open_heads.pop(panel)
                width = LANE_WIDTH * 0.5
                y1 = top + head_beat * PX_PER_BEAT
                y2 = top + _beat(step) * PX_PER_BEAT
                parts.append(
                    f'<rect x="{_lane_x(x, column) - width / 2}" y="{y1}" width="{width}" '
                    f'height="{y2 - y1 + width / 2}" rx="{width / 2}" '
                    f'fill="{HOLD_BODY if kind == NoteType.HOLD else ROLL_BODY}" '
                    'stroke="#000" stroke-width="1.2"/>'
                )
    return parts


def _notes(step: ResolvedStep, x: float, top: float) -> list[str]:
    beat = _beat(step)
    row_y = top + beat * PX_PER_BEAT
    color, _ = QUANT_COLORS.get(quantization(beat), OTHER_QUANT)
    parts = []
    for column, (panel, note) in enumerate(zip(PANELS, step.note_row.notes, strict=True)):
        cx = _lane_x(x, column)
        if note == NoteType.MINE:
            parts.append(_mine(cx, row_y))
        elif note in PRESSABLE_NOTES:
            parts.append(_arrow(cx, row_y, panel, fill=color, stroke="#000"))
            foot = column_foot(step, panel)
            if foot in FOOT_LABEL:
                parts.append(
                    f'<text x="{cx}" y="{row_y + 6}" text-anchor="middle" class="foot">'
                    f"{FOOT_LABEL[foot]}</text>"
                )
    return parts


def _span_columns(spans: Sequence[PatternSpan]) -> list[int]:
    """Marker column per span: the first column whose spans it doesn't overlap.

    Spans that only share an endpoint row may share a column.
    """
    column_ends: list[float] = []
    columns = []
    for span in spans:
        column = next(
            (i for i, end in enumerate(column_ends) if span.start_beat >= end),
            len(column_ends),
        )
        if column == len(column_ends):
            column_ends.append(span.end_beat)
        else:
            column_ends[column] = span.end_beat
        columns.append(column)
    return columns


def _span_marker(span: PatternSpan, x: float, top: float, label: str) -> list[str]:
    """A bracket beside the playfield joining the span's first and last rows.

    A single-row span (e.g. a bracket) gets a short bracket around its row and no time.
    """
    y1 = top + _beat(span.steps[0]) * PX_PER_BEAT
    y2 = top + _beat(span.steps[-1]) * PX_PER_BEAT
    middle = (y1 + y2) / 2
    parts = []
    if y1 == y2:
        half = LANE_WIDTH / 2 - 4
        parts.append(
            f'<path d="M{x},{y1 - half} h8 V{y1 + half} h-8" fill="none" '
            f'stroke="{HIGHLIGHT}" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + 14}" y="{middle + 5}" class="cap" fill="{HIGHLIGHT}">{label}</text>'
        )
        return parts
    gap = span.steps[-1].note_row.timestamp - span.steps[0].note_row.timestamp
    return [
        f'<path d="M{x},{y1} h8 V{y2} h-8" fill="none" stroke="{HIGHLIGHT}" stroke-width="2"/>',
        f'<text x="{x + 14}" y="{middle - 2}" class="cap" fill="{HIGHLIGHT}">{label}</text>',
        f'<text x="{x + 14}" y="{middle + 14}" class="lbl" fill="{MUTED}">{gap:.3f} s</text>',
    ]


def _legend(quants: Sequence[int], x: float, y: float) -> list[str]:
    parts = []
    for quant in quants:
        color, label = QUANT_COLORS.get(quant, OTHER_QUANT)
        parts.append(
            f'<g transform="translate({x + 8} {y - 4}) scale(0.6)">'
            f'<polygon points="{ARROW}" fill="{color}" stroke="#000" stroke-width="2" '
            'stroke-linejoin="round"/></g>'
        )
        parts.append(f'<text x="{x + 20}" y="{y}" class="lbl" fill="{TEXT}">{label} note</text>')
        x += 90
    return parts


def _arrow(cx: float, cy: float, panel: Panel, fill: str, stroke: str) -> str:
    return (
        f'<g transform="translate({cx} {cy}) rotate({ROTATION[panel]}) scale(1.6)">'
        f'<polygon points="{ARROW}" fill="{fill}" stroke="{stroke}" stroke-width="1.2" '
        'stroke-linejoin="round"/></g>'
    )


def _mine(cx: float, cy: float) -> str:
    spokes = "".join(
        f'<rect x="{cx - 1.6}" y="{cy - 22}" width="3.2" height="17" fill="#111" '
        f'transform="rotate({angle} {cx} {cy})"/>'
        for angle in (0, 120, 240)
    )
    return (
        f'<circle cx="{cx}" cy="{cy}" r="15" fill="#fff" stroke="#111" stroke-width="2"/>'
        f'<circle cx="{cx}" cy="{cy}" r="9.5" fill="#e5252a"/>{spokes}'
    )


def _description(d: Decoded) -> str:
    notes = ", ".join(
        "+".join(p.name for p in PANELS if p in s.note_row.pressed)
        + f" ({quantization(_beat(s))}th, "
        + "/".join(FOOT_LABEL[f] for p in PANELS if (f := column_foot(s, p)) in FOOT_LABEL)
        + ")"
        for s in d.steps
        if _pressed(s)
    )
    return (
        f"{d.example.title} at {d.example.bpm:g} BPM: {notes}; "
        f"{len(d.spans)} {d.example.kind.value} detected."
    )


def _lane_x(x: float, column: int) -> float:
    return x + LANE_WIDTH * (column + 0.5)


def _beat(step: ResolvedStep) -> float:
    return step.note_row.beat


def _pressed(step: ResolvedStep) -> bool:
    return bool(step.note_row.pressed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    for example in EXAMPLES:
        path = args.out / f"pattern_{example.name}.svg"
        path.write_text(render(example))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()

"""Shared builders for unit tests: chart text, gold-annotated paths, synthetic paths."""

from patternity.footing import ResolvedStep
from patternity.footing.features import FEATURE_NAMES
from patternity.footing.search import build_trellis, viterbi
from patternity.footing.stance import FootMove, FootPlacement, FootRow, Stance
from patternity.simfile import NoteRow
from patternity.training import parse_annotated_sm


def chart_text(rows: list[str], bpm: float = 120.0) -> str:
    """A minimal single-chart ``.sm`` with constant ``bpm`` and the given note rows.

    Rows may carry ``// @foot=...`` style annotations; end the list with ``","``.
    """
    body = "\n".join(rows)
    return (
        f"#TITLE:t;\n#BPMS:0.000={bpm};\n#STOPS:;\n#NOTES:\n"
        "     dance-single:\n     t:\n     Challenge:\n     1:\n"
        f"     0,0,0,0,0:\n{body}\n;\n"
    )


def chart_rows(rows: list[str], bpm: float = 120.0) -> list[NoteRow]:
    """Parsed ``NoteRow``s of ``chart_text(rows, bpm)``."""
    return parse_annotated_sm(chart_text(rows, bpm)).chart.notes


def gold_steps(rows: list[str], bpm: float = 120.0) -> list[ResolvedStep]:
    """The path that satisfies every ``@foot`` / ``@feet`` tag, decoded with zero weights."""
    annotated = parse_annotated_sm(chart_text(rows, bpm))
    trellis = build_trellis(annotated.chart.notes)
    decoded = viterbi(
        trellis, [0.0] * len(FEATURE_NAMES), allowed=annotated.tagged_assignments
    )
    return [
        ResolvedStep(index=i, note_row=row, foot_row=state)
        for i, (row, state) in enumerate(
            zip(annotated.chart.notes, decoded.states(trellis), strict=True)
        )
    ]


def synthetic_steps(moves: list[tuple[str, str, str]]) -> list[ResolvedStep]:
    """A hand-built path, bypassing the decoder.

    Each move is ``(foot, left_panel, right_panel)``: the stance after the row,
    where ``foot`` ("L" or "R") moved and presses its panel. Rows are 8ths at
    120 BPM (0.25 s apart).
    """
    steps = []
    for i, (foot, left, right) in enumerate(moves):
        moved = FootMove.LEFT if foot == "L" else FootMove.RIGHT
        panel = FootPlacement(left if foot == "L" else right)
        row = "".join("1" if panel.mask >> col & 1 else "0" for col in range(4))
        steps.append(
            ResolvedStep(
                index=i,
                note_row=NoteRow.from_str(row, beat=i * 0.5, timestamp=i * 0.25),
                foot_row=FootRow(
                    stance=Stance.from_feet(FootPlacement(left), FootPlacement(right)),
                    moved=moved,
                ),
            )
        )
    return steps

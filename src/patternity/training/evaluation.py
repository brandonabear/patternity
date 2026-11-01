"""Score decoded footing and tech labels against annotated fixtures.

Reports per-row foot accuracy, per-pattern precision/recall against
``@pattern`` tags, rows whose annotation is physically impossible, and every
disagreement sorted by model confidence (least confident first).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from patternity.footing.model import FootingModel
from patternity.footing.resolve import resolve_chart
from patternity.footing.search import Trellis, build_trellis, viterbi
from patternity.footing.stance import FootMove
from patternity.patterns.detector import detect_tech_patterns
from patternity.patterns.spans import PatternKind
from patternity.simfile.reader import read_simfile
from patternity.training.annotations import AnnotatedChart, parse_annotated_sm

PATTERN_TAGS: dict[str, PatternKind] = {
    "jack": PatternKind.JACK,
    "footswitch": PatternKind.FOOTSWITCH,
    "holdswitch": PatternKind.FOOTSWITCH,
    "sideswitch": PatternKind.SIDESWITCH,
    "doublestep": PatternKind.DOUBLESTEP,
    "bracket": PatternKind.BRACKET,
    "candle": PatternKind.CANDLE,
}
SCORED_KINDS: tuple[PatternKind, ...] = tuple(dict.fromkeys(PATTERN_TAGS.values()))


@dataclass(frozen=True)
class Disagreement:
    index: int
    line_number: int
    beat: float
    expected: FootMove
    actual: FootMove
    confidence: float | None


@dataclass
class PatternScore:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    false_positive_rows: list[int] = field(default_factory=list)
    false_negative_rows: list[int] = field(default_factory=list)

    @property
    def precision(self) -> float:
        found = self.true_positives + self.false_positives
        return self.true_positives / found if found else 1.0

    @property
    def recall(self) -> float:
        wanted = self.true_positives + self.false_negatives
        return self.true_positives / wanted if wanted else 1.0


@dataclass
class FixtureReport:
    name: str
    rows: int
    disagreements: list[Disagreement]
    patterns: dict[PatternKind, PatternScore]
    impossible_annotations: list[int]

    @property
    def errors(self) -> int:
        return len(self.disagreements)

    @property
    def accuracy(self) -> float:
        return 1.0 - self.errors / self.rows if self.rows else 1.0


def score_patterns(
    annotated: AnnotatedChart, detected: dict[PatternKind, set[int]]
) -> dict[PatternKind, PatternScore]:
    """Compare detected pattern anchor rows (last step of each span) to tags.

    Only rows carrying @foot/@feet tags are scored, so a partially annotated
    chart is not penalized for labels in its unannotated stretches.
    """
    footed = set(annotated.tagged_assignments)
    tagged: dict[PatternKind, set[int]] = {kind: set() for kind in SCORED_KINDS}
    for row in annotated.rows:
        for tag in row.patterns:
            kind = PATTERN_TAGS.get(tag)
            if kind is not None:
                tagged[kind].add(row.index)
    scores: dict[PatternKind, PatternScore] = {}
    for kind in SCORED_KINDS:
        want = tagged[kind]
        got = detected.get(kind, set()) & footed
        scores[kind] = PatternScore(
            true_positives=len(want & got),
            false_positives=len(got - want),
            false_negatives=len(want - got),
            false_positive_rows=sorted(got - want),
            false_negative_rows=sorted(want - got),
        )
    return scores


def evaluate_annotated(
    name: str,
    annotated: AnnotatedChart,
    model: FootingModel | None = None,
    *,
    trellis: Trellis | None = None,
) -> FixtureReport:
    model = model or FootingModel.default()
    trellis = trellis or build_trellis(annotated.chart.notes)
    result = resolve_chart(annotated.chart.notes, model, trellis=trellis)
    gold = annotated.tagged_assignments

    disagreements = []
    for index, expected in gold.items():
        step = result.steps[index]
        if step.foot_row.moved == expected:
            continue
        row = annotated.rows[index]
        disagreements.append(
            Disagreement(
                index=index,
                line_number=row.line_number,
                beat=row.beat,
                expected=expected,
                actual=step.foot_row.moved,
                confidence=step.confidence,
            )
        )
    disagreements.sort(
        key=lambda d: math.inf if d.confidence is None else d.confidence
    )

    detected: dict[PatternKind, set[int]] = {}
    for span in detect_tech_patterns(result.steps).spans:
        detected.setdefault(span.kind, set()).add(span.steps[-1].index)

    impossible = list(viterbi(trellis, model.vector(), allowed=gold).relaxed_rows)
    return FixtureReport(
        name=name,
        rows=len(gold),
        disagreements=disagreements,
        patterns=score_patterns(annotated, detected),
        impossible_annotations=impossible,
    )


def evaluate_fixture(path: Path, model: FootingModel | None = None) -> FixtureReport:
    return evaluate_annotated(path.name, parse_annotated_sm(read_simfile(path)), model)


def format_report(report: FixtureReport, annotated: AnnotatedChart, *, show: int = 20) -> str:
    lines = [
        (
            f"{report.name}: {report.accuracy:.2%} per-row "
            f"({report.errors} disagreements / {report.rows} annotated rows)"
        )
    ]
    for index in report.impossible_annotations:
        row = annotated.rows[index]
        lines.append(f"  IMPOSSIBLE annotation: line {row.line_number} beat {row.beat}")
    for kind, score in report.patterns.items():
        if not (score.true_positives or score.false_positives or score.false_negatives):
            continue
        detail = ""
        if score.false_positive_rows:
            detail += " FP lines " + ",".join(
                str(annotated.rows[i].line_number) for i in score.false_positive_rows
            )
        if score.false_negative_rows:
            detail += " FN lines " + ",".join(
                str(annotated.rows[i].line_number) for i in score.false_negative_rows
            )
        lines.append(
            f"  {kind.value:12s} P={score.precision:6.1%} R={score.recall:6.1%} "
            f"(tp={score.true_positives} fp={score.false_positives} "
            f"fn={score.false_negatives}){detail}"
        )
    for d in report.disagreements[:show]:
        conf = "n/a" if d.confidence is None else f"{d.confidence:.2f}"
        lines.append(
            f"  line {d.line_number:5d} beat {d.beat:8.3f}: annotated "
            f"{d.expected.name:5s} model {d.actual.name:5s} (margin {conf})"
        )
    return "\n".join(lines)

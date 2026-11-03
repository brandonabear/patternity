# Debugging

Most surprises fall into one of three buckets. Work out which one first, because the fixes are different:

| Symptom | Likely cause | Fix in |
|---------|--------------|--------|
| The footing is right, but a pattern is counted (or not) wrongly | Labeling rule | `patterns/detector.py` |
| A passage is footed in a way a player wouldn't | Weights or missing training data | Annotate and retrain ([Training workflow](training.md)) |
| A passage is footed oddly even though the annotation says otherwise, and the trainer can't fix it | Missing feature or hard rule | `footing/features.py` or `footing/transitions.py` |
| Counts are wildly off everywhere (hundreds of jacks, all timestamps 0) | Parsing | `simfile/parser.py` |

## Look at the footing

Print the decoded path around a measure. `step.confidence` is the margin to the best alternative foot on that row (low = the model nearly chose the other foot).

```python
from pathlib import Path

from patternity import StepmaniaFileParser, detect_tech_patterns, read_simfile, resolve_chart

song = StepmaniaFileParser.parse(read_simfile(Path("tests/fixtures/charts/fots.sm")))
chart = song.charts[0]
result = resolve_chart(chart.notes)
labels = {}
for span in detect_tech_patterns(result.steps).spans:
    labels.setdefault(span.steps[-1].index, []).append(span.kind.value)

for step in result.steps:
    row = step.note_row
    if row.measure in (168, 169) and row.press_mask:
        cols = "".join("LDUR"[c] if row.press_mask >> c & 1 else "." for c in range(4))
        fr = step.foot_row
        print(f"m{row.measure} beat {row.beat:7.2f} {cols} {fr.moved.name:5} "
              f"L={fr.stance.left} R={fr.stance.right} "
              f"margin={step.confidence} {labels.get(step.index, '')}")
```

If the footing printed here is what a player would do, the problem is in labeling (`patterns/detector.py`). If not, it is a footing problem.

### Using the suggestion script as a viewer

For a chart with no footing tags yet, `scripts/suggest_annotations.py` writes `@suggest_foot` / `@suggest_feet` and `@margin` on every press row, plus `@suggest_pattern` wherever the decoder finds a pattern; on a partially tagged chart it only adds rows that are untagged or where the model disagrees with your `@foot` / `@feet` / `@pattern`. That is often the fastest way to read footing and detected patterns in an editor. It edits the file in place, so run it on a copy or revert the file afterwards if you don't intend to keep the suggestions. See [Training workflow → Bootstrapping a new chart](training.md#bootstrapping-a-new-chart).

## Compare the model with annotations

```bash
uv run python scripts/evaluate.py charts/my_chart.ssc --show 50
```

For each fixture this prints:

- **Per-row accuracy**: rows where the model's foot differs from `@foot` / `@feet`, sorted by margin. A disagreement with a large margin means the model is confidently wrong (or the tag is wrong); a small margin means a near tie.
- **Pattern precision/recall** against `@pattern` tags, with false-positive and false-negative line numbers. Only rows that carry `@foot` / `@feet` are scored, so unannotated stretches don't count against it.
- **Impossible annotations**: tags no legal path can satisfy. Fix the tag first; these are excluded from training.

## Why does the model prefer its footing?

When the model consistently picks a different footing than the annotation, compare the features of the two paths. The difference shows which costs decide it.

```python
from pathlib import Path

from patternity import FootingModel, read_simfile
from patternity.footing.features import FEATURE_NAMES
from patternity.footing.search import build_trellis, path_features, viterbi
from patternity.training import parse_annotated_sm

annotated = parse_annotated_sm(read_simfile(Path("tests/fixtures/charts/my_chart.ssc")))
trellis = build_trellis(annotated.chart.notes)
weights = FootingModel.default().vector()

predicted = viterbi(trellis, weights)
gold = viterbi(trellis, weights, allowed=annotated.tagged_assignments)
print("cost: predicted", predicted.cost, "annotated", gold.cost)

diff = [g - p for g, p in zip(path_features(trellis, gold), path_features(trellis, predicted))]
for name, d, w in zip(FEATURE_NAMES, diff, weights):
    if abs(d) > 1e-9:
        print(f"{name:24} annotated-predicted {d:+7.2f}  x weight {w:+7.1f} = {d * w:+8.1f}")
```

Positive contributions are what make the annotated footing more expensive. Use this to decide between:

- **More data**: the features *can* tell the passages apart, but the corpus doesn't show the model which way to lean. Annotate more passages like this one.
- **A new feature**: the two footings have the same features in every way that matters (often the difference list is short and balanced), so no weights could separate them. See [Footing model → Adding a feature](footing-model.md#adding-a-feature).

To focus on one passage, restrict `allowed` to the rows outside it, so only that passage is free to differ:

```python
rows = {r.index for r in annotated.rows if 540 <= r.line_number <= 560}
outside = {i: m for i, m in annotated.tagged_assignments.items() if i not in rows}
free_here = viterbi(trellis, weights, allowed=outside)
```

## The trainer did not converge

Symptoms: training-set fit shows errors, or `footing_weights.json` says `"trainer": "averaged-structured-perceptron"`.

1. Run `scripts/evaluate.py` and note which charts and lines disagree.
2. Look for annotations that contradict each other: two passages that look the same to the model but are tagged differently. Common causes are a mistyped tag, or a passage that really is ambiguous (consider leaving it untagged).
3. If both annotations are right, use the feature comparison above. If the passages produce the same features, the model needs a feature that distinguishes them.

## Relaxed rows

`foot_path_feasible: False` (or `relaxed_rows` on a `FootingResult`) means some row had no legal state and was forced with a 1000-point penalty. Causes:

- a chart that is unplayable under the hard rules (for example a press with mines on every reachable panel), or
- during evaluation, an annotation that no legal path can satisfy (reported as an impossible annotation).

Check the row's notes and the hold/roll state around it. If the chart is fine and the rule is too strict, the fix is in `footing/transitions.py`.

## Parsing problems

If counts are absurd across a whole chart, check the parsed timing first:

```python
for row in chart.notes[:20]:
    print(row.measure, row.beat, row.timestamp, row)
```

All-zero or `None` timestamps mean the `#BPMS` tag was not parsed. (A past bug: `#BPMS` values split across several lines were dropped.) Also check that `chart.metadata.difficulty` is the chart you expect; the CLI analyzes every chart in file order.

## Running the checks

```bash
uv run pytest -q                       # all tests
uv run pytest -q tests/integration     # regression layers only
uv run ruff check src tests scripts
uv run mypy
```

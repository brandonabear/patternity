# Development guide

How to make common changes to Patternity and debug surprising output. For how the pieces fit together and the rules the codebase follows, see [Architecture](architecture.md).

## Running the checks

Run all of these before finishing a change:

```bash
uv run pytest -q                       # all tests
uv run pytest -q tests/integration     # regression layers only
uv run ruff check src tests scripts    # lint
uv run ty check                        # type check
```

## Where to change what

| You want to… | Change |
|--------------|--------|
| Fix how a pattern is *counted* (cutoffs, pairing rules) | `patterns/detector.py` |
| Fix how a passage is *footed* | Annotate it and retrain ([Training workflow](training.md)). |
| Fix footing that stays wrong after annotating and retraining | `footing/features.py` ([Adding a feature](#adding-a-feature)) or `footing/rules.py` |
| Allow or forbid a physical move outright | `footing/rules.py` (hard rules) |
| Change what basic metrics count | `analysis/metrics.py` (`BasicMetrics.add_note`) |
| Change movement counts (direction shifts) | `movement/detector.py` |
| Support a new simfile tag | `simfile/parser.py`, `simfile/song.py` |
| Fix a missing chart, or counts that are off across a whole chart | `simfile/parser.py` ([Parsing problems](#parsing-problems)) |

## Adding a feature

Add a feature only when the existing features can't produce the expected footing (see [Why does the model prefer its footing?](#why-does-the-model-prefer-its-footing)); otherwise annotate more passages and retrain.

1. Add a member to `Feature` in `footing/features.py` with a one-line comment. Describe what the feet do, not a pattern name, and avoid tech-pattern timing cutoffs.
2. Set it in the matching group helper that `featurize` calls (`_hold_release_features`, `_repetition_features`, `_mine_cue_features`, `_movement_features`, or `_stance_features`). If none fits, add a new helper and call it from `featurize`.
3. Add a unit test that checks the feature fires on a minimal passage.
4. Retrain ([Training workflow](training.md#3-retrain)). Weights are keyed by name, so older weight files load with the new feature at `0.0`.

## Debugging

Start by looking at the footing. Whether it is right decides which row of the [table above](#where-to-change-what) applies.

### Look at the footing

Print the decoded path around a measure. `confidence` is the cost margin to the best path that moves a different foot on that row; a low value means a near tie.

```python
from pathlib import Path

from patternity import StepmaniaFileParser, detect_tech_patterns, read_simfile, resolve_chart
from patternity.simfile import PANELS

song = StepmaniaFileParser.parse(read_simfile(Path("tests/fixtures/charts/fots.sm")))
result = resolve_chart(song.charts[0].notes)
labels = {}
for span in detect_tech_patterns(result.steps).spans:
    labels.setdefault(span.steps[-1].index, []).append(span.kind.value)

for step in result.steps:
    row = step.note_row
    if row.measure in (168, 169) and row.pressed:
        cols = "".join(p.name if p in row.pressed else "." for p in PANELS)
        fr = step.foot_row
        print(f"m{row.measure} beat {row.beat:7.2f} {cols} {fr.moved.name:5} "
              f"L={fr.stance.left} R={fr.stance.right} "
              f"margin={step.confidence} {labels.get(step.index, '')}")
```

If this footing is what a player would do, the problem is in labeling. If not, it is a footing problem.

To read footing in an editor instead, run `scripts/suggest_annotations.py` on a copy of the chart: it writes the model's foot, margin and detected patterns as comments on each row. It edits the file in place. See [Training workflow](training.md#using-suggestions).

### Compare the model with annotations

```bash
uv run python scripts/evaluate.py charts/my_chart.ssc --show 50
```

For each fixture this prints:

- **Accuracy**, and the rows where the model's foot differs from `@foot` / `@feet`. A large margin means the model is confidently wrong, or the tag is.
- **Pattern precision and recall** against `@pattern` tags, with the line numbers of false positives and false negatives. Only rows with a foot tag are scored.
- **Impossible annotations**: tags no legal path can satisfy. Fix these first; training refuses to load a chart that has one.

### Why does the model prefer its footing?

Compare the features of the model's path with the annotated path. The difference shows which costs decide it.

```python
from pathlib import Path

from patternity import FootingModel, read_simfile
from patternity.footing.features import FEATURE_NAMES
from patternity.footing.search import build_trellis, path_features, viterbi
from patternity.training import parse_annotated_sm

annotated = parse_annotated_sm(read_simfile(Path("tests/fixtures/charts/hoot.ssc")))
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

Positive lines are what make the annotated footing more expensive.

- If the features differ, the model can tell the two footings apart but leans the wrong way. Annotate more passages like this one.
- If the difference is empty or cancels out, no weights can separate them. [Add a feature](#adding-a-feature).

To isolate one passage, constrain every tagged row outside it:

```python
rows = {r.index for r in annotated.rows if 540 <= r.line_number <= 560}
outside = {i: m for i, m in annotated.tagged_assignments.items() if i not in rows}
free_here = viterbi(trellis, weights, allowed=outside)
```

### The trainer did not converge

Symptoms: the training-set fit shows errors, or `footing_weights.json` says `"trainer": "averaged-structured-perceptron"`.

1. Run `scripts/evaluate.py` and note which charts and lines disagree.
2. Look for two passages that are the same shape but tagged differently. Usually one tag is mistyped, or the passage is ambiguous and should be left untagged.
3. If both tags are right, run the feature comparison above on each. If the features match, the model needs a new feature.

### Relaxed rows

`foot_path_feasible: False` in the output, or a non-empty `relaxed_rows` on a `FootingResult`, means some row had no legal move and was forced through at a penalty (`RELAXED_PENALTY` in `footing/search.py`). The usual cause is a press with mines on every reachable panel.

If the chart is playable, a rule is too strict. Each rule in `RULES` in `footing/rules.py` is a small named function; find the one rejecting every candidate on that row.

### Parsing problems

- **A chart is missing.** Charts the parser can't model (doubles, unknown difficulties, unsupported note characters) are left out of `song.charts` and listed in `song.skipped_charts` with a reason. The CLI prints them.
- **Wrong chart.** `song.charts` is in file order; check `chart.metadata.difficulty`.
- **Counts are off across a whole chart.** Check beats and timestamps against the file:

  ```python
  for row in chart.notes[:20]:
      print(row.measure, row.beat, row.timestamp, "".join(n.value for n in row.notes))
  ```

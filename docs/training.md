# Training workflow

The footing weights are learned from charts you annotate: annotate, add the chart to the corpus, retrain, check.

## 1. Annotate

Annotations are `//` comments on note rows in a chart under `tests/fixtures/` (`patterns/` for short pattern examples, `charts/` for real charts).

```text
// measure 0
1000 // @foot=L
0100 // @foot=R
M100 // @foot=L @pattern=footswitch
0001 // @foot=R
1000 // @foot=L
0011 // @feet=R,R @pattern=bracket
1000 // @foot=L
1001 // @feet=L,R @pattern=jump
,  // measure 1
```

| Tag | Meaning |
|-----|---------|
| `@foot=L` / `@foot=R` | Which foot presses this row. |
| `@feet=L,R` | Two panels pressed by different feet (a jump). |
| `@feet=L,L` / `@feet=R,R` | Both panels pressed by one foot (a bracket). |
| `@pattern=name` | The tech pattern that ends on this row: `jack`, `footswitch`, `holdswitch` (scored as a footswitch), `sideswitch`, `doublestep`, `bracket`, `candle`. Comma-separate several. `crossover` and `jump` are accepted but not scored. Patterns are scored, never trained on. |
| `@section=name` | Names the rows that follow. Informational. |
| `@suggest_foot`, `@suggest_feet`, `@suggest_pattern`, `@margin` | Written by the suggestion script. Ignored until you drop the `suggest_` prefix. |

- **Partial annotation is fine.** Untagged rows are left to the model. Leave ambiguous rows untagged; a guess teaches the model noise.
- **Only the first chart in a file is read.**
- **Tags are checked.** A malformed tag, an unknown pattern name, or a physically impossible tag (for example `@foot=R` while the right foot holds another panel) stops the chart from loading, with the line number.
- **Measure comments** (`// measure 0`, `,  // measure 1`) are 0-based, as in the StepMania editor, and are for readers only.
- **Never put** `;` **in a comment** inside note data. StepMania treats it as the end of the section.

A good training chart has passages where a reasonable alternative footing exists and you can say why yours is right. A few different charts teach more than one long one. Start with passages where the analyzer's counts look wrong ([Debugging](development.md#debugging)).

### Using suggestions

To annotate a long chart faster, let the model propose footing and review it. The script edits the file in place.

```bash
uv run python scripts/suggest_annotations.py tests/fixtures/charts/my_chart.ssc
```

It writes `@suggest_foot` or `@suggest_feet` with a `@margin` on every untagged press row and on rows where the model disagrees with your tag, and `@suggest_pattern` where the detected patterns differ from your `@pattern` tag (`none` means it found nothing on a row you tagged). It never changes your tags, and a rerun replaces its earlier suggestions.

1. **Review low margins first.** Those are the rows the model is unsure of, so your answer teaches it the most.
2. **Accept** a suggestion by dropping the `suggest_` prefix; accept `@suggest_pattern=none` by deleting the row's `@pattern` tag. Delete suggestions you don't want.
3. **Check the** `@pattern` **tags.** Suggested patterns only reflect what the detector already finds. Fix them wherever a player would read the pattern differently.
4. **Evaluate.** The chart doesn't need to be in the corpus yet:
   ```bash
     uv run python scripts/evaluate.py charts/my_chart.ssc --show 50
   ```

Never bulk-accept suggestions you haven't reviewed: the model can't be its own ground truth.

## 2. Add the chart to the corpus

Add its path, relative to `tests/fixtures/`, to [`training_corpus.txt`](../tests/fixtures/training_corpus.txt). `#` starts a comment. Charts not listed can still be evaluated, but don't influence the weights.

To measure generalization, list the chart in [`holdout_corpus.txt`](../tests/fixtures/holdout_corpus.txt) instead. Hold-out charts are never trained on. Once you tune features or annotations to improve a hold-out, it is no longer unseen: move it to the training corpus. A hold-out with only a few annotated rows says little.

## 3. Retrain

```bash
uv run python -m patternity.training
```

This prints leave-one-chart-out accuracy, trains on the corpus, prints the training-set fit, and writes `src/patternity/data/footing_weights.json`.

| Option | Default | Meaning |
|--------|---------|---------|
| `fixtures` (positional) | `training_corpus.txt` | Train on these fixtures instead. |
| `--fixtures-root` | nearest `tests/fixtures` | Where the fixtures and corpus files live. |
| `--epochs` | 100 | Maximum passes over the charts. |
| `--margin` | 5.0 | How much the annotated foot must win by. |
| `--output` | packaged weights file | Write the weights elsewhere, for experiments. |
| `--no-loo` | off | Skip leave-one-chart-out. |

## 4. Check the result

```bash
uv run python scripts/evaluate.py            # accuracy, pattern scores, disagreements
uv run python scripts/evaluate.py --holdout  # the hold-out charts
uv run pytest -q
```

- **Training-set fit** should be 0 errors, and `"trainer"` in the weights file should be `"structured-perceptron"`. Otherwise see [The trainer did not converge](development.md#the-trainer-did-not-converge).
- **Leave-one-chart-out** shows how each chart is footed by a model that never saw it. A low number for a new chart means it taught the model a lot.
- `test_foot_path.py` holds a minimum accuracy for every training chart (`_MIN_ACCURACY`), the measured accuracy of each hold-out (`_HOLDOUT_ACCURACY`), and exact per-pattern counts (`_PATTERN_SCORES`). Add new charts there. If a number gets worse, update it with a comment saying why.
- `test_snapshots.py` fails after a retrain, because footing output changed. Rewrite the snapshots and review the diff; only `snapshots/footing/` should change.
  ```bash
  uv run pytest tests/integration/test_snapshots.py --update-snapshots
  ```
- `test_canonical.py` compares against hand-counted files. If you change a pattern fixture's notes, recount by hand; see the [canonical README](../tests/fixtures/canonical/README.md).

## The structured perceptron

We want weights under which every annotated foot choice lies on the cheapest path. Each epoch, for each chart in shuffled order (`training/trainer.py`):

1. **Predict** the cheapest path under the current weights. Paths that disagree with an annotation get a discount of `margin`, so the annotated footing has to win by that much.
2. If any annotated row is wrong, find the **gold path**: the cheapest path that agrees with every annotation. Untagged rows are filled in by the decoder, which is why partial annotation works.
3. **Update** `w ← w − step × (features(gold) − features(predicted))`. `step` is scaled down for charts with many annotated rows, so a long chart can't drown out a short pattern fixture.
4. **Clip** the weights in `NONNEGATIVE` at zero. Those features can only add physical effort, so the model must not learn to reward them.

Training stops when an epoch decodes every chart correctly at the margin (`"trainer": "structured-perceptron"`). If that never happens within `--epochs`, it returns the average of the weights over all updates (`"averaged-structured-perceptron"`), which means some annotations conflict under the current features. Training is deterministic.

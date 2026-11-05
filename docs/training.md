# Training workflow

The footing weights are learned from charts you annotate. The loop is:

1. Annotate a chart (or part of one).
2. Add it to the training set.
3. Retrain.
4. Check training fit, leave-one-chart-out, and the tests.

For what the trainer does internally, see [The Structured Perceptron](#the-structured-perceptron) below.

## 1. Annotate

Annotations are `//` comments on note rows in a fixture chart under `tests/fixtures/` (`patterns/` for short pattern examples, `charts/` for real charts).

```text
// measure 0
1000 // @foot=L
0100 // @foot=R
0100 // @foot=L @pattern=footswitch
1001 // @feet=L,R
0110 // @feet=R,R @pattern=bracket
,  // measure 1
```

| Tag | Meaning |
|-----|---------|
| `@foot=L` / `@foot=R` | Which foot presses this row. |
| `@feet=L,R` | Two panels pressed by different feet (a jump). |
| `@feet=L,L` / `@feet=R,R` | Both panels pressed by one foot (a bracket). |
| `@pattern=…` | The tech pattern that **ends** on this row: `jack`, `footswitch`, `holdswitch` (scored as a footswitch), `sideswitch`, `doublestep`, `bracket`, `candle`. Comma-separate several. Only scored, never trained on. |
| `@section=name` | Groups following rows under a name (informational). |
| `@suggest_foot=…` / `@suggest_feet=…`  `@margin=…` | Foot suggestion written by the suggestion script. Ignored by training until you drop the `suggest_` prefix. |
| `@suggest_pattern=…` | Pattern suggestion written by the suggestion script (`none` means the decoder found no pattern on a row you tagged). Ignored until you drop the `suggest_` prefix. |

Rules and conventions:

- **Partial annotation is fine.** Rows without `@foot`/`@feet` are left to the model. Leave genuinely ambiguous rows untagged rather than guessing; a forced label on an ambiguous row teaches the model noise.
- **Only the first chart in a file is read.** Put the chart you annotate first, or keep one chart per fixture file.
- **Measure comments**: `// measure 0` on its own line before the first row, and each comma labeled with the measure that starts after it (`,  // measure 1`). Measures are 0-based, as in the StepMania editor. These are for humans; the parser ignores them.
- **Never put `;` in a comment** inside note data. StepMania treats `;` as the end of a section.
- An annotation that is physically impossible (for example `@foot=R` while the right foot is holding a different panel) is reported as an "impossible annotation" by the evaluation and the tests; fix the tag.

### Using suggestions

To annotate a long chart faster, let the model propose footing and review it:

```bash
uv run python scripts/suggest_annotations.py tests/fixtures/charts/my_chart.ssc
```

This writes `@suggest_foot=L @margin=12.3` (or `@suggest_feet=L,R` for jumps and brackets) on every untagged press row and on rows where the model disagrees with your tag. It also runs the tech pattern detector on the decoded path and writes `@suggest_pattern=…` where the detected patterns differ from the row's `@pattern` tag: `jack`, `doublestep`, `footswitch`, `sideswitch`, `bracket`, `crossover` (normal and inverted), and `candle`. `holdswitch` counts as `footswitch`, and other tags such as `jump` are left alone. Patterns come from the model's own footing, as in `evaluate.py`, not from your `@foot` tags.

The script adds 0-based `// measure 0` before the first note row and `// measure N` on comma lines (measure starts after each comma), and prints the lowest-margin foot rows and the pattern suggestions with `mN` in the log. It never changes existing tags, preserves line endings, and replaces its own previous suggestions (including legacy `@suggest=` tags) and measure markers on rerun.

Review **low margins first**: those are rows where the model is unsure, so your answer teaches it the most. High-margin rows mostly confirm what it already does. Accept a suggestion by dropping the `suggest_` prefix (`@suggest_foot` → `@foot`, `@suggest_pattern` → `@pattern`); accept `@suggest_pattern=none` by deleting the row's `@pattern` tag. A leftover `@margin=` is ignored, but deleting it keeps the file tidy.

On a new, untagged chart whose output you've reviewed and found correct, a find/replace of `@suggest_` with `@` accepts everything at once. Don't do this on a partially tagged chart: disagreeing rows would end up with two `@foot` or `@pattern` tags, and the parser keeps the first (yours). Never bulk-accept suggestions you haven't reviewed: the model can't be its own ground truth.

Optional flags: `--weights path/to.json` (default: packaged weights), `--list N` (print the `N` lowest-margin rows; default 25).

### Bootstrapping a new chart

Example: you added [`tests/fixtures/charts/shake_the_city.ssc`](../tests/fixtures/charts/shake_the_city.ssc) and want footing tags without writing every row by hand.

1. **Propose footing.** The script edits the file in place; use git or a copy if you might revert bulk suggestions.

   ```bash
   uv run python scripts/suggest_annotations.py tests/fixtures/charts/shake_the_city.ssc
   ```

   On a chart with no `@foot` / `@feet` yet, every press row gets `@suggest_foot` / `@suggest_feet` and `@margin`, and every row where the decoder finds a pattern gets `@suggest_pattern`. On a partially tagged chart, only **untagged** rows and rows where the model **disagrees** with your tag get suggestions.

2. **Accept tags by hand.** Drop the `suggest_` prefix where you agree; delete suggestions you do not need. Partial annotation is fine—keep only interesting or decisive passages tagged. Leave ambiguous rows untagged.

3. **Check `@pattern` tags.** Accepted `@suggest_pattern` tags only reflect what the detector already finds. Add or fix `@pattern=…` on the anchor row (pattern end) wherever a player would read the pattern differently; see the tag table above.

4. **Evaluate before training.** You do not need a line in `training_corpus.txt` to score a fixture:

   ```bash
   uv run python scripts/evaluate.py charts/shake_the_city.ssc --show 50
   ```

   Fix impossible annotations and disagreements on the rows you tagged. To see where end-to-end counts look wrong (where to annotate next):

   ```bash
   uv run patternity -f tests/fixtures/charts/shake_the_city.ssc -a
   ```

5. **Add to the corpus and retrain** when footing tags are stable (step 2 below).

## 2. Add the chart to the training set

Add the path (relative to `tests/fixtures/`) as a new line in [`tests/fixtures/training_corpus.txt`](../tests/fixtures/training_corpus.txt):

```text
charts/hoot.ssc
charts/move_mint.ssc
charts/my_chart.ssc
```

`#` starts a comment, so a chart can be dropped from training by commenting it out. Charts in `tests/fixtures/` that are *not* listed (for example `# charts/fots.sm`) are still useful for evaluation, but don't influence the weights.

### Hold-out charts

If the model already footing-annotates a new chart correctly on the first pass, consider holding it out instead: list it in [`tests/fixtures/holdout_corpus.txt`](../tests/fixtures/holdout_corpus.txt) and add it to `_MIN_ACCURACY` in `tests/integration/test_foot_path.py`. Hold-out charts are never trained on, so they measure how well the model generalizes, and the test suite flags a retrain that regresses them.

```bash
uv run python scripts/evaluate.py --holdout
```

If you fix a hold-out regression by tuning features or annotations, the chart is no longer unseen: move it to `training_corpus.txt`, and hold out the next new chart instead.

## 3. Retrain

```bash
uv run python -m patternity.training
```

This prints leave-one-chart-out accuracy, then trains on all listed charts, prints the training-set fit, writes `src/patternity/data/footing_weights.json` (which the CLI and `Analyzer` load by default), and prints the weights.

| Option | Default | Meaning |
|--------|---------|---------|
| positional `fixtures` | `training_corpus.txt` | Train on these fixtures instead (paths relative to the fixtures root). |
| `--fixtures-root` | nearest `tests/fixtures` | Directory holding the fixtures and `training_corpus.txt`. Found by walking up from the current directory; pass it when running from elsewhere. |
| `--epochs` | 100 | Maximum passes over the charts. Training usually stops earlier. |
| `--margin` | 5.0 | How much the annotated foot must win by. |
| `--output` | packaged weights file | Write weights elsewhere, for experiments. |
| `--no-loo` | off | Skip leave-one-chart-out (faster). |

To experiment without touching the packaged weights:

```bash
uv run python -m patternity.training --no-loo --output /tmp/experiment.json
uv run python scripts/evaluate.py --weights /tmp/experiment.json
```

## 4. Check the result

Read the training output in this order:

1. **Training-set fit** should be 0 errors on every chart. If not, some annotations conflict; see [Debugging](debugging.md#the-trainer-did-not-converge).
2. **`"trainer"`** in `footing_weights.json` should be `"structured-perceptron"`. `"averaged-structured-perceptron"` means training could not satisfy every annotation.
3. **Leave-one-chart-out** shows how each chart is footed by a model that never saw it. When you add a chart, its own held-out number tells you how much new information it brought (low means the model learned a lot from it), and the other charts' numbers tell you whether it helped or hurt them.

Then run the evaluation report and the tests:

```bash
uv run python scripts/evaluate.py            # accuracy, pattern P/R, disagreements
uv run python scripts/evaluate.py --loo      # plus leave-one-chart-out
uv run pytest -q
```

`tests/integration/test_foot_path.py` holds a minimum accuracy per fixture in `_MIN_ACCURACY`. Add new annotated charts there so a future retrain can't silently break them. If new data makes an older chart slightly worse, lower its threshold with a comment explaining why.

`tests/integration/test_canonical.py` compares end-to-end counts with hand-counted `tests/fixtures/canonical/*.json`. If you change a pattern fixture's notes, recount its JSON by hand (never copy analyzer output into it); see [`tests/fixtures/canonical/README.md`](../tests/fixtures/canonical/README.md).

## What makes a good training chart

- **Real ambiguity, decided by a person.** The model learns most from passages where a reasonable alternative footing exists and you can say why yours is right.
- **Coverage of what's missing.** Look at charts where the analyzer's counts look wrong and annotate the passages responsible (see [Debugging](debugging.md)). Jumpstreams, uncued footswitches, and long same-panel runs have historically been under-covered.
- **Variety over volume.** A few distinct charts teach more than one very long chart; long charts are already scaled down during training so they don't dominate.

## The Structured Perceptron

StepMania does not embed the notion of footing within its engines, nor is this information persisted in chart data in `.sm` or `.ssc` files. We hand-annotate charts that an ML model can fit and effectively mimic player footing decision-making.

We want weights under which every annotated foot choice is part of the cheapest path. A **structured perceptron** learns exactly that: decode with the current weights, and if the result disagrees with the annotations, nudge the weights so the annotated path gets cheaper and the wrong path gets more expensive. Repeat. No gradients or probabilities needed — just the same Viterbi decoder used at runtime — and with a linear model and a few dozen features it converges quickly on a small corpus.

### The Update

Every epoch, for each annotated chart in shuffled order (`training.trainer.train`):

1. **Predict** the cheapest path using the current weights with **cost-augmented decoding**: a path that disagrees with an annotation gets a `margin` (default 5) discount, so the annotated path must win by at least that margin, not merely tie.
2. If any annotated row is wrong, find the **gold path**: the cheapest path that agrees with every annotation. Annotations only say which foot moved, not every detail of the stance, so the decoder fills in the rest under the current weights (a "latent-variable" perceptron). This is also why charts can be **partially annotated** — untagged rows are simply left to the decoder.
3. **Update**: `w ← w − step × (features(gold) − features(predicted))`. Features the gold path relies on get cheaper; features the wrong path relied on get more expensive.
4. **Clip** a few weights at zero (`NONNEGATIVE` in `training/trainer.py`): travel, inverted, crossover entry, facing flip, technique change, jack speed², bracket speed, hold release, early release. These can only add physical effort, so clipping stops the perceptron from learning to reward them on sparse data.

`step` is scaled per chart by `mean annotated rows / this chart's annotated rows`, so one long, fully annotated chart can't drown out a 12-row pattern fixture.

### Stopping And The Returned Weights

- If a whole epoch passes with every chart decoded correctly at the margin, training stops and returns those weights (`footing_weights.json` then records `"trainer": "structured-perceptron"`).
- Otherwise, after `epochs` (default 100), it returns the **average** of the weights across all updates (`"averaged-structured-perceptron"`) — the standard remedy when no single weight vector satisfies every annotation.

> [!NOTE]
> "Averaged" means some annotations conflict under the current features: either the tags disagree with each other, or the model is missing a feature that would tell the passages apart. See [Debugging](debugging.md#the-trainer-did-not-converge).

Training is deterministic (`seed=0`).


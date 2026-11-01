# Training workflow

The footing weights are learned from charts you annotate. The loop is:

1. Annotate a chart (or part of one).
2. Add it to the training set.
3. Retrain.
4. Check training fit, leave-one-chart-out, and the tests.

For what the trainer does internally, see [Footing model](footing-model.md#training-the-structured-perceptron).

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
| `@suggest=…  @margin=…` | Written by the suggestion script. Ignored by training until you rename it to `@foot` / `@feet`. |

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

This writes `@suggest=L @margin=12.3` on every untagged press row and on rows where the model disagrees with your tag, adds 0-based `// measure 0` before the first note row and `// measure N` on comma lines (measure starts after each comma), and prints the lowest-margin rows with `mN` in the log. It never changes `@foot` tags, preserves line endings, and replaces its own previous suggestions and measure markers on rerun.

Review **low margins first**: those are rows where the model is unsure, so your answer teaches it the most. High-margin rows mostly confirm what it already does. Accept a suggestion by renaming `@suggest` to `@foot` (or `@feet` for jumps and brackets); a leftover `@margin=` is ignored, but deleting it keeps the file tidy. Never bulk-accept suggestions: the model can't be its own ground truth.

Optional flags: `--weights path/to.json` (default: packaged weights), `--list N` (print the `N` lowest-margin rows; default 25).

### Bootstrapping a new chart

Example: you added [`tests/fixtures/charts/shake_the_city.ssc`](../tests/fixtures/charts/shake_the_city.ssc) and want footing tags without writing every row by hand.

1. **Propose footing.** The script edits the file in place; use git or a copy if you might revert bulk suggestions.

   ```bash
   uv run python scripts/suggest_annotations.py tests/fixtures/charts/shake_the_city.ssc
   ```

   On a chart with no `@foot` / `@feet` yet, every press row gets `@suggest` and `@margin`. On a partially tagged chart, only **untagged** rows and rows where the model **disagrees** with your tag get suggestions.

2. **Accept tags by hand.** Rename `@suggest` → `@foot` / `@feet` where you agree; delete suggestions you do not need. Partial annotation is fine—keep only interesting or decisive passages tagged. Leave ambiguous rows untagged.

3. **Add `@pattern` yourself.** The suggestion script never writes pattern tags. Put `@pattern=…` on the anchor row (pattern end) for rows you want in evaluation; see the tag table above.

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

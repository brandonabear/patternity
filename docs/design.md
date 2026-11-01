# Design Principles

These are the rules the codebase follows, and why. How the pieces work is described in [Architecture](architecture.md) and [Footing model](footing-model.md).

## Scope

- Parse `.sm` and `.ssc` files, including song header data, chart metadata, and groove radar values.
- Analyze 4-panel singles charts. Doubles are out of scope.

## Footing is inferred, not hand-tuned

- **Footing is learned from annotated charts.** Costs are a weighted sum of features, and the weights come from training. Nobody adjusts a bonus or penalty to make one example come out right; a footing that is wrong gets fixed by annotating it (and, if needed, by adding a feature that describes what the player is physically doing).
- **Features are pattern-agnostic.** They describe what the feet do (same foot again, travel, crossing, speed, mine cues), never named patterns, and never ITG timing cutoffs.
- **Hard rules only for physics.** `footing/transitions.py` forbids what is impossible (leaving a hold, stepping off a panel you must press). Everything that is merely unusual is a cost.
- **The search is exact.** Viterbi with a complete state, no beam, so the result is the true minimum for the weights, and a wrong footing always means a wrong cost, never a search shortcut.

## Counting is separate from footing

- **ITG / community cutoffs live only in `patterns/detector.py`.** The labeler reads the decoded foot path and applies the community definitions. Changing a cutoff never changes footing, and retraining never changes the definitions.

## Ground truth comes from people

- **Annotations are never generated from model output.** `scripts/suggest_annotations.py` writes `@suggest=` tags that a person must accept by renaming them; `@foot` tags are only written by hand.
- **Canonical counts are hand-counted.** `tests/fixtures/canonical/*.json` must not be filled from analyzer output.
- **Partial and ambiguous annotations are allowed.** Untagged rows are left to the model; genuinely ambiguous passages should stay untagged.

## Regression layers

| Layer | Source | What it guards |
|-------|--------|----------------|
| Foot path | `@foot` / `@feet` tags via `training/annotations.py` | Per-row accuracy thresholds and no physically impossible tags (`test_foot_path.py`) |
| Pattern labels | `@pattern` tags | Per-kind precision/recall on the decoded path (`test_foot_path.py`) |
| Tech counts | Hand-counted `tests/fixtures/canonical/*.json` with `"validated": true` | End-to-end counts, with an optional `tech_tolerance` for a documented miss (`test_canonical.py`) |

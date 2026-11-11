# Design Principles

## Scope

- Parse `.sm` and `.ssc` files, including song header data, chart metadata, and groove radar values.
- Analyze 4-panel singles charts. Doubles are out of scope.
- Lifts and fakes are parsed and counted in the basic metrics, but footing never steps on them. ITG charts don't use lifts.

## Inferred Foot Placement

- **Foot placement is learned from annotated charts.** Foot placement costs are the weighted sum of features, and the weights come from training; there is no hand-tuning of weights.
- **Features are pattern-agnostic.** They describe what the feet do (same foot again, travel, crossing, speed, mine cues), never named patterns, and never ITG timing cutoffs.
- **Hard rules only for restricting legal foot placements.** `footing/rules.py` forbids what is impossible (leaving a hold too early, ignoring a panel you must press). Leaving a hold is only impossible outside its grace window before the tail; inside the window it is a cost (`hold_release`, `early_release`).
- **The search is exact.** The trellis of possible foot placement states does not get pruned; Viterbi has visibility into all legal states. This avoids converging on local cost minima.

## Pattern Counts Derived From Foot Placement

- **ITG / community cutoffs live only in `patterns/detector.py`.** The labeler reads the decoded foot path and applies the community definitions.

## Foot Placement is Learned

- **Annotations are never generated from model output.** `scripts/suggest_annotations.py` writes `@suggest_foot=` / `@suggest_feet=` / `@suggest_pattern=` tags that a person can review and accept by dropping the `suggest_` prefix; the script itself never writes definitive `@foot`, `@feet`, or `@pattern` annotations.
- **Partial and ambiguous annotations are allowed.** Untagged rows are left to the model; genuinely ambiguous passages should stay untagged.

## Multiple Regression Checks

| Check | Source | Description |
|-------|--------|----------------|
| Foot path | `@foot` / `@feet` tags via `training/annotations.py` | Per-row accuracy thresholds and no physically impossible tags (`test_foot_path.py`) |
| Pattern labels | `@pattern` tags | Per-kind precision/recall on the decoded path (`test_foot_path.py`) |
| Tech counts | Hand-counted `tests/fixtures/canonical/*.json` with `"validated": true` | End-to-end counts, with an optional `tech_tolerance` for a documented miss (`test_canonical.py`) |

> [!IMPORTANT]
> **Canonical counts are hand-counted.** `tests/fixtures/canonical/*.json` must not be filled from analyzer output.

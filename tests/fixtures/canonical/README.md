# Canonical tech regressions

Files here are **hand-counted ground truth** for basic and tech metrics on fixture charts. Never fill them from `analyze_chart` output.

## Workflow

1. Count the metrics by hand on the fixture named in the JSON's `"fixture"`.
2. Fill in `charts[].basic` and `charts[].tech`.
3. Set top-level `"validated": true`.

`tests/integration/test_canonical.py` then checks those counts. Until `validated` is `true`, it only checks that the fixture parses and analyzes.

## Counting rules

- **Basic counts are exact.** `taps` are press rows (a jump or hand is one tap); `steps` are tap, hold and roll heads (a jump is two). See `BasicMetrics` in `src/patternity/analysis/metrics.py`.
- **Tech counts are exact unless the file sets `"tech_tolerance"`.** Use it only for a known miss by the footing model, and say what the miss is. `brackets.json` allows 1 because the model plays the crossover-bracket section as a jump.
- **`movement` is recorded but not asserted.**

For the `@foot` / `@pattern` comments inside the fixture charts, see [Training workflow](../../../docs/training.md#1-annotate).

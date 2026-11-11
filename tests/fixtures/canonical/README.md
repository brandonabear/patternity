# Canonical tech regressions

Files here are **hand-counted ground truth** for basic/tech metrics on pattern fixtures. They are not generated from `analyze_chart` output.

## Workflow

1. Count metrics on the linked `.sm` fixture (ITG/docs/community rules you intend to match).
2. Fill in `charts[].basic` and `charts[].tech` in the JSON file.
3. Set top-level `"validated": true`.
4. The test suite checks equality on those keys via `tests/integration/test_canonical.py`. Basic counts are always exact; tech counts may differ by an optional top-level `"tech_tolerance"` (default 0) when the footing model has a known, documented miss on the fixture.

Until `validated` is `true`, tests only smoke-check that the fixture parses and analyzes; they **do not** assert counts.

Basic counts use one rule everywhere: **taps** are presses (one per row with stepping heads; jumps/hands still one press), **steps** are total TAP/HOLD/ROLL arrow heads. See `BasicMetrics` in `src/patternity/analysis/metrics.py`.

For full-chart foot tags (e.g. `tests/fixtures/charts/burger.ssc`), `scripts/suggest_annotations.py` writes 0-based `// measure N` markers at measure boundaries and `@suggest_foot=` / `@suggest_feet=` / `@margin=` / `@suggest_pattern=` on suggestion rows; review low margins first and drop the `suggest_` prefix to accept. Inline `@foot` / `@pattern` comments on flat `.ssc` `#NOTES:` bodies are parsed by `parse_annotated_sm` and checked in `tests/integration/test_foot_path.py`. `brackets.json` has `tech_tolerance: 1` because the model plays the crossover-bracket section as a jump. Comma markers use **0-based** measure numbers (StepMania editor). Do not put `;` inside `//` comments in `.ssc` note data — StepMania uses semicolons as section terminators.

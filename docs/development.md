# Development guide

How to make common changes to Patternity. For how the pieces fit together, see [Architecture](architecture.md); for the rules the codebase follows, see [Design principles](design.md).

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
| Fix how a passage is *footed* | Annotate it and retrain ([Training workflow](training.md)). Only add or change a feature when the existing features cannot express the distinction ([Adding a feature](#adding-a-feature)). |
| Allow or forbid a physical move outright | `footing/rules.py` (hard rules) |
| Change what basic metrics count | `analysis/metrics.py` (`BasicMetrics.add_note`) |
| Change movement counts (direction shifts) | `movement/detector.py` |
| Support a new simfile tag | `simfile/parser.py`, `simfile/song.py` |

## Adding a feature

Add a feature only when the existing features can't produce the expected footing (see [Debugging](debugging.md#why-does-the-model-prefer-its-footing)); otherwise annotate more passages and retrain.

1. Add the name to `FEATURE_NAMES` in `footing/features.py` with a one-line comment. Describe what the feet do, not a pattern name, and avoid tech-pattern timing cutoffs.
2. Set it in the matching group helper that `featurize` calls (`_hold_release_features`, `_repetition_features`, `_mine_cue_features`, `_movement_features`, or `_stance_features`). If none fits, add a new helper and call it from `featurize`.
3. Add a unit test that checks the feature fires on a minimal passage.
4. Retrain ([Training workflow](training.md#3-retrain)). Weights are keyed by name, so older weight files load with the new feature at `0.0`.

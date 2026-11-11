# Usage

## Install

Patternity needs Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Command line

```bash
uv run patternity -f path/to/chart.ssc -a
```

| Flag | Meaning |
|------|---------|
| `-f`, `--file` | Simfile to read (`.sm` or `.ssc`). Required. |
| `-a`, `--analyze` | Analyze every chart in the file and print the metrics. |
| `-s`, `--serialize` | Write the parsed song to JSON. |
| `-o`, `--output` | Output directory for `--serialize` (default `data/`). Created if missing. |

Without `-a`, the CLI only parses the file and prints the song title.

### Output

`-a` prints each chart's difficulty and rating, then one dictionary, in file order:

```python
{
    'basic': {'taps': 587, 'jumps': 14, 'hands': 14, 'holds': 135, 'rolls': 5,
              'mines': 20, 'lifts': 0, 'fakes': 0, 'steps': 601},
    'tech': {'crossovers': 0, 'footswitches': 60, 'sideswitches': 0,
             'jacks': 0, 'brackets': 14, 'doublesteps': 20, 'candles': 56},
    'movement': {'direction_shifts': 52, 'total_cost': 15777.96,
                 'foot_path_feasible': True}
}
```

- **`basic`** counts come from each step's `note_row` after decode (same chart data as `chart.notes`; footing weights do not affect them). `taps` counts press rows (a jump is one tap); `steps` counts arrow heads (a jump is two).
- **`tech`** counts come from the inferred foot path. Definitions are in [Architecture → Tech labels](architecture.md#tech-labels).
- **`movement`** counts also come from the inferred foot path (see [Architecture → Movement metrics](architecture.md#movement-metrics)):
  - **`direction_shifts`** — turns from facing left to facing right or back. Neutral and inverted rows in between don't reset the last facing direction.
  - **`total_cost`** — cost of the chosen path under the current weights (compare charts only under the same weights; not a difficulty score; can be negative).
  - **`foot_path_feasible`** — `False` when any row needed a relaxed fallback. See [Debugging](debugging.md#relaxed-rows).

## Python

```python
from pathlib import Path

from patternity import StepmaniaFileParser, analyze_chart, read_simfile

song = StepmaniaFileParser.parse(read_simfile(Path("chart.ssc")))
for chart in song.charts:
    analysis = analyze_chart(chart)
    print(chart.metadata.difficulty, analysis.tech.jacks, analysis.to_dict())
```

`analyze_chart` returns a `ChartAnalysis` holding `basic`, `tech` and `movement`; `to_dict()` gives the dictionaries shown above.

To inspect the foot path itself rather than the counts:

```python
from patternity import detect_tech_patterns, resolve_chart

result = resolve_chart(chart.notes)          # packaged weights, with confidence
for step in result.steps:
    if step.note_row.pressed:
        fr = step.foot_row
        print(step.note_row.measure, step.note_row.beat,
              fr.moved.name, fr.stance.left, fr.stance.right, step.confidence)

tech = detect_tech_patterns(result.steps)
for span in tech.spans:                      # each detection, with its steps
    print(span.kind, span.start_measure, span.start_beat)
```

`resolve_chart` and `analyze_chart` accept a `model` argument to use other weights:

```python
from patternity import FootingModel

model = FootingModel.load(Path("/tmp/experiment.json"))
analyze_chart(chart, model)
```

## Limits

- Singles (4-panel) only; doubles are out of scope. Charts in other modes, or with note characters Patternity doesn't model, are skipped and listed in `song.skipped_charts` (the CLI prints them).
- Footing is learned from a small annotated corpus. Unusual patterns that no annotated chart covers (for example long jumpstreams) can be footed oddly; see [Training workflow](training.md) for how to fix that with data.

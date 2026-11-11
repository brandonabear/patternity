# File Format

StepMania note data is stored in structured text files. `patternity` supports two of these formats: `.sm` and `.ssc`.

## Shared Features

Both formats are organized in the same manner:
- A single **header** section containing song-level metadata, such as the title, artist, music file location, etc.
- One or more **charts** (SM tags `#NOTES` / `#NOTEDATA` plus a notes body): chart-level metadata and row-level note placements. In patternity each chart becomes a **`Chart`** (`metadata` + `notes`).

Most of the metadata is stored as key-value pairs like `KEY:VALUE;`.

The same logical **Chart** is encoded differently by format:

- **`.sm`**: one `#NOTES:` section with metadata and notes packed as colon-separated fields — `[mode]:[credit]:[difficulty]:[meter]:[radar]:[notes…]`.
- **`.ssc`**: a `#NOTEDATA` block with chart tags (`#STEPSTYPE`, `#METER`, `#RADARVALUES`, …), then `#NOTES:` (or `#NOTES2:`) whose body is the note rows only.

## Parsing

The parser splits the text data into sections on the `;` character. From there, we perform additional parsing to extract data like BPM changes, Groove Radar statistics, etc. Note bodies are grouped into **measures** (lines starting with `,` in the file); each measure’s **quantization** is its row count, which the parser uses to assign **beats** to each row. While `.sm` and `.ssc` differ in how chart metadata is stored, the hierarchy above is the same.

```text
Song (one .sm / .ssc file)
|-- Header (#TITLE, #ARTIST, #MUSIC, …)
|   |-- Scalar tags (title, artist, offset, display BPM, …)
|   |-- BPM changes (#BPMS: beat → BPM)
|   |-- Stops (#STOPS: beat → duration)
|   |-- … (bg/fg changes, etc.)
|
|-- Chart[] (each #NOTES / #NOTEDATA + notes body)
    |-- Chart metadata
    |   |-- Mode (#STEPSTYPE / .sm field 1 — e.g. dance-single)
    |   |-- Credit
    |   |-- Difficulty
    |   |-- Meter (#METER → rating in patternity)
    |   `-- Groove Radar (#RADARVALUES)
    |       |-- Stream, Voltage, Air, Freeze, Chaos
    |       |-- Steps, Taps, Jumps, Holds, Mines, Hands
    |
    |-- Note rows (not in separate tags — body after metadata)
        |-- Measure[] (comma-separated in file)
            |-- Row[] (one line per row: Left Down Up Right)
```

> NOTE: `.ssc` extends `.sm` with features such as per-chart timing, native gimmick support, and decoupled chart metadata (tags under `#NOTEDATA` instead of a single packed `#NOTES:` line).

## Code Model Mapping

[`StepmaniaFileParser.parse`](../src/patternity/simfile/parser.py) reads a file string and returns a **`Song`**. Exhaustive SM/SSC tag lists live in the [OutFox SM support wiki](https://outfox.wiki/en/dev/mode-support/sm-support).

| Concept | Python type | Module |
| --- | --- | --- |
| Song (file) | `Song` | `patternity.simfile.song` |
| Header | `Header` | `patternity.simfile.song` |
| Chart | `Chart` | `patternity.simfile.song` |
| Chart metadata | `ChartMetadata` | `patternity.simfile.song` |
| Difficulty | `Difficulty` | `patternity.simfile.song` |
| Groove Radar | `GrooveRadar` | `patternity.simfile.song` |
| Note row (LDUR + derived timing) | `NoteRow` | `patternity.simfile.notes` |
| Column symbol (`0`, `1`, `M`, …) | `NoteType` | `patternity.simfile.notes` |

**Derived at parse time (not SM tags):** each `NoteRow` gets `measure`, `quantization`, and `beat` from measure boundaries and row index. **Analysis** metrics (`BasicMetrics`, `TechMetrics`, `MovementMetrics`) are computed later and are not part of the simfile; see [Architecture](architecture.md).

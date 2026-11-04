# Footing Model

The fundamental building block for identifying patterns is player footing. To replicate player foot selection, we model the state at each row (player stance, active holds, etc.) and possible legal transitions between them as a graph and use Viterbi to solve for the lowest cost path. This inferred footing becomes the basis for deriving various tech patterns like footswitches or brackets.

## Viterbi Search

### Hidden State

Each row of the chart has a set of possible player states. A `FootRow` (`footing/stance.py`) captures information about player position, footing used to obtain that position, intermediate mines, same-panel repetition, etc.

Every field takes part in equality and hashing. Two paths only merge in the search when everything that affects future costs is identical, so the search is **exact**; no pruning or beam search is performed.

### Transition Rules

Between each pair of states are a set of possible transitions (`footing/transitions.py`). For each row, a `RowContext` names the panel sets involved (`pressed`, `held`, `releasable` in a grace window, and the derived `must_stay_held` and `touchable`). `_candidates` proposes every foot move, and a candidate is legal only if it passes every named rule in `_RULES`:

- `presses_are_covered`: every pressed panel is under a moving foot
- `moving_feet_touch_only_pressed_or_held`: no foot moves to an unpressed panel (unless it is already held)
- `each_jumping_foot_presses` / `jumping_feet_dont_share_a_panel`: in a jump, each foot presses something and the feet don't overlap
- `held_panels_stay_covered`, `hold_owner_stays_on_panel`, `no_bracket_onto_held_panel`: active holds and rolls stay covered by their "owning" foot, and the other foot can't bracket onto them
- Individual placements can only be single panel or legal two-panel presses (i.e. brackets)

Panel sets are `Panel` values (`simfile/notes.py`): read `Panel.U in row.pressed` as "Up is pressed".

> [!NOTE] 
> We account for the hold/roll grace windows (`footing/grace.py`) since StepMania doesn't instantly penalize a lifted foot as long as the panel is re-pressed within said window.

> [!WARNING] 
> A row without a legal state (possibly from a malformed chart or incorrect annotation) defaults to a large penalty `RELAXED_PENALTY`.

### Cost Features

Each transition is stored in a feature vector `FEATURE_NAMES` (see `footing/features.py`). These are physical player stance, movement, or state descriptions, not pattern names.

> [!IMPORTANT]
> The cost of a transition is the dot product of its `weights` and `features`. The cost of a path is simply the sum over its moves!

### Footing Decoding

`build_trellis` (`footing/search.py`) enumerates all states for every row once (it doesn't depend on the weights) and stores each edge's feature vector. `viterbi` then finds the minimum-cost path for the given weight vector.

`row_confidence` runs a forward and a backward pass and, for each row press, compares the best path overall with the best path that uses a different foot on that row. The difference is the row's **margin**.

> [!NOTE]
> The margin's size indicates difference in cost between footing options. `inf` indicates no alternative foot was physically possible on a given row.

### Visualizing the Trellis

It helps to maintain a mental model of how `patternity` solves footing by visualizing the trellis and Viterbi-selected paths. The following diagrams show short arrow phrases and provide a simplified trellis representation. The modeled footing is labeled in the chart on the left and the winning path (lowest cost) is highlighted in the diagram on the right. Edge costs are the real transition costs from the packaged weights at 120 BPM (150 BPM in Example 3), rounded, and will change when the model is retrained.

### Example 1: Simple Alternating Feet

One of the earliest optimizations players learn is to alternate feet between arrows and effectively "walk" instead of returning to the center arrow each time. This becomes a necessity as arrow density increases with difficulty.

The opening step is an exact tie (26.3 either way) because the neutral stance is symmetric. The diagram follows the decoder, which happens to break that tie toward the right foot; opening with the left foot (Left, Right, Left) costs the same 73.5 in total.

![Playfield for three 8th notes (down, up, down; arrows labeled R, L, R for the winning foot and colored red on 4th-note beats, blue on 8th-note beats) beside the footing trellis for the same rows, starting from a neutral stance. The minimum-cost path (white-outlined nodes, solid edges) alternates right, left, right; dashed nodes and edges are alternatives, each branching from the winning node above.](images/trellis_alternating.svg)

### Example 2: Mine-Cued Footswitch

A footswitch is a technique where consecutive same-arrow presses are hit by alternating feet. This can be coerced by placing a mine such that performing a jack would result in triggering the mine or where the speed of consecutive taps is sufficiently quick that alternating feet requires less effort.

![Playfield for a footswitch (Left, Down, mine on Left, Down, Right on 16th notes; arrows labeled with the winning foot L, R, L, R and colored red on 4th-note beats, green on 16th-note beats) beside the footing trellis for the same rows. The minimum-cost path (white-outlined nodes, solid edges) alternates feet, with the left foot stepping off the mined Left panel to take over Down; dashed nodes and edges are alternatives branching from the winning node above.](images/trellis_footswitch.svg)

### Example 3: Crossover Bracket

A crossover-bracket is the combination of a crossover (right foot used to hit left panel or left foot used to hit right panel) and a bracket (one foot used to hit two adjacent panels). While a player could opt to perform a jump, depending on the speed, the cost may be lower to simpler turn and bracket the two-panel hit instead.

![Playfield for a crossover bracket (Right, Down, Left and Up together, Down, Right on 16th notes at 150 BPM; arrows labeled with the winning foot R, L, R and R, L, R, colored red on 4th-note beats, blue on 8th-note beats and green on 16th-note beats) beside the footing trellis for the same rows. The minimum-cost path (white-outlined nodes, solid edges) has the right foot bracket Left and Up across the left foot rather than jumping; dashed nodes and edges are alternatives branching from the winning node above.](images/trellis_crossover_bracket.svg)

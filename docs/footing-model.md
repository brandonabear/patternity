# Footing model

Footing is the hard part: the chart says which arrows to hit, not which foot hits them. Patternity treats this as finding the cheapest path through every legal sequence of foot positions, with the cost of each move learned from human-annotated charts. This is the same idea as Viterbi-based piano auto-fingering.

## The search

### State: `FootRow`

Each row of the chart has a set of possible states. A state (`footing/stance.py`) records:

| Field | Why it is in the state |
|-------|------------------------|
| `stance` | Where each foot is (a panel, or a two-panel bracket) and the resulting orientation (neutral, facing left/right, inverted). |
| `moved` | Which foot or feet pressed on this row (`LEFT`, `RIGHT`, `BOTH`, `NONE`). |
| `last_press_col`, `last_press_foot` | Needed to recognize same-panel repeats (jack vs switch) and same-foot repeats. |
| `mines_since_press` | Mines between presses act as footswitch cues. |
| `hold_owners` | Which foot is holding which hold/roll, so it must stay there (until it releases inside the grace window). |
| `released_since_press` | Which foot just released a hold (a re-press after a release is not a doublestep). |
| `last_repeat_jack` | Whether the previous same-panel repeat was a jack or a switch, so a run that changes technique midway can be costed. |

Every field takes part in equality and hashing. Two paths only merge in the search when everything that affects future costs is identical, so the search is **exact** (no beam, no pruning of good paths).

### Hard rules: `footing/transitions.py`

`iter_legal_transitions(prev, row)` yields every physically possible next state:

- every pressed panel is covered by a moving foot, and no moving foot lands on an unpressed panel (except a panel it is already holding);
- held and rolled panels stay covered by the foot that owns them, and the other foot can't bracket onto them;
- placements are single panels or legal two-panel brackets (Left+Down, Left+Up, Right+Down, Right+Up).

The one exception to the hold rule is the **grace window** (`footing/grace.py`): from `HOLD_GRACE_SEC` (0.32 s) before a hold's tail, or `ROLL_GRACE_SEC` (0.35 s) before a roll's, through the tail row itself, the owning foot may leave. That foot is then free, and the release is costed by `hold_release` and `early_release` instead of being forbidden. The windows follow StepMania / ITG hold and roll life. They describe how long a hold survives without a foot, not a tech-pattern cutoff.

In `footing.search.build_trellis`, a state that leaves a foot on a mine during a press row is also removed. If a row has *no* legal state (rare, usually a malformed chart or an impossible annotation), it is kept with a large penalty (`RELAXED_PENALTY = 1000`) and reported as relaxed.

### Cost: features × weights

Each transition is described by a small feature vector (`featurize` in `footing/features.py`). Features are generic physical descriptions, not pattern names, and none of them uses an ITG timing cutoff. Several are also multiplied by **speed**: `min(1/dt, 20) / 10`, where `dt` is the time since the previous press row (so speed ranges 0 to 2).

| Feature | Fires when |
|---------|-----------|
| `same_foot`, `same_foot_speed` | The same foot presses twice in a row (any panels). |
| `same_foot_after_release` | Same, but the other foot just released a hold, including a grace-window release on this row (natural after a hold). |
| `jack`, `jack_speed`, `jack_speed_sq` | Same foot, same panel, consecutive presses. The squared term lets fast jacks cost disproportionately more. |
| `switch`, `switch_speed` | Other foot, same panel, consecutive presses. |
| `repeat_change` | A same-panel run changes technique midway (jack then switch, or the reverse). |
| `travel`, `travel_speed` | Distance the moving foot travels. |
| `overlap` | Both feet end up sharing a panel area during a single-foot press. |
| `crossed`, `cross_entry` | The stance is crossed; `cross_entry` only on the step that enters it. |
| `inverted` | Fully backwards stance. |
| `facing_flip` | Turning from facing one side to facing the other. |
| `twisted` | Facing sideways without being crossed. |
| `bracket`, `bracket_speed` | A foot lands on a two-panel bracket. |
| `jump`, `jump_speed` | Both feet press on the same row. |
| `hold_bracket_tap` | A foot that owns a hold brackets to tap another panel. |
| `mine_cued_switch`, `mine_cued_same_foot` | A switch / same-foot repeat with a mine cue since the last press. |
| `cued_foot_moves`, `cued_foot_stays` | A foot standing on a mine-cued panel moves off it / stays on it. |
| `hold_release` | A foot leaves a hold or roll it owns during the grace window (tail row included). |
| `early_release` | Same, scaled by how early: seconds left to the tail / grace window (0 on the tail row, up to 1). |

The cost of a move is `weights · features`. The cost of a path is the sum over its moves.

### Decoding

`build_trellis` enumerates all states for every row once (it doesn't depend on the weights) and stores each edge's feature vector. `viterbi` then finds the minimum-cost path for a given weight vector by dynamic programming. On real charts this takes well under a second.

`row_confidence` runs a forward and a backward pass and, for each press row, compares the best path overall with the best path that uses a different foot on that row. The gap is the row's **margin**: small means the model nearly chose the other foot; `inf` means only one choice is physically possible.

## Training: the structured perceptron

### Why a perceptron

We want weights under which every annotated foot choice is part of the cheapest path. That is exactly what a **structured perceptron** learns: decode with the current weights; if the result disagrees with the annotations, move the weights so the annotated path gets cheaper and the wrong path gets more expensive; repeat. It needs no gradients or probabilities, just the same Viterbi decoder the runtime uses, and with a linear model and a few dozen features it converges quickly on a small corpus.

### The update

For each annotated chart, in shuffled order, every epoch (`training.trainer.train`):

1. **Predict** the cheapest path with the current weights, using **cost-augmented decoding**: a path that disagrees with an annotation gets a `margin` (default 5) discount. The real annotated path must therefore win by at least that margin, not merely tie.
2. If any annotated row is wrong, find the **gold path**: the cheapest path that agrees with every annotation. Annotations only say which foot moved, not every detail of the stance, so the gold path's remaining details are filled in by the decoder under the current weights (a "latent-variable" perceptron). This is also why charts can be **partially annotated**: untagged rows are simply left to the decoder.
3. Update: `w ← w − step × (features(gold) − features(predicted))`. Features the gold path uses more often get cheaper, and features the wrong path relied on get more expensive.
4. **Clip** a few weights at zero (`NONNEGATIVE` in `training/trainer.py`): travel, inverted, crossover entry, facing flip, technique change, jack speed², bracket speed, hold release, early release. Physically these can only add effort; with little data the perceptron could otherwise learn to reward them.

`step` is scaled per chart by `mean annotated rows / this chart's annotated rows`, so a long, fully annotated chart cannot drown out a 12-row pattern fixture.

### Stopping and the returned weights

- If a whole epoch passes with every chart decoded correctly at the margin, training stops and returns those weights. The metadata in `footing_weights.json` then says `"trainer": "structured-perceptron"`.
- Otherwise, after `epochs` (default 100), it returns the **average** of the weights across all updates (`"averaged-structured-perceptron"`). Averaging is the standard remedy when no weight vector satisfies every annotation. **Seeing "averaged" means some annotations conflict under the current features**: either the tags disagree with each other, or the model is missing a feature that would tell the passages apart. See [Debugging](debugging.md#the-trainer-did-not-converge).

Training is deterministic (`seed=0`).

### Measuring generalization

Fitting the training charts perfectly says little on its own; a model can memorize. **Leave-one-chart-out** (`training.trainer.leave_one_out`, printed by the training command) trains on all charts but one and scores the held-out chart, once per chart. That number estimates how well the model foots a chart it has never seen, and it is the one to watch as the corpus grows.

## Adding a feature

Prefer adding annotated data. Add a feature only when two annotated passages need different footings but produce the same features (so no weights could separate them). Past examples:

- `same_foot_after_release`: re-pressing after a hold release was being costed like a doublestep.
- `repeat_change`: the model played a same-panel run as "jack twice, then switch", which resolved the same way as the annotated pure jack or pure switch, so nothing penalized it.
- `jack_speed_sq`: fast 16th runs (switch) and slower 8th runs (jack) needed a cost that grows faster than linearly with speed.
- `hold_release`: once the grace window let a foot leave a hold on its tail row, that release had no cost. The model began uncrossing out of holds (burger) where players doublestep, and it could not also learn that a foot stepping off its own tail is natural (too_much).

To add one:

1. Add the name to `FEATURE_NAMES` in `footing/features.py` and compute it in `featurize`. Keep it generic (what the feet do) rather than naming a pattern, and never use an ITG cutoff.
2. If it needs history the state doesn't have, add a field to `FootRow` and set it in `footing/transitions._emit_foot_row`. Keep the field small; it multiplies the number of states.
3. If it can only add effort physically, add it to `NONNEGATIVE` in `training/trainer.py`.
4. Retrain and compare leave-one-chart-out before and after. Keep the feature only if it fixes the target passages without making held-out results worse.

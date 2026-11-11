# Patterns

Tech patterns in `patternity` are detected based on the inferred foot path from the Viterbi solution. For detection code, see [`patterns/detector.py`](../src/patternity/patterns/detector.py).

Jacks and switches pair a panel only with the very next press row, as in ITGmania. Returning to a panel after other steps (Down, Up, Down in a stream) is neither.

## Jack

The same foot presses the same panel on consecutive steps.

> [!IMPORTANT]
> Counts only when the presses are less than **0.176 s** apart (faster than ~5.7 NPS, i.e. 170 BPM 8ths). A mine on the panel in between resets the timer. Hold tails don't count as presses.

The classic jack is a single foot repeatedly hitting the same arrow:

![Playfield at 120 BPM: Left on a 4th note (left foot), then Right on an 8th and Right again on the next 16th, both with the right foot. The two Right presses, 0.125 s apart, are marked as a jack.](images/pattern_jack.svg)

A jump can start a jack. Here the left foot lands the jump's Left and has to hit Left again on the very next 16th:

![Playfield at 120 BPM: Left on a 4th note (left foot), Up on an 8th (right foot), a Left and Up jump on the next 4th (left and right feet), then Left on the following 16th with the left foot. The jump's Left and the 16th Left, 0.125 s apart, are marked as a jack.](images/pattern_jack_from_jump.svg)

> [!TIP]
> Regenerate diagrams with `uv run python scripts/pattern_diagrams.py`.

## Doublestep

The same foot presses two different single panels in a row, while the other foot stays where it is.

> [!NOTE]
> It counts whether or not the other foot was free to step. A foot coming off a hold just before the second press doesn't excuse it, so a holdswitch is also a doublestep.

A hold anchors one foot, leaving the other to take consecutive arrows:

![Playfield at 120 BPM: a Left hold on a 4th note (left foot) lasting until beat 1.5, Down on an 8th (right foot), then Right on the next 4th (right foot) while the hold continues. The Down and Right presses, 0.25 s apart, are marked as a doublestep.](images/pattern_doublestep_hold.svg)

A mine can push a foot off its panel and onto the next arrow. In this Left, Down, Right, Up phrase, the mine on Down sends the right foot over to Right instead of the left foot crossing over:

![Playfield at 120 BPM: Left on a 4th note (left foot), Down on an 8th (right foot), a mine on Down on the next 16th, Right on the following 4th (right foot), then Up on an 8th (left foot). The Down and Right presses, 0.25 s apart, are marked as a doublestep.](images/pattern_doublestep_mine.svg)

## Footswitch

The player swaps feet on the same panel across consecutive steps.

> [!IMPORTANT]
> Counts only within **1/3 s** (≥ 3 NPS, inclusive of 90 BPM 8ths). A mine on the panel in between resets the timer, as for a jack. Switching onto a panel right after a hold/roll releases there (holdswitch) needs a mine cue after the release.

A mine under the left foot pushes it onto Down, where it takes over from the right foot:

![Playfield at 120 BPM: Left on a 4th note (left foot), Down on a 12th (right foot), Down again on the next 12th (left foot) with a mine on Left in the same row, then Right on the following 4th (right foot). The two Down presses, 0.167 s apart, are marked as a footswitch.](images/pattern_footswitch.svg)

## Sideswitch

A subset of `footswitches` where the player swaps feet on the Left or Right panels, generally requiring a turn to enter or exit the pattern.

The left foot crosses over to Right. A mine on Down cues the right foot off Down to take Right from the left foot, which returns to Left:

![Playfield at 120 BPM, 8th notes: Left (left foot), Down (right foot), Right (left foot, crossing over), Right again (right foot) with a mine on Down in the same row, then Left (left foot). The two Right presses, 0.25 s apart, are marked as a sideswitch.](images/pattern_sideswitch.svg)

## Bracket

One foot presses two panels at the same time.

The left foot covers Left and Up together:

![Playfield at 120 BPM: Left on a 4th note (left foot), Right on an 8th (right foot), Left and Up together on the next 4th (both with the left foot), then Right on an 8th (right foot). The Left and Up row is marked as a bracket.](images/pattern_bracket.svg)

A crossover bracket has a foot bracket two panels on the far side of the other foot:

![Playfield at 150 BPM: Right on a 4th note (right foot), Down on a 16th (left foot), Left and Up together on the next 8th (both with the right foot, crossing over the left), Down on a 16th (left foot), then Right on a 4th (right foot). The Left and Up row is marked as a bracket.](images/pattern_crossover_bracket.svg)

## Crossover

The legs cross so the player turns away from facing forward. A new crossover is counted each time the legs cross, or turn to a different crossed orientation while staying crossed. Stepping to an uncrossed stance ends it, even if the player stays turned.

Crossing in front: the left foot moves past the right foot, which is back on Down, to reach Right, then returns to Left:

![Playfield at 120 BPM: Left on a 4th note (left foot), Down on an 8th (right foot), Right on the next 4th (left foot), Down on an 8th (right foot), then Left on a 4th (left foot). The Down and Right presses, 0.25 s apart, are marked as a crossover.](images/pattern_crossover.svg)

Crossing behind (a crossunder): the right foot is forward on Up, so the left foot passes behind it to reach Right before returning to Left. Patternity counts crossunders as crossovers.

![Playfield at 120 BPM: Left on a 4th note (left foot), Up on an 8th (right foot), Right on the next 4th (left foot), Up on an 8th (right foot), then Left on a 4th (left foot). The Up and Right presses, 0.25 s apart, are marked as a crossunder.](images/pattern_crossunder.svg)

## Inverted Crossover

A crossover that turns the player to face backward (left foot on right arrow and right foot on left arrow). This most commonly occurs during laterals.

In this lateral, the left foot crosses over to Right and then the right foot sweeps across to Left so the player faces backward. The spin continues through Up and Right back to facing forward:

![Playfield at 120 BPM: Left on a 4th note (left foot), Down on an 8th (right foot), Right on the next 4th (left foot), Left on an 8th (right foot), Up on a 4th (left foot), then Right on an 8th (right foot). The Right and Left presses, 0.25 s apart, are marked as an inverted crossover.](images/pattern_inverted_crossover.svg)

## Candle

One foot moves between opposite panels (Up↔Down or Left↔Right) between its own presses. The other foot's presses in between don't count. A bracket that keeps one of its panels (Left+Up to Left+Down) is not a candle.

In a run of alternating feet, a candle appears whenever a foot's next arrow is opposite its last one. Here the right foot goes from Down to Up, and later the left foot goes from Down to Up:

![Playfield at 120 BPM, 16th notes with alternating feet: Left (left foot), Down (right foot), Left (left foot), Up (right foot), Down (left foot), Right (right foot), Up (left foot), Down (right foot), Left (left foot). The right foot's Down-to-Up move and the left foot's later Down-to-Up move, each 0.25 s apart, are marked as candles.](images/pattern_candle_run.svg)

Left↔Right counts too, so the crossover from above has two candles. The crossing left foot moves from Left to Right, then from Right back to Left:

![Playfield at 120 BPM, 8th notes: Left (left foot), Down (right foot), Right (left foot), Down (right foot), Left (left foot). The left foot's Left-to-Right move and its Right-to-Left return, each 0.5 s apart, are marked as candles.](images/pattern_candle_crossover.svg)

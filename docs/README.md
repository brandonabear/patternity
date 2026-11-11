# Patternity documentation

Patternity parses StepMania `.sm` / `.ssc` charts (4-panel singles), works out which foot hits each arrow, and reports basic and "tech" metrics (jacks, footswitches, sideswitches, doublesteps, brackets, crossovers, candles).

| Page | Read it when you want to… |
|------|---------------------------|
| [Usage](../README.md#install) | Install, run the CLI, or call Patternity from Python |
| [Patterns](patterns.md) | See what each tech pattern means and the rules that limit it |
| [Architecture](architecture.md) | Understand the scope, the pipeline, where code lives, and the rules the codebase follows |
| [Footing model](footing-model.md) | Understand how footing is inferred: states, features, Viterbi, the perceptron |
| [Training workflow](training.md) | Annotate charts, retrain the weights, and check the result |
| [Development guide](development.md) | Run the checks, find where to make a change, add a footing feature, or debug surprising counts or footing |
| [File format](format.md) | Understand `.sm` / `.ssc` structure and how it maps to the parsed model |

Fixture-specific notes for hand-counted regression files live in [`tests/fixtures/canonical/README.md`](../tests/fixtures/canonical/README.md).

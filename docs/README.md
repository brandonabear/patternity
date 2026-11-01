# Patternity documentation

Patternity parses StepMania `.sm` / `.ssc` charts (4-panel singles), works out which foot hits each arrow, and reports basic and "tech" metrics (jacks, footswitches, sideswitches, doublesteps, brackets, crossovers, candles).

| Page | Read it when you want to… |
|------|---------------------------|
| [Usage](usage.md) | Install, run the CLI, or call Patternity from Python |
| [Architecture](architecture.md) | Understand the pipeline and where each piece of code lives |
| [Footing model](footing-model.md) | Understand how footing is inferred: states, features, Viterbi, the perceptron |
| [Training workflow](training.md) | Annotate charts, retrain the weights, and check the result |
| [Debugging](debugging.md) | Find out why a chart reports surprising counts or footing |
| [Design principles](design.md) | Know the rules the codebase follows and why |
| [File format](format.md) | Understand `.sm` / `.ssc` structure and how it maps to the parsed model |

Fixture-specific notes for hand-counted regression files live in [`tests/fixtures/canonical/README.md`](../tests/fixtures/canonical/README.md).

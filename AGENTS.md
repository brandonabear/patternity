# Agent Instructions

## Project Overview

`patternity` is a Python project managed via `uv` that parses and analyzes StepMania `.sm` and `.ssc`. files.

### Project Organization

See [docs/architecture.md](docs/architecture.md) for an overview of code organization and behavior.

## Agent Behavior

- Be concise with responses.
- Request clarification given ambiguous instructions or unclear implementation/design choices.
- Ensure all tests, linting, and type checks pass before completing work.
- Write code with a focus on legibility and maintainability. Avoid pre-mature optimization.
- Orchestration functions should read like a table of contents.
- Strive for immutability.
- Provide reasonable code comments that describe intent rather than functionality unless sufficiently complex.

### Checks

```bash
uv run pytest -q                       # tests
uv run ruff check src tests scripts    # lint
uv run ty check                        # type check
```

Use `ty` for type checking, not `mypy`. Suppressions are `# ty: ignore[rule]`;
`# type: ignore[code]` comments are mypy-specific and `ty` does not honor them.

## Coding Conventions

- Prefer simple `dataclass` for data containers.
- Use `slots=True` and/or `frozen=True` in dataclasses where applicable.
- Ensure complete type hints for clarity (`ty` will help call out gaps).

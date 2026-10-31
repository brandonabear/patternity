"""Learn footing weights from annotated charts with a structured perceptron.

Usage: ``python -m patternity.training [fixtures ...] [--fixtures-root DIR]``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from patternity.footing.features import FEATURE_NAMES
from patternity.footing.model import PACKAGED_WEIGHTS
from patternity.training.corpus import default_fixtures_root, load_corpus
from patternity.training.trainer import leave_one_out, load_examples, row_errors, train


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "fixtures",
        nargs="*",
        help="fixture paths relative to the fixtures root (default: training_corpus.txt)",
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        help="directory holding fixtures and training_corpus.txt (default: nearest tests/fixtures)",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--margin", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=PACKAGED_WEIGHTS)
    parser.add_argument("--no-loo", action="store_true", help="skip leave-one-out")
    args = parser.parse_args(argv)

    root = args.fixtures_root or default_fixtures_root()
    examples = load_examples(args.fixtures or load_corpus(root), root)
    if not args.no_loo:
        print("Leave-one-chart-out (per-row foot accuracy on the held-out chart):")
        for fold in leave_one_out(examples, epochs=args.epochs, margin=args.margin):
            print(
                f"  {fold.held_out:32s} {fold.accuracy:7.2%}  "
                f"({fold.errors} errors / {fold.rows} rows)"
            )

    model = train(examples, epochs=args.epochs, margin=args.margin)
    print("Training-set fit:")
    for example in examples:
        errors = row_errors(example, model.vector())
        print(f"  {example.name:32s} {errors} errors / {len(example.gold)} rows")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    model.save(args.output)
    print(f"Wrote {args.output}")
    for name in FEATURE_NAMES:
        print(f"  {name:22s} {model.weights[name]:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

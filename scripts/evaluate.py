#!/usr/bin/env python3
"""Report footing accuracy, pattern precision/recall, and disagreements per fixture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from patternity.footing import FootingModel
from patternity.simfile import read_simfile
from patternity.training import (
    default_fixtures_root,
    evaluate_annotated,
    format_report,
    leave_one_out,
    load_corpus,
    load_examples,
    parse_annotated_sm,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument("--weights", type=Path, help="weights JSON (default: packaged)")
    parser.add_argument("--show", type=int, default=20, help="disagreements to list")
    parser.add_argument(
        "--loo", action="store_true", help="also train/score leave-one-chart-out"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    console = Console()
    parser = build_parser()
    args = parser.parse_args(args=argv)

    root = args.fixtures_root or default_fixtures_root()
    fixtures = args.fixtures or load_corpus(root)

    model = FootingModel.load(args.weights) if args.weights else FootingModel.default()
    total_rows = total_errors = 0

    for rel in fixtures:
        annotated = parse_annotated_sm(read_simfile(root / rel))
        report = evaluate_annotated(rel, annotated, model)
        total_rows += report.rows
        total_errors += report.errors
        console.print(format_report(report, annotated, show=args.show))

    if total_rows:
        console.print(
            f"TOTAL: {1 - total_errors / total_rows:.2%} "
            f"({total_errors} / {total_rows} rows)"
        )

    if args.loo:
        console.print("Leave-one-chart-out:")
        for fold in leave_one_out(load_examples(fixtures, root)):
            console.print(
                f"  {fold.held_out:32s} {fold.accuracy:7.2%} ({fold.errors}/{fold.rows})"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

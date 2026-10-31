"""Annotations, weight training, and evaluation against hand-footed charts.

Run training with ``python -m patternity.training``.
"""

from patternity.training.annotations import AnnotatedChart, parse_annotated_sm
from patternity.training.corpus import default_fixtures_root, load_corpus
from patternity.training.evaluation import evaluate_annotated, format_report
from patternity.training.trainer import (
    Example,
    leave_one_out,
    load_example,
    load_examples,
    row_errors,
    train,
)

__all__ = [
    "AnnotatedChart",
    "Example",
    "default_fixtures_root",
    "evaluate_annotated",
    "format_report",
    "leave_one_out",
    "load_corpus",
    "load_example",
    "load_examples",
    "parse_annotated_sm",
    "row_errors",
    "train",
]

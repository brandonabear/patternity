"""Annotations, weight training, and evaluation against hand-footed charts.

Run training with ``python -m patternity.training``.
"""

from patternity.training.annotations import AnnotatedChart, parse_annotated_sm
from patternity.training.corpus import (
    add_fixture_arguments,
    default_fixtures_root,
    load_corpus,
    load_holdout,
)
from patternity.training.evaluation import accuracy, evaluate_annotated, format_report
from patternity.training.trainer import (
    Example,
    format_folds,
    leave_one_out,
    load_example,
    load_examples,
    row_errors,
    train,
)

__all__ = [
    "AnnotatedChart",
    "Example",
    "accuracy",
    "add_fixture_arguments",
    "default_fixtures_root",
    "evaluate_annotated",
    "format_folds",
    "format_report",
    "leave_one_out",
    "load_corpus",
    "load_holdout",
    "load_example",
    "load_examples",
    "parse_annotated_sm",
    "row_errors",
    "train",
]

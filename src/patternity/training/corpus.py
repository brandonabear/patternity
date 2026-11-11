"""Locate the annotated fixtures and the chart lists used for training and hold-out."""

from __future__ import annotations

from pathlib import Path

CORPUS_FILE = "training_corpus.txt"
HOLDOUT_FILE = "holdout_corpus.txt"


def default_fixtures_root(start: Path | None = None) -> Path:
    """Nearest ``tests/fixtures`` at or above ``start`` (default: the current directory)."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / "tests" / "fixtures"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"no tests/fixtures directory at or above {here}; pass --fixtures-root")


def _read_fixture_list(path: Path) -> list[str]:
    """One fixture path per line; ``#`` starts a comment, blank lines are ignored."""
    paths: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            paths.append(entry)
    return paths


def load_corpus(root: Path) -> list[str]:
    """Fixture paths (relative to ``root``) listed in ``root/training_corpus.txt``."""
    return _read_fixture_list(root / CORPUS_FILE)


def load_holdout(root: Path) -> list[str]:
    """Fixture paths (relative to ``root``) listed in ``root/holdout_corpus.txt``.

    Hold-out charts are annotated but never trained on; they measure how well
    the model generalizes to unseen charts.
    """
    return _read_fixture_list(root / HOLDOUT_FILE)

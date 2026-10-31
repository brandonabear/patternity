"""Locate the annotated fixtures and the list of charts used for training."""

from __future__ import annotations

from pathlib import Path

CORPUS_FILE = "training_corpus.txt"


def default_fixtures_root(start: Path | None = None) -> Path:
    """Nearest ``tests/fixtures`` at or above ``start`` (default: the current directory)."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / "tests" / "fixtures"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"no tests/fixtures directory at or above {here}; pass --fixtures-root"
    )


def load_corpus(root: Path) -> list[str]:
    """Fixture paths (relative to ``root``) listed in ``root/training_corpus.txt``.

    One path per line; ``#`` starts a comment, blank lines are ignored.
    """
    paths: list[str] = []
    for line in (root / CORPUS_FILE).read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            paths.append(entry)
    return paths

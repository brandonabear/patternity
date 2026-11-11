"""Learned transition-cost weights and their JSON storage."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from patternity.footing.features import FEATURE_NAMES

# Filesystem path to the packaged weights, used only as the training CLI's
# ``--output`` default: writing needs a real path, whereas reading goes through
# ``importlib.resources`` (see ``FootingModel.default``) so it also works when the
# package is installed as a zip or wheel.
PACKAGED_WEIGHTS = Path(__file__).resolve().parent.parent / "data" / "footing_weights.json"


@dataclass
class FootingModel:
    """Linear transition-cost weights keyed by feature name."""

    weights: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def vector(self) -> list[float]:
        return [float(self.weights.get(name, 0.0)) for name in FEATURE_NAMES]

    @classmethod
    def from_vector(
        cls, vector: Sequence[float], metadata: dict[str, Any] | None = None
    ) -> FootingModel:
        return cls(
            weights={name: float(v) for name, v in zip(FEATURE_NAMES, vector, strict=True)},
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(FEATURE_NAMES),
            "weights": {name: self.weights.get(name, 0.0) for name in FEATURE_NAMES},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FootingModel:
        """Load weights keyed by feature name.

        A feature missing from ``data`` weighs 0.0, so older files still load
        after a feature is added. A name that is not a feature raises: it is a
        renamed or removed feature whose weight would otherwise be dropped.
        """
        weights = {str(k): float(v) for k, v in dict(data["weights"]).items()}
        unknown = sorted(set(weights) - set(FEATURE_NAMES))
        if unknown:
            raise ValueError(f"weights for unknown features: {', '.join(unknown)}")
        return cls(weights=weights, metadata=dict(data.get("metadata", {})))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> FootingModel:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def default(cls) -> FootingModel:
        """Weights shipped with the package (``patternity/data/footing_weights.json``)."""
        resource = files("patternity").joinpath("data", "footing_weights.json")
        return cls.from_dict(json.loads(resource.read_text(encoding="utf-8")))

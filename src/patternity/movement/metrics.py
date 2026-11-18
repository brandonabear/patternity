from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MovementMetrics:
    """Player movement metrics from foot-path resolution."""

    direction_shifts: int = 0
    total_cost: float = 0.0
    foot_path_feasible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

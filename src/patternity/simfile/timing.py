import itertools
import math


class TimingEngine:
    """Track elapsed beats and seconds."""

    def __init__(
        self,
        bpms: dict[float, float] | None,
        stops: dict[float, float] | None,
    ):
        # Add default ceiling of (math.inf, math.nan)
        self.bpms = (
            sorted([*bpms.items(), (math.inf, math.nan)], key=lambda x: x[0]) if bpms else []
        )
        self.stops = sorted(stops.items(), key=lambda x: x[0]) if stops else []

    def convert_beat_to_seconds(self, target_beat: float) -> float:
        """Convert a target beat to elapsed seconds.

        Only handles BPM changes and stops. ``#OFFSET`` is intentionally not
        applied: every consumer compares differences between timestamps, where a
        constant offset cancels out, so timestamps are seconds from beat 0.
        """

        # Calculate elapsed time across BPM changes.
        elapsed_time = 0.0
        for (current_beat, current_bpm), (next_beat, _) in itertools.pairwise(self.bpms):
            if target_beat <= current_beat:
                break
            if target_beat <= next_beat:
                elapsed_time += (target_beat - current_beat) * (60.0 / current_bpm)
                break
            elapsed_time += (next_beat - current_beat) * (60.0 / current_bpm)

        # Increment elapsed time across stops.
        for stop_beat, stop_duration in self.stops:
            # Stops applied AFTER target beat
            if stop_beat < target_beat:
                elapsed_time += stop_duration
            else:
                break

        return elapsed_time

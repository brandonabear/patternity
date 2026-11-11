"""Reading and parsing StepMania ``.sm`` / ``.ssc`` files into ``Song`` / ``Chart`` /
``NoteRow``."""

from patternity.simfile.notes import (
    ANCHORED_NOTES,
    MINE_NOTES,
    PANELS,
    PRESSABLE_NOTES,
    TAIL_NOTES,
    InvalidNoteRow,
    NoteRow,
    NoteType,
    Panel,
)
from patternity.simfile.parser import MissingTimingError, SimfileError, StepmaniaFileParser
from patternity.simfile.reader import UnsupportedSimfileSuffix, read_simfile
from patternity.simfile.song import (
    Chart,
    ChartMetadata,
    Difficulty,
    Header,
    SkippedChart,
    Song,
)

__all__ = [
    "ANCHORED_NOTES",
    "MINE_NOTES",
    "PANELS",
    "PRESSABLE_NOTES",
    "TAIL_NOTES",
    "Chart",
    "ChartMetadata",
    "Difficulty",
    "Header",
    "InvalidNoteRow",
    "MissingTimingError",
    "NoteRow",
    "NoteType",
    "Panel",
    "SimfileError",
    "SkippedChart",
    "Song",
    "StepmaniaFileParser",
    "UnsupportedSimfileSuffix",
    "read_simfile",
]

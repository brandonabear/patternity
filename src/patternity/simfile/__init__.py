"""Reading and parsing StepMania ``.sm`` / ``.ssc`` files into ``Song`` / ``Chart`` / ``NoteRow``."""

from patternity.simfile.notes import NoteRow, NoteType
from patternity.simfile.parser import StepmaniaFileParser
from patternity.simfile.reader import UnsupportedSimfileSuffix, read_simfile
from patternity.simfile.song import Chart, ChartMetadata, Difficulty, Header, Song

__all__ = [
    "Chart",
    "ChartMetadata",
    "Difficulty",
    "Header",
    "NoteRow",
    "NoteType",
    "Song",
    "StepmaniaFileParser",
    "UnsupportedSimfileSuffix",
    "read_simfile",
]

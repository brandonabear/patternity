import json
from pathlib import Path

from patternity.simfile.song import Song


def serialize(song: Song, output: Path) -> Path:
    """Serialize a song to JSON, creating the output directory if needed."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(song.to_dict(), indent=2) + "\n", encoding="utf-8")
    return output.resolve()


def deserialize(path: Path) -> Song:
    """Deserialize a song from JSON"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return Song.from_dict(data)


def output_path(input_file: Path, output_dir: Path) -> Path:
    """Build serialized output path (JSON)."""
    return output_dir / f"{input_file.stem}.json"

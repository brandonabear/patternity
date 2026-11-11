from pathlib import Path

from patternity.simfile.parser import StepmaniaFileParser
from patternity.simfile.serializer import deserialize, serialize

_SIMFILE = (
    "#TITLE:t;\n#SELECTABLE:YES;\n#BPMS:0.000=120.000;\n"
    "#NOTES:\n     dance-single:\n     t:\n     Challenge:\n     1:\n"
    "     0.5,0,0,0,0,2,2,0,1,0,0:\n2000\n3100\n,\n;\n"
)


def test_song_round_trips_through_json(tmp_path: Path) -> None:
    song = StepmaniaFileParser.parse(_SIMFILE)
    restored = deserialize(serialize(song, tmp_path / "nested" / "song.json"))
    assert restored == song


def test_round_trip_keeps_selectable_and_zero_radar_values(tmp_path: Path) -> None:
    song = StepmaniaFileParser.parse(_SIMFILE)
    restored = deserialize(serialize(song, tmp_path / "song.json"))

    assert restored.header.selectable is True
    radar = restored.charts[0].metadata.radar
    assert (radar.stream, radar.voltage, radar.jumps, radar.holds) == (0.5, 0.0, 0, 1)

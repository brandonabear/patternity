"""
SM/SSC File Reference:
https://outfox.wiki/en/dev/mode-support/sm-support
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from dataclasses import fields as _fields
from enum import StrEnum
from typing import Any

from patternity.simfile.notes import NoteRow


def parse_beat_value_map(value: str) -> dict[float, float]:
    """Parse ``beat=value,beat=value`` (as in ``#BPMS`` / ``#STOPS``) into a dict."""
    beat_value_map = {}
    if value.strip():
        for beat_value in value.split(","):
            b, v = beat_value.split("=", maxsplit=1)
            beat_value_map[float(b)] = float(v)
    return beat_value_map


@dataclass
class Header:
    title: str | None = None
    subtitle: str | None = None
    artist: str | None = None
    titletranslit: str | None = None
    subtitletranslit: str | None = None
    artisttranslit: str | None = None
    genre: str | None = None
    credit: str | None = None
    banner: str | None = None
    background: str | None = None
    lyricspath: str | None = None
    cdtitle: str | None = None
    music: str | None = None
    samplestart: float | None = None
    samplelength: float | None = None
    displaybpm: str | float | None = None
    selectable: bool | None = None
    bgchanges: str | None = None
    fgchanges: str | None = None
    offset: float | None = None
    stops: dict[float, float] | None = None
    bpms: dict[float, float] | None = None

    def set_tag(self, tag: str, value: str) -> None:
        """Store a header tag such as ``#TITLE`` in the field of the same name.

        Tags with no matching field are ignored.
        """
        name = tag.removeprefix("#").lower()
        if name in _HEADER_FIELDS:
            setattr(self, name, _HEADER_CONVERTERS.get(name, str)(value))

    def to_dict(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in _fields(self)
            if getattr(self, f.name) is not None
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Header:
        obj = cls()
        for field_name in _fields(obj):
            # Skip missing keys
            value = data.get(field_name.name)
            if value is None:
                continue

            if field_name.name in {"selectable"}:
                # ``to_dict`` writes a bool; older JSON may hold the raw "YES" / "NO".
                selectable = value if isinstance(value, bool) else str(value).lower() == "yes"
                setattr(obj, field_name.name, selectable)
            elif isinstance(value, dict):
                setattr(
                    obj, field_name.name, {float(k): float(v) for k, v in value.items()}
                )
            elif field_name.name in {"samplestart", "samplelength", "offset"}:
                setattr(obj, field_name.name, float(value))
            else:
                setattr(obj, field_name.name, value)
        return obj


def _number_or_text(value: str) -> str | float:
    """``#DISPLAYBPM`` is a number, or text such as a ``120:180`` range or ``*``."""
    try:
        return float(value)
    except ValueError:
        return value


def _is_yes(value: str) -> bool:
    return value.lower() == "yes"


_HEADER_FIELDS = frozenset(f.name for f in _fields(Header))
# How a header tag's text becomes its field value; fields not listed stay text.
_HEADER_CONVERTERS: dict[str, Callable[[str], Any]] = {
    "samplestart": float,
    "samplelength": float,
    "displaybpm": _number_or_text,
    "selectable": _is_yes,
    "offset": float,
    "stops": parse_beat_value_map,
    "bpms": parse_beat_value_map,
}


class Difficulty(StrEnum):
    BEGINNER = "Beginner"
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    CHALLENGE = "Challenge"
    EDIT = "Edit"

    @classmethod
    def from_sm(cls, sm_string: str) -> Difficulty:
        for member in cls:
            if member.value.lower() == sm_string.lower():
                return member
        raise ValueError(f"Unable to parse difficulty: {sm_string}")


@dataclass
class GrooveRadar:
    stream: float | None = None
    voltage: float | None = None
    air: float | None = None
    freeze: float | None = None
    chaos: float | None = None
    steps: int | None = None
    taps: int | None = None
    jumps: int | None = None
    holds: int | None = None
    mines: int | None = None
    hands: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in _fields(self)
            if getattr(self, f.name) is not None
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GrooveRadar:
        # ``is None`` rather than truthiness: zero is a real radar value.
        def ratio(name: str) -> float | None:
            value = data.get(name)
            return None if value is None else float(value)

        def count(name: str) -> int | None:
            value = data.get(name)
            return None if value is None else int(value)

        return cls(
            stream=ratio("stream"),
            voltage=ratio("voltage"),
            air=ratio("air"),
            freeze=ratio("freeze"),
            chaos=ratio("chaos"),
            steps=count("steps"),
            taps=count("taps"),
            jumps=count("jumps"),
            holds=count("holds"),
            mines=count("mines"),
            hands=count("hands"),
        )


@dataclass
class ChartMetadata:
    mode: str
    credit: str
    difficulty: Difficulty
    rating: float
    radar: GrooveRadar

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "credit": self.credit,
            "difficulty": self.difficulty.value,
            "rating": self.rating,
            "radar": self.radar.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChartMetadata:
        return cls(
            mode=data["mode"],
            credit=data["credit"],
            difficulty=Difficulty(str(data["difficulty"])),
            rating=float(data["rating"]),
            radar=GrooveRadar.from_dict(data["radar"]),
        )


@dataclass
class Chart:
    metadata: ChartMetadata
    notes: list[NoteRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "notes": [note.to_dict() for note in self.notes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chart:
        return cls(
            metadata=ChartMetadata.from_dict(data["metadata"]),
            notes=[NoteRow.from_dict(n) for n in data.get("notes", [])],
        )


@dataclass(frozen=True)
class SkippedChart:
    """A chart the parser found but could not model (e.g. doubles), and why."""

    mode: str
    difficulty: str
    reason: str


@dataclass
class Song:
    header: Header
    charts: list[Chart] = field(default_factory=list)
    # Charts left out of ``charts``. Not serialized.
    skipped_charts: list[SkippedChart] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "charts": [chart.to_dict() for chart in self.charts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Song:
        return cls(
            header=Header.from_dict(data["header"]),
            charts=[Chart.from_dict(c) for c in data.get("charts", [])],
        )

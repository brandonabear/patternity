"""
SM/SSC File Reference:
https://outfox.wiki/en/dev/mode-support/sm-support
"""

from dataclasses import dataclass, field
from dataclasses import fields as _fields
from enum import StrEnum
from typing import Any

from patternity.models.engine import NoteRow

HEADER_SETTERS = {
    "#TITLE": "set_title",
    "#SUBTITLE": "set_subtitle",
    "#ARTIST": "set_artist",
    "#TITLETRANSLIT": "set_titletranslit",
    "#SUBTITLETRANSLIT": "set_subtitletranslit",
    "#ARTISTTRANSLIT": "set_artisttranslit",
    "#GENRE": "set_genre",
    "#CREDIT": "set_credit",
    "#BANNER": "set_banner",
    "#BACKGROUND": "set_background",
    "#LYRICSPATH": "set_lyricspath",
    "#CDTITLE": "set_cdtitle",
    "#MUSIC": "set_music",
    "#SAMPLESTART": "set_samplestart",
    "#SAMPLELENGTH": "set_samplelength",
    "#DISPLAYBPM": "set_displaybpm",
    "#SELECTABLE": "set_selectable",
    "#BGCHANGES": "set_bgchanges",
    "#FGCHANGES": "set_fgchanges",
    "#OFFSET": "set_offset",
    "#STOPS": "set_stops",
    "#BPMS": "set_bpms",
}


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
    notes: str | None = None

    def set_title(self, value: str) -> None:
        self.title = value

    def set_subtitle(self, value: str) -> None:
        self.subtitle = value

    def set_artist(self, value: str) -> None:
        self.artist = value

    def set_titletranslit(self, value: str) -> None:
        self.titletranslit = value

    def set_subtitletranslit(self, value: str) -> None:
        self.subtitletranslit = value

    def set_artisttranslit(self, value: str) -> None:
        self.artisttranslit = value

    def set_genre(self, value: str) -> None:
        self.genre = value

    def set_credit(self, value: str) -> None:
        self.credit = value

    def set_banner(self, value: str) -> None:
        self.banner = value

    def set_background(self, value: str) -> None:
        self.background = value

    def set_lyricspath(self, value: str) -> None:
        self.lyricspath = value

    def set_cdtitle(self, value: str) -> None:
        self.cdtitle = value

    def set_music(self, value: str) -> None:
        self.music = value

    def set_samplestart(self, value: str) -> None:
        self.samplestart = float(value)

    def set_samplelength(self, value: str) -> None:
        self.samplelength = float(value)

    def set_displaybpm(self, value: str) -> None:
        try:
            self.displaybpm = float(value)
        except ValueError:
            self.displaybpm = value

    def set_selectable(self, value: str) -> None:
        self.selectable = value.lower() == "yes"

    def set_bgchanges(self, value: str) -> None:
        self.bgchanges = value

    def set_fgchanges(self, value: str) -> None:
        self.fgchanges = value

    def set_offset(self, value: str) -> None:
        self.offset = float(value)

    def set_stops(self, value: str) -> None:
        stops = {}
        if value.strip():
            for stop in value.split(","):
                time_val, duration = stop.split("=")
                stops[float(time_val)] = float(duration)
        self.stops = stops

    def set_bpms(self, value: str) -> None:
        bpms = {}
        if value.strip():
            for bpm in value.split(","):
                time_val, bpm_value = bpm.split("=")
                bpms[float(time_val)] = float(bpm_value)
        self.bpms = bpms

    def to_dict(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in _fields(self)
            if getattr(self, f.name) is not None
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Header:
        obj = cls()
        skip_booleans = {"selectable"}
        for field_name in _fields(obj):
            value = data.get(field_name.name)
            if value is None:
                continue
            if field_name.name in skip_booleans:
                setattr(obj, field_name.name, value == "yes")
            elif isinstance(value, dict):
                setattr(
                    obj, field_name.name, {float(k): float(v) for k, v in value.items()}
                )
            elif field_name.name in {"samplestart", "samplelength", "offset"}:
                setattr(obj, field_name.name, float(value))
            else:
                setattr(obj, field_name.name, value)
        return obj


class Difficulty(StrEnum):
    BEGINNER = "Beginner"
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    CHALLENGE = "Challenge"

    @classmethod
    def from_sm(cls, sm_string: str) -> Difficulty:
        for member in cls:
            if member.value.lower() == sm_string.lower():
                return member
        raise ValueError(f"Unable to parse difficulty: {sm_string}")


RADAR_FIELDS = [
    "stream",
    "voltage",
    "air",
    "freeze",
    "chaos",
    "steps",
    "taps",
    "jumps",
    "holds",
    "mines",
    "hands",
]


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
        return cls(
            stream=float(data["stream"]) if data.get("stream") else None,
            voltage=float(data["voltage"]) if data.get("voltage") else None,
            air=float(data["air"]) if data.get("air") else None,
            freeze=float(data["freeze"]) if data.get("freeze") else None,
            chaos=float(data["chaos"]) if data.get("chaos") else None,
            steps=int(data["steps"]) if data.get("steps") else None,
            taps=int(data["taps"]) if data.get("taps") else None,
            jumps=int(data["jumps"]) if data.get("jumps") else None,
            holds=int(data["holds"]) if data.get("holds") else None,
            mines=int(data["mines"]) if data.get("mines") else None,
            hands=int(data["hands"]) if data.get("hands") else None,
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


@dataclass
class Song:
    header: Header
    charts: list[Chart] = field(default_factory=list)

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

    def format_info(self) -> str:
        h = self.header
        lines = [
            "=== Song Information ===",
            f"Title: {h.title}",
            f"Artist: {h.artist}",
            f"BPMs: {h.displaybpm or h.bpms}",
            "",
        ]
        return "\n".join(lines)

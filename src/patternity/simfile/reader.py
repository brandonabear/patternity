from pathlib import Path


class UnsupportedSimfileSuffix(ValueError):
    """Simfile suffix must be one of [`.sm`, `.ssc`]."""


def read_simfile(file: Path) -> str:
    if file.suffix not in [".sm", ".ssc"]:
        raise UnsupportedSimfileSuffix(
            "Invalid file extension: must be one of [`.sm`, `.ssc`]: "
            + f"Received {file.name}"
        )
    return file.read_text(encoding="utf-8")

"""Command-line interface for Patternity library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from patternity.analysis import analyze_chart
from patternity.simfile.parser import SimfileError, StepmaniaFileParser
from patternity.simfile.reader import UnsupportedSimfileSuffix, read_simfile
from patternity.simfile.serializer import output_path, serialize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patternity",
        description="Parse and analyze StepMania charts.",
    )
    parser.add_argument(
        "--file",
        "-f",
        help="The file to parse.",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--analyze",
        "-a",
        help="Analyze the song.",
        action="store_true",
        default=False,
        required=False,
    )
    parser.add_argument(
        "--serialize",
        "-s",
        help="Serialize the parsed song to JSON.",
        action="store_true",
        default=False,
        required=False,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Directory for --serialize output (default: data/).",
        type=Path,
        required=False,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    console = Console()
    argument_parser = build_parser()
    args = argument_parser.parse_args(args=argv)
    if args.output and not args.serialize:
        argument_parser.error("--output only applies with --serialize")

    try:
        data = read_simfile(args.file)
        console.print(f"Read file: {args.file.name}")
        song = StepmaniaFileParser.parse(data)
    except (OSError, UnsupportedSimfileSuffix, SimfileError) as exc:
        console.print(f"Error: {exc}")
        return 1
    console.print(f"Parsed song: {song.header.title}")
    for skipped in song.skipped_charts:
        console.print(f"Skipped {skipped.mode} {skipped.difficulty} chart: {skipped.reason}")

    if args.analyze:
        for chart in song.charts:
            console.print(f"{chart.metadata.difficulty} {chart.metadata.rating:g}")
            console.print(analyze_chart(chart).to_dict())

    if args.serialize:
        out_dir = args.output or Path("data/")
        resolved_path = serialize(song, output_path(args.file, out_dir))
        console.print(f"Serialized song to: {resolved_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

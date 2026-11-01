"""Command-line interface for Patternity library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from patternity.analysis import Analyzer
from patternity.simfile.parser import StepmaniaFileParser
from patternity.simfile.reader import read_simfile
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
        help="Serialize the parsed or analyzed song to disk.",
        action="store_true",
        default=False,
        required=False,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="The directory to output the parsed song results to.",
        type=Path,
        required=False,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    console = Console()
    argument_parser = build_parser()
    args = argument_parser.parse_args(args=argv)

    data = read_simfile(args.file)
    console.print(f"Read file: {args.file.name}")

    song = StepmaniaFileParser.parse(data)
    console.print(f"Parsed song: {song.header.title}")

    if args.analyze:
        for chart in song.charts:
            analyzer = Analyzer(chart)
            console.print(analyzer.analyze())

    if args.serialize:
        out_dir = args.output or Path("data/")
        resolved_path = serialize(song, output_path(args.file, out_dir))
        console.print(f"Serialized song to: {resolved_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

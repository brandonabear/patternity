import argparse
import sys
from pathlib import Path

from rich.console import Console

from patternity.parser import StepmaniaFileParser


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
    return parser

def main(argv: list[str] | None = None) -> int:
    argument_parser = build_parser()
    args = argument_parser.parse_args(args=argv)
    console = Console()

    with open(args.file, "r") as f:
        data = f.read()
        console.print(f"Successfully read file: {args.file.name}")

    song = StepmaniaFileParser.parse(data)
    console.print(song.header)
    console.print(song.charts[0].metadata)

    return 0

if __name__ == "__main__":
    sys.exit(main())

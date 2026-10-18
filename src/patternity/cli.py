import argparse
import sys
from pathlib import Path

from rich.console import Console

from patternity.parser import StepmaniaFileParser
from patternity.serializer import output_path, serialize


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
        "--output",
        "-o",
        help="The directory to output the parsed song results to.",
        type=Path,
        default=Path("data"),
        required=False,
    )
    return parser

def main(argv: list[str] | None = None) -> int:
    console = Console()
    argument_parser = build_parser()
    args = argument_parser.parse_args(args=argv)

    if not args.file.suffix in [".sm", ".ssc"]:
        console.print(f"Invalid extension: must be a .sm or .ssc file: {args.file.name}")
        return 1

    with open(args.file, "r") as f:
        data = f.read()
    console.print(f"Read file: {args.file.name}")

    song = StepmaniaFileParser.parse(data)
    console.print(f"Parsed song: {song.header.title}")

    if args.output:
        serialize(song, output_path(args.file, args.output))
        console.print(f"Serialized song to: {output_path(args.file, args.output)}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

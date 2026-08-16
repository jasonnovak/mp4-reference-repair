from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import RepairError, compatibility, default_output, describe, inspect_media, repair


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mp4repair",
        description="Repair a truncated MP4/MOV using a healthy recording as a reference.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    fix = sub.add_parser("repair", help="repair a damaged recording")
    fix.add_argument("reference", help="healthy clip from the same device/settings")
    fix.add_argument("damaged", help="truncated or damaged clip")
    fix.add_argument("-o", "--output", help="output path (default: *_repaired.ext)")
    fix.add_argument(
        "--strategy",
        choices=("auto", "reference", "deep-scan", "sony-xavc", "remux"),
        default="auto",
        help="deep-scan forces untrunc -s to scan past unknown/corrupt byte sequences",
    )
    fix.add_argument("--engine", help="path to untrunc executable")
    fix.add_argument("--extractor", help="path to recover_mp4.exe for Sony XAVC recovery")
    fix.add_argument("--overwrite", action="store_true", help="replace an existing output")

    check = sub.add_parser("check", help="inspect files and score reference compatibility")
    check.add_argument("damaged")
    check.add_argument("--reference")
    sub.add_parser("gui", help="open the desktop interface")
    return parser


def _gui() -> int:
    try:
        from .gui import launch

        launch()
        return 0
    except ImportError as exc:
        print(f"GUI unavailable: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.command or args.command == "gui":
        return _gui()
    try:
        if args.command == "check":
            damaged = inspect_media(args.damaged)
            print(describe(damaged))
            if args.reference:
                reference = inspect_media(args.reference)
                print("\nReference\n---------")
                print(describe(reference))
                score, notes = compatibility(reference, damaged)
                print(f"\nCompatibility: {'unknown' if score is None else str(score) + '/100'}")
                for note in notes:
                    print(f"- {note}")
            return 0

        output = Path(args.output).resolve() if args.output else default_output(args.damaged)
        print(f"Output: {output}")
        result = repair(
            args.reference,
            args.damaged,
            output,
            strategy=args.strategy,
            engine=args.engine,
            extractor=args.extractor,
            overwrite=args.overwrite,
            log=print,
        )
        print(f"\nRepair complete ({result.method}): {result.output}")
        return 0
    except (RepairError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

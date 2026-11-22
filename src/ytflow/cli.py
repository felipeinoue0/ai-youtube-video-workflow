"""Command-line entry point. Commands are added one workflow step at a time."""

from __future__ import annotations

import argparse

from ytflow import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytflow",
        description="Guide a YouTube video from channel branding to publish.",
    )
    parser.add_argument("--version", action="version", version=f"ytflow {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0

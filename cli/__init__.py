"""Command-line interface for Garmin Cycling.

This package holds everything specific to the terminal frontend:

* :mod:`cli.parser`    -- argparse wiring (``build_parser``).
* :mod:`cli.commands`  -- the subcommand handlers.
* :mod:`cli.reporting` -- plain-text formatters for console output.

The top-level ``main.py`` is only a thin launcher that calls :func:`main`.
"""

from __future__ import annotations

import logging

from .parser import build_parser

__all__ = ["build_parser", "main"]


def main() -> None:
    """Parse command-line arguments and dispatch to the chosen subcommand."""
    logging.basicConfig(level=logging.INFO)

    parser = build_parser()
    args = parser.parse_args()

    # Require an explicit subcommand; show help and exit otherwise.
    if not getattr(args, "command", None):
        parser.print_help()
        return

    args.func(args)

#!/usr/bin/env python3
"""Thin entry point for the Garmin Cycling CLI.

All argument parsing, command handling and output formatting live in the
:mod:`cli` package. This module only launches it, so ``python main.py ...``
keeps working as the documented entry point.
"""

from cli import main

if __name__ == "__main__":
    main()

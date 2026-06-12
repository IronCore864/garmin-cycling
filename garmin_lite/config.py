"""Configuration loaded entirely from environment variables.

Only Garmin CN and Garmin Global credentials are required.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    cn_email: str
    cn_password: str
    global_email: str
    global_password: str


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config() -> Config:
    """Load all settings from environment variables."""
    return Config(
        cn_email=_require("GARMIN_CN_EMAIL"),
        cn_password=_require("GARMIN_CN_PASSWORD"),
        global_email=_require("GARMIN_GLOBAL_EMAIL"),
        global_password=_require("GARMIN_GLOBAL_PASSWORD"),
    )

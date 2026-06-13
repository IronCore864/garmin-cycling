"""Credential configuration loaded from an env file and/or environment variables.

Supports two accounts:
  - CN account (source), used by all single-account features.
  - Global account (target), only required for syncing.

Recognised keys (env file or environment variables):
  GARMIN_CN_EMAIL / GARMIN_CN_PASSWORD       (CN account)
  GARMIN_GLOBAL_EMAIL / GARMIN_GLOBAL_PASSWORD (Global account)
  username / password                         (legacy aliases for the CN account)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Default env file lives at the repository root (one level above this package).
DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / "env"


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


@dataclass(frozen=True)
class Config:
    cn: Credentials
    global_: Credentials | None = None

    def require_global(self) -> Credentials:
        if self.global_ is None:
            raise RuntimeError(
                "Garmin Global credentials are required for this operation. "
                "Set GARMIN_GLOBAL_EMAIL and GARMIN_GLOBAL_PASSWORD."
            )
        return self.global_


def _parse_env_file(env_path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    path = Path(env_path)
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_config(env_path: str | Path | None = None) -> Config:
    """Load credentials from an env file, overridden by environment variables.

    Args:
        env_path: Path to the env file. Defaults to ``<repo>/env``.

    Returns:
        A populated Config. CN credentials are required; Global is optional.
    """
    values = _parse_env_file(env_path if env_path is not None else DEFAULT_ENV_PATH)
    # Environment variables take precedence over the env file.
    values.update({k: v for k, v in os.environ.items() if v})

    cn_email = values.get("GARMIN_CN_EMAIL") or values.get("username")
    cn_password = values.get("GARMIN_CN_PASSWORD") or values.get("password")
    if not cn_email or not cn_password:
        raise RuntimeError(
            "Missing Garmin CN credentials. Set GARMIN_CN_EMAIL/GARMIN_CN_PASSWORD "
            "(or legacy username/password)."
        )

    global_email = values.get("GARMIN_GLOBAL_EMAIL")
    global_password = values.get("GARMIN_GLOBAL_PASSWORD")
    global_creds = (
        Credentials(global_email, global_password)
        if global_email and global_password
        else None
    )

    return Config(cn=Credentials(cn_email, cn_password), global_=global_creds)

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


# Banister TRIMP sex coefficients (exponential weighting factor).
_TRIMP_K = {"male": 1.92, "female": 1.67}


@dataclass(frozen=True)
class AthleteProfile:
    """Heart-rate parameters needed for HR-based training-load (TRIMP).

    ``max_hr`` may be omitted if ``age`` is provided (estimated via Tanaka).
    ``sex`` selects the TRIMP exponential coefficient.
    """

    resting_hr: int | None = None
    max_hr: int | None = None
    sex: str = "male"
    age: int | None = None

    def resolve_max_hr(self) -> int:
        """Return configured max HR, else estimate from age (Tanaka).

        Raises:
            RuntimeError: If max HR is neither configured nor derivable.
        """
        if self.max_hr:
            return int(self.max_hr)
        if self.age:
            # Tanaka et al. (2001): HRmax = 208 - 0.7 * age.
            return int(round(208 - 0.7 * self.age))
        raise RuntimeError(
            "Max HR unavailable: set GARMIN_MAX_HR (or GARMIN_AGE to estimate it)."
        )

    def trimp_params(self) -> tuple[int, int, float]:
        """Resolve ``(resting_hr, max_hr, k)`` for TRIMP, validating inputs.

        Raises:
            RuntimeError: If resting HR is missing, max HR is unresolvable, or
                the HR reserve range is non-positive.
        """
        if self.resting_hr is None:
            raise RuntimeError("Resting HR unavailable: set GARMIN_RESTING_HR.")
        max_hr = self.resolve_max_hr()
        if max_hr - self.resting_hr <= 0:
            raise RuntimeError("Max HR must be greater than resting HR.")
        k = _TRIMP_K.get(self.sex.lower(), _TRIMP_K["male"])
        return int(self.resting_hr), max_hr, k


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


def _as_int(value: str | None) -> int | None:
    """Parse an optional integer config value, ignoring blanks/garbage."""
    if value is None or not str(value).strip():
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def load_athlete_profile(env_path: str | Path | None = None) -> AthleteProfile:
    """Load HR parameters for training-load from env file + environment.

    Recognised keys (env file or environment variables, env vars win):
    ``GARMIN_RESTING_HR``, ``GARMIN_MAX_HR``, ``GARMIN_SEX``, ``GARMIN_AGE``.

    Unlike :func:`load_config`, this does not require Garmin credentials, since
    training-load analysis runs offline against local FIT files.
    """
    values = _parse_env_file(env_path if env_path is not None else DEFAULT_ENV_PATH)
    values.update({k: v for k, v in os.environ.items() if v})

    sex = (values.get("GARMIN_SEX") or "male").strip().lower()
    if sex not in ("male", "female"):
        sex = "male"

    return AthleteProfile(
        resting_hr=_as_int(values.get("GARMIN_RESTING_HR")),
        max_hr=_as_int(values.get("GARMIN_MAX_HR")),
        sex=sex,
        age=_as_int(values.get("GARMIN_AGE")),
    )

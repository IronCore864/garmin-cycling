"""Core Garmin Connect client: authentication and low-level requests.

Wraps a per-instance ``garth.Client`` so that multiple accounts (for
example Garmin CN and Garmin Global) can be used simultaneously.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

warnings.filterwarnings("ignore", category=DeprecationWarning)
import garth  # noqa: E402

logger = logging.getLogger("garmin")

_LOGIN_RETRIES = 7
# Graduated delay schedule (seconds). Garmin's SSO rate limits can persist
# for several minutes, so we escalate aggressively.
_RETRY_DELAYS = [5, 15, 30, 60, 120, 180]

# Cached OAuth tokens are reused across runs to avoid repeated full SSO logins
# (which Garmin rate-limits with 429s). Override the location with GARMINTOKENS.
_DEFAULT_TOKEN_DIR = Path.home() / ".cache" / "garmin-cycling" / "tokens"
# Writable fallback for read-only/serverless filesystems (e.g. Vercel/Lambda,
# where only /tmp is writable).
_TMP_TOKEN_DIR = Path(tempfile.gettempdir()) / "garmin-cycling" / "tokens"


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "too many requests" in text


def _is_writable(path: Path) -> bool:
    """Return True if ``path`` (the nearest existing ancestor) is writable."""
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    return os.access(p, os.W_OK)


@dataclass
class BaseClient:
    """Authenticated Garmin Connect client backed by its own garth session."""

    email: str
    password: str
    is_cn: bool = False
    _logged_in: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._garth = garth.Client(pool_connections=20, pool_maxsize=20)

    @property
    def domain(self) -> str:
        return "garmin.cn" if self.is_cn else "garmin.com"

    @property
    def garth(self) -> garth.Client:
        """The underlying garth client (configured after login)."""
        return self._garth

    @property
    def _region(self) -> str:
        return "CN" if self.is_cn else "GLOBAL"

    @property
    def _token_env(self) -> str | None:
        """A serialized token blob from an env var, if provided.

        ``GARMIN_CN_TOKENS`` / ``GARMIN_GLOBAL_TOKENS`` let serverless
        deployments (e.g. Vercel) supply tokens without a writable disk.
        """
        return os.environ.get(f"GARMIN_{self._region}_TOKENS")

    @property
    def _token_dir(self) -> Path:
        """Per-account directory where this client's OAuth tokens are cached."""
        base = os.environ.get("GARMINTOKENS")
        if base:
            base_path = Path(base).expanduser()
        elif _is_writable(_DEFAULT_TOKEN_DIR.parent.parent):
            base_path = _DEFAULT_TOKEN_DIR
        else:
            # Home dir is read-only (e.g. serverless): fall back to a writable
            # temp dir. Ephemeral, but still avoids re-login within a warm run.
            base_path = _TMP_TOKEN_DIR
        key = hashlib.sha256(f"{self.domain}:{self.email}".encode()).hexdigest()[:16]
        return base_path / key

    def login(self) -> None:
        """Authenticate with Garmin Connect.

        Reuses cached OAuth tokens when available (avoiding repeated full SSO
        logins, which Garmin rate-limits). Falls back to a full credential
        login with retry/backoff, then caches the resulting tokens.
        """
        self._garth.configure(domain=self.domain)
        if self._try_cached_login():
            self._logged_in = True
            return
        self._login_with_retry()
        self._save_tokens()
        self._logged_in = True

    def _try_cached_login(self) -> bool:
        """Attempt to log in using cached tokens. Returns True on success."""
        token_env = self._token_env
        token_dir = self._token_dir
        try:
            if token_env:
                self._garth.loads(token_env)
            elif (token_dir / "oauth2_token.json").exists():
                self._garth.load(str(token_dir))
            else:
                return False
            # Validate (and trigger oauth2 refresh if needed) with a cheap call.
            self._garth.connectapi("/userprofile-service/socialProfile")
        except Exception as exc:  # noqa: BLE001
            # If validation failed due to rate-limiting, the tokens themselves
            # are likely still valid — trust them rather than triggering a full
            # SSO login (which will also be rate-limited).
            if _is_rate_limited(exc):
                logger.warning(
                    "Cached token validation hit 429; trusting cached tokens."
                )
                return True
            logger.info("Cached Garmin tokens unusable (%s); logging in fresh.", exc)
            return False
        source = "env" if token_env else "disk"
        logger.info("Reused cached Garmin tokens for %s (%s).", self.domain, source)
        return True

    def _save_tokens(self) -> None:
        # When tokens come from an env var, there's nothing to persist to disk.
        if self._token_env:
            return
        token_dir = self._token_dir
        try:
            token_dir.mkdir(parents=True, exist_ok=True)
            self._garth.dump(str(token_dir))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not cache Garmin tokens: %s", exc)

    def _login_with_retry(self) -> None:

        last_exc: Exception | None = None
        for attempt in range(1, _LOGIN_RETRIES + 1):
            try:
                self._garth.login(self.email, self.password)
                if attempt > 1:
                    logger.info("Garmin login succeeded on attempt %d.", attempt)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= _LOGIN_RETRIES:
                    break
                delay = _RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)]
                reason = "rate limit (429)" if _is_rate_limited(exc) else str(exc)
                logger.warning(
                    "Garmin login attempt %d/%d failed (%s), retrying in %ds...",
                    attempt,
                    _LOGIN_RETRIES,
                    reason,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError(
            f"Login failed after {_LOGIN_RETRIES} attempts: {last_exc}"
        ) from last_exc

    def _require_login(self) -> None:
        if not self._logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

    def connectapi(self, path: str, **kwargs: Any) -> Any:
        """Make an authenticated JSON API call."""
        self._require_login()
        return self._garth.connectapi(path, **kwargs)

    def download(self, path: str, **kwargs: Any) -> bytes:
        """Download raw bytes from a Garmin Connect path."""
        self._require_login()
        return self._garth.download(path, **kwargs)

    def upload(self, fp: IO[bytes]) -> dict[str, Any]:
        """Upload an activity file object (its name must end in a valid suffix)."""
        self._require_login()
        return self._garth.upload(fp)

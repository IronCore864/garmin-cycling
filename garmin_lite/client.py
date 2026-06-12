"""Garmin client helpers: build and log in CN / Global clients from config."""

import logging
import time

import requests

from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .config import Config

logger = logging.getLogger("garmin_lite")

_LOGIN_RETRIES = 5
# Graduated delay schedule (seconds). The first failure is almost always a
# spurious 429 from Garmin's SSO endpoint that clears on an immediate retry,
# so we retry quickly first and only escalate the backoff if it keeps failing.
_RETRY_DELAYS = [2, 10, 30, 60]
_CN_TIMEOUT = 30  # seconds
_CN_RETRIES = 3

# Connection-like errors worth retrying.
_RETRYABLE_EXC = (
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def _is_rate_limited(exc: Exception) -> bool:
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return True
    text = str(exc).lower()
    return "429" in text or "too many requests" in text


def _login_with_retry(client: Garmin) -> None:
    last_exc = None
    # Garminconnect logs a full traceback (logger.exception) on every failed
    # login. Since intermediate failures are expected and retried, suppress
    # those tracebacks and only let the final outcome surface.
    gc_logger = logging.getLogger("garminconnect")
    prev_level = gc_logger.level
    gc_logger.setLevel(logging.CRITICAL)
    try:
        for attempt in range(1, _LOGIN_RETRIES + 1):
            try:
                client.login()
                if attempt > 1:
                    logger.info("Garmin login succeeded on attempt %d.", attempt)
                return
            except _RETRYABLE_EXC as exc:
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
    finally:
        gc_logger.setLevel(prev_level)
    raise GarminConnectConnectionError(
        f"Login failed after {_LOGIN_RETRIES} attempts: {last_exc}"
    ) from last_exc


def make_cn_client(config: Config) -> Garmin:
    """Create and log in a Garmin CN client."""
    client = Garmin(config.cn_email, config.cn_password, is_cn=True)
    _login_with_retry(client)
    client.garth.configure(timeout=_CN_TIMEOUT, retries=_CN_RETRIES)
    return client


def make_global_client(config: Config) -> Garmin:
    """Create and log in a Garmin Global client."""
    client = Garmin(config.global_email, config.global_password, is_cn=False)
    _login_with_retry(client)
    return client

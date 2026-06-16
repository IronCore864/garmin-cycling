"""The composed Garmin Connect client and login factory helpers.

``GarminClient`` combines all endpoint/feature groups (activities, gear,
VO2 max, analytics, power, laps, sync) on top of the authentication/transport
layer in :mod:`garmin._base`.
"""

from __future__ import annotations

from ._base import BaseClient
from .activities import ActivitiesMixin
from .analytics import AnalyticsMixin
from .config import Config
from .gear import GearMixin
from .laps import LapsMixin
from .power import PowerMixin
from .sync import SyncMixin
from .vo2 import VO2Mixin


class GarminClient(
    BaseClient,
    ActivitiesMixin,
    GearMixin,
    VO2Mixin,
    AnalyticsMixin,
    PowerMixin,
    LapsMixin,
    SyncMixin,
):
    """Garmin Connect API client.

    Usage:
        client = GarminClient(email="...", password="...", is_cn=True)
        client.login()
        activities = client.get_activities("2026-01-01", activity_type="cycling")
    """


def make_cn_client(config: Config) -> GarminClient:
    """Create and log in a Garmin CN client from config."""
    client = GarminClient(
        email=config.cn.email, password=config.cn.password, is_cn=True
    )
    client.login()
    return client


def make_global_client(config: Config) -> GarminClient:
    """Create and log in a Garmin Global client from config."""
    creds = config.require_global()
    client = GarminClient(email=creds.email, password=creds.password, is_cn=False)
    client.login()
    return client

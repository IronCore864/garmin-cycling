"""Garmin Connect client for CN/Global regions.

Uses garth's OAuth1→OAuth2 flow for authentication, which works
reliably for garmin.cn even after Garmin's 2025 auth changes.

The package is organised by functionality. The endpoint/feature groups are
implemented as mixins composed into ``GarminClient``, so features are called
as methods on a client instance (e.g. ``client.count_latest_activity_laps()``).

  - ``client``    : the composed ``GarminClient`` + login factories
  - ``activities``: activity listing and download
  - ``gear``      : gear (bike) endpoints and stats
  - ``vo2``       : VO2 max retrieval and monthly plotting
  - ``analytics`` : power/HR analytics (max avg power by duration)
  - ``laps``      : lake lap (circle) counting
  - ``sync``      : CN -> Global activity sync
  - ``config``    : credential configuration
  - ``workflow``  : the combined sync + analysis workflow
"""

from .analytics import max_avg_pwr_and_hr
from .client import GarminClient, make_cn_client, make_global_client
from .config import Config, Credentials, load_config
from .workflow import run_workflow

__all__ = [
    "GarminClient",
    "make_cn_client",
    "make_global_client",
    "Config",
    "Credentials",
    "load_config",
    "max_avg_pwr_and_hr",
    "run_workflow",
]

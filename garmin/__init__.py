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
  - ``weight``    : body-weight retrieval and history plotting
  - ``badges``    : earned-badge retrieval and a show-off poster image
  - ``analytics`` : power/HR analytics (max avg power by duration)
  - ``laps``      : lake lap (circle) counting
  - ``sync``      : CN -> Global activity sync
  - ``config``    : credential configuration
  - ``workflow``  : the combined sync + analysis workflow
"""

from .analytics import max_avg_pwr_and_hr
from .badges import (
    BadgeStats,
    badge_image_url,
    compute_badge_stats,
    dominant_color,
    render_badge_color_mosaic,
    render_badge_poster,
    sort_badges,
)
from .client import GarminClient, make_cn_client, make_global_client
from .config import (
    AthleteProfile,
    Config,
    Credentials,
    load_athlete_profile,
    load_config,
)
from .gear import GearActivity, GearReport
from .laps import (
    DEFAULT_LAKE,
    Lake,
    LapResult,
    count_circles,
    count_fit_laps,
    count_laps_in_directory,
)
from .power import (
    Coasting,
    CriticalPower,
    Decoupling,
    RideAnalysis,
    analyze_ride,
    compute_coasting,
    compute_critical_power,
    compute_decoupling,
    mean_max_power,
    normalized_power,
)
from .training_load import (
    DayLoad,
    ReadinessMetrics,
    ReadinessReport,
    Recommendation,
    activity_load,
    acwr,
    analyze_readiness,
    has_todays_activity,
    recommend,
    rolling_metrics,
)
from .workflow import run_workflow
from .zones import calculate_zones, format_zones

__all__ = [
    # Client + factories
    "GarminClient",
    "make_cn_client",
    "make_global_client",
    # Configuration
    "Config",
    "Credentials",
    "load_config",
    "AthleteProfile",
    "load_athlete_profile",
    # Analytics
    "max_avg_pwr_and_hr",
    # Badges
    "BadgeStats",
    "badge_image_url",
    "compute_badge_stats",
    "sort_badges",
    "dominant_color",
    "render_badge_poster",
    "render_badge_color_mosaic",
    # Gear
    "GearActivity",
    "GearReport",
    # Laps
    "Lake",
    "DEFAULT_LAKE",
    "LapResult",
    "count_circles",
    "count_fit_laps",
    "count_laps_in_directory",
    # Single-ride power analysis
    "RideAnalysis",
    "Decoupling",
    "CriticalPower",
    "Coasting",
    "analyze_ride",
    "normalized_power",
    "mean_max_power",
    "compute_critical_power",
    "compute_decoupling",
    "compute_coasting",
    # Workflow
    "run_workflow",
    # Training load & readiness
    "DayLoad",
    "Recommendation",
    "ReadinessMetrics",
    "ReadinessReport",
    "activity_load",
    "acwr",
    "analyze_readiness",
    "has_todays_activity",
    "recommend",
    "rolling_metrics",
    # Heart-rate zones
    "calculate_zones",
    "format_zones",
]

"""Heart-rate zone calculation utilities.

Provides:

* :func:`calculate_zones` -- five heart-rate zones from a Functional Threshold
  Heart Rate (FTHR), expressed as bpm ``start``/``end`` boundaries.
* :func:`format_zones` -- render those zones into a human-readable table.

Zone upper bounds are integer-truncated percentages of FTHR (Z1 <= 81%,
Z2 <= 89%, Z3 <= 93%, Z4 <= 99%); Zone 5 is FTHR and above (open-ended). Zones
are contiguous: each zone starts one bpm above the previous zone's end.
"""

from __future__ import annotations

# HR zone upper thresholds as a percentage of FTHR.
ZONE_1_MAX = 81
ZONE_2_MAX = 89
ZONE_3_MAX = 93
ZONE_4_MAX = 99
# Zone 5 is FTHR and above.
ZONE_1_START = 91  # Fixed lower bound, matches prior logic.


def calculate_zones(fthr: int | float) -> list[dict]:
    """Calculate the five heart-rate zones for a given FTHR.

    Args:
        fthr: Functional Threshold Heart Rate (bpm).

    Returns:
        A list of five dicts, each with ``zone`` (1-5), ``start`` and ``end``.
        Zones 1-4 have integer ``end`` values; Zone 5 is open-ended and its
        ``end`` is the string ``">{start}"``.

    Raises:
        TypeError: If ``fthr`` is not an ``int`` or ``float``.
    """
    if not isinstance(fthr, (int, float)):
        raise TypeError("FTHR must be a number.")

    zones: list[dict] = []
    current_start = ZONE_1_START - 1

    for zone_number, pct in (
        (1, ZONE_1_MAX),
        (2, ZONE_2_MAX),
        (3, ZONE_3_MAX),
        (4, ZONE_4_MAX),
    ):
        zone_end = int((pct / 100) * fthr)
        zones.append({"zone": zone_number, "start": current_start + 1, "end": zone_end})
        current_start = zone_end

    # Zone 5: FTHR and above, open-ended.
    zones.append(
        {"zone": 5, "start": current_start + 1, "end": f">{current_start + 1}"}
    )
    return zones


def format_zones(zones: list[dict]) -> str:
    """Render calculated zones as a human-readable table.

    Args:
        zones: The output of :func:`calculate_zones`.

    Returns:
        A plain-text table with one row per zone and its bpm range. Zone 5 is
        shown as an open-ended range (``>N``).
    """
    lines = ["Zone   HR range (bpm)", "-" * 24]
    for z in zones:
        end = z["end"]
        if isinstance(end, str):
            # Open-ended zone (e.g. Zone 5): end already carries the ">" prefix.
            hr_range = end
        else:
            hr_range = f"{z['start']}-{end}"
        lines.append(f"Z{z['zone']:<5} {hr_range}")
    return "\n".join(lines)

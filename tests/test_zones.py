"""Tests for garmin.zones heart-rate zone calculation."""

from itertools import pairwise

import pytest

from garmin.zones import ZONE_1_START, calculate_zones, format_zones


def test_boundary_values_for_representative_fthr():
    zones = calculate_zones(170)
    ends = {z["zone"]: z["end"] for z in zones}
    assert ends[1] == int((81 / 100) * 170)  # 137
    assert ends[2] == int((89 / 100) * 170)  # 151
    assert ends[3] == int((93 / 100) * 170)  # 158
    assert ends[4] == int((99 / 100) * 170)  # 168


def test_returns_five_zones_numbered_1_to_5():
    zones = calculate_zones(160)
    assert [z["zone"] for z in zones] == [1, 2, 3, 4, 5]


def test_truncation_floors_not_rounds():
    # 0.81 * 170 = 137.7 -> floor 137 (rounding would give 138).
    zones = calculate_zones(170)
    assert zones[0]["end"] == 137


def test_contiguous_boundaries_and_fixed_zone1_start():
    zones = calculate_zones(175)
    assert zones[0]["start"] == ZONE_1_START == 91
    for prev, cur in pairwise(zones):
        assert cur["start"] == prev["end"] + 1


def test_zone5_is_open_ended():
    zones = calculate_zones(180)
    z4_end = zones[3]["end"]
    z5 = zones[4]
    assert z5["start"] == z4_end + 1
    assert z5["end"] == f">{z4_end + 1}"


def test_accepts_float_fthr():
    zones = calculate_zones(170.0)
    assert zones[0]["end"] == 137


def test_non_numeric_fthr_raises_type_error():
    with pytest.raises(TypeError, match="FTHR must be a number"):
        calculate_zones("170")


def test_format_zones_output_shape():
    zones = calculate_zones(170)
    text = format_zones(zones)
    lines = text.splitlines()
    # Header + separator + 5 zone rows.
    zone_rows = [ln for ln in lines if len(ln) > 1 and ln[0] == "Z" and ln[1].isdigit()]
    assert len(zone_rows) == 5
    # Zone 5 shown as an open-ended range.
    assert zone_rows[4].startswith("Z5")
    assert ">" in zone_rows[4]
    # A numeric zone shows a start-end range.
    assert "91-137" in zone_rows[0]

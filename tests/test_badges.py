"""Tests for garmin.badges pure logic (image URLs, stats, sorting)."""

from datetime import date

from garmin.badges import (
    badge_image_filename,
    badge_image_url,
    compute_badge_stats,
    sort_badges,
)


def _badge(**overrides):
    base = {
        "badgeId": 1,
        "badgeUuid": "ABC123",
        "badgeName": "Test Badge",
        "badgePoints": 5,
        "badgeEarnedDate": "2026-07-06T10:18:00.0",
        "badgeEarnedNumber": 1,
        "badgeCategoryId": 4,
    }
    base.update(overrides)
    return base


def test_image_filename_prefers_uuid():
    assert badge_image_filename(_badge()) == "badge_ABC123_sml.png"


def test_image_filename_falls_back_to_id_without_uuid():
    b = _badge(badgeUuid=None, badgeId=30)
    assert badge_image_filename(b) == "badge_30_sml.png"


def test_image_url_uses_resolution_bucket_and_cn_host():
    url = badge_image_url(_badge(), res="xxhdpi")
    assert url == (
        "https://connect.garmin.cn/images/badges/xxhdpi/badge_ABC123_sml.png"
    )


def test_compute_badge_stats_counts_repeats_and_points():
    badges = [
        _badge(badgeId=1, badgePoints=5, badgeEarnedNumber=3,
               badgeEarnedDate="2026-07-06T10:00:00.0"),
        _badge(badgeId=2, badgePoints=2, badgeEarnedNumber=1,
               badgeEarnedDate="2022-08-03T23:53:04.975"),
    ]
    stats = compute_badge_stats(badges)
    assert stats.unique_badges == 2
    assert stats.total_badges == 4  # 3 + 1
    assert stats.total_points == 17  # 5*3 + 2*1
    assert stats.first_earned == date(2022, 8, 3)
    assert stats.last_earned == date(2026, 7, 6)
    assert stats.date_span == "2022-08-03 -> 2026-07-06"


def test_compute_badge_stats_handles_missing_dates_and_fields():
    stats = compute_badge_stats([{"badgeId": 9}])
    assert stats.unique_badges == 1
    assert stats.total_badges == 1  # missing earned number defaults to 1
    assert stats.total_points == 0
    assert stats.first_earned is None
    assert stats.date_span == "n/a"


def test_sort_badges_by_points_desc():
    badges = [
        _badge(badgeId=1, badgePoints=1),
        _badge(badgeId=2, badgePoints=10),
        _badge(badgeId=3, badgePoints=5),
    ]
    ordered = sort_badges(badges, by="points")
    assert [b["badgeId"] for b in ordered] == [2, 3, 1]


def test_sort_badges_by_date_recent_first():
    badges = [
        _badge(badgeId=1, badgeEarnedDate="2022-01-01"),
        _badge(badgeId=2, badgeEarnedDate="2026-01-01"),
        _badge(badgeId=3, badgeEarnedDate="2024-01-01"),
    ]
    ordered = sort_badges(badges, by="date")
    assert [b["badgeId"] for b in ordered] == [2, 3, 1]


def test_sort_badges_by_category_then_points():
    badges = [
        _badge(badgeId=1, badgeCategoryId=6, badgePoints=1),
        _badge(badgeId=2, badgeCategoryId=4, badgePoints=2),
        _badge(badgeId=3, badgeCategoryId=4, badgePoints=9),
    ]
    ordered = sort_badges(badges, by="category")
    # Category 4 first (grouped), highest points first within a category.
    assert [b["badgeId"] for b in ordered] == [3, 2, 1]


def test_color_sort_key_orders_vivid_by_hue_then_greys_last():
    from garmin.badges import _color_sort_key

    red = _color_sort_key((220, 20, 20))
    green = _color_sort_key((20, 200, 20))
    blue = _color_sort_key((20, 20, 220))
    grey = _color_sort_key((128, 128, 128))
    # Vivid colours (band 0) sort ahead of near-greys (band 2).
    assert red[0] == green[0] == blue[0] == 0.0
    assert grey[0] == 2.0
    # Within vivid colours, ordering follows the hue wheel: R < G < B.
    assert red[1] < green[1] < blue[1]


def test_dominant_color_detects_vivid_hue(tmp_path):
    from PIL import Image

    from garmin.badges import dominant_color

    # A mostly-transparent badge with a vivid red core should read as red.
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    for x in range(12, 28):
        for y in range(12, 28):
            img.putpixel((x, y), (230, 20, 20, 255))
    p = tmp_path / "red.png"
    img.save(p)
    r, g, b = dominant_color(p)
    assert r > 150 and g < 90 and b < 90


def test_bicycle_layout_places_all_points_within_canvas():
    from garmin.badges import _BIKE_BADGE, _BIKE_SPACING, _bicycle_layout

    points, segs, width, height = _bicycle_layout(304, _BIKE_SPACING, _BIKE_BADGE)
    # One point per badge, all inside the content canvas.
    assert len(points) == 304
    assert all(0 <= x <= width and 0 <= y <= height for x, y in points)
    # The outline has the two wheels plus the frame/handlebar/saddle lines.
    circles = [s for s in segs if s[0] == "circle"]
    assert len(circles) == 2


"""Tests for garmin.heatmap: track extraction, parsing, filtering, rendering."""

from garmin.heatmap import (
    _SEMI_TO_DEG,
    GpsTrack,
    build_heatmap_html,
    extract_track,
    filter_tracks,
    location_from_label,
    parse_filename,
    summarize_locations,
)

# --- FIT fakes (mirroring tests/test_laps.py) ------------------------------


class _Field:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _Record:
    def __init__(self, lat_deg, lon_deg):
        self.fields = [
            _Field("position_lat", lat_deg / _SEMI_TO_DEG),
            _Field("position_long", lon_deg / _SEMI_TO_DEG),
        ]


class _FakeFitFile:
    def __init__(self, points):
        self._records = [_Record(lat, lon) for lat, lon in points]

    def get_messages(self, _kind):
        return self._records


# --- extract_track ---------------------------------------------------------


def test_extract_track_converts_semicircles_to_degrees():
    fit = _FakeFitFile([(30.5, 104.0), (30.6, 104.1)])
    track = extract_track(fit)
    assert track == [(30.5, 104.0), (30.6, 104.1)]


def test_extract_track_skips_records_without_position():
    fit = _FakeFitFile([(30.5, 104.0)])
    no_fix = _Record(0.0, 0.0)
    no_fix.fields = [_Field("position_lat", None), _Field("position_long", None)]
    fit._records.append(no_fix)
    track = extract_track(fit)
    assert track == [(30.5, 104.0)]


def test_extract_track_decimates_to_max_points_and_keeps_last():
    pts = [(30.0 + i / 1000, 104.0) for i in range(100)]
    track = extract_track(_FakeFitFile(pts), max_points=10)
    assert len(track) <= 11  # capped near max_points
    assert track[0] == pts[0]
    assert track[-1] == pts[-1]  # last point preserved


# --- filename + location parsing -------------------------------------------


def test_parse_filename_download_convention():
    date_str, activity_id, label = parse_filename(
        "2026-05-29_599884527_Chengdu_Road_Cycling"
    )
    assert date_str == "2026-05-29"
    assert activity_id == "599884527"
    assert label == "Chengdu Road Cycling"


def test_parse_filename_non_matching_falls_back():
    date_str, activity_id, label = parse_filename("random_name")
    assert date_str == ""
    assert activity_id == ""
    assert label == "random name"


def test_location_from_label_strips_sport_words():
    assert location_from_label("Chengdu Road Cycling") == "Chengdu"
    assert location_from_label("Munich Road Cycling") == "Munich"
    assert location_from_label("Kirchseeon Gravel Unpaved Cycling") == "Kirchseeon"


def test_location_from_label_keeps_label_when_only_sport():
    assert location_from_label("Running") == "Running"


# --- filtering -------------------------------------------------------------


def _track(date, location):
    return GpsTrack(date=date, name=location, location=location, points=[(1.0, 2.0)])


def test_filter_tracks_by_year():
    tracks = [_track("2025-01-01", "A"), _track("2026-01-01", "B")]
    kept = filter_tracks(tracks, year=2026)
    assert [t.location for t in kept] == ["B"]


def test_filter_tracks_by_city_is_case_insensitive_substring():
    tracks = [_track("2026-01-01", "Chengdu"), _track("2026-01-02", "Munich")]
    kept = filter_tracks(tracks, city="cheng")
    assert [t.location for t in kept] == ["Chengdu"]


def test_summarize_locations_counts_most_common_first():
    tracks = [
        _track("2026-01-01", "Chengdu"),
        _track("2026-01-02", "Chengdu"),
        _track("2026-01-03", "Munich"),
    ]
    assert summarize_locations(tracks) == {"Chengdu": 2, "Munich": 1}


# --- rendering -------------------------------------------------------------


def test_build_heatmap_html_writes_a_map(tmp_path):
    tracks = [
        GpsTrack(
            date="2026-01-01",
            name="Chengdu Road Cycling",
            location="Chengdu",
            points=[(30.5, 104.0), (30.6, 104.1), (30.7, 104.2)],
        )
    ]
    out = build_heatmap_html(tracks, tmp_path / "heatmap.html")
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    assert "leaflet" in html.lower()


def test_build_heatmap_html_raises_without_points():
    empty = [GpsTrack(date="2026-01-01", name="x", location="x", points=[])]
    try:
        build_heatmap_html(empty, "unused.html")
    except ValueError:
        pass
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("expected ValueError for empty tracks")

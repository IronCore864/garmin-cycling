"""Tests for garmin._fit archive helpers."""

import io
import zipfile

from garmin._fit import extract_fit_bytes, write_fit_download


def _make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_extract_fit_bytes_returns_fit_member():
    archive = _make_zip({"junk.txt": b"nope", "activity.fit": b"FITDATA"})
    assert extract_fit_bytes(archive) == b"FITDATA"


def test_extract_fit_bytes_none_when_no_fit():
    archive = _make_zip({"readme.txt": b"hello"})
    assert extract_fit_bytes(archive) is None


def test_write_fit_download_non_zip_content(tmp_path):
    base = tmp_path / "2026-01-01_1_Ride"
    saved = write_fit_download(b"RAWFIT", base)
    assert saved == [base.with_suffix(".fit")]
    assert saved[0].read_bytes() == b"RAWFIT"


def test_write_fit_download_single_member_zip(tmp_path):
    base = tmp_path / "2026-01-01_1_Ride"
    archive = _make_zip({"123.fit": b"ONEFIT"})
    saved = write_fit_download(archive, base)
    assert saved == [base.with_suffix(".fit")]
    assert saved[0].read_bytes() == b"ONEFIT"


def test_write_fit_download_multi_member_zip(tmp_path):
    base = tmp_path / "2026-01-01_1_Ride"
    archive = _make_zip({"a.fit": b"AAA", "b.fit": b"BBB"})
    saved = write_fit_download(archive, base)
    names = sorted(p.name for p in saved)
    assert names == ["2026-01-01_1_Ride_0.fit", "2026-01-01_1_Ride_1.fit"]
    assert {p.read_bytes() for p in saved} == {b"AAA", b"BBB"}


def test_write_fit_download_member_without_suffix_defaults_fit(tmp_path):
    base = tmp_path / "ride"
    archive = _make_zip({"nosuffix": b"DATA"})
    saved = write_fit_download(archive, base)
    assert saved == [base.with_suffix(".fit")]
    assert saved[0].read_bytes() == b"DATA"

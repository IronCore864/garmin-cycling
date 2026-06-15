"""Helpers for working with Garmin FIT activity downloads.

Garmin's "original format" download (``fmt="fit"``) is a ZIP archive that
usually contains a single ``.fit`` member. These helpers centralise reading
the FIT bytes out of that archive and writing downloads to disk, so the logic
lives in exactly one place.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def extract_fit_bytes(activity_bytes: bytes) -> bytes | None:
    """Return the first ``.fit`` member of a downloaded activity archive.

    Args:
        activity_bytes: Raw bytes of a Garmin ``fmt="fit"`` download (a ZIP).

    Returns:
        The raw FIT bytes, or ``None`` if the archive has no ``.fit`` member.
    """
    with zipfile.ZipFile(io.BytesIO(activity_bytes)) as zipf:
        for fname in zipf.namelist():
            if fname.endswith(".fit"):
                with zipf.open(fname) as fit_file:
                    return fit_file.read()
    return None


def write_fit_download(content: bytes, base_path: Path) -> list[Path]:
    """Write a ``fmt="fit"`` download to disk next to ``base_path``.

    The download is usually a ZIP holding one or more ``.fit`` files. When the
    archive holds a single file it is written as ``base_path`` + the member's
    suffix; multiple members are suffixed with an index. Non-ZIP content is
    written directly as a ``.fit`` file.

    Args:
        content: Raw bytes of the download.
        base_path: Target path without suffix (e.g. ``out/2026-01-01_123_Ride``).

    Returns:
        The list of paths actually written.
    """
    if content[:2] != b"PK":  # not a ZIP archive
        out = base_path.with_suffix(".fit")
        out.write_bytes(content)
        return [out]

    saved: list[Path] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        for i, name in enumerate(names):
            suffix = Path(name).suffix or ".fit"
            if len(names) > 1:
                out = base_path.with_name(f"{base_path.name}_{i}{suffix}")
            else:
                out = base_path.with_suffix(suffix)
            out.write_bytes(zf.read(name))
            saved.append(out)
    return saved

"""Garmin Connect badges: retrieval + a "show-off" poster image.

Garmin Connect (including the CN region) awards badges for challenges,
milestones and activities. This module fetches the earned badges and composes
a single poster image out of the official badge artwork.

Badge artwork is served from Garmin's public image CDN, keyed by badge UUID
(with a numeric-id fallback for the handful of legacy badges without a UUID)::

    https://connect.garmin.cn/images/badges/{res}/badge_{UUID}_sml.png

The ``xxhdpi`` bucket is the highest resolution available.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("garmin")

# Public badge-image CDN. Resolution buckets: mdpi < hdpi < xhdpi < xxhdpi.
_IMAGE_HOST = "https://connect.garmin.cn/images/badges"
_DEFAULT_RES = "xxhdpi"

# Where downloaded badge artwork is cached between runs.
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "garmin-cycling" / "badges"


def badge_image_filename(badge: dict[str, Any]) -> str:
    """Return the CDN image filename for a badge.

    Uses the badge UUID when present (the common case), otherwise falls back to
    the numeric badge id (used by a few legacy social badges).
    """
    uuid = badge.get("badgeUuid")
    if uuid:
        return f"badge_{uuid}_sml.png"
    return f"badge_{badge.get('badgeId')}_sml.png"


def badge_image_url(badge: dict[str, Any], res: str = _DEFAULT_RES) -> str:
    """Return the full CDN URL for a badge's artwork."""
    return f"{_IMAGE_HOST}/{res}/{badge_image_filename(badge)}"


def _parse_earned_date(badge: dict[str, Any]) -> date | None:
    """Parse a badge's earned date (Garmin uses ISO-ish, sometimes no tz)."""
    raw = badge.get("badgeEarnedDate")
    if not raw:
        return None
    text = str(raw).replace("Z", "").split(".")[0].replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class BadgeStats:
    """Aggregate summary of a set of earned badges."""

    total_badges: int
    unique_badges: int
    total_points: int
    first_earned: date | None
    last_earned: date | None

    @property
    def date_span(self) -> str:
        """Human-readable earned-date span, e.g. ``2022-08-03 -> 2026-07-06``."""
        if self.first_earned and self.last_earned:
            return f"{self.first_earned.isoformat()} -> {self.last_earned.isoformat()}"
        return "n/a"


def compute_badge_stats(badges: list[dict[str, Any]]) -> BadgeStats:
    """Summarise earned badges (counts, points, and earned-date span).

    ``total_badges`` counts repeats (a badge earned N times counts N times),
    while ``unique_badges`` counts distinct badges. ``total_points`` weights
    each badge's points by how many times it was earned.
    """
    unique = len(badges)
    total = 0
    points = 0
    dates: list[date] = []
    for b in badges:
        times = int(b.get("badgeEarnedNumber") or 1)
        total += times
        points += int(b.get("badgePoints") or 0) * times
        d = _parse_earned_date(b)
        if d:
            dates.append(d)
    return BadgeStats(
        total_badges=total,
        unique_badges=unique,
        total_points=points,
        first_earned=min(dates) if dates else None,
        last_earned=max(dates) if dates else None,
    )


def sort_badges(badges: list[dict[str, Any]], by: str = "points") -> list[dict]:
    """Return badges sorted for display.

    Args:
        badges: Earned-badge dicts.
        by: ``"points"`` (highest value first, then most recent),
            ``"date"`` (most recently earned first), or
            ``"category"`` (grouped by category, then points).
    """
    if by == "date":
        return sorted(
            badges,
            key=lambda b: (_parse_earned_date(b) or date.min),
            reverse=True,
        )
    if by == "category":
        return sorted(
            badges,
            key=lambda b: (
                int(b.get("badgeCategoryId") or 0),
                -int(b.get("badgePoints") or 0),
            ),
        )
    # Default: points desc, then most recent.
    return sorted(
        badges,
        key=lambda b: (
            int(b.get("badgePoints") or 0),
            _parse_earned_date(b) or date.min,
        ),
        reverse=True,
    )


class BadgesMixin:
    """Earned-badges Garmin Connect endpoints + poster rendering."""

    def get_earned_badges(self) -> list[dict[str, Any]]:
        """Fetch all badges the user has earned.

        Returns:
            A list of raw badge dicts from Garmin Connect (keys include
            ``badgeId``, ``badgeUuid``, ``badgeName``, ``badgePoints``,
            ``badgeEarnedDate`` and ``badgeEarnedNumber``).
        """
        result = self.connectapi("/badge-service/badge/earned")
        return result if isinstance(result, list) else []

    def download_badge_images(
        self,
        badges: list[dict[str, Any]],
        cache_dir: str | Path = _DEFAULT_CACHE_DIR,
        res: str = _DEFAULT_RES,
        max_workers: int = 12,
    ) -> dict[Any, Path]:
        """Download badge artwork to ``cache_dir`` (skipping cached files).

        Args:
            badges: Earned-badge dicts.
            cache_dir: Directory to cache PNGs in.
            res: CDN resolution bucket (``mdpi``/``hdpi``/``xhdpi``/``xxhdpi``).
            max_workers: Parallel download threads.

        Returns:
            Mapping of ``badgeId`` -> local PNG path for every image that was
            successfully fetched (or already cached).
        """
        import requests

        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
        session = requests.Session()
        session.headers["User-Agent"] = "garmin-cycling/badges"

        def _fetch(badge: dict[str, Any]) -> tuple[Any, Path | None]:
            bid = badge.get("badgeId")
            dest = cache / f"{res}_{badge_image_filename(badge)}"
            if dest.exists() and dest.stat().st_size > 0:
                return bid, dest
            url = badge_image_url(badge, res=res)
            try:
                resp = session.get(url, timeout=30)
                if resp.status_code == 200 and resp.content:
                    dest.write_bytes(resp.content)
                    return bid, dest
                logger.warning("Badge image %s -> HTTP %s", url, resp.status_code)
            except Exception as exc:  # noqa: BLE001 -- skip and continue
                logger.warning("Failed to download badge image %s: %s", url, exc)
            return bid, None

        results: dict[Any, Path] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for bid, path in pool.map(_fetch, badges):
                if path is not None:
                    results[bid] = path
        return results

    def plot_badges(
        self,
        out_path: str,
        style: str = "grid",
        sort_by: str = "points",
        columns: int = 16,
        res: str = _DEFAULT_RES,
        cache_dir: str | Path = _DEFAULT_CACHE_DIR,
    ) -> str | None:
        """Fetch earned badges and render a poster image showing them all off.

        Args:
            out_path: File path to write the poster PNG to.
            style: Poster style -- ``"grid"`` (uniform grid) or ``"color"``
                (badges arranged by dominant colour inside a bicycle shape).
            sort_by: Badge ordering for the grid style
                (``points``/``date``/``category``). Ignored by the color style,
                which orders badges by colour.
            columns: Number of badges per row (grid style).
            res: CDN resolution bucket for the artwork.
            cache_dir: Directory to cache downloaded artwork in.

        Returns:
            The output path, or None if the account has no earned badges.
        """
        badges = self.get_earned_badges()
        if not badges:
            logger.warning("No earned badges found.")
            return None

        ordered = sort_badges(badges, by=sort_by)
        stats = compute_badge_stats(badges)
        images = self.download_badge_images(ordered, cache_dir=cache_dir, res=res)
        if style == "color":
            return render_badge_color_mosaic(ordered, images, stats, out_path)
        return render_badge_poster(ordered, images, stats, out_path, columns=columns)


# ------------------------------------------------------------------
# Poster rendering (PIL)
# ------------------------------------------------------------------

# Poster styling.
_BG_TOP = (24, 26, 33)  # near-black slate, top of gradient
_BG_BOTTOM = (44, 52, 74)  # deep blue, bottom of gradient
_TITLE_COLOR = (255, 255, 255)
_SUBTITLE_COLOR = (170, 200, 235)
_ACCENT = (86, 204, 242)  # cyan accent (repeat-count chips)
_CELL = 150  # grid cell size (px)
_BADGE = 128  # badge artwork size within a cell (px)
_MARGIN = 60  # outer margin (px)
_HEADER_H = 210  # header band height (px)
_FOOTER_H = 70  # footer band height (px)

# "color" style: badges arranged by colour along a bicycle line-drawing
# (thin, single-badge-wide wheels + frame), not a filled silhouette.
_BIKE_BADGE = 116  # badge artwork size along the outline (px)
_BIKE_SPACING = 108  # centre-to-centre spacing of badges along the path (px)
_WHEEL_THICKNESS = 2  # wheels are 2 badges deep; the frame stays 1 badge
_MOSAIC_BG = (16, 17, 22)  # near-black backdrop so colour tiles pop


def _load_font(size: int, bold: bool = False):
    """Load a TrueType font, falling back to PIL's default if unavailable."""
    from PIL import ImageFont

    # matplotlib bundles DejaVu fonts; reuse them for crisp text everywhere.
    candidates = []
    try:
        from matplotlib import font_manager

        name = "DejaVu Sans"
        candidates.append(
            font_manager.findfont(
                font_manager.FontProperties(
                    family=name, weight="bold" if bold else "normal"
                )
            )
        )
    except Exception:  # noqa: BLE001 -- fall through to defaults
        pass
    candidates += [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _vertical_gradient(width: int, height: int, top, bottom):
    """Create a vertical gradient background image."""
    from PIL import Image

    base = Image.new("RGB", (width, height), top)
    top_r, top_g, top_b = top
    bot_r, bot_g, bot_b = bottom
    px = base.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(top_r + (bot_r - top_r) * t)
        g = int(top_g + (bot_g - top_g) * t)
        b = int(top_b + (bot_b - top_b) * t)
        for x in range(width):
            px[x, y] = (r, g, b)
    return base


def _text_size(draw, text: str, font) -> tuple[int, int]:
    """Return (width, height) of ``text`` rendered with ``font``."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _draw_header(draw, width: int, stats: BadgeStats, subtitle: str | None = None):
    """Draw the poster's title band (title, headline stats, earned span)."""
    title_font = _load_font(64, bold=True)
    stat_font = _load_font(30, bold=True)
    sub_font = _load_font(22)

    draw.text((_MARGIN, 46), "My Garmin Badges", font=title_font, fill=_TITLE_COLOR)
    stat_line = (
        f"{stats.total_badges} badges earned"
        f"     {stats.unique_badges} unique"
        f"     {stats.total_points} points"
    )
    draw.text((_MARGIN + 2, 132), stat_line, font=stat_font, fill=_ACCENT)
    span = f"Earned {stats.date_span}"
    if subtitle:
        span = f"{span}      \u2022  {subtitle}"
    draw.text((_MARGIN + 2, 172), span, font=sub_font, fill=_SUBTITLE_COLOR)
    draw.line(
        [(_MARGIN, _HEADER_H - 12), (width - _MARGIN, _HEADER_H - 12)],
        fill=_ACCENT,
        width=2,
    )


def _draw_footer(draw, width: int, height: int):
    """Draw the centered footer caption."""
    footer_font = _load_font(20)
    footer = "Generated from Garmin Connect - garmin-cycling"
    fw, _ = _text_size(draw, footer, footer_font)
    draw.text(
        ((width - fw) // 2, height - _FOOTER_H + 24),
        footer,
        font=footer_font,
        fill=_SUBTITLE_COLOR,
    )


def _paste_repeat_chip(poster, draw, cx: int, cy: int, half: int, times: int):
    """Draw an ``xN`` chip at the bottom-right of a badge, if earned > once."""
    if times <= 1:
        return
    chip_font = _load_font(max(14, int(half * 0.28)), bold=True)
    label = f"x{times}"
    tw, th = _text_size(draw, label, chip_font)
    pad = max(4, half // 16)
    chip_w = tw + 2 * pad
    chip_h = th + 2 * pad
    rx = cx + half - chip_w
    ry = cy + half - chip_h
    draw.rounded_rectangle(
        [rx, ry, rx + chip_w, ry + chip_h], radius=chip_h // 2, fill=_ACCENT
    )
    draw.text((rx + pad, ry + pad - 1), label, font=chip_font, fill=(20, 24, 32))


def render_badge_poster(
    badges: list[dict[str, Any]],
    images: dict[Any, Path],
    stats: BadgeStats,
    out_path: str,
    columns: int = 16,
) -> str:
    """Compose a poster PNG from badge artwork and a summary header.

    Args:
        badges: Badges in the desired display order.
        images: Mapping of ``badgeId`` -> local artwork path.
        stats: Aggregate stats for the header.
        out_path: Where to write the PNG.
        columns: Number of badges per row.

    Returns:
        ``out_path``.
    """
    from PIL import Image, ImageDraw

    # Only lay out badges whose artwork we actually have.
    drawable = [b for b in badges if images.get(b.get("badgeId"))]
    count = len(drawable)
    columns = max(1, columns)
    rows = max(1, (count + columns - 1) // columns)

    grid_w = columns * _CELL
    grid_h = rows * _CELL
    width = grid_w + 2 * _MARGIN
    height = _HEADER_H + grid_h + _FOOTER_H

    poster = _vertical_gradient(width, height, _BG_TOP, _BG_BOTTOM)
    draw = ImageDraw.Draw(poster)
    _draw_header(draw, width, stats)

    # ---- Badge grid ----------------------------------------------
    for idx, badge in enumerate(drawable):
        row, col = divmod(idx, columns)
        cx = _MARGIN + col * _CELL + _CELL // 2
        cy = _HEADER_H + row * _CELL + _CELL // 2

        path = images[badge.get("badgeId")]
        try:
            art = Image.open(path).convert("RGBA")
        except Exception:  # noqa: BLE001 -- skip unreadable image
            continue
        art.thumbnail((_BADGE, _BADGE), Image.LANCZOS)
        ax = cx - art.width // 2
        ay = cy - art.height // 2
        poster.paste(art, (ax, ay), art)

        times = int(badge.get("badgeEarnedNumber") or 1)
        _paste_repeat_chip(poster, draw, cx, cy, _BADGE // 2, times)

    _draw_footer(draw, width, height)
    poster.save(out_path)
    return out_path


# ------------------------------------------------------------------
# "color" style: mosaic sorted by dominant colour
# ------------------------------------------------------------------


def _rgb_to_hsv_arrays(rgb01):
    """Vectorised RGB->HSV for an ``Nx3`` array in [0,1]. Returns (h, s, v)."""
    import numpy as np

    r, g, b = rgb01[:, 0], rgb01[:, 1], rgb01[:, 2]
    mx = np.max(rgb01, axis=1)
    mn = np.min(rgb01, axis=1)
    delta = mx - mn
    h = np.zeros_like(mx)
    nz = delta > 1e-6
    idx = (mx == r) & nz
    h[idx] = ((g[idx] - b[idx]) / delta[idx]) % 6
    idx = (mx == g) & nz
    h[idx] = ((b[idx] - r[idx]) / delta[idx]) + 2
    idx = (mx == b) & nz
    h[idx] = ((r[idx] - g[idx]) / delta[idx]) + 4
    h = (h / 6.0) % 1.0
    s = np.where(mx > 0, delta / mx, 0.0)
    return h, s, mx


def dominant_color(path: str | Path) -> tuple[int, int, int]:
    """Estimate a badge's dominant colour via its peak hue.

    Transparent pixels are dropped. Among the vivid (saturated, bright) pixels
    we find the most common hue (a circular histogram peak) and return the mean
    colour of that hue band -- far more accurate than a plain colour average,
    which muddies multi-hue badges toward grey. Badges with no vivid pixels
    fall back to their overall mean (i.e. they read as neutral/greyscale).
    """
    import numpy as np
    from PIL import Image

    try:
        im = Image.open(path).convert("RGBA").resize((36, 36), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return (128, 128, 128)
    arr = np.asarray(im, dtype=float)
    rgb = arr[..., :3].reshape(-1, 3)
    alpha = arr[..., 3].reshape(-1)
    keep = alpha > 110
    if not keep.any():
        return (128, 128, 128)
    rgb = rgb[keep]

    h, s, v = _rgb_to_hsv_arrays(rgb / 255.0)
    vivid = (s > 0.30) & (v > 0.22)
    if int(vivid.sum()) >= 5:
        bins = 36
        idx = (np.floor(h[vivid] * bins).astype(int)) % bins
        counts = np.bincount(idx, minlength=bins)
        peak = int(counts.argmax())
        sel = idx == peak
        band = rgb[vivid][sel]
        color = band.mean(axis=0)
        return tuple(int(round(c)) for c in color)
    return tuple(int(round(c)) for c in rgb.mean(axis=0))


def _color_sort_key(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Sort key that arranges vivid colours by hue, then neutrals by lightness."""
    import colorsys

    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.18:  # near-greyscale badges: group together, ordered dark -> light
        return (2.0, v, h)
    return (0.0, h, -v)


def _bicycle_segments() -> list[tuple]:
    """Bicycle outline in unit coordinates (rear hub at origin, y up).

    Each segment is ``("line", p, q, thickness)`` or
    ``("circle", centre, radius, thickness)``. ``thickness`` is how many badges
    deep to stack across that part -- wheels are 2 deep, the frame 1 -- so the
    wheels read as bold tyres while the frame stays a clean single line.
    """
    import math

    r = 0.78  # wheel radius (small relative to the frame)
    rh = (0.0, 0.0)  # rear hub
    fh = (2.54, 0.0)  # front hub (pulled in slightly -> shorter fork)
    bb = (1.06, 0.0)  # bottom bracket (crank)
    top_y = 1.05  # top-tube height: low (short seat tube + short fork)
    seat = (0.72, top_y)  # seat cluster (top of seat tube)
    head = (2.06, top_y)  # top of head tube
    # Dropped seat stay: it meets the seat tube partway up, not at the top.
    ss = (bb[0] + 0.58 * (seat[0] - bb[0]), 0.58 * top_y)
    # Seatpost continues in line with the seat tube (bb -> seat), extended up,
    # so post and tube are collinear. It stays long (saddle above the bars).
    _dx, _dy = seat[0] - bb[0], seat[1] - bb[1]
    _dl = math.hypot(_dx, _dy) or 1.0
    _ux, _uy = _dx / _dl, _dy / _dl
    post_len = 0.55
    post_top = (seat[0] + _ux * post_len, seat[1] + _uy * post_len)
    saddle_l = (post_top[0] - 0.20, post_top[1])  # saddle: flat line on top
    saddle_r = (post_top[0] + 0.16, post_top[1])
    stem_top = (2.09, 1.30)  # top of the stem
    bar_l = (1.90, 1.32)  # handlebar (long, lower than the saddle)
    bar_r = (2.44, 1.25)
    w = _WHEEL_THICKNESS
    return [
        ("line", bb, head, 1),  # down tube
        ("line", bb, seat, 1),  # seat tube
        ("line", seat, head, 1),  # top tube (horizontal)
        ("line", ss, rh, 1),  # seat stay (dropped)
        ("line", bb, rh, 1),  # chain stay
        ("line", head, fh, 1),  # fork
        ("line", seat, post_top, 1),  # seatpost
        ("line", saddle_l, saddle_r, 1),  # saddle (flat line)
        ("line", head, stem_top, 1),  # stem
        ("line", bar_l, bar_r, 1),  # handlebar
        ("circle", rh, r, w),  # rear wheel
        ("circle", fh, r, w),  # front wheel
    ]


def _seg_length(seg) -> float:
    """Arc length of an outline segment (line or full circle)."""
    import math

    if seg[0] == "line":
        (x1, y1), (x2, y2) = seg[1], seg[2]
        return math.hypot(x2 - x1, y2 - y1)
    return 2 * math.pi * seg[2]


def _seg_point(seg, t: float) -> tuple[float, float, float, float]:
    """Point + unit normal at parameter ``t`` in [0, 1] along a segment.

    Returns ``(x, y, nx, ny)``. The normal points perpendicular to a line, or
    radially outward on a circle -- used to stack badges across the outline.
    """
    import math

    if seg[0] == "line":
        (x1, y1), (x2, y2) = seg[1], seg[2]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        return (x1 + dx * t, y1 + dy * t, nx, ny)
    (cx, cy), r = seg[1], seg[2]
    a = -math.pi / 2 + t * 2 * math.pi
    ca, sa = math.cos(a), math.sin(a)
    return (cx + r * ca, cy + r * sa, ca, sa)


def _bicycle_layout(n: int, spacing_px: float, badge_px: int):
    """Place ``n`` badge centres along a bicycle outline.

    Each segment carries its own thickness (wheels 2 deep, frame 1), so badges
    are stacked across that segment's normal accordingly. Returns
    ``(points, segments_px, width, height)`` in content coordinates, where each
    entry of ``segments_px`` includes the tube width to draw behind it.
    """
    segs = _bicycle_segments()
    ulens = [_seg_length(s) for s in segs]
    thicks = [s[3] for s in segs]
    # Badge capacity per segment is proportional to length * thickness.
    weighted = sum(length * th for length, th in zip(ulens, thicks, strict=True))
    perp = spacing_px
    scale = n * spacing_px / weighted

    # Number of along-path points per segment (rounded), then nudge the thin
    # (thickness == 1) segments up/down until the badge total is exactly n --
    # so every segment is evenly filled and no slot is left empty.
    n_along = [max(1, round(ulen * scale / spacing_px)) for ulen in ulens]

    def badge_total():
        return sum(a * t for a, t in zip(n_along, thicks, strict=True))

    thin = [i for i, t in enumerate(thicks) if t == 1]
    guard = 0
    while badge_total() != n and guard < 10000:
        guard += 1
        if badge_total() < n:  # add where badges are currently most spread out
            i = max(thin, key=lambda i: ulens[i] / n_along[i])
            n_along[i] += 1
        else:  # remove where they are most crowded (keep at least 1)
            cand = [i for i in thin if n_along[i] > 1]
            if not cand:
                break
            i = min(cand, key=lambda i: ulens[i] / n_along[i])
            n_along[i] -= 1

    positions = []
    for s, th, na in zip(segs, thicks, n_along, strict=True):
        offsets = [(k - (th - 1) / 2.0) * perp for k in range(th)]
        for i in range(na):
            t = (i + 0.5) / na
            x, y, nx, ny = _seg_point(s, t)
            sx, sy = x * scale, y * scale
            for off in offsets:
                positions.append((sx + off * nx, sy + off * ny))

    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    pad = badge_px // 2 + 14
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def txp(x, y):
        return (x - min_x + pad, (max_y - y) + pad)

    def tx(x, y):
        return (x * scale - min_x + pad, (max_y - y * scale) + pad)

    positions = [txp(x, y) for (x, y) in positions]
    seg_px = []
    for s, th in zip(segs, thicks, strict=True):
        tube = int((th - 1) * perp + badge_px * 0.9)
        if s[0] == "line":
            seg_px.append(("line", tx(*s[1]), tx(*s[2]), tube))
        else:
            cx, cy = tx(*s[1])
            seg_px.append(("circle", (cx, cy), s[2] * scale, tube))
    width = int(max_x - min_x + 2 * pad)
    height = int(max_y - min_y + 2 * pad)
    return positions, seg_px, width, height


def render_badge_color_mosaic(
    badges: list[dict[str, Any]],
    images: dict[Any, Path],
    stats: BadgeStats,
    out_path: str,
    columns: int = 18,  # unused; kept for a stable signature
) -> str:
    """Arrange badges by colour along a bicycle line-drawing.

    Badges form the outline of a bicycle (two wheels + frame) and flow
    left-to-right by hue so the machine sweeps across the spectrum.
    """
    from PIL import Image, ImageDraw

    drawable = [b for b in badges if images.get(b.get("badgeId"))]
    if not drawable:
        return out_path

    keyed = []
    for b in drawable:
        rgb = dominant_color(images[b.get("badgeId")])
        keyed.append((_color_sort_key(rgb), rgb, b))
    keyed.sort(key=lambda t: t[0])
    n = len(keyed)

    points, _seg_px, cw, ch = _bicycle_layout(n, _BIKE_SPACING, _BIKE_BADGE)
    # Point indices ordered left-to-right (then top-down): the k-th hue-sorted
    # badge goes to the k-th left-most point, so colour sweeps across the bike.
    order = sorted(range(n), key=lambda i: (points[i][0], points[i][1]))

    width = cw + 2 * _MARGIN
    height = _HEADER_H + ch + _FOOTER_H
    poster = Image.new("RGB", (width, height), _MOSAIC_BG)
    draw = ImageDraw.Draw(poster)
    _draw_header(draw, width, stats, subtitle="arranged by colour")

    ox, oy = _MARGIN, _HEADER_H

    tile = _BIKE_BADGE
    for slot, (_, rgb, badge) in zip(order, keyed, strict=True):
        px, py = points[slot]
        x0 = int(px + ox - tile / 2)
        y0 = int(py + oy - tile / 2)
        tile_color = tuple(int(c * 0.9) for c in rgb)
        draw.rounded_rectangle(
            [x0, y0, x0 + tile, y0 + tile], radius=16, fill=tile_color
        )
        try:
            art = Image.open(images[badge.get("badgeId")]).convert("RGBA")
        except Exception:  # noqa: BLE001 -- skip unreadable image
            continue
        art.thumbnail((tile - 6, tile - 6), Image.LANCZOS)
        poster.paste(
            art,
            (x0 + (tile - art.width) // 2, y0 + (tile - art.height) // 2),
            art,
        )

    _draw_footer(draw, width, height)
    poster.save(out_path)
    return out_path

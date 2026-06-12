"""CLI script entry point.

Runs the full Garmin workflow:
  - sync latest 3 activities from CN to Global
  - fetch latest cycling VO2max precise value
  - count lake circles for the latest activity
  - generate a cycling VO2max image for the past month

Credentials are read from environment variables:
  GARMIN_CN_EMAIL, GARMIN_CN_PASSWORD,
  GARMIN_GLOBAL_EMAIL, GARMIN_GLOBAL_PASSWORD
"""

import argparse
import logging

from dotenv import load_dotenv

from garmin_lite.workflow import DEFAULT_VO2MAX_IMAGE, run_workflow

_STATUS_ICON = {
    "synced": "✓",
    "exists": "•",
    "error": "✗",
}


def _format_result(result: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 48)
    lines.append("Garmin FIT Lite - Workflow Summary")
    lines.append("=" * 48)

    # 1. Sync
    lines.append("")
    lines.append("Sync (Garmin CN -> Global):")
    sync = result.get("sync")
    if not sync:
        lines.append("  (no activities synced)")
    else:
        for item in sync:
            icon = _STATUS_ICON.get(item.get("status"), "?")
            name = item.get("activityName") or "Unnamed activity"
            when = item.get("startTimeLocal") or ""
            detail = item.get("detail") or item.get("status") or ""
            lines.append(f"  {icon} {name} ({when})")
            lines.append(f"      {detail}")

    # 2. VO2max
    lines.append("")
    vo2 = result.get("vo2max")
    if vo2:
        lines.append(
            f"Latest cycling VO2max: {vo2.get('vo2max_precise')} "
            f"(on {vo2.get('date')})"
        )
    else:
        lines.append("Latest cycling VO2max: no data available")

    # 3. Laps
    lines.append("")
    laps = result.get("laps")
    if laps is None:
        lines.append("Lake circles (latest activity): unavailable")
    else:
        unit = "circle" if laps == 1 else "circles"
        lines.append(f"Lake circles (latest activity): {laps} {unit}")

    # 4. VO2max image
    lines.append("")
    image = result.get("vo2max_image")
    if image:
        lines.append(f"VO2max image (past month): saved to {image}")
    else:
        lines.append("VO2max image (past month): not generated (no data)")

    # Errors
    errors = result.get("errors")
    if errors:
        lines.append("")
        lines.append("Warnings (some steps failed):")
        for step, msg in errors.items():
            lines.append(f"  ✗ {step}: {msg}")

    lines.append("")
    lines.append("=" * 48)
    return "\n".join(lines)


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Garmin FIT Lite workflow.")
    parser.add_argument(
        "--vo2max-image",
        default=DEFAULT_VO2MAX_IMAGE,
        help="Output path for the past-month cycling VO2max image.",
    )
    args = parser.parse_args()

    result = run_workflow(vo2max_image_path=args.vo2max_image)
    print(_format_result(result))


if __name__ == "__main__":
    main()

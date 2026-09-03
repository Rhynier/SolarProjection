"""Deterministic synthetic energy dataset for tests.

Produces committed-free, reproducible utility and solar CSV inputs that match
the schema and structural shape of the real (uncommitted) personal exports:
8783 consecutive hourly rows starting 2025-08-17 00:00 local, spanning just
over one year, with matching utility and solar local hours and non-negative
energy everywhere. Values follow a simple diurnal/seasonal pattern; magnitudes
are illustrative, not real.

The generator is the source of truth for the test fixture, so the suite runs
green without the personal CSVs. See ``tests/conftest.py`` for how the app is
pointed at the generated files via the CSV path environment overrides.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

SAMPLE_START = datetime(2025, 8, 17, 0, 0)
SAMPLE_ROW_COUNT = 8783
SAMPLE_OFFSET = "-0700"


def write_sample_energy_csvs(utility_path: Path, solar_path: Path) -> None:
    """Write the deterministic utility and solar CSVs to the given paths."""
    utility_lines = [
        "DATE,START TIME,END TIME,IMPORT (kWh),EXPORT (kWh),COST,NOTES"
    ]
    solar_lines = ["Date/Time,Energy Produced (Wh)"]

    for index in range(SAMPLE_ROW_COUNT):
        timestamp = SAMPLE_START + timedelta(hours=index)
        hour = timestamp.hour
        day_of_year = timestamp.timetuple().tm_yday

        load_kwh = (
            0.6
            + 0.5 * (1 + math.sin((hour - 8) / 24 * 2 * math.pi))
            + (0.4 if hour in (7, 8, 18, 19, 20) else 0.0)
        )

        seasonal = 0.75 + 0.25 * math.cos((day_of_year - 172) / 365 * 2 * math.pi)
        if 6 <= hour <= 19:
            solar_kwh = max(
                0.0, 3.2 * seasonal * math.sin((hour - 6) / 13 * math.pi)
            )
        else:
            solar_kwh = 0.0

        if solar_kwh <= load_kwh:
            grid_import = load_kwh - solar_kwh
            grid_export = 0.0
        else:
            grid_import = 0.0
            grid_export = solar_kwh - load_kwh

        date_str = timestamp.strftime("%Y-%m-%d")
        start_str = timestamp.strftime("%H:%M")
        end_str = timestamp.strftime("%H:59")
        utility_lines.append(
            f"{date_str},{start_str},{end_str},"
            f"{grid_import:.4f},{grid_export:.4f},$0.00,"
        )
        solar_lines.append(
            f"{date_str} {start_str}:00 {SAMPLE_OFFSET},{solar_kwh * 1000:.4f}"
        )

    Path(utility_path).write_text("\n".join(utility_lines) + "\n", encoding="utf-8")
    Path(solar_path).write_text("\n".join(solar_lines) + "\n", encoding="utf-8")

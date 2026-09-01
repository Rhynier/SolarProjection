from datetime import date

import pandas as pd
import pytest

from solar_model.aggregation import aggregate_history, choose_auto_bucket


def hourly_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=72, freq="h"),
        "household_load_kwh": [1.0] * 72,
        "actual_solar_kwh": [0.5] * 72,
        "grid_export_kwh": [0.25] * 72,
    })


@pytest.mark.parametrize(("start", "end", "expected"), [
    (date(2026, 1, 1), date(2026, 1, 3), "hour"),
    (date(2026, 1, 1), date(2026, 2, 26), "day"),
    (date(2026, 1, 1), date(2027, 6, 30), "week"),
    (date(2026, 1, 1), date(2027, 7, 2), "month"),
])
def test_choose_auto_bucket(start, end, expected):
    assert choose_auto_bucket(start, end) == expected


def test_daily_aggregation_filters_inclusive_dates_and_sums_energy():
    result, resolved = aggregate_history(
        hourly_frame(), date(2026, 1, 2), date(2026, 1, 3), "day"
    )
    assert resolved == "day"
    assert list(result["bucket_start"]) == [
        pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")
    ]
    assert list(result["household_load_kwh"]) == [24.0, 24.0]
    assert list(result["actual_solar_kwh"]) == [12.0, 12.0]
    assert list(result["grid_export_kwh"]) == [6.0, 6.0]


def test_weekly_buckets_start_on_monday():
    result, _ = aggregate_history(
        hourly_frame(), date(2026, 1, 1), date(2026, 1, 3), "week"
    )
    assert result.loc[0, "bucket_start"] == pd.Timestamp("2025-12-29")

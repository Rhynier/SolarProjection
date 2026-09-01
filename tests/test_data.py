from pathlib import Path

import pandas as pd
import pytest

from solar_model.data import DataValidationError, load_hourly_energy


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_aligns_sources_and_derives_household_load(tmp_path: Path):
    utility = write_csv(tmp_path / "utility.csv", """
DATE,START TIME,END TIME,IMPORT (kWh),EXPORT (kWh),COST,NOTES
2026-07-01,12:00,12:59,1.00,0.25,$0.10,
""")
    solar = write_csv(tmp_path / "solar.csv", """
Date/Time,Energy Produced (Wh)
2026-07-01 12:00:00 -0700,250
2026-07-01 12:15:00 -0700,250
2026-07-01 12:30:00 -0700,250
2026-07-01 12:45:00 -0700,250
""")
    result = load_hourly_energy(utility, solar)
    assert list(result.columns) == [
        "timestamp", "grid_import_kwh", "grid_export_kwh",
        "actual_solar_kwh", "household_load_kwh",
    ]
    assert result.loc[0, "timestamp"] == pd.Timestamp("2026-07-01 12:00")
    assert result.loc[0, "actual_solar_kwh"] == pytest.approx(1.0)
    assert result.loc[0, "household_load_kwh"] == pytest.approx(1.75)


def test_fall_back_offsets_are_distinct_before_local_hour_aggregation(tmp_path: Path):
    utility = write_csv(tmp_path / "utility.csv", """
DATE,START TIME,END TIME,IMPORT (kWh),EXPORT (kWh),COST,NOTES
2025-11-02,01:00,01:59,0.20,0.00,$0.02,
""")
    rows = ["Date/Time,Energy Produced (Wh)"]
    for offset in ("-0700", "-0800"):
        for minute in ("00", "15", "30", "45"):
            rows.append(f"2025-11-02 01:{minute}:00 {offset},100")
    solar = write_csv(tmp_path / "solar.csv", "\n".join(rows))
    result = load_hourly_energy(utility, solar)
    assert len(result) == 1
    assert result.loc[0, "actual_solar_kwh"] == pytest.approx(0.8)
    assert result.loc[0, "household_load_kwh"] == pytest.approx(1.0)


def test_missing_matching_solar_hour_is_rejected(tmp_path: Path):
    utility = write_csv(tmp_path / "utility.csv", """
DATE,START TIME,END TIME,IMPORT (kWh),EXPORT (kWh),COST,NOTES
2026-07-01,12:00,12:59,1.00,0.00,$0.10,
""")
    solar = write_csv(tmp_path / "solar.csv", """
Date/Time,Energy Produced (Wh)
2026-07-01 13:00:00 -0700,0
""")
    with pytest.raises(DataValidationError, match="matching solar hour"):
        load_hourly_energy(utility, solar)


def test_spring_forward_gap_is_not_invented(tmp_path: Path):
    utility = write_csv(tmp_path / "utility.csv", """
DATE,START TIME,END TIME,IMPORT (kWh),EXPORT (kWh),COST,NOTES
2026-03-08,01:00,01:59,0.50,0.00,$0.05,
2026-03-08,03:00,03:59,0.60,0.00,$0.06,
""")
    solar = write_csv(tmp_path / "solar.csv", """
Date/Time,Energy Produced (Wh)
2026-03-08 01:00:00 -0800,0
2026-03-08 03:00:00 -0700,0
""")
    result = load_hourly_energy(utility, solar)
    assert list(result["timestamp"]) == [
        pd.Timestamp("2026-03-08 01:00"), pd.Timestamp("2026-03-08 03:00")
    ]


def test_negative_derived_load_is_rejected(tmp_path: Path):
    utility = write_csv(tmp_path / "utility.csv", """
DATE,START TIME,END TIME,IMPORT (kWh),EXPORT (kWh),COST,NOTES
2026-07-01,12:00,12:59,0.00,2.00,-$0.20,
""")
    solar = write_csv(tmp_path / "solar.csv", """
Date/Time,Energy Produced (Wh)
2026-07-01 12:00:00 -0700,100
""")
    with pytest.raises(DataValidationError, match="household_load_kwh"):
        load_hourly_energy(utility, solar)


def test_supplied_csvs_form_a_clean_hourly_dataset():
    root = Path(__file__).parents[1]
    result = load_hourly_energy(
        root / "combined-electric-usage.csv",
        root / "combined-monthly-energy.csv",
    )
    assert len(result) == 8783
    assert result["timestamp"].is_monotonic_increasing
    assert not result.isna().any().any()
    assert (result[[
        "grid_import_kwh", "grid_export_kwh", "actual_solar_kwh",
        "household_load_kwh",
    ]] >= 0).all().all()

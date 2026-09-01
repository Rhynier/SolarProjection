from pathlib import Path

import numpy as np
import pandas as pd


UTILITY_COLUMNS = {
    "DATE", "START TIME", "END TIME", "IMPORT (kWh)", "EXPORT (kWh)",
    "COST", "NOTES",
}
SOLAR_COLUMNS = {"Date/Time", "Energy Produced (Wh)"}
ENERGY_COLUMNS = [
    "grid_import_kwh", "grid_export_kwh", "actual_solar_kwh",
    "household_load_kwh",
]


class DataValidationError(ValueError):
    pass


def _require_columns(frame: pd.DataFrame, required: set[str], source: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise DataValidationError(
            f"{source} is missing required columns: {', '.join(missing)}"
        )


def _numeric(series: pd.Series, label: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    bad = values.isna() | ~np.isfinite(values)
    if bad.any():
        rows = [str(index + 2) for index in values.index[bad][:5]]
        raise DataValidationError(
            f"{label} contains invalid numbers at CSV rows {', '.join(rows)}"
        )
    return values.astype(float)


def _load_utility(path: Path) -> pd.DataFrame:
    utility = pd.read_csv(path)
    _require_columns(utility, UTILITY_COLUMNS, "utility")

    timestamps = pd.to_datetime(
        utility["DATE"] + " " + utility["START TIME"],
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    if timestamps.isna().any():
        raise DataValidationError("utility contains invalid local-hour timestamps")
    if timestamps.duplicated().any():
        raise DataValidationError("utility contains duplicate local-hour timestamps")

    return (
        pd.DataFrame(
            {
                "timestamp": timestamps,
                "grid_import_kwh": _numeric(
                    utility["IMPORT (kWh)"], "utility import"
                ),
                "grid_export_kwh": _numeric(
                    utility["EXPORT (kWh)"], "utility export"
                ),
            }
        )
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def _load_solar(path: Path) -> pd.DataFrame:
    solar = pd.read_csv(path)
    _require_columns(solar, SOLAR_COLUMNS, "solar")

    absolute_timestamps = pd.to_datetime(
        solar["Date/Time"],
        format="%Y-%m-%d %H:%M:%S %z",
        utc=True,
        errors="coerce",
    )
    if absolute_timestamps.isna().any():
        raise DataValidationError("solar contains invalid absolute timestamps")
    if absolute_timestamps.duplicated().any():
        raise DataValidationError("solar contains duplicate absolute timestamps")

    local_hours = pd.to_datetime(
        solar["Date/Time"].str[:13], format="%Y-%m-%d %H", errors="coerce"
    )
    if local_hours.isna().any():
        raise DataValidationError("solar contains invalid local-hour timestamps")

    normalized = pd.DataFrame(
        {
            "timestamp": local_hours,
            "actual_solar_kwh": _numeric(
                solar["Energy Produced (Wh)"], "solar energy"
            )
            / 1000,
        }
    )
    return normalized.groupby("timestamp", as_index=False)["actual_solar_kwh"].sum()


def load_hourly_energy(utility_path: Path, solar_path: Path) -> pd.DataFrame:
    utility = _load_utility(Path(utility_path))
    solar = _load_solar(Path(solar_path))
    start = max(utility["timestamp"].min(), solar["timestamp"].min())
    end = min(utility["timestamp"].max(), solar["timestamp"].max())
    if start > end:
        raise DataValidationError(
            "utility and solar files have no overlapping hourly range; "
            "utility hours have no matching solar hour"
        )
    utility = utility[utility["timestamp"].between(start, end)].copy()
    result = utility.merge(solar, on="timestamp", how="left", validate="one_to_one")
    missing = result["actual_solar_kwh"].isna()
    if missing.any():
        examples = result.loc[missing, "timestamp"].dt.strftime("%Y-%m-%d %H:%M").head(5)
        raise DataValidationError(
            f"{int(missing.sum())} utility hours have no matching solar hour: "
            + ", ".join(examples)
        )
    result["household_load_kwh"] = (
        result["grid_import_kwh"] + result["actual_solar_kwh"]
        - result["grid_export_kwh"]
    )
    for column in ENERGY_COLUMNS:
        invalid = ~np.isfinite(result[column]) | (result[column] < 0)
        if invalid.any():
            examples = result.loc[invalid, "timestamp"].dt.strftime(
                "%Y-%m-%d %H:%M"
            ).head(5)
            raise DataValidationError(
                f"{column} is invalid at {int(invalid.sum())} hours: "
                + ", ".join(examples)
            )
    return result[["timestamp", *ENERGY_COLUMNS]].sort_values("timestamp").reset_index(
        drop=True
    )

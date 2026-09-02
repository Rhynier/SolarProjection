from datetime import date
from typing import Literal

import pandas as pd


Bucket = Literal["auto", "hour", "day", "week", "month"]
VALUE_COLUMNS = ["household_load_kwh", "actual_solar_kwh", "grid_export_kwh"]
MODEL_ENERGY_COLUMNS = [
    "household_load_kwh",
    "modeled_solar_kwh",
    "grid_import_kwh",
    "grid_export_kwh",
]


def choose_auto_bucket(start_date: date, end_date: date) -> str:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    days = (end_date - start_date).days + 1
    if days <= 3:
        return "hour"
    if days <= 57:
        return "day"
    if pd.Timestamp(end_date) <= pd.Timestamp(start_date) + pd.DateOffset(months=18):
        return "week"
    return "month"


def _bucket_start(timestamps: pd.Series, bucket: str) -> pd.Series:
    if bucket == "hour":
        return timestamps.dt.floor("h")
    if bucket == "day":
        return timestamps.dt.normalize()
    if bucket == "week":
        return timestamps.dt.to_period("W-SUN").dt.start_time
    if bucket == "month":
        return timestamps.dt.to_period("M").dt.start_time
    raise ValueError(f"unsupported bucket: {bucket}")


def aggregate_history(
    hourly: pd.DataFrame, start_date: date, end_date: date, bucket: Bucket
) -> tuple[pd.DataFrame, str]:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    resolved = choose_auto_bucket(start_date, end_date) if bucket == "auto" else bucket
    dates = hourly["timestamp"].dt.date
    selected = hourly.loc[
        (dates >= start_date) & (dates <= end_date), ["timestamp", *VALUE_COLUMNS]
    ].copy()
    if selected.empty:
        raise ValueError("selected date range contains no energy data")
    selected["bucket_start"] = _bucket_start(selected["timestamp"], resolved)
    return selected.groupby("bucket_start", as_index=False)[VALUE_COLUMNS].sum(), resolved


def aggregate_model_result(
    hourly: pd.DataFrame, start_date: date, end_date: date, bucket: Bucket
) -> tuple[pd.DataFrame, str]:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    resolved = choose_auto_bucket(start_date, end_date) if bucket == "auto" else bucket
    dates = hourly["timestamp"].dt.date
    selected = hourly.loc[
        (dates >= start_date) & (dates <= end_date),
        ["timestamp", *MODEL_ENERGY_COLUMNS, "battery_soc_kwh"],
    ].copy()
    if selected.empty:
        raise ValueError("selected date range contains no modeled energy data")
    selected["bucket_start"] = _bucket_start(selected["timestamp"], resolved)
    aggregations = {column: "sum" for column in MODEL_ENERGY_COLUMNS}
    aggregations["battery_soc_kwh"] = "last"
    return selected.groupby("bucket_start", as_index=False).agg(aggregations), resolved

# Home Energy Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Streamlit prototype that visualizes historical household energy and replays one week of historical demand and weather against configurable solar and battery systems.

**Architecture:** Parse both source CSVs into one validated hourly pandas DataFrame, then keep historical aggregation, TOU classification, battery replay, and Plotly chart construction in independent modules. `app.py` owns Streamlit state and layout but delegates all calculations, allowing focused pytest coverage without browser-heavy infrastructure.

**Tech Stack:** Python 3.11, pandas, Streamlit, Plotly, pytest

**Spec:** `docs/superpowers/specs/2026-09-01-home-energy-model-design.md`

## Global Constraints

- This is a local personal-use prototype; do not add accounts, a database, cloud hosting, telemetry, or production packaging.
- Read `combined-electric-usage.csv` and `combined-monthly-energy.csv` from the project root; keep both files untracked.
- Treat **Used** as `grid import + actual solar production - grid export`.
- Run the model at one-hour resolution for one through seven selected days.
- Charge the battery from solar only; never charge from the grid.
- Support Self-consumption and TOU reserve strategies exactly as defined in the spec.
- Use symmetric charge/discharge efficiency equal to the square root of round-trip efficiency.
- Make malformed or inconsistent data visible; do not interpolate, clamp, or silently repair it.
- Keep edited settings session-only and exclude cost, savings, optimization, and forecasting.
- Use the approved colors: blue use, amber production, violet battery, red import, and green export.

## Planned File Structure

- `pyproject.toml`: Python version, dependencies, and pytest discovery.
- `.gitignore`: local CSVs, visual drafts, virtual environments, and Python caches.
- `.streamlit/config.toml`: approved vibrant Streamlit accent.
- `app.py`: two-page Streamlit UI and session-level controls.
- `solar_model/__init__.py`: package marker and public exception export.
- `solar_model/data.py`: CSV validation, offset-aware parsing, hourly alignment, and derived load.
- `solar_model/aggregation.py`: historical date filtering and bucket aggregation.
- `solar_model/tou.py`: recurring TOU rule parsing, validation, and classification.
- `solar_model/simulation.py`: battery validation and deterministic hourly replay.
- `solar_model/charts.py`: historical and modeled Plotly figures.
- `tests/test_data.py`: ingestion and real-data smoke tests.
- `tests/test_aggregation.py`: range and bucket tests.
- `tests/test_tou.py`: recurring-rule tests.
- `tests/test_simulation.py`: battery and energy-balance tests.
- `tests/test_charts.py`: trace, color, axis, and signed-grid tests.
- `tests/test_app.py`: minimal Streamlit startup smoke test.
- `README.md`: setup, launch, inputs, assumptions, and limitations.

---

### Task 1: Validated Hourly Dataset

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `solar_model/__init__.py`
- Create: `solar_model/data.py`
- Create: `tests/test_data.py`

**Interfaces:**
- Produces: `DataValidationError(ValueError)`.
- Produces: `load_hourly_energy(utility_path: Path, solar_path: Path) -> pandas.DataFrame`.
- Produces DataFrame columns: `timestamp`, `grid_import_kwh`, `grid_export_kwh`, `actual_solar_kwh`, `household_load_kwh`.
- Guarantees: one row per unique utility local-hour key, ascending timestamps, finite nonnegative energy values, and a solar aggregate for every returned utility row.

- [ ] **Step 1: Add dependency metadata and local-only ignores**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "home-energy-model"
version = "0.1.0"
description = "Local prototype for historical and modeled home energy use"
requires-python = ">=3.11"
dependencies = ["numpy", "pandas", "plotly", "streamlit"]

[project.optional-dependencies]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.superpowers/
combined-electric-usage.csv
combined-monthly-energy.csv
```

Install the editable project and tests:

```powershell
python -m pip install -e ".[dev]"
```

Expected: installation succeeds and all four dependencies import.

- [ ] **Step 2: Write failing ingestion tests**

Create `tests/test_data.py`:

```python
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
```

- [ ] **Step 3: Run ingestion tests to verify they fail**

Run: `python -m pytest tests/test_data.py -v`

Expected: collection fails because `solar_model.data` does not exist.

- [ ] **Step 4: Implement schema validation and hourly alignment**

Create `solar_model/__init__.py`:

```python
from .data import DataValidationError

__all__ = ["DataValidationError"]
```

Create `solar_model/data.py` with:

```python
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
        raise DataValidationError(f"{source} is missing required columns: {', '.join(missing)}")

def _numeric(series: pd.Series, label: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    bad = values.isna() | ~np.isfinite(values)
    if bad.any():
        rows = [str(index + 2) for index in values.index[bad][:5]]
        raise DataValidationError(f"{label} contains invalid numbers at CSV rows {', '.join(rows)}")
    return values.astype(float)
```

Implement `_load_utility(path: Path) -> pd.DataFrame` to read the file, require `UTILITY_COLUMNS`, parse `DATE + " " + START TIME` with `%Y-%m-%d %H:%M`, reject unparsable or duplicate keys, validate import/export numerically, rename them, and return the three normalized columns sorted ascending.

Implement `_load_solar(path: Path) -> pd.DataFrame` to:

1. Require `SOLAR_COLUMNS`.
2. Parse absolute timestamps with `pd.to_datetime(..., format="%Y-%m-%d %H:%M:%S %z", utc=True, errors="coerce")`.
3. Reject unparsable or duplicate absolute timestamps.
4. Parse the source-local hour from the first 13 timestamp characters with `%Y-%m-%d %H`.
5. Convert Wh to kWh and group by local hour, preserving the energy from both distinct fall-back hours.

Implement:

```python
def load_hourly_energy(utility_path: Path, solar_path: Path) -> pd.DataFrame:
    utility = _load_utility(Path(utility_path))
    solar = _load_solar(Path(solar_path))
    start = max(utility["timestamp"].min(), solar["timestamp"].min())
    end = min(utility["timestamp"].max(), solar["timestamp"].max())
    if start > end:
        raise DataValidationError("utility and solar files have no overlapping hourly range")
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
            examples = result.loc[invalid, "timestamp"].dt.strftime("%Y-%m-%d %H:%M").head(5)
            raise DataValidationError(
                f"{column} is invalid at {int(invalid.sum())} hours: " + ", ".join(examples)
            )
    return result[["timestamp", *ENERGY_COLUMNS]].sort_values("timestamp").reset_index(drop=True)
```

- [ ] **Step 5: Add the real-data smoke test**

Append to `tests/test_data.py`:

```python
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
```

- [ ] **Step 6: Run Task 1 tests**

Run: `python -m pytest tests/test_data.py -v`

Expected: all ingestion and real-data smoke tests pass.

- [ ] **Step 7: Commit the validated data layer**

```powershell
git add pyproject.toml .gitignore solar_model/__init__.py solar_model/data.py tests/test_data.py
git commit -m "feat: normalize hourly home energy data"
```

---

### Task 2: Historical Range Aggregation

**Files:**
- Create: `solar_model/aggregation.py`
- Create: `tests/test_aggregation.py`

**Interfaces:**
- Consumes: normalized DataFrame from `load_hourly_energy`.
- Produces: `Bucket = Literal["auto", "hour", "day", "week", "month"]`.
- Produces: `choose_auto_bucket(start_date: date, end_date: date) -> str`.
- Produces: `aggregate_history(hourly, start_date, end_date, bucket) -> tuple[pd.DataFrame, str]`.
- Result columns: `bucket_start`, `household_load_kwh`, `actual_solar_kwh`, `grid_export_kwh`.

- [ ] **Step 1: Write failing aggregation tests**

Create `tests/test_aggregation.py`:

```python
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
```

- [ ] **Step 2: Run aggregation tests to verify they fail**

Run: `python -m pytest tests/test_aggregation.py -v`

Expected: collection fails because `solar_model.aggregation` does not exist.

- [ ] **Step 3: Implement bucket selection and summed grouping**

Create `solar_model/aggregation.py`:

```python
from datetime import date
from typing import Literal
import pandas as pd

Bucket = Literal["auto", "hour", "day", "week", "month"]
VALUE_COLUMNS = ["household_load_kwh", "actual_solar_kwh", "grid_export_kwh"]

def choose_auto_bucket(start_date: date, end_date: date) -> str:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    days = (end_date - start_date).days + 1
    if days <= 3:
        return "hour"
    if days <= 56:
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

def aggregate_history(hourly, start_date, end_date, bucket):
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
```

- [ ] **Step 4: Run Task 2 tests and ingestion regressions**

Run: `python -m pytest tests/test_aggregation.py tests/test_data.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit historical aggregation**

```powershell
git add solar_model/aggregation.py tests/test_aggregation.py
git commit -m "feat: aggregate historical energy ranges"
```

---

### Task 3: Recurring Time-of-Use Rules

**Files:**
- Create: `solar_model/tou.py`
- Create: `tests/test_tou.py`

**Interfaces:**
- Produces: `TouValidationError(ValueError)`.
- Produces immutable `TouRule(name, start_month_day, end_month_day, weekdays, start_time, end_time, classification)`.
- Month/day values are `(month: int, day: int)` tuples.
- `weekdays` is `frozenset[int]` using Monday `0` through Sunday `6`.
- Classification is lowercase `"expensive"` or `"normal"`.
- Produces: `parse_tou_rules(rows: Sequence[Mapping[str, object]]) -> list[TouRule]`.
- Produces: `is_expensive(timestamp: datetime, rules: Sequence[TouRule]) -> bool`.

- [ ] **Step 1: Write failing TOU tests**

Create `tests/test_tou.py`:

```python
from datetime import datetime
import pytest
from solar_model.tou import TouValidationError, is_expensive, parse_tou_rules

def rule(**overrides):
    values = {
        "Name": "Summer peak",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "17:00",
        "End time": "20:00",
        "Classification": "Expensive",
    }
    values.update(overrides)
    return values

def test_weekday_peak_is_start_inclusive_end_exclusive():
    rules = parse_tou_rules([rule()])
    assert is_expensive(datetime(2026, 7, 6, 17), rules)
    assert not is_expensive(datetime(2026, 7, 6, 20), rules)
    assert not is_expensive(datetime(2026, 7, 5, 18), rules)

def test_overnight_rule_uses_starting_weekday():
    rules = parse_tou_rules([rule(**{
        "Name": "Overnight", "Start date": "01-01", "End date": "12-31",
        "Weekdays": "Mon", "Start time": "22:00", "End time": "06:00",
    })])
    assert is_expensive(datetime(2026, 7, 6, 23), rules)
    assert is_expensive(datetime(2026, 7, 7, 5), rules)
    assert not is_expensive(datetime(2026, 7, 7, 23), rules)

def test_year_wrapping_date_range_matches_both_sides_of_new_year():
    rules = parse_tou_rules([rule(**{
        "Start date": "11-01", "End date": "02-28",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    })])
    assert is_expensive(datetime(2026, 1, 12, 18), rules)
    assert is_expensive(datetime(2026, 12, 7, 18), rules)
    assert not is_expensive(datetime(2026, 7, 6, 18), rules)

def test_expensive_wins_when_normal_also_matches():
    rows = [rule(Classification="Normal"), rule(Name="Override", Classification="Expensive")]
    assert is_expensive(datetime(2026, 7, 6, 18), parse_tou_rules(rows))

def test_equal_start_and_end_time_is_rejected():
    with pytest.raises(TouValidationError, match="must differ"):
        parse_tou_rules([rule(**{"Start time": "17:00", "End time": "17:00"})])
```

- [ ] **Step 2: Run TOU tests to verify they fail**

Run: `python -m pytest tests/test_tou.py -v`

Expected: collection fails because `solar_model.tou` does not exist.

- [ ] **Step 3: Implement TOU parsing and matching**

Create `solar_model/tou.py` with:

```python
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal, Mapping, Sequence

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

class TouValidationError(ValueError):
    pass

@dataclass(frozen=True)
class TouRule:
    name: str
    start_month_day: tuple[int, int]
    end_month_day: tuple[int, int]
    weekdays: frozenset[int]
    start_time: time
    end_time: time
    classification: Literal["expensive", "normal"]
```

Implement `_parse_month_day(value, field)` by parsing `2000-{value}` with `%Y-%m-%d`; year 2000 permits February 29. Implement `_parse_time(value, field)` with `%H:%M`. Implement `_parse_weekdays(value)` from comma-separated three-letter names and reject blanks or unknown names.

Implement `parse_tou_rules` to require the seven display-column names used in the tests, normalize classification case, reject blank names, reject classifications outside Normal/Expensive, and reject equal start/end times. Prefix validation errors with the one-based editor row number.

Use these matching helpers:

```python
def _date_in_range(anchor: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    value = (anchor.month, anchor.day)
    return start <= value <= end if start <= end else value >= start or value <= end

def _rule_matches(timestamp: datetime, rule: TouRule) -> bool:
    current = timestamp.time()
    if rule.start_time < rule.end_time:
        if not (rule.start_time <= current < rule.end_time):
            return False
        anchor = timestamp.date()
    else:
        if current >= rule.start_time:
            anchor = timestamp.date()
        elif current < rule.end_time:
            anchor = timestamp.date() - timedelta(days=1)
        else:
            return False
    return anchor.weekday() in rule.weekdays and _date_in_range(
        anchor, rule.start_month_day, rule.end_month_day
    )

def is_expensive(timestamp: datetime, rules: Sequence[TouRule]) -> bool:
    return any(
        item.classification == "expensive" and _rule_matches(timestamp, item)
        for item in rules
    )
```

Normal matches need no special return because unmatched hours are Normal and Expensive wins overlaps.

- [ ] **Step 4: Run Task 3 tests**

Run: `python -m pytest tests/test_tou.py -v`

Expected: all TOU tests pass.

- [ ] **Step 5: Commit TOU rules**

```powershell
git add solar_model/tou.py tests/test_tou.py
git commit -m "feat: classify recurring time-of-use hours"
```

---

### Task 4: Solar and Battery Replay Engine

**Files:**
- Create: `solar_model/simulation.py`
- Create: `tests/test_simulation.py`

**Interfaces:**
- Consumes normalized columns `timestamp`, `household_load_kwh`, and `actual_solar_kwh`.
- Consumes `TouRule` and `is_expensive` from Task 3.
- Produces: `SimulationValidationError(ValueError)`.
- Produces immutable `BatteryConfig(capacity_kwh, starting_percent, reserve_percent, round_trip_efficiency, max_charge_kw, max_discharge_kw)`.
- Produces immutable `SimulationConfig(solar_scale, battery, strategy)` with strategy `"self_consumption"` or `"tou_reserve"`.
- Produces: `simulate(hourly, config, tou_rules) -> pd.DataFrame`.
- Result columns: `timestamp`, `household_load_kwh`, `modeled_solar_kwh`, `battery_soc_kwh`, `battery_charge_input_kwh`, `battery_discharge_output_kwh`, `grid_import_kwh`, `grid_export_kwh`, `is_expensive`.

- [ ] **Step 1: Write failing simulation tests**

Create `tests/test_simulation.py`:

```python
import pandas as pd
import pytest
from solar_model.simulation import (
    BatteryConfig, SimulationConfig, SimulationValidationError, simulate,
)
from solar_model.tou import parse_tou_rules

def frame(loads, solar, start="2026-07-06 17:00"):
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=len(loads), freq="h"),
        "household_load_kwh": loads,
        "actual_solar_kwh": solar,
    })

def battery(**overrides):
    values = dict(
        capacity_kwh=10.0, starting_percent=50.0, reserve_percent=10.0,
        round_trip_efficiency=1.0, max_charge_kw=5.0, max_discharge_kw=5.0,
    )
    values.update(overrides)
    return BatteryConfig(**values)

def test_self_consumption_discharges_for_any_deficit():
    result = simulate(
        frame([3.0], [0.0]),
        SimulationConfig(1.0, battery(), "self_consumption"), [],
    )
    assert result.loc[0, "battery_discharge_output_kwh"] == pytest.approx(3.0)
    assert result.loc[0, "grid_import_kwh"] == pytest.approx(0.0)
    assert result.loc[0, "battery_soc_kwh"] == pytest.approx(2.0)

def test_tou_reserve_preserves_normal_charge_and_discharge_in_peak():
    rules = parse_tou_rules([{
        "Name": "Peak", "Start date": "01-01", "End date": "12-31",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri", "Start time": "18:00",
        "End time": "20:00", "Classification": "Expensive",
    }])
    result = simulate(
        frame([2.0, 2.0], [0.0, 0.0]),
        SimulationConfig(1.0, battery(), "tou_reserve"), rules,
    )
    assert list(result["grid_import_kwh"]) == pytest.approx([2.0, 0.0])
    assert list(result["battery_soc_kwh"]) == pytest.approx([5.0, 3.0])

def test_solar_charging_honors_efficiency_capacity_and_exports_overflow():
    result = simulate(
        frame([0.0], [10.0]),
        SimulationConfig(1.0, battery(
            capacity_kwh=5.0, starting_percent=0.0, reserve_percent=0.0,
            round_trip_efficiency=0.81, max_charge_kw=10.0,
        ), "self_consumption"), [],
    )
    assert result.loc[0, "battery_charge_input_kwh"] == pytest.approx(5.0 / 0.9)
    assert result.loc[0, "battery_soc_kwh"] == pytest.approx(5.0)
    assert result.loc[0, "grid_export_kwh"] == pytest.approx(10.0 - 5.0 / 0.9)

def test_power_limit_and_reserve_bound_discharge():
    result = simulate(
        frame([8.0], [0.0]),
        SimulationConfig(1.0, battery(
            starting_percent=50.0, reserve_percent=20.0, max_discharge_kw=2.0,
        ), "self_consumption"), [],
    )
    assert result.loc[0, "battery_discharge_output_kwh"] == pytest.approx(2.0)
    assert result.loc[0, "grid_import_kwh"] == pytest.approx(6.0)
    assert result.loc[0, "battery_soc_kwh"] == pytest.approx(3.0)

def test_grid_import_never_charges_an_empty_battery():
    result = simulate(
        frame([3.0], [0.0]),
        SimulationConfig(1.0, battery(starting_percent=0.0, reserve_percent=0.0), "self_consumption"),
        [],
    )
    assert result.loc[0, "grid_import_kwh"] == pytest.approx(3.0)
    assert result.loc[0, "battery_charge_input_kwh"] == pytest.approx(0.0)
    assert result.loc[0, "battery_soc_kwh"] == pytest.approx(0.0)

def test_tou_reserve_requires_an_expensive_rule():
    with pytest.raises(SimulationValidationError, match="Expensive rule"):
        simulate(
            frame([1.0], [0.0]),
            SimulationConfig(1.0, battery(), "tou_reserve"),
            [],
        )

def test_every_hour_conserves_ac_bus_energy():
    result = simulate(
        frame([2.0, 1.0, 4.0], [5.0, 0.0, 1.0]),
        SimulationConfig(2.0, battery(round_trip_efficiency=0.9), "self_consumption"), [],
    )
    left = result["modeled_solar_kwh"] + result["grid_import_kwh"] + result["battery_discharge_output_kwh"]
    right = result["household_load_kwh"] + result["grid_export_kwh"] + result["battery_charge_input_kwh"]
    assert list(left) == pytest.approx(list(right), abs=1e-9)
```

- [ ] **Step 2: Run simulation tests to verify they fail**

Run: `python -m pytest tests/test_simulation.py -v`

Expected: collection fails because `solar_model.simulation` does not exist.

- [ ] **Step 3: Implement configuration validation**

Create `solar_model/simulation.py`:

```python
from dataclasses import dataclass
from math import isclose, isfinite, sqrt
from typing import Literal, Sequence
import pandas as pd
from .tou import TouRule, is_expensive

Strategy = Literal["self_consumption", "tou_reserve"]

class SimulationValidationError(ValueError):
    pass

@dataclass(frozen=True)
class BatteryConfig:
    capacity_kwh: float
    starting_percent: float
    reserve_percent: float
    round_trip_efficiency: float
    max_charge_kw: float
    max_discharge_kw: float

@dataclass(frozen=True)
class SimulationConfig:
    solar_scale: float
    battery: BatteryConfig
    strategy: Strategy
```

Implement `_validate_config(config, tou_rules)` to reject non-finite values; negative solar scale, capacity, or power; percentages outside 0–100; starting percentage below reserve; efficiency outside `(0, 1]`; unknown strategy; and TOU reserve without an Expensive rule.

- [ ] **Step 4: Implement deterministic hourly replay**

Inside a chronological `itertuples` loop, use:

```python
leg_efficiency = sqrt(config.battery.round_trip_efficiency)
capacity = config.battery.capacity_kwh
reserve = capacity * config.battery.reserve_percent / 100.0
soc = capacity * config.battery.starting_percent / 100.0

modeled_solar = row.actual_solar_kwh * config.solar_scale
direct_solar = min(modeled_solar, row.household_load_kwh)
surplus = modeled_solar - direct_solar
deficit = row.household_load_kwh - direct_solar
charge_input = min(
    surplus, config.battery.max_charge_kw,
    (capacity - soc) / leg_efficiency,
)
soc += charge_input * leg_efficiency
grid_export = surplus - charge_input
expensive = is_expensive(row.timestamp.to_pydatetime(), tou_rules)
may_discharge = config.strategy == "self_consumption" or expensive
discharge_output = 0.0
if may_discharge:
    discharge_output = min(
        deficit, config.battery.max_discharge_kw,
        (soc - reserve) * leg_efficiency,
    )
    soc -= discharge_output / leg_efficiency
grid_import = deficit - discharge_output
```

Clamp only floating-point drift within `1e-12` of reserve, capacity, or zero after verifying the unrounded value is within that tolerance. Append every result column in the interface block. At every hour, use `isclose(..., rel_tol=0, abs_tol=1e-9)` to enforce the AC-bus balance from the spec and raise `SimulationValidationError` with the timestamp if it fails.

- [ ] **Step 5: Run Task 4 tests and TOU regressions**

Run: `python -m pytest tests/test_simulation.py tests/test_tou.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit the replay engine**

```powershell
git add solar_model/simulation.py tests/test_simulation.py
git commit -m "feat: replay solar and battery scenarios"
```

---

### Task 5: Historical and Modeled Charts

**Files:**
- Create: `solar_model/charts.py`
- Create: `tests/test_charts.py`

**Interfaces:**
- Consumes aggregated history from Task 2 and simulation results from Task 4.
- Produces `SERIES_COLORS` with `Used=#2563EB`, `Production=#F59E0B`, `Battery=#7C3AED`, `Grid import=#DC2626`, `Grid export=#059669`.
- Produces: `build_history_figure(aggregated, visible_series) -> go.Figure`.
- Produces: `build_model_figure(result) -> go.Figure`.

- [ ] **Step 1: Write failing chart-structure tests**

Create `tests/test_charts.py`:

```python
import pandas as pd
from solar_model.charts import SERIES_COLORS, build_history_figure, build_model_figure

def test_history_figure_has_requested_grouped_bars_and_colors():
    data = pd.DataFrame({
        "bucket_start": [pd.Timestamp("2026-01-01")],
        "household_load_kwh": [10.0],
        "actual_solar_kwh": [4.0],
        "grid_export_kwh": [1.0],
    })
    figure = build_history_figure(data, ["Used", "Production", "Grid export"])
    assert [trace.name for trace in figure.data] == ["Used", "Production", "Grid export"]
    assert all(trace.type == "bar" for trace in figure.data)
    assert [trace.marker.color for trace in figure.data] == [
        SERIES_COLORS["Used"], SERIES_COLORS["Production"], SERIES_COLORS["Grid export"]
    ]
    assert figure.layout.barmode == "group"

def test_model_figure_has_battery_axis_and_signed_grid_panel():
    result = pd.DataFrame({
        "timestamp": pd.date_range("2026-07-01", periods=2, freq="h"),
        "household_load_kwh": [2.0, 3.0],
        "modeled_solar_kwh": [4.0, 1.0],
        "battery_soc_kwh": [5.0, 3.0],
        "battery_charge_input_kwh": [2.0, 0.0],
        "battery_discharge_output_kwh": [0.0, 2.0],
        "grid_import_kwh": [0.0, 0.5],
        "grid_export_kwh": [1.5, 0.0],
        "is_expensive": [False, True],
    })
    figure = build_model_figure(result)
    assert [trace.name for trace in figure.data] == [
        "Used", "Production", "Battery", "Grid import", "Grid export"
    ]
    assert list(figure.data[3].y) == [0.0, 0.5]
    assert list(figure.data[4].y) == [-1.5, -0.0]
    assert figure.data[2].yaxis == "y2"
    assert figure.data[3].yaxis == "y3"
    assert figure.layout.yaxis2.title.text == "Battery level (kWh)"
    assert figure.layout.yaxis3.title.text == "Grid exchange (kWh)"
```

- [ ] **Step 2: Run chart tests to verify they fail**

Run: `python -m pytest tests/test_charts.py -v`

Expected: collection fails because `solar_model.charts` does not exist.

- [ ] **Step 3: Implement stable Plotly chart construction**

Create `solar_model/charts.py` with `plotly.graph_objects` and `make_subplots`.

For history:

- Map Used to `household_load_kwh`, Production to `actual_solar_kwh`, and Grid export to `grid_export_kwh`.
- Reject unknown or empty series with `ValueError`.
- Add bars in requested order with approved colors.
- Set grouped bars, transparent backgrounds, a horizontal legend, `Time` x title, and `Energy (kWh)` y title.

For the modeled chart, start with:

```python
figure = make_subplots(
    rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
    row_heights=[0.72, 0.28],
    specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
)
```

Add Used and Production bars to row 1 primary y, Battery as a violet line to row 1 secondary y, Grid import bars to row 2, and negated Grid export bars to row 2. Give every trace its approved name and color. Set axis titles to `Hourly energy (kWh)`, `Battery level (kWh)`, `Grid exchange (kWh)`, and `Time`; add a zero line to grid exchange; keep legend toggling enabled.

- [ ] **Step 4: Run Task 5 tests**

Run: `python -m pytest tests/test_charts.py -v`

Expected: both chart tests pass.

- [ ] **Step 5: Commit chart construction**

```powershell
git add solar_model/charts.py tests/test_charts.py
git commit -m "feat: chart historical and modeled energy"
```

---

### Task 6: Streamlit Prototype and Handoff

**Files:**
- Create: `.streamlit/config.toml`
- Create: `app.py`
- Create: `tests/test_app.py`
- Create: `README.md`

**Interfaces:**
- Consumes every public interface from Tasks 1–5.
- Exposes local command `streamlit run app.py`.
- Exposes pages `Historical view` and `System model`.
- Keeps scalar model controls in the sidebar and the wide TOU editor below the modeled charts.

- [ ] **Step 1: Add the accent and write a failing app smoke test**

Create `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#2563EB"
```

Create `tests/test_app.py`:

```python
from streamlit.testing.v1 import AppTest

def test_app_starts_against_supplied_csvs_without_exceptions():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Home Energy Model"
    assert app.radio[0].options == ["Historical view", "System model"]
    app.radio[0].set_value("System model").run()
    assert not app.exception
```

- [ ] **Step 2: Run the app smoke test to verify it fails**

Run: `python -m pytest tests/test_app.py -v`

Expected: FAIL because `app.py` does not exist.

- [ ] **Step 3: Build the shell and cached load**

Create `app.py`:

```python
from datetime import timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from solar_model.aggregation import aggregate_history
from solar_model.charts import build_history_figure, build_model_figure
from solar_model.data import DataValidationError, load_hourly_energy
from solar_model.simulation import (
    BatteryConfig, SimulationConfig, SimulationValidationError, simulate,
)
from solar_model.tou import TouValidationError, parse_tou_rules

ROOT = Path(__file__).parent
UTILITY_PATH = ROOT / "combined-electric-usage.csv"
SOLAR_PATH = ROOT / "combined-monthly-energy.csv"
BASE_SOLAR_KW = 1.29

st.set_page_config(page_title="Home Energy Model", page_icon="☀️", layout="wide")
st.title("Home Energy Model")

@st.cache_data(show_spinner="Loading energy history…")
def load_data() -> pd.DataFrame:
    return load_hourly_energy(UTILITY_PATH, SOLAR_PATH)

try:
    hourly = load_data()
except (OSError, DataValidationError) as error:
    st.error(f"Energy data could not be loaded: {error}")
    st.stop()

page = st.radio(
    "View", ["Historical view", "System model"], horizontal=True,
    label_visibility="collapsed",
)
```

Add `render_history(hourly)` and `render_model(hourly)`, then dispatch on `page`. Keep calculations in imported modules.

- [ ] **Step 4: Implement the Historical view**

In `render_history`:

1. Get minimum and maximum dates from `timestamp`.
2. Put a date-range input, Auto/Hour/Day/Week/Month selector, and Used/Production/Grid export multiselect in `st.sidebar`.
3. Default to full range, Auto, and all three series.
4. Require exactly two dates and at least one series.
5. Call `aggregate_history` and `build_history_figure`.
6. Sum filtered hourly data and show Household use, Solar produced, and Grid exported metrics.
7. Caption the resolved bucket and call `st.plotly_chart(..., use_container_width=True)`.

Do not recalculate household load in the UI.

- [ ] **Step 5: Implement model controls and TOU editor**

Default to the latest complete seven days. Add sidebar controls:

```python
start_date = st.sidebar.date_input(
    "Start date", value=default_start, min_value=min_date, max_value=max_date
)
duration = st.sidebar.number_input(
    "Duration (days)", min_value=1, max_value=7, value=7, step=1
)
solar_scale = st.sidebar.number_input(
    "Solar scale", min_value=0.0, value=1.0, step=0.1
)
st.sidebar.caption(f"Equivalent array: {BASE_SOLAR_KW * solar_scale:.2f} kW")
strategy_label = st.sidebar.selectbox(
    "Battery strategy", ["Self-consumption", "TOU reserve"]
)
capacity = st.sidebar.number_input(
    "Battery usable capacity (kWh)", min_value=0.0, value=13.5, step=0.5
)
```

In `st.sidebar.expander("Advanced battery settings")`, add Starting charge 50%, Minimum reserve 10%, Round-trip efficiency 90%, Maximum charge power 5.0 kW, and Maximum discharge power 5.0 kW with spec-valid bounds.

Create the chart placeholder before the wide editor so the completed chart renders above it:

```python
chart_slot = st.empty()
st.subheader("Time-of-use rules")
st.caption("Add your current schedule. Dates use MM-DD; weekdays use Mon,Tue,…")
default_rules = pd.DataFrame(columns=[
    "Name", "Start date", "End date", "Weekdays",
    "Start time", "End time", "Classification",
])
edited_rules = st.data_editor(
    default_rules, num_rows="dynamic", use_container_width=True, key="tou_rules"
)
```

Convert nonblank rows to dictionaries and call `parse_tou_rules`. Show `TouValidationError` under the editor and place a concise instruction in `chart_slot` rather than simulating invalid input.

- [ ] **Step 6: Run the model and render results**

Filter through `start_date + duration - 1 day` and reject selections beyond the shared range. Construct:

```python
battery = BatteryConfig(
    capacity_kwh=capacity,
    starting_percent=starting_percent,
    reserve_percent=reserve_percent,
    round_trip_efficiency=round_trip_percent / 100.0,
    max_charge_kw=max_charge_kw,
    max_discharge_kw=max_discharge_kw,
)
config = SimulationConfig(
    solar_scale=solar_scale,
    battery=battery,
    strategy="self_consumption" if strategy_label == "Self-consumption" else "tou_reserve",
)
result = simulate(selected, config, rules)
```

Catch `SimulationValidationError` in `chart_slot`. Otherwise fill `chart_slot.container()` with total Grid import, Expensive import, and Grid export metrics plus `build_model_figure(result)`. The Plotly legend supplies all five toggles; do not add duplicate Streamlit toggles.

- [ ] **Step 7: Run the app smoke test and full suite**

Run: `python -m pytest -v`

Expected: every data, aggregation, TOU, simulation, chart, and app test passes.

- [ ] **Step 8: Write the local-use README**

Create `README.md` containing:

- Purpose and prototype limitations.
- Python 3.11 prerequisite.
- `python -m pip install -e ".[dev]"` setup.
- `streamlit run app.py` launch.
- Exact input filenames and source columns.
- Household-load formula.
- Hourly replay, solar-only charging, both strategies, efficiency, and starting-state assumptions.
- Statement that CSVs and session settings remain local and uncommitted.
- `python -m pytest -v` test command.

- [ ] **Step 9: Manually verify the real UI**

Launch: `streamlit run app.py`

Verify:

1. Full-year history opens with weekly Auto buckets and three vibrant bars.
2. One-day history resolves hourly; Month override produces monthly totals.
3. Historical series can be hidden and restored.
4. Model defaults to the latest complete seven days and 1.29 kW at scale 1.0.
5. A summer week at scale 3.0 and 13.5 kWh battery shows green export below zero when surplus remains.
6. Self-consumption and TOU reserve differ after adding an Expensive rule.
7. Battery stays within reserve/capacity and never grid-charges.
8. The legend hides each of five modeled series.
9. Narrow width stacks controls without clipping.
10. Invalid TOU input and out-of-range periods show concise errors without tracebacks.

Stop Streamlit after verification.

- [ ] **Step 10: Commit the runnable prototype**

```powershell
git add .streamlit/config.toml app.py tests/test_app.py README.md
git commit -m "feat: add local home energy modeling app"
```

- [ ] **Step 11: Run final branch verification**

Run:

```powershell
python -m pytest -v
git status --short
```

Expected: every test passes and the working tree is clean because `.gitignore` excludes the local CSVs and visual drafts.

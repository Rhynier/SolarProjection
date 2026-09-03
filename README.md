# Home Energy Model

This is a local Streamlit prototype for exploring historical household energy
use and replaying it with different solar and battery assumptions. It is not a
production service: it has no accounts, database, forecast, named scenarios,
or cloud persistence. It retains local user configuration.

## Run locally

Python 3.11 is required. From the project directory, install the prototype and
development test dependency:

```powershell
python -m pip install -e ".[dev]"
streamlit run app.py
```

Run the automated checks with:

```powershell
python -m pytest -v
```

## Saved configuration

Valid changes to export rates, battery settings, solar-production scaling, and
time-of-use rules save automatically to:

```text
~/.home-energy-model/config.json
```

Date ranges, aggregation, chart-series visibility, and the selected page remain
session-only. Set `HOME_ENERGY_MODEL_CONFIG_PATH` to a complete alternate file
path for isolated development or testing.

If the file is malformed, uses an unsupported version, or contains unknown
fields, the app shows a warning, uses defaults for that session, and does not
overwrite the file.

## Local inputs and assumptions

Keep these uncommitted files in the project root:

- `combined-electric-usage.csv`, with `DATE`, `START TIME`, `END TIME`,
  `IMPORT (kWh)`, `EXPORT (kWh)`, `COST`, and `NOTES`.
- `combined-monthly-energy.csv`, with `Date/Time` and
  `Energy Produced (Wh)`.

Set `HOME_ENERGY_MODEL_UTILITY_CSV` and/or `HOME_ENERGY_MODEL_SOLAR_CSV` to read
either input from an alternate path. The automated tests use these overrides to
point the app at a committed, deterministic synthetic dataset
(`tests/sample_data.py`), so `python -m pytest` passes without the personal CSVs;
the one test that validates the real exports is skipped when they are absent.

The app aligns matching utility and solar hours. Its estimated household load
is `grid import + actual solar production - grid export` (all in kWh).

The system model replays selected historical hours. The Configuration view
places Solar production scaling immediately before its shared TOU editor.
Annual production scaling divides the proposed system's configured annual
production by the configured reference annual production; both values default
to `2017.56 kWh`. Monthly scaling provides independent reference and proposed
values for every calendar month and applies each calculated ratio only to
historical hours in that month. The System model sidebar shows a read-only
summary of the active scaling configuration.
The monthly values initially distribute the retained annual settings as evenly
as possible at four-decimal kWh precision, while the annual fields become
read-only monthly totals. Annual and monthly settings remain independent when
switching modes. Monthly reference and proposed values are required; invalid
values stop simulation with a month-specific error. The historical
household-load curve stays fixed. The battery charges from solar surplus only,
never from the grid. Both self-consumption and TOU-reserve strategies obey
usable capacity, reserve, starting charge, AC-side charge and discharge limits,
and symmetric per-leg efficiency derived from the configured round-trip
efficiency. Starting charge and minimum reserve appear directly beneath Battery
strategy; efficiency and charge/discharge power remain in Advanced battery
settings. The Configuration view's shared TOU editor starts with SMUD's
published 2026 rates, without holiday exceptions. TOU reserve derives Cheap,
Less Expensive, and Expensive tiers from each season's configured prices and
discharges only at the seasonal maximum.

The Historical and System model views share one period and one aggregation
setting. Choose all available data, a seven-day range beginning on a selected
Start date, a one-month range ending one day before the corresponding date in
the next month, or a custom inclusive date range. Week and month modes include
previous/next navigation and clearly identify ranges clipped by the available
data. New sessions default to a custom one-month range beginning on the first
date with available data. The model still simulates every selected hour in
order; aggregation changes only the chart, summing energy flows and showing the
final battery level in each hour, day, week, or month bucket.

Both views show a Projected cost calculated as hourly grid imports at the shared
configured TOU rate minus grid exports at the configured utility purchase rate.
The Historical view defaults that export rate to $0.0563/kWh; the System model
defaults it to $0.0960/kWh. Beneath the model's Grid exchange panel, one signed
Net cost bar per time bucket shows net charges above zero and net export credits
below zero. The projection excludes fixed charges, taxes, fees, and other bill
adjustments.

The CSVs and Streamlit session settings remain local and uncommitted. Restart
the app after replacing either CSV export.

# Home Energy Modeling Tool Design

**Status:** Approved for implementation
**Date:** 2026-09-01

## Purpose

Build a local, personal-use prototype for exploring historical household energy behavior and replaying that behavior against hypothetical larger solar and battery systems. The tool favors clear assumptions and useful visual feedback over production packaging or customer-facing polish.

## Goals

- Plot historical household use, solar production, and grid export over a selectable time range.
- Aggregate historical bars into sensible hourly, daily, weekly, or monthly buckets.
- Replay one to seven historical days at hourly resolution with scaled solar production and a configurable battery.
- Compare self-consumption and time-of-use battery strategies.
- Show modeled household use, solar production, battery level, grid import, and grid export.
- Project utility energy cost from hourly import prices and a configurable export purchase rate.
- Keep the application local, small, and easy to change.

## Non-goals

- Production deployment, authentication, accounts, or a database.
- Detailed billing, fixed charges, taxes, fees, or payback calculations.
- Automatic system-size optimization.
- Named or persisted modeling scenarios.
- Future weather or load forecasting.
- Grid charging or energy-rate arbitrage.
- Extensive UI automation, packaging, or production test infrastructure.

## Technology and Runtime

The application will use Python 3.11, Streamlit, pandas, and Plotly. It will run locally with a command such as:

```powershell
streamlit run app.py
```

The application reads these fixed files from the project directory on startup:

- `combined-electric-usage.csv`
- `combined-monthly-energy.csv`

Replacing a file with an updated export of the same schema and restarting the application refreshes the data. No upload workflow is required for this prototype.

## Input Data and Normalization

### Utility data

The utility file contains one local-clock row per represented hour:

- `DATE`
- `START TIME`
- `END TIME`
- `IMPORT (kWh)`
- `EXPORT (kWh)`
- `COST`
- `NOTES`

The model uses import and export. The source Cost and Notes fields are required for source compatibility but are not used; Projected cost is calculated from configured rates.

### Solar data

The solar file contains 15-minute readings:

- `Date/Time`, including a UTC offset
- `Energy Produced (Wh)`

Solar timestamps are parsed as offset-aware timestamps and ordered by absolute time. Production is converted from Wh to kWh and summed into the local date-and-hour key used by the utility file. Repeated fall-back timestamps remain distinct during parsing and both contribute to the matching utility hour; a spring-forward hour absent from the utility data is not invented.

### Shared hourly dataset

The application uses only the date range for which both sources have matching utility-hour keys. It does not interpolate missing hours.

For each matching hour, estimated household load is:

```text
household_load_kwh = grid_import_kwh + actual_solar_production_kwh - grid_export_kwh
```

This actual derived load is used by both views. Hypothetical solar scaling changes modeled production only; it never changes the historical household-load curve.

The application may retain raw grid import as diagnostic data, but the label **Used** always means estimated total household load.

## Application Structure

The code will stay divided into small modules with explicit responsibilities:

- `app.py`: Streamlit page shell, controls, and presentation flow.
- `solar_model/data.py`: CSV validation, parsing, hourly alignment, and household-load derivation.
- `solar_model/aggregation.py`: historical date filtering and bucket aggregation.
- `solar_model/tou.py`: time-of-use rule validation and hour classification.
- `solar_model/simulation.py`: deterministic hourly solar-and-battery replay.
- `solar_model/costs.py`: shared projected utility cost calculation and currency formatting.
- `solar_model/charts.py`: Plotly figure construction and stable series styling.
- `tests/`: focused calculation and real-data smoke tests.

UI code consumes normalized data and simulation results; it does not reproduce energy calculations. The simulation code has no Streamlit dependency so it can be tested directly.

## Historical View

The Historical view provides:

- A date-range selector constrained to the shared dataset.
- A bucket selector with `Auto`, `Hour`, `Day`, `Week`, and `Month`.
- Series selection for Used, Produced, and Exported.
- Utility purchase rate for exported energy, defaulting to $0.0563/kWh.
- A grouped bar chart, energy totals, and Projected cost for the selected period.

Auto bucketing uses:

- Hourly for ranges up to 3 days.
- Daily for ranges up to 8 weeks.
- Weekly for ranges up to 18 months.
- Monthly for longer ranges.

Manual bucket selection overrides Auto. Every bucket uses sums because each series represents energy, not instantaneous power.

## System Model View

The System model replays a selected historical period of one through seven days at hourly resolution.

### Controls

- Start date.
- Duration from 1 to 7 days.
- Solar production scaling factor.
- Utility purchase rate for exported energy, defaulting to $0.0960/kWh.
- Equivalent nominal array size, calculated from the existing 1.29 kW system.
- Battery usable capacity in kWh.
- Starting state of charge as a percentage.
- Minimum reserve as a percentage.
- Round-trip efficiency as a percentage.
- Maximum AC-side charge power in kW.
- Maximum AC-side discharge power in kW.
- Strategy: Self-consumption or TOU reserve.
- Editable time-of-use rules.

Battery and TOU changes remain in the current Streamlit session and reset to defaults when the application restarts.

### Startup defaults

- Historical view: full shared range, Auto bucket, and all three series visible.
- Model period: the most recent complete seven days in the shared range.
- Solar scale: 1.0.
- Strategy: Self-consumption.
- Battery usable capacity: 13.5 kWh.
- Starting charge: 50 percent.
- Minimum reserve: 10 percent.
- Round-trip efficiency: 90 percent.
- Maximum charge and discharge power: 5 kW each.
- TOU rules: SMUD's published 2026 Time-of-Day schedule and prices, ignoring holiday exceptions.
- Historical export purchase rate: $0.0563/kWh.
- System-model export purchase rate: $0.0960/kWh.

TOU reserve requires at least one season with multiple prices. This avoids presenting a model that silently preserves the battery for a schedule with no seasonal maximum above its minimum.

### Time-of-use rules

Each editable rule has:

- Name.
- Recurring effective start and end month/day.
- Applicable weekdays.
- Start and end time.
- Price in dollars per kWh.

Effective date endpoints are inclusive. Time intervals are start-inclusive and end-exclusive. Equal start and end times represent a full day. Overnight time ranges and date ranges that wrap across the end of the year are supported. For an overnight rule, the applicable weekday is the day on which the interval starts.

If multiple valid rules match, the highest price wins. Within each season, the minimum price is Cheap, the maximum price is Expensive, and any intermediate price is Less Expensive. Hours without a matching rule have no price and are not Expensive.

### Projected utility cost

Both views calculate Projected cost over their selected hourly data:

```text
sum(grid_import_kwh * hourly_import_price)
  - sum(grid_export_kwh * export_purchase_rate)
```

Historical import uses the preloaded SMUD schedule. System-model import uses the editable time-of-use rules and modeled grid exchange. A negative result is displayed as a net credit. Imported energy without a matching utility price is a validation error.

## Hourly Simulation

For each selected utility hour:

1. Multiply actual solar production by the selected scale factor.
2. Apply solar directly to household load.
3. Send any solar surplus to the battery, subject to capacity, charge-power, and efficiency limits.
4. Export remaining solar surplus to the grid.
5. Handle any remaining load deficit according to the selected battery strategy.
6. Import any deficit that solar and permitted battery discharge cannot serve.

The battery never charges from the grid.

### Efficiency and power limits

Let `round_trip_efficiency` be a value greater than zero and no greater than one. The application uses a symmetric per-leg efficiency:

```text
leg_efficiency = sqrt(round_trip_efficiency)
```

Maximum charge and discharge settings are AC-side power limits. With one-hour simulation steps, a kW limit has the same numeric value as the maximum kWh transferred at the AC bus during that step.

For charging:

```text
charge_input_kwh = min(
    solar_surplus_kwh,
    max_charge_kw,
    (capacity_kwh - state_of_charge_kwh) / leg_efficiency
)

stored_energy_added_kwh = charge_input_kwh * leg_efficiency
```

For discharging:

```text
deliverable_from_battery_kwh = min(
    remaining_load_deficit_kwh,
    max_discharge_kw,
    (state_of_charge_kwh - reserve_kwh) * leg_efficiency
)

stored_energy_removed_kwh = deliverable_from_battery_kwh / leg_efficiency
```

Battery state of charge stays between the configured reserve and usable capacity. The starting percentage makes the beginning-of-period assumption explicit and must not be below the reserve.

### Strategies

**Self-consumption** discharges the battery for any load deficit while charge remains above reserve.

**TOU reserve** discharges the battery only when the current hour uses the maximum configured price for its season. At Cheap, Less Expensive, or unmatched hours, grid import serves any deficit and stored energy is preserved.

Both strategies always allow direct solar consumption and solar-only charging.

### Energy balance

Every simulated hour must satisfy the AC-bus balance within a small floating-point tolerance:

```text
scaled_solar
  + grid_import
  + battery_energy_delivered
= household_load
  + grid_export
  + battery_charge_input
```

Battery state changes independently account for charge and discharge efficiency losses.

## Modeled Charts and Results

The modeled result uses two vertically aligned panels with a shared hourly time axis:

1. **Home and battery:** grouped bars for household use and scaled solar production, plus a violet battery-level line on a secondary kWh axis.
2. **Grid exchange:** red import bars above zero and green export bars below zero.

The chart legend can hide Used, Production, Battery, Grid import, or Grid export. Default styling uses a vibrant but readable mapping:

- Used: blue.
- Production: amber.
- Battery: violet.
- Grid import: red.
- Grid export: green.

Summary values show:

- Total grid import.
- Grid import during Expensive hours.
- Total grid export.
- Projected cost.

Scalar and strategy controls remain in a left sidebar on wider screens and stack above results at narrow widths. Because it needs more horizontal space, the TOU rule editor sits beneath the charts in the main content area.

## Validation and Error Handling

The prototype fails clearly instead of silently correcting data. The application validates:

- Required columns and parseable numeric values.
- Offset-aware solar timestamps.
- Unique utility date-and-hour keys.
- Unique solar absolute timestamps before hourly aggregation.
- A matching solar hour for every utility hour used in the shared dataset.
- Nonnegative import, export, production, and derived household load.
- Requested dates within the shared data range.
- Valid TOU date, weekday, and time values.
- Nonnegative capacity and power limits.
- Reserve and starting percentages from 0 through 100, with starting charge at or above reserve.
- Round-trip efficiency greater than 0 and no greater than 100 percent.

Errors appear in the Streamlit page with a concise explanation, a count when several rows are affected, and a few representative timestamps or row numbers. Invalid model configuration prevents simulation but does not prevent the Historical view from loading when the source data itself is valid.

## Verification Scope

Focused automated tests will cover:

- CSV schema validation and hourly alignment.
- Wh-to-kWh conversion and household-load derivation.
- Daylight-saving fall-back and spring-forward behavior.
- Auto and manual time bucketing.
- Recurring, overnight, year-wrapping, and overlapping TOU rules.
- Self-consumption and TOU-reserve behavior.
- Starting charge, reserve, capacity, efficiency, and charge/discharge limits.
- Solar-only charging.
- Grid import and export calculations.
- Hourly energy balance and battery bounds.

A smoke test loads the two supplied CSVs and confirms that the normalized dataset is nonempty, aligned, chronologically ordered, and free from negative derived loads.

Manual verification will launch Streamlit against the real files, exercise both pages and strategies, inspect a summer week with modeled export, and confirm that chart controls and responsive stacking behave as designed.

## Acceptance Criteria

- The application launches locally and reads the two supplied CSVs without modification.
- The Historical view filters dates, chooses logical buckets, toggles the three requested series, and reports correct summed values.
- Both views show Projected cost using their configured export purchase rates and the applicable hourly import prices.
- The model replays any valid one-to-seven-day period with configurable solar, battery, strategy, and TOU inputs.
- The model chart displays use, production, battery level, grid import, and grid export with the approved color mapping and split-panel layout.
- Both strategies obey reserve, efficiency, power, capacity, and solar-only charging rules.
- Invalid inputs produce clear local errors rather than guessed or silently corrected output.
- Focused tests and the real-data smoke test pass.

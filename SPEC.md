# Home Energy Model Specification

**Status:** Authoritative specification for the current prototype
**Last updated:** 2026-09-01

## 1. Purpose

Home Energy Model is a local, personal-use Streamlit application for exploring
historical household electricity behavior and replaying that behavior against
hypothetical solar and battery configurations.

The application prioritizes transparent assumptions, deterministic calculations,
and useful visual comparison. It is a prototype, not customer-facing or
production software.

## 2. Goals

The application must:

- Display historical household use, solar production, and grid export over a
  selectable time range.
- Aggregate historical energy into readable hourly, daily, weekly, or monthly
  buckets.
- Replay one to seven historical days at hourly resolution.
- Scale production from the existing 1.29 kW solar array to represent a larger
  hypothetical array.
- Model a configurable battery that charges from solar surplus only.
- Support both self-consumption and time-of-use reserve strategies.
- Display modeled household use, production, battery state of charge, grid
  import, and grid export.
- Keep source data and model settings local to the user's computer.

## 3. Non-goals

The prototype does not provide:

- Production deployment, authentication, authorization, accounts, or a database.
- Cloud storage, telemetry, or external service integrations.
- Dollar-cost totals, bill calculations, payback analysis, or financial advice.
- Automatic solar or battery sizing recommendations.
- Named, saved, or shareable modeling scenarios.
- Future load, production, or weather forecasts.
- Grid charging, rate arbitrage, or battery export to the grid.
- Holiday-aware TOU scheduling.
- A packaged Windows executable or installer.

TOU prices classify hours for battery dispatch. They do not calculate a bill.

## 4. Runtime and Local Files

### 4.1 Technology

The application uses:

- Python 3.11 or later within the supported project range.
- Streamlit for the local user interface.
- pandas and NumPy for data processing.
- Plotly for charts.
- pytest for automated verification.

The application starts from the repository root with:

```powershell
python -m streamlit run app.py
```

### 4.2 Required input files

The following files must exist beside `app.py`:

- `combined-electric-usage.csv`
- `combined-monthly-energy.csv`

The filenames are fixed. Replacing either file with a newer export of the same
schema and restarting the application reloads the data. There is no upload UI.

The CSV files are local data and must remain uncommitted.

## 5. Input Data Contract

### 5.1 Utility data

`combined-electric-usage.csv` must contain:

- `DATE`
- `START TIME`
- `END TIME`
- `IMPORT (kWh)`
- `EXPORT (kWh)`
- `COST`
- `NOTES`

The application uses `DATE`, `START TIME`, import, and export. The remaining
columns are required to match the expected source schema but are not used in
calculations.

Each represented utility hour must have a unique local date-and-start-time key.
Import and export must be finite, numeric, and nonnegative.

### 5.2 Solar data

`combined-monthly-energy.csv` must contain:

- `Date/Time`, including an explicit UTC offset.
- `Energy Produced (Wh)`.

Solar timestamps are parsed as absolute offset-aware timestamps. Duplicate
absolute timestamps are invalid. Production must be finite, numeric, and
nonnegative.

Production is converted from Wh to kWh and summed by the local date and hour
used by the utility export. The nominal source system size is 1.29 kW.

### 5.3 Daylight-saving behavior

- Repeated fall-back readings remain distinct as absolute timestamps before
  their energy is combined into the applicable local utility hour.
- A spring-forward hour absent from the utility data is not invented.
- The application does not interpolate missing hours.

## 6. Normalized Hourly Dataset

The application uses the overlapping date range of the two sources. Every
utility hour retained in that range must have matching solar production.

The normalized dataset is chronologically ordered and contains:

- `timestamp`
- `grid_import_kwh`
- `grid_export_kwh`
- `actual_solar_kwh`
- `household_load_kwh`

Estimated total household load is:

```text
household_load_kwh = grid_import_kwh + actual_solar_kwh - grid_export_kwh
```

All normalized energy values must be finite and nonnegative. The label **Used**
always means `household_load_kwh`, not utility import alone.

Historical household load remains fixed during modeling. Solar scaling changes
modeled production only.

## 7. Application Structure

The code is divided by responsibility:

- `app.py`: Streamlit page shell, controls, session state, and presentation.
- `solar_model/data.py`: CSV validation, normalization, source alignment, and
  household-load derivation.
- `solar_model/aggregation.py`: inclusive date filtering and energy aggregation.
- `solar_model/tou.py`: TOU defaults, rule validation, price lookup, and rate
  classification.
- `solar_model/simulation.py`: deterministic hourly solar and battery replay.
- `solar_model/charts.py`: Plotly chart construction and stable styling.
- `tests/`: unit, integration, real-data, and Streamlit smoke tests.

`app.py` must delegate energy calculations to the model modules. The simulation
and data-processing modules must not depend on Streamlit.

## 8. Historical View

The Historical view is the default page.

### 8.1 Controls

The sidebar provides:

- An inclusive date range constrained to the shared dataset.
- An aggregation selector: `Auto`, `Hour`, `Day`, `Week`, or `Month`.
- A multi-select for `Used`, `Production`, and `Grid export`.

The defaults are the full shared date range, `Auto`, and all three series.
Exactly two dates and at least one series are required.

### 8.2 Automatic aggregation

Auto selects:

- Hour for inclusive ranges of 1 through 3 days.
- Day for inclusive ranges of 4 through 57 days.
- Week for longer ranges through 18 calendar months.
- Month for ranges longer than 18 calendar months.

Weekly buckets begin on Monday. Monthly buckets begin on the first day of the
month. Manual selection overrides Auto. Every bucket uses sums because all
displayed values represent energy.

### 8.3 Results

The page shows:

- Total household use.
- Total solar production.
- Total grid export.
- The resolved aggregation bucket.
- A grouped bar chart containing the selected series.

## 9. System Model View

The System model replays an inclusive historical period of one through seven
days at hourly resolution.

### 9.1 Period and solar controls

The sidebar provides:

- Start date, constrained to the shared dataset.
- Duration from 1 to 7 days.
- Solar scale, which must be nonnegative.
- Equivalent nominal array size:

```text
equivalent_array_kw = 1.29 * solar_scale
```

The default period is the latest seven days in the shared dataset. Solar scale
defaults to 1.0.

### 9.2 Battery strategy

The strategy choices are:

- `Self-consumption`
- `TOU reserve`

Self-consumption is the default.

### 9.3 Battery settings modes

The user chooses either `Custom values` or `Battery preset`.

#### Custom values

Custom mode allows direct editing of:

- Usable capacity in kWh, default 13.5.
- Round-trip efficiency, default 90 percent.
- Maximum AC-side charge power, default 5.0 kW.
- Maximum AC-side discharge power, default 5.0 kW.

#### Battery presets

Preset mode provides:

| Battery model | Usable capacity | Round-trip efficiency | Max charge | Max discharge |
|---|---:|---:|---:|---:|
| Tesla Powerwall 3 | 13.5 kWh | 89% | 5.0 kW | 11.5 kW |
| Enphase IQ Battery 10C | 10.0 kWh | 90% | 7.08 kW | 7.08 kW |

The number of batteries is an integer of at least one. Capacity, maximum charge
power, and maximum discharge power scale linearly by quantity. Round-trip
efficiency does not scale. Preset-derived fields are read-only.

Switching between custom and preset modes must preserve the user's custom
values for the current session.

### 9.4 Common battery controls

Both battery modes provide:

- Starting state of charge from 0 through 100 percent, default 50 percent.
- Minimum reserve from 0 through 100 percent, default 10 percent.

Starting state of charge must not be below the reserve.

### 9.5 Session behavior

Model dates, duration, solar scale, strategy, battery mode, battery model,
battery quantity, custom battery values, common battery values, and TOU edits
must survive navigation between the two pages during the current Streamlit
session.

All session settings reset when the application process restarts. No settings
are written to disk.

## 10. Time-of-Use Rules

### 10.1 Editor schema

The editable table appears in the main content area beneath the modeled result
and contains:

- `Name`
- `Start date` in `MM-DD` format.
- `End date` in `MM-DD` format.
- `Weekdays` as comma-separated three-letter names.
- `Start time` in `HH:MM` format.
- `End time` in `HH:MM` format.
- `Price ($/kWh)` as a finite nonnegative number.

Rows may be added or removed. Blank rows are ignored. Invalid nonblank rows stop
simulation and show a concise row-specific error.

### 10.2 Default SMUD schedule

New sessions preload this 2026 SMUD Time-of-Day schedule:

| Season | Days | Time | Price |
|---|---|---|---:|
| Non-summer, Oct 1-May 31 | Mon-Fri | 00:00-17:00 | $0.1285/kWh |
| Non-summer, Oct 1-May 31 | Mon-Fri | 17:00-20:00 | $0.1776/kWh |
| Non-summer, Oct 1-May 31 | Mon-Fri | 20:00-00:00 | $0.1285/kWh |
| Non-summer, Oct 1-May 31 | Sat-Sun | All day | $0.1285/kWh |
| Summer, Jun 1-Sep 30 | Mon-Fri | 00:00-12:00 | $0.1550/kWh |
| Summer, Jun 1-Sep 30 | Mon-Fri | 12:00-17:00 | $0.2139/kWh |
| Summer, Jun 1-Sep 30 | Mon-Fri | 17:00-20:00 | $0.3765/kWh |
| Summer, Jun 1-Sep 30 | Mon-Fri | 20:00-00:00 | $0.2139/kWh |
| Summer, Jun 1-Sep 30 | Sat-Sun | All day | $0.1550/kWh |

Holiday exceptions are intentionally ignored; holidays are classified using
their ordinary weekday.

### 10.3 Matching semantics

- Effective start and end month/day values are inclusive.
- A time interval is start-inclusive and end-exclusive.
- Equal start and end times represent an all-day rule.
- Overnight intervals are supported.
- For an overnight interval, the applicable weekday and season date are the day
  on which the interval starts.
- Effective date ranges may wrap across the end of the year.
- If multiple rules match an hour, the highest matching price wins.
- An unmatched hour has no price and is not Expensive.

### 10.4 Seasonal classification

For the season containing a matched rule's anchor date:

- The lowest configured price is Cheap.
- The highest configured price is Expensive.
- Any price between the minimum and maximum is Less Expensive.

Classification is derived from configured prices; it is not manually entered.
TOU reserve requires at least one recurring date on which the configured rules
contain more than one distinct price.

## 11. Hourly Simulation

For each selected historical hour, the simulation:

1. Multiplies actual solar production by the solar scale.
2. Applies modeled solar directly to household load.
3. Sends solar surplus to the battery, subject to capacity, charge-power, and
   efficiency limits.
4. Exports remaining solar surplus to the grid.
5. Handles remaining load deficit according to the selected strategy.
6. Imports any deficit that solar and permitted battery discharge cannot serve.

The battery never charges from grid import.

### 11.1 Efficiency

Round-trip efficiency must be greater than zero and no greater than one when
represented as a fraction. The simulation uses symmetric per-leg efficiency:

```text
leg_efficiency = sqrt(round_trip_efficiency)
```

### 11.2 Charge behavior

Charge and discharge limits are AC-side kW limits. Each simulation interval is
one hour, so the numeric kW limit is also the maximum AC-side kWh transfer for
that interval.

```text
charge_input_kwh = min(
    solar_surplus_kwh,
    max_charge_kw,
    (capacity_kwh - state_of_charge_kwh) / leg_efficiency
)

stored_energy_added_kwh = charge_input_kwh * leg_efficiency
```

Any surplus beyond the accepted charge becomes grid export.

### 11.3 Discharge behavior

```text
deliverable_from_battery_kwh = min(
    remaining_load_deficit_kwh,
    max_discharge_kw,
    (state_of_charge_kwh - reserve_kwh) * leg_efficiency
)

stored_energy_removed_kwh = deliverable_from_battery_kwh / leg_efficiency
```

State of charge remains between reserve and usable capacity, allowing only
small floating-point tolerance at a boundary.

### 11.4 Strategy behavior

**Self-consumption** permits discharge for every load deficit while stored
energy remains above reserve.

**TOU reserve** permits discharge only during hours classified as Expensive.
At Cheap, Less Expensive, or unmatched hours, grid import serves the remaining
deficit and battery energy is preserved.

Both strategies always permit direct solar use and solar-only charging.

### 11.5 Hourly energy balance

Every hour must satisfy this AC-bus equation within `1e-9` kWh absolute
tolerance:

```text
modeled_solar
  + grid_import
  + battery_discharge_output
= household_load
  + grid_export
  + battery_charge_input
```

Battery state changes separately account for efficiency loss.

### 11.6 Simulation output

Each result row contains:

- Timestamp.
- Historical household load.
- Modeled solar production.
- Battery state of charge.
- Battery charge input.
- Battery discharge output.
- Grid import.
- Grid export.
- Whether the hour is Expensive.

## 12. Modeled Results and Charts

The modeled page shows summary values for:

- Total grid import.
- Grid import during Expensive hours.
- Total grid export.

The Plotly figure has two vertically aligned panels sharing an hourly time axis:

1. **Home and battery:** grouped bars for Used and Production, plus a Battery
   state-of-charge line on a secondary kWh axis.
2. **Grid exchange:** Grid import as positive bars and Grid export as negative
   bars around a zero line.

The legend allows each of the five series to be hidden independently.

The stable color mapping is:

- Used: blue `#2563EB`.
- Production: amber `#F59E0B`.
- Battery: violet `#7C3AED`.
- Grid import: red `#DC2626`.
- Grid export: green `#059669`.

The application uses a wide page layout. Scalar controls live in the sidebar;
the wider TOU table lives in the main content area. Streamlit's responsive
layout handles narrower windows.

## 13. Validation and Error Handling

Source data validation rejects:

- Missing required columns.
- Empty source files.
- Invalid or non-finite numeric values.
- Negative import, export, or production values.
- Invalid utility or solar timestamps.
- Duplicate utility local-hour keys.
- Duplicate solar absolute timestamps.
- Non-overlapping source ranges.
- Missing solar hours in the retained utility range.
- Negative or non-finite derived household load.

Model validation rejects:

- Dates outside the available shared range.
- Durations outside 1 through 7 days.
- Negative or non-finite solar scale, capacity, or power limits.
- Starting or reserve percentages outside 0 through 100.
- Starting state of charge below reserve.
- Round-trip efficiency outside `(0, 1]`.
- Unknown strategy values.
- TOU reserve without a seasonal price spread.
- Invalid TOU names, dates, weekdays, times, or prices.

Errors appear in the page with concise context. Invalid model inputs prevent the
model run but do not make valid historical data unavailable.

## 14. Verification Requirements

Automated tests cover:

- Source schemas, numeric validation, normalization, and household-load
  derivation.
- Daylight-saving fall-back and spring-forward behavior.
- Real supplied CSV loading.
- Auto and manual historical aggregation.
- TOU price parsing, seasonal ranking, overlap precedence, all-day rules,
  overnight rules, and year-wrapping seasons.
- Default SMUD rates.
- Self-consumption and TOU-reserve dispatch.
- Battery starting charge, reserve, capacity, efficiency, and power limits.
- Solar-only charging, grid import/export, battery bounds, and hourly energy
  balance.
- Stable chart traces, colors, axes, legend behavior, signed export, and input
  immutability.
- Streamlit startup, page navigation, session persistence, battery presets,
  custom-value restoration, TOU defaults, and absence of known deprecation
  warnings.

The complete suite runs with:

```powershell
python -m pytest -v
```

Feature changes must update or add focused tests for changed behavior.

## 15. Acceptance Criteria

The application is conformant when:

- It launches locally and reads the two fixed CSV files without modifying them.
- Historical filtering, aggregation, series selection, totals, and charts follow
  this specification.
- Any valid one-to-seven-day period can be replayed with configurable solar,
  battery, strategy, and TOU inputs.
- Custom and preset battery settings produce the specified effective battery
  configuration and persist for the session.
- TOU rules use configured prices and the specified seasonal classification.
- Battery dispatch obeys reserve, capacity, efficiency, power, strategy, and
  solar-only charging rules.
- Modeled charts and summary values use the specified signs, axes, traces, and
  colors.
- Invalid inputs produce clear local errors instead of guessed or silently
  corrected results.
- The automated test suite passes against the current implementation and the
  supplied local data.

## 16. Specification Maintenance

This file is the source of truth for externally observable application behavior.
Any feature change or behavior change must update `SPEC.md` in the same change.
Implementation, tests, README guidance, and this specification must not knowingly
contradict one another.

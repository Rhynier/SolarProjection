# Home Energy Model Specification

**Status:** Authoritative specification for the current prototype
**Last updated:** 2026-09-02

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
- Replay any selected historical date range at hourly resolution.
- Scale historical solar production from configurable reference and proposed
  production, using either one annual ratio or twelve calendar-month ratios.
- Model a configurable battery that charges from solar surplus only.
- Support self-consumption, fixed time-of-use reserve, historical-cost
  optimization, and full-backup strategies.
- Display modeled household use, production, battery state of charge, grid
  import, and grid export.
- Display projected utility energy cost for the selected data in both views.
- Keep source data and model settings local to the user's computer.

## 3. Non-goals

The prototype does not provide:

- Production deployment, authentication, authorization, accounts, or a database.
- Cloud storage, telemetry, or external service integrations.
- Detailed bill calculations, fixed charges, taxes, fees, payback analysis, or
  financial advice.
- Automatic solar or battery sizing recommendations.
- Named, saved, or shareable modeling scenarios.
- Future load, production, or weather forecasts.
- Grid charging, grid-energy arbitrage, or battery export to the grid.
- Holiday-aware TOU scheduling.
- A packaged Windows executable or installer.

Projected cost is an energy-only estimate, not a complete utility bill.

## 4. Runtime and Local Files

### 4.1 Technology

The application uses:

- Python 3.11 or later within the supported project range.
- Streamlit for the local user interface.
- pandas and NumPy for data processing.
- SciPy for continuous historical-cost dispatch optimization.
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

The default filenames are fixed. Replacing either file with a newer export of
the same schema and restarting the application reloads the data. There is no
upload UI.

The `HOME_ENERGY_MODEL_UTILITY_CSV` and `HOME_ENERGY_MODEL_SOLAR_CSV`
environment variables may each provide a complete alternate path to the
corresponding input file, mirroring the configuration-path override. When unset,
the application reads the two default files beside `app.py`. The automated tests
use these overrides to point the application at a committed deterministic sample
dataset so the suite runs without the personal exports.

The personal CSV files are local data and must remain uncommitted.

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
used by the utility export.

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
- `solar_model/aggregation.py`: inclusive date filtering and energy and cost
  aggregation.
- `solar_model/periods.py`: rolling week and month range calculation,
  navigation, and labels.
- `solar_model/configuration.py`: local configuration schema validation,
  startup loading, and atomic saves.
- `solar_model/tou.py`: TOU defaults, rule validation, price lookup, and rate
  classification.
- `solar_model/costs.py`: hourly and total projected utility cost calculation
  and currency formatting.
- `solar_model/optimization.py`: continuous historical battery-dispatch cost
  optimization.
- `solar_model/simulation.py`: deterministic hourly solar and battery replay.
- `solar_model/metrics.py`: strategy-comparison summary calculations.
- `solar_model/charts.py`: Plotly chart construction and stable styling.
- `tests/`: unit, integration, real-data, and Streamlit smoke tests.

`app.py` must delegate energy calculations to the model modules. The simulation
and data-processing modules must not depend on Streamlit.

## 8. Historical View

The Historical view is the default page.

### 8.1 Controls

The sidebar provides:

- A period selector with `Custom`, `Week`, `Month`, and `All` options.
- An aggregation selector: `Auto`, `Hour`, `Day`, `Week`, or `Month`.
- A multi-select for `Used`, `Production`, and `Grid export`.
- Utility purchase rate for exported energy, defaulting to `$0.0563/kWh`.

`Custom` is the default. Its initial inclusive range begins on the first date
in the shared dataset and ends one calendar month later minus one day. The end
is clipped to the last available date when the dataset contains less than one
month. `Custom` provides the inclusive two-date picker constrained to the shared
dataset and preserves the currently selected range when entered.

`All` selects the full shared date range. `Week` provides a Start date picker
plus Previous week and Next week buttons. Its inclusive range contains seven
days beginning on the selected Start date. Previous and Next shift the Start
date by seven days.

`Month` provides the same Start date picker plus Previous month and Next month
buttons. Its inclusive range ends one day before the corresponding date in the
next month. A Start date on the first therefore ends on the last day of that
calendar month. Previous and Next shift the Start date by one calendar month.

Week and Month display their resulting range below the Start date. A resulting
end after the last available date is clipped to the shared dataset and labeled
as clipped. Switching period types uses the current range's Start date.

The other defaults are `Auto`, all three series, and the export purchase rate
above. Custom selection requires exactly two dates, and at least one series is
required. The export rate is finite and nonnegative.

The period type, resulting inclusive date range, and aggregation value are
shared with the System model. A change made in either view is immediately
reflected in the other view.

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
- Projected cost for the selected hourly data.
- The resolved aggregation bucket.
- A grouped bar chart containing the selected series.

## 9. System Model View

The System model replays the shared inclusive historical date range at hourly
resolution.

### 9.1 Period and solar controls

The System model sidebar provides:

- The same `Custom`, `Week`, `Month`, and `All` period selector used by the
  Historical view.
- The same `Auto`, `Hour`, `Day`, `Week`, or `Month` aggregation selector used
  by the Historical view.
- Utility purchase rate for exported energy, defaulting to `$0.0960/kWh`.

The Configuration page contains a `Solar production scaling` section before
the `Time-of-use rules` section. The production-scaling section provides:

- An `Annual` or `Monthly` production-scaling mode, defaulting to `Annual`.
- Reference annual solar production in kWh, which must be greater than zero in
  Annual mode.
- Proposed-system annual solar production in kWh, which must be nonnegative in
  Annual mode.
- The calculated annual production scale:

```text
solar_scale = proposed_annual_production_kwh / reference_annual_production_kwh
```

Monthly mode provides a fixed twelve-row editor with Month, Reference
production, Proposed production, and calculated Scale columns. Month and Scale
are read-only. Reference and Proposed production are required numeric values.
Every monthly reference value must be finite and greater than zero, and every
monthly proposed value must be finite and nonnegative. Invalid cells produce a
month-specific error and prevent simulation. Each scale is calculated as:

```text
monthly_solar_scale[month] = proposed_monthly_production_kwh[month]
                           / reference_monthly_production_kwh[month]
```

The first time Monthly mode is selected, each monthly reference and proposed
value is initialized by distributing its corresponding retained Annual-mode
value as evenly as possible at the editor's four-decimal kWh precision across
the twelve months. The displayed monthly values therefore sum to the retained
annual value, including when the annual reference is the minimum `0.01 kWh`.
In Monthly mode, the annual reference and proposed controls are
read-only and display the sums of their respective monthly columns. The UI
states that calendar-month scales are active rather than presenting the annual
totals ratio as an applied scale. Annual and Monthly values remain independent:
returning to Annual mode restores the prior editable Annual-mode values, and
returning to Monthly mode restores the prior monthly values.

The System model does not repeat the editable production controls. Its sidebar
shows a read-only summary of the active annual scale or states that monthly
calendar scales are active.

The period type, resulting date range, and aggregation value remain synchronized
between views. Their defaults are `Custom`, the first available inclusive
one-month range, and `Auto`. Annual-mode reference and proposed production both
default to `2017.56 kWh`, producing a default solar scale of `1.0`. Aggregation
changes chart presentation only; the battery simulation always processes each
selected hour in chronological order.

### 9.2 Battery strategy

The strategy choices are:

- `Self-consumption`
- `Fixed TOU reserve`
- `Cost optimized (historical foresight)`
- `Full backup`

Self-consumption is the default.

Immediately below the Battery strategy selector, the sidebar provides:

- Starting state of charge from 0 through 100 percent, default 50 percent.
- Minimum reserve from 0 through 100 percent, default 10 percent.

Starting state of charge must not be below the reserve. These controls appear
before the Battery settings mode selector and remain editable in both battery
settings modes. Full backup instead displays disabled effective values of 100
percent for both controls. Selecting Full backup does not overwrite the user's
stored editable starting charge or reserve, which return when another strategy
is selected.

Fixed TOU reserve is a deterministic peak-period strategy, not a claim of exact
Enphase Savings or AI Optimization behavior. Cost optimized uses the recorded
future load and solar within the selected period and is labeled as historical
foresight rather than a production forecast. Its projected cost is an idealized
utility-energy comparison that excludes battery degradation and other bill
charges. Full backup represents normal on-grid operation only.

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

### 9.4 Advanced battery settings

The Advanced battery settings expander contains round-trip efficiency and the
maximum AC-side charge and discharge power. These values are editable in Custom
values mode and read-only nameplate values in Battery preset mode. Starting
charge and Minimum reserve are not advanced settings.

### 9.5 Session and durable configuration behavior

The shared period type, date range, rolling-period Start date, aggregation, and
chart-series visibility, plus model production-scaling mode, independent annual
and monthly production values, strategy, battery mode, battery model, battery
quantity, custom battery values, common battery values, shared TOU edits, and
the independent Historical and System-model export purchase rates must survive
navigation between all three pages during the current Streamlit session.

At startup, before widgets are initialized, the application loads its local
configuration exactly once. The default path is
`~/.home-energy-model/config.json`; `HOME_ENERGY_MODEL_CONFIG_PATH` may provide
a complete alternate file path. The versioned document uses
`schema_version: 1` and contains only `historical`, `system_model`, `battery`,
`solar_production`, and `time_of_use` settings. Date range, period type,
aggregation, chart-series visibility, and selected page remain session-only.
The Configuration page identifies the resolved path and states that valid
durable settings save automatically.

Fresh sessions load the independent Historical and System-model export purchase
rates; every battery strategy, mode, preset, quantity, common, and custom
setting; Solar production scaling mode with its independent Annual and Monthly
values; and valid TOU rules. The TOU editor's display fields map to the seven
semantic JSON keys `name`, `start_date`, `end_date`, `weekdays`, `start_time`,
`end_time`, and `price_per_kwh`; blank TOU rows are excluded.

Schema-version-1 files saved by an earlier release with the battery strategy
label `TOU reserve` remain valid and load as `Fixed TOU reserve`. The normalized
label is used for later saves.

Each valid edit saves only its top-level section automatically. Writes validate
the complete document and atomically replace the destination file. A new
installation continues to use the listed defaults and does not create a
configuration file until the user changes a durable setting.

## 10. Time-of-Use Rules

The Configuration page contains the shared Time-of-use rules editor immediately
after the Solar production scaling section. Historical cost calculation and
System-model simulation and cost calculation use the same configured rules.

### 10.1 Editor schema

The editable table appears in the Configuration page's main content area and
contains:

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

## 11. Projected Utility Cost

Both views calculate an energy-only Projected cost over the hourly data in the
current view:

```text
projected_cost =
    sum(grid_import_kwh * applicable_import_price_per_kwh)
    - sum(grid_export_kwh * export_purchase_rate_per_kwh)
```

Historical View uses the filtered normalized hourly data and the configured TOU
rules for import prices. System model uses its simulated hourly grid import and
export and the same configured TOU rules.

Each view has its own persisted export purchase rate. Historical defaults to
`$0.0563/kWh`; System model defaults to `$0.0960/kWh`. These settings are finite
and nonnegative.

An hour with imported energy must have a matching import price. An unmatched
hour with no imported energy contributes only any export credit. If export
credit exceeds import charges, Projected cost is negative and displays as a net
credit such as `-$1.25`.

The projection excludes the source CSV's `COST` value, fixed charges, minimum
charges, taxes, fees, and other utility bill adjustments.

## 12. Hourly Simulation

For each selected historical hour, the simulation:

1. Multiplies actual solar production by either the Annual-mode scale or, in
   Monthly mode, the scale for the hour's calendar month.
2. Applies modeled solar directly to household load.
3. Sends solar surplus to the battery, subject to capacity, charge-power, and
   efficiency limits.
4. Exports remaining solar surplus to the grid.
5. Handles remaining load deficit according to the selected strategy.
6. Imports any deficit that solar and permitted battery discharge cannot serve.

The battery never charges from grid import.

### 12.1 Efficiency

Round-trip efficiency must be greater than zero and no greater than one when
represented as a fraction. The simulation uses symmetric per-leg efficiency:

```text
leg_efficiency = sqrt(round_trip_efficiency)
```

### 12.2 Charge behavior

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

### 12.3 Discharge behavior

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

### 12.4 Strategy behavior

**Self-consumption** permits discharge for every load deficit while stored
energy remains above reserve.

**Fixed TOU reserve** permits discharge only during hours classified as Expensive.
At Cheap, Less Expensive, or unmatched hours, grid import serves the remaining
deficit and battery energy is preserved.

**Cost optimized (historical foresight)** minimizes projected utility energy
cost across the complete selected period using its recorded hourly load,
recorded and scaled solar production, configured hourly import prices, and the
System-model export purchase rate. The continuous optimizer may forgo charging
when the lost export credit is worth more than a later efficiency-adjusted
import reduction. It may preserve limited stored energy for a later,
higher-priced load deficit. It has no terminal state-of-charge target, so the
selected period's starting charge is available to use and the optimizer may end
at reserve. It does not include a battery degradation or cycling cost.

**Full backup** uses an effective starting state of charge and reserve equal to
100 percent of usable capacity. It does not discharge while the grid is
available. Because this prototype does not model grid charging or outages, a
Full-backup replay begins full and the battery remains full.

All four strategies permit direct solar use. Charging is always limited to
solar surplus, and discharge is always limited to remaining household load;
none of the strategies charges from or discharges directly to the grid.

### 12.5 Hourly energy balance

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

### 12.6 Simulation output

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

## 13. Modeled Results and Charts

The modeled page shows summary values for:

- Total grid import.
- Grid import during Expensive hours.
- Total grid export.
- Projected cost for the modeled hourly grid exchange.
- Solar self-consumed as modeled solar minus grid export, divided by modeled
  solar and displayed as a percentage. It is zero when modeled solar is zero.
- Total AC-side battery discharge output.
- Equivalent full cycles, calculated as AC-side discharge divided by the
  discharge leg efficiency and then by usable capacity above reserve. It is
  zero when capacity above reserve is zero.
- Ending battery charge as final state of charge divided by usable capacity. It
  is zero when usable capacity is zero.

All summary values use the hourly result rather than chart aggregation.

The Plotly figure has three vertically aligned panels sharing the selected bucket
time axis:

1. **Home and battery:** grouped bars for Used and Production, plus a Battery
   state-of-charge line on a secondary kWh axis.
2. **Grid exchange:** Grid import as positive bars and Grid export as negative
   bars around a zero line.
3. **Net cost:** one signed bar per bucket around a zero line. Positive values
   are net charges and negative values are net export credits.

Used, Production, Grid import, Grid export, and hourly Net cost are summed within
each resolved bucket. The Battery line uses the final hourly state of charge in
each bucket. The Net cost bars sum to the Projected cost summary. `Auto` uses the
same date-range thresholds specified for the Historical view.

The legend allows each of the six series to be hidden independently.

The stable color mapping is:

- Used: blue `#2563EB`.
- Production: amber `#F59E0B`.
- Battery: violet `#7C3AED`.
- Grid import: red `#DC2626`.
- Grid export: green `#059669`.
- Net cost: teal `#0F766E`.

The application uses a wide page layout. Analytical-view scalar controls live
in the sidebar. Production scaling controls and the wider TOU table live in the
Configuration page's main content area. Streamlit's responsive layout handles
narrower windows.

## 14. Validation and Error Handling

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
- Nonpositive or non-finite reference annual production.
- Negative or non-finite proposed annual production, solar scale, capacity, or
  power limits.
- Monthly scale profiles that do not contain exactly twelve finite,
  nonnegative values.
- Starting or reserve percentages outside 0 through 100.
- Starting state of charge below reserve.
- Round-trip efficiency outside `(0, 1]`.
- Unknown strategy values.
- TOU reserve without a seasonal price spread.
- Invalid TOU names, dates, weekdays, times, or prices.
- Negative or non-finite export purchase rates.
- Imported energy without a matching utility price when calculating Projected
  cost.

Configuration validation rejects missing or unknown fields, unsupported schema
versions, invalid section values, and invalid TOU semantic rows. A missing file
uses defaults and permits later automatic saves. A malformed, unsupported, or
unknown-field configuration file shows its path in a warning, uses defaults for
that session, disables automatic saves, and is never overwritten.

An invalid nonblank Solar or TOU editor value remains visible in the current
session, shows concise row-specific context, and neither replaces the last
valid saved section nor prevents a valid edit in another section from saving.
If a write fails, the current in-session value remains usable and a save error
with the configuration path remains visible until a later successful save clears
it. Errors appear in the page with concise context. Invalid model inputs prevent
the model run but do not make valid historical data unavailable.

## 15. Verification Requirements

Automated tests cover:

- Source schemas, numeric validation, normalization, and household-load
  derivation.
- Daylight-saving fall-back and spring-forward behavior.
- Deterministic sample-dataset loading via the CSV path overrides. Real supplied
  CSV loading is verified only when the personal files are present and is skipped
  otherwise.
- Auto and manual historical and modeled-chart aggregation.
- TOU price parsing, seasonal ranking, overlap precedence, all-day rules,
  overnight rules, and year-wrapping seasons.
- Default SMUD rates.
- Projected-cost arithmetic, export credit, missing import prices, invalid
  export rates, and net-credit formatting.
- Self-consumption, fixed-TOU-reserve, historical-cost-optimized, and
  full-backup dispatch.
- Historical optimization across multiple hourly prices, export opportunity
  cost, efficiency, missing prices, reserve, capacity, and power limits.
- Strategy summary arithmetic, including zero-solar and zero-usable-capacity
  cases.
- Battery starting charge, reserve, capacity, efficiency, and power limits.
- Solar-only charging, grid import/export, battery bounds, and hourly energy
  balance.
- Stable chart traces, colors, axes, legend behavior, signed export, and input
  immutability.
- Streamlit startup, page navigation, session persistence, battery presets,
  custom-value restoration, TOU defaults, and absence of known deprecation
  warnings.
- Synchronized date-range and aggregation controls across both views.
- All-data, rolling seven-day, rolling one-month, and custom period selection,
  including previous/next navigation and clipped boundary periods.
- Per-view export purchase defaults, persistence, and Projected cost response.
- Local configuration path selection, schema validation, startup loading,
  round-trip persistence, semantic TOU mapping, and atomic replacement.
- Invalid configuration-file isolation, per-section persistence isolation,
  visible save failures, invalid editor retention, and transient-view-state
  exclusion.

The complete suite runs with:

```powershell
python -m pytest -v
```

Feature changes must update or add focused tests for changed behavior.

## 16. Acceptance Criteria

The application is conformant when:

- It launches locally and reads the two fixed CSV files without modifying them.
- Historical filtering, aggregation, series selection, totals, and charts follow
  this specification.
- Both views calculate Projected cost over their selected hourly data using the
  specified import prices and independent export purchase rates.
- Any valid date range within the shared data can be replayed with configurable
  solar, battery, strategy, and TOU inputs.
- Custom and preset battery settings produce the specified effective battery
  configuration and persist for the session.
- TOU rules use configured prices and the specified seasonal classification.
- The modeled Net cost chart has one signed bar per resolved bucket and sums to
  the Projected cost summary.
- Battery dispatch obeys reserve, capacity, efficiency, power, strategy, and
  solar-only charging rules.
- Historical-cost optimization uses configured import and export prices without
  grid charging, battery export, or claims of matching Enphase's proprietary
  forecast behavior.
- Modeled charts and summary values use the specified signs, axes, traces, and
  colors.
- Invalid inputs produce clear local errors instead of guessed or silently
  corrected results.
- The automated test suite passes against the current implementation and the
  supplied local data.

## 17. Specification Maintenance

This file is the source of truth for externally observable application behavior.
Any feature change or behavior change must update `SPEC.md` in the same change.
Implementation, tests, README guidance, and this specification must not knowingly
contradict one another.

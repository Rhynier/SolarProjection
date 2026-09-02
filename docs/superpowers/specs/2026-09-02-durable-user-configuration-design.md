# Durable User Configuration Design

**Status:** Awaiting written-spec review
**Date:** 2026-09-02

## Purpose

Persist the user's modeling configuration across Streamlit process restarts
without turning the personal prototype into an account-based or database-backed
application. Configuration remains local to the operating-system user and is
saved automatically when a durable setting changes.

## Goals

- Persist the independent Historical and System-model utility purchase rates.
- Persist battery strategy, common battery values, custom battery values, and
  the selected preset mode, model, and quantity.
- Persist every setting currently edited on the Configuration page: annual or
  monthly solar-production scaling and time-of-use rules.
- Preserve invalid in-progress editor values in the current Streamlit session
  without replacing the last valid values on disk.
- Keep persistence independent of Streamlit widget keys and pandas types.
- Make configuration loading and saving deterministic and directly testable.

## Non-goals

- Persisting the selected page, date range, rolling-period start, aggregation,
  visible chart series, expanded controls, or other presentation state.
- Named configurations, multiple profiles, import/export UI, cloud sync,
  accounts, secrets, encryption, or concurrent multi-process editing.
- Watching the file for changes while the application is running.
- Preserving unknown fields from a different or future schema version.

## File Location

The default configuration path is:

```text
~/.home-energy-model/config.json
```

`~` is resolved with `Path.home()`, so the file is stored below the current
user's profile directory on Windows and remains conventional on other platforms.
The application creates the hidden directory only when it first has a durable
change to save.

The optional `HOME_ENERGY_MODEL_CONFIG_PATH` environment variable overrides the
complete file path. It exists for test and development isolation and is
documented in the README. Tests must always set this override and must never read
or modify the real user-profile configuration.

The Configuration page displays a small caption stating that settings save
automatically and showing the resolved configuration path.

## Document Schema

The file is formatted UTF-8 JSON with a top-level integer `schema_version`.
Version 1 has these exact sections and fields:

```json
{
  "schema_version": 1,
  "historical": {
    "export_purchase_rate_per_kwh": 0.0563
  },
  "system_model": {
    "export_purchase_rate_per_kwh": 0.096
  },
  "battery": {
    "strategy": "Self-consumption",
    "settings_mode": "Custom values",
    "starting_charge_percent": 50.0,
    "minimum_reserve_percent": 10.0,
    "preset": {
      "model": "Tesla Powerwall 3",
      "quantity": 1
    },
    "custom": {
      "usable_capacity_kwh": 13.5,
      "round_trip_efficiency_percent": 90.0,
      "maximum_charge_power_kw": 5.0,
      "maximum_discharge_power_kw": 5.0
    }
  },
  "solar_production": {
    "scaling_mode": "Annual",
    "annual": {
      "reference_kwh": 2017.56,
      "proposed_kwh": 2017.56
    },
    "monthly": [
      {
        "month": "January",
        "reference_kwh": 168.13,
        "proposed_kwh": 168.13
      }
    ]
  },
  "time_of_use": {
    "rules": [
      {
        "name": "Summer off-peak",
        "start_date": "06-01",
        "end_date": "09-30",
        "weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "start_time": "00:00",
        "end_time": "23:59",
        "price_per_kwh": 0.1425
      }
    ]
  }
}
```

The example abbreviates the `monthly` and `rules` arrays. A complete default
document contains the existing twelve monthly rows and all current SMUD default
TOU rows. JSON field names are semantic and do not expose Streamlit's current
`model.*`, `shared.*`, or widget-key conventions.

Preset-derived usable capacity, efficiency, charge power, and discharge power
are not duplicated in the document. They remain deterministic outputs of the
selected preset and quantity. The independently retained custom values are all
stored even while preset mode is active.

## Components and Responsibilities

### `solar_model/configuration.py`

This new module has no Streamlit or pandas dependency. It owns:

- The version-1 default document.
- Default and overridden path resolution.
- Exact structural and domain validation for persisted documents.
- Conversion between the typed configuration representation and plain JSON
  values.
- Loading and atomic saving.
- A concise configuration-specific exception type suitable for UI messages.

### `app.py`

The UI remains responsible for mapping between the configuration model and the
existing session-state values. It:

- Loads configuration once before rendering page controls.
- Seeds only durable session-state keys from the loaded configuration.
- Converts monthly production and TOU rule arrays to and from DataFrames at the
  UI boundary.
- Saves the affected valid section after a durable control changes.
- Renders load and save messages without preventing access to valid historical
  data.

The energy, cost, TOU, and simulation modules remain unchanged unless a small
reuse of their existing validators is necessary to enforce the same domain
rules at the persistence boundary.

## Startup Flow

1. Resolve the configuration path.
2. If no file exists, use the complete version-1 defaults without creating a
   file.
3. If the file exists, decode JSON and validate the complete document before
   applying any value.
4. Seed the durable session-state keys once. Subsequent Streamlit reruns retain
   current session state and do not reread the file.
5. Render the requested page using the same session-state-backed control flow as
   today.

An existing valid file is the initial last-known-valid configuration. When no
file exists, the in-memory defaults are the initial last-known-valid
configuration.

## Automatic Save Flow

Simple widget callbacks first copy the widget value to the existing durable
session-state key and then request persistence. Data editors request persistence
after their returned data has been normalized at the UI boundary.

Persistence validates the affected logical section. When valid, it replaces
that section in the last-known-valid configuration and saves the complete
document. Comparing the normalized document with the last saved document avoids
rewriting the file when no durable value changed.

When an edited section is invalid, its in-progress session values remain visible
and the existing page validation explains the problem. That section does not
replace its last-known-valid on-disk value. A valid edit in another section may
still update and save that other section.

The logical save sections are:

- Historical export rate.
- System-model export rate.
- Battery configuration.
- Solar-production configuration.
- Time-of-use rules.

## Atomic Writes

Saving creates the parent directory if necessary, writes formatted UTF-8 JSON
to a temporary file in the same directory, flushes and closes it, then replaces
`config.json` with `os.replace`. A temporary file left by a failed write is
cleaned up when possible. The previous configuration remains intact if writing
or replacement fails before completion.

No file lock or multi-process merge is required for this local, single-user
prototype. The last successful application write wins if multiple processes are
run concurrently.

## Validation and Failure Behavior

Persisted version-1 documents require every documented field, reject additional
fields at every schema level, and reject unsupported schema versions. Values use
the same domain contracts already enforced by the UI and model, including:

- Finite, nonnegative export rates.
- Known strategy, settings-mode, and preset-model names.
- Integer preset quantity of at least one.
- Battery percentages and custom values within their existing bounds, including
  starting charge not below minimum reserve.
- Known production-scaling mode, valid annual values, and exactly twelve ordered
  valid monthly values.
- Structurally and semantically valid TOU rows.

Failure behavior is:

- A missing file is normal and produces no warning.
- Invalid JSON, invalid structure or values, unknown fields, or an unsupported
  version produces a concise warning containing the path. The app uses defaults
  for that session, leaves the invalid file untouched, and disables automatic
  saves for the session so it cannot overwrite unrecognized content. The warning
  tells the user to correct or move the file and restart.
- An invalid in-progress UI edit retains the edit in session state, displays the
  existing domain error, and leaves the last valid persisted section unchanged.
- A save failure retains current session values, keeps the prior file whenever
  atomic replacement did not complete, and displays an actionable error. A later
  edit may retry saving.

Configuration errors never modify the two source CSV files and never prevent
the application from presenting otherwise valid historical data.

## Documentation Changes

`SPEC.md` will replace the current session-only persistence statement with the
durable scope, excluded transient state, path, automatic-save behavior, schema
versioning, and failure rules. `README.md` will document the default path,
automatic saving, and the optional path override. Implementation, tests, README,
and SPEC must describe the same behavior.

## Verification

Focused unit tests in `tests/test_configuration.py` cover:

- Default and overridden path resolution.
- Complete defaults and JSON round-trip behavior.
- Missing-file behavior.
- Invalid JSON, missing or unknown fields, invalid domain values, and unsupported
  versions.
- No write when normalized configuration has not changed.
- Parent-directory creation and successful atomic replacement.
- Failed writes or replacements preserving the prior file.

Streamlit AppTest coverage in `tests/test_app.py` uses a temporary override path
for every test and covers:

- Persistence across separate, fresh AppTest sessions for both export rates.
- Persistence of battery strategy, common battery values, retained custom
  values, mode, preset model, and quantity.
- Persistence of annual and monthly solar-production settings.
- Persistence of edited TOU rules.
- Invalid editor values retaining the prior valid file.
- Visible load and save errors.
- Transient navigation, date, aggregation, and series state not being stored.

Development runs the relevant focused tests first. Before completion, the full
suite runs with:

```powershell
python -m pytest -v
```

`git diff --check` must also pass, and the two local CSV inputs must remain
unmodified and untracked.

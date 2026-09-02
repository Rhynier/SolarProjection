# Durable User Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the approved subset of Home Energy Model settings in a validated, versioned JSON file under the current user's profile and save valid edits automatically.

**Architecture:** Add a Streamlit-independent configuration module that owns the version-1 document, path resolution, validation, loading, and atomic saving. `app.py` adapts that document to existing session-state keys, retains a last-known-valid copy, and saves one logical section after each valid edit while leaving transient view state and invalid in-progress edits in memory only.

**Tech Stack:** Python 3.11, standard-library `dataclasses`, `json`, `math`, `os`, `pathlib`, and `tempfile`; existing pandas, Streamlit, pytest, and Streamlit AppTest.

**Spec:** `docs/superpowers/specs/2026-09-02-durable-user-configuration-design.md`

## Global Constraints

- Default path: `~/.home-energy-model/config.json`, resolved with `Path.home()`.
- `HOME_ENERGY_MODEL_CONFIG_PATH` overrides the complete path for tests and development.
- JSON schema version is integer `1`; every documented field is required and unknown fields are rejected at every object level.
- Only both export rates, all battery and strategy settings, solar-production configuration, and TOU rules are durable.
- Page, date, rolling-period, aggregation, visible-series, and presentation state remain session-only.
- Preset-derived battery values are recomputed; retained custom battery values are always stored.
- Missing configuration is normal and is not written until the first durable edit.
- An invalid file loads defaults, remains untouched, and disables automatic saving for that Streamlit session.
- Invalid editor data stays in session and does not replace its section's last valid value; valid changes in other sections can still save.
- Writes use a same-directory temporary file followed by `os.replace`.
- Add no dependency, production infrastructure, account, cloud persistence, encryption, or multi-process locking.
- Keep `app.py` as UI/session glue and `solar_model/configuration.py` free of Streamlit and pandas.
- Keep `SPEC.md`, `README.md`, implementation, and tests consistent.
- Preserve both local CSV inputs and unrelated user changes or untracked files.

## File Structure

- Create `solar_model/configuration.py`: defaults, exact validation, path resolution, load results, and atomic saving.
- Create `tests/test_configuration.py`: storage-boundary unit tests.
- Modify `app.py`: initialization, adapters, section persistence, status rendering, and callbacks.
- Modify `tests/test_app.py`: per-test path isolation and fresh-session persistence/error tests.
- Modify `SPEC.md`: authoritative durable-state behavior.
- Modify `README.md`: user-facing location, autosave, durable scope, and override.

---

### Task 1: Versioned Configuration Storage Boundary

**Files:**
- Create: `solar_model/configuration.py`
- Create: `tests/test_configuration.py`

**Interfaces:**
- Consumes: `solar_model.tou.SMUD_DEFAULT_TOU_ROWS`, `TouValidationError`, and `parse_tou_rules`.
- Produces: `CONFIG_VERSION`, `ConfigurationError`, `ConfigurationValidationError`, `LoadResult`, `configuration_path`, `default_configuration`, `validate_configuration`, `load_configuration`, and `save_configuration`.

- [ ] **Step 1: Write failing path and default-document tests**

Create `tests/test_configuration.py`:

```python
from copy import deepcopy
import json
from pathlib import Path

import pytest

from solar_model.configuration import (
    CONFIG_VERSION,
    ConfigurationError,
    ConfigurationValidationError,
    configuration_path,
    default_configuration,
    load_configuration,
    save_configuration,
    validate_configuration,
)


def test_configuration_path_defaults_below_user_profile():
    assert configuration_path(environ={}, home=Path("C:/Users/Test User")) == Path(
        "C:/Users/Test User/.home-energy-model/config.json"
    )


def test_configuration_path_uses_complete_environment_override():
    assert configuration_path(
        environ={"HOME_ENERGY_MODEL_CONFIG_PATH": "D:/scratch/solar.json"},
        home=Path("C:/ignored"),
    ) == Path("D:/scratch/solar.json")


def test_default_configuration_returns_independent_complete_documents():
    first = default_configuration()
    second = default_configuration()
    assert first == second
    assert first is not second
    assert first["schema_version"] == CONFIG_VERSION == 1
    assert len(first["solar_production"]["monthly"]) == 12
    assert len(first["time_of_use"]["rules"]) == 9
    first["battery"]["custom"]["usable_capacity_kwh"] = 99.0
    assert second["battery"]["custom"]["usable_capacity_kwh"] == 13.5
```

- [ ] **Step 2: Run the tests and verify the import fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_configuration.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'solar_model.configuration'`.

- [ ] **Step 3: Implement public types, defaults, and path resolution**

Create `solar_model/configuration.py` with these public definitions:

```python
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
from math import isfinite
import os
from pathlib import Path
import tempfile
from typing import Any

from solar_model.tou import SMUD_DEFAULT_TOU_ROWS, TouValidationError, parse_tou_rules

CONFIG_VERSION = 1
CONFIG_PATH_ENV = "HOME_ENERGY_MODEL_CONFIG_PATH"

class ConfigurationError(RuntimeError):
    pass

class ConfigurationValidationError(ConfigurationError):
    pass

@dataclass(frozen=True)
class LoadResult:
    document: dict[str, Any]
    autosave_enabled: bool
    warning: str | None = None

def configuration_path(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if environ is None else environ
    override = values.get(CONFIG_PATH_ENV)
    if override:
        return Path(override).expanduser()
    profile = Path.home() if home is None else home
    return profile / ".home-energy-model" / "config.json"
```

Build `_DEFAULT_CONFIGURATION` from every exact field in the approved spec. Convert each current SMUD row to semantic keys (`name`, `start_date`, `end_date`, `weekdays`, `start_time`, `end_time`, `price_per_kwh`). Build January-through-December rows by distributing each `2017.56` annual default at four-decimal precision; every default month is `168.13`. `default_configuration()` returns `deepcopy(_DEFAULT_CONFIGURATION)`.

- [ ] **Step 4: Write failing exact-validation tests**

Add:

```python
def test_validate_configuration_returns_a_normalized_copy():
    source = default_configuration()
    normalized = validate_configuration(source)
    assert normalized == source
    assert normalized is not source

@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda value: value.update({"extra": True}), "unknown field 'extra'"),
        (lambda value: value.pop("battery"), "battery is required"),
        (lambda value: value["historical"].update(
            {"export_purchase_rate_per_kwh": -0.01}
        ), "historical.export_purchase_rate_per_kwh"),
        (lambda value: value["battery"].update(
            {"strategy": "unknown strategy"}
        ), "battery.strategy"),
        (lambda value: value["battery"].update(
            {"starting_charge_percent": 5.0, "minimum_reserve_percent": 10.0}
        ), "starting charge must not be below minimum reserve"),
        (lambda value: value["battery"]["preset"].update(
            {"quantity": 1.5}
        ), "battery.preset.quantity"),
        (lambda value: value["solar_production"].update(
            {"monthly": []}
        ), "solar_production.monthly must contain exactly 12 rows"),
        (lambda value: value["time_of_use"]["rules"][0].update(
            {"start_date": "bad"}
        ), "time_of_use.rules Row 1"),
    ],
)
def test_validate_configuration_rejects_invalid_documents(mutate, message):
    document = default_configuration()
    mutate(document)
    with pytest.raises(ConfigurationValidationError, match=message):
        validate_configuration(document)
```

Add explicit cases for unsupported `schema_version`, unknown nested fields, booleans used as numbers, non-finite numbers, unknown settings modes and preset models, percentage bounds, custom battery bounds, annual production rules, and out-of-order month names.

Use a second parametrized table so each case has a precise mutation and message:

```python
@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda value: value.update({"schema_version": 2}), "unsupported schema_version 2"),
        (lambda value: value["battery"]["custom"].update({"extra": 1}), "unknown field 'extra'"),
        (lambda value: value["historical"].update({"export_purchase_rate_per_kwh": True}), "must be a finite number"),
        (lambda value: value["system_model"].update({"export_purchase_rate_per_kwh": float("nan")}), "must be a finite number"),
        (lambda value: value["battery"].update({"settings_mode": "Other"}), "battery.settings_mode"),
        (lambda value: value["battery"]["preset"].update({"model": "Other"}), "battery.preset.model"),
        (lambda value: value["battery"].update({"starting_charge_percent": 101}), "battery.starting_charge_percent"),
        (lambda value: value["battery"]["custom"].update({"round_trip_efficiency_percent": 0}), "round_trip_efficiency_percent"),
        (lambda value: value["solar_production"]["annual"].update({"reference_kwh": 0}), "annual.reference_kwh"),
        (lambda value: value["solar_production"]["annual"].update({"proposed_kwh": -1}), "annual.proposed_kwh"),
        (lambda value: value["solar_production"]["monthly"][0].update({"month": "February"}), "month must be 'January'"),
    ],
)
def test_validate_configuration_rejects_additional_invalid_values(mutate, message):
    document = default_configuration()
    mutate(document)
    with pytest.raises(ConfigurationValidationError, match=message):
        validate_configuration(document)
```

- [ ] **Step 5: Run validation tests and verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_configuration.py -v`

Expected: path/default cases pass; validation cases fail because exact validation is absent.

- [ ] **Step 6: Implement exact structural and domain validation**

Implement these private helpers, then use them to reconstruct the exact public document:

```python
def _require_object(value: object, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationValidationError(f"{path} must be an object")
    missing = sorted(fields - value.keys())
    if missing:
        raise ConfigurationValidationError(f"{path}.{missing[0]} is required")
    unknown = sorted(value.keys() - fields)
    if unknown:
        raise ConfigurationValidationError(
            f"{path} contains unknown field {unknown[0]!r}"
        )
    return value

def _require_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ConfigurationValidationError(f"{path} must be an array")
    return value

def _require_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationValidationError(f"{path} must be nonblank text")
    return value.strip()

def _require_number(
    value: object, path: str, minimum: float | None = None
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationValidationError(f"{path} must be a finite number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ConfigurationValidationError(f"{path} must be a finite number")
    if minimum is not None and normalized < minimum:
        raise ConfigurationValidationError(f"{path} must be at least {minimum}")
    return normalized

def _require_integer(
    value: object, path: str, minimum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationValidationError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigurationValidationError(f"{path} must be at least {minimum}")
    return value
```

`_require_object` reports missing fields before unknown fields and rejects a key set different from the expected set. Numeric helpers reject `bool`, reject non-finite values, and enforce inclusive minima. Reconstruct a new normalized document rather than mutating the input. Enforce known enums, percentages from 0 through 100, positive efficiency, starting charge at least reserve, exactly twelve ordered months with positive reference and nonnegative proposed values, and all custom battery bounds. Map semantic TOU keys back to display keys and wrap `TouValidationError` with a `time_of_use.rules` prefix.

- [ ] **Step 7: Write failing load/save and atomicity tests**

Add:

```python
def test_load_missing_file_returns_defaults_without_creating_file(tmp_path):
    path = tmp_path / "nested" / "config.json"
    result = load_configuration(path)
    assert result.document == default_configuration()
    assert result.autosave_enabled
    assert result.warning is None
    assert not path.exists()

def test_load_invalid_file_uses_defaults_and_disables_autosave(tmp_path):
    path = tmp_path / "config.json"
    original = "{not json"
    path.write_text(original, encoding="utf-8")
    result = load_configuration(path)
    assert result.document == default_configuration()
    assert not result.autosave_enabled
    assert str(path) in result.warning
    assert path.read_text(encoding="utf-8") == original

def test_save_and_load_round_trip_complete_document(tmp_path):
    path = tmp_path / "nested" / "config.json"
    document = default_configuration()
    document["battery"]["preset"]["model"] = "Enphase IQ Battery 10C"
    saved = save_configuration(path, document)
    assert saved == validate_configuration(document)
    assert load_configuration(path).document == saved
    assert json.loads(path.read_text(encoding="utf-8")) == saved

def test_save_does_not_replace_semantically_unchanged_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    document = default_configuration()
    save_configuration(path, document)
    monkeypatch.setattr(
        "solar_model.configuration.os.replace",
        lambda *_: pytest.fail("replace called"),
    )
    assert save_configuration(path, deepcopy(document)) == document

def test_failed_replace_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    original = default_configuration()
    save_configuration(path, original)
    updated = deepcopy(original)
    updated["historical"]["export_purchase_rate_per_kwh"] = 0.07
    monkeypatch.setattr(
        "solar_model.configuration.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("replacement denied")),
    )
    with pytest.raises(ConfigurationError, match="replacement denied"):
        save_configuration(path, updated)
    assert json.loads(path.read_text(encoding="utf-8")) == original
```

Add parametrized load cases for valid JSON with unsupported version, unknown or missing fields, and invalid domain values. Each returns defaults, disables autosave, includes the path in the warning, and preserves original bytes.

- [ ] **Step 8: Implement loading and atomic saving**

`load_configuration(path)` returns defaults with autosave enabled for a missing path. For an existing path, read UTF-8, decode JSON, and validate. Catch `OSError`, `json.JSONDecodeError`, and `ConfigurationValidationError`; return defaults with autosave disabled and this warning shape: `Configuration at {path} could not be loaded: {error}. Correct or move the file, then restart the app.`

`save_configuration(path, document)` validates first, compares with a currently valid file and returns without writing when semantically equal, creates the parent directory, writes `json.dump(normalized, indent=2)` plus one newline to `NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)`, flushes and closes, then calls `os.replace`. On `OSError`, remove only the exact temporary path with `unlink(missing_ok=True)` and raise `ConfigurationError(f"Configuration could not be saved to {path}: {error}")`.

- [ ] **Step 9: Run and commit the storage boundary**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_configuration.py -v`

Expected: all storage tests pass.

```powershell
git add -- solar_model/configuration.py tests/test_configuration.py
git diff --cached --check
git commit -m "feat: add durable configuration storage"
```

---

### Task 2: Initialize Streamlit State and Persist Rates and Battery Settings

**Files:**
- Modify: `app.py:1-75, 323-380, 500-735, 900-end`
- Modify: `tests/test_app.py:1-95, 500-635, 760-786`

**Interfaces:**
- Consumes: Task 1's complete public API.
- Produces: `_initialize_configuration()`, `_apply_configuration(document)`, `_configuration_section_from_state(section)`, and `_persist_configuration_section(section)`; later tasks reuse the adapter for solar and TOU.

- [ ] **Step 1: Isolate every AppTest from the real profile**

Add near the top of `tests/test_app.py`:

```python
@pytest.fixture(autouse=True)
def isolate_user_configuration(monkeypatch, tmp_path):
    path = tmp_path / ".home-energy-model" / "config.json"
    monkeypatch.setenv("HOME_ENERGY_MODEL_CONFIG_PATH", str(path))
    return path

def _new_app() -> AppTest:
    return AppTest.from_file(
        Path(__file__).parents[1] / "app.py", default_timeout=30
    ).run()
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_app.py -v`

Expected: existing tests pass, and startup alone creates no configuration file.

- [ ] **Step 2: Write failing fresh-session rate and battery tests**

Add these tests:

```python
def test_export_rates_persist_across_fresh_sessions(isolate_user_configuration):
    first = _new_app()
    _number_input(
        first, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.07).run()
    first.radio[0].set_value("System model").run()
    _number_input(
        first, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.11).run()
    assert isolate_user_configuration.exists()

    second = _new_app()
    assert _number_input(
        second, "Utility purchase rate for exported energy ($/kWh)"
    ).value == pytest.approx(0.07)
    second.radio[0].set_value("System model").run()
    assert _number_input(
        second, "Utility purchase rate for exported energy ($/kWh)"
    ).value == pytest.approx(0.11)

def test_all_battery_settings_persist_across_fresh_sessions():
    first = _new_app()
    first.radio[0].set_value("System model").run()
    _selectbox(first, "Battery strategy").set_value("TOU reserve").run()
    _number_input(first, "Starting charge (%)").set_value(80.0).run()
    _number_input(first, "Minimum reserve (%)").set_value(25.0).run()
    _number_input(first, "Battery usable capacity (kWh)").set_value(18.0).run()
    _number_input(first, "Round-trip efficiency (%)").set_value(86.0).run()
    _number_input(first, "Maximum charge power (kW)").set_value(4.5).run()
    _number_input(first, "Maximum discharge power (kW)").set_value(8.5).run()
    _radio(first, "Battery settings").set_value("Battery preset").run()
    _selectbox(first, "Battery model").set_value("Enphase IQ Battery 10C").run()
    _number_input(first, "Number of batteries").set_value(2).run()

    second = _new_app()
    second.radio[0].set_value("System model").run()
    assert _selectbox(second, "Battery strategy").value == "TOU reserve"
    assert _number_input(second, "Starting charge (%)").value == 80.0
    assert _number_input(second, "Minimum reserve (%)").value == 25.0
    assert _radio(second, "Battery settings").value == "Battery preset"
    assert _selectbox(second, "Battery model").value == "Enphase IQ Battery 10C"
    assert _number_input(second, "Number of batteries").value == 2
    _radio(second, "Battery settings").set_value("Custom values").run()
    assert _number_input(second, "Battery usable capacity (kWh)").value == 18.0
    assert _number_input(second, "Round-trip efficiency (%)").value == 86.0
    assert _number_input(second, "Maximum charge power (kW)").value == 4.5
    assert _number_input(second, "Maximum discharge power (kW)").value == 8.5
```

- [ ] **Step 3: Run new cases and verify fresh sessions reset**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_app.py -k "export_rates_persist_across_fresh_sessions or all_battery_settings_persist_across_fresh_sessions" -v`

Expected: both fail because no file is saved and the second app receives defaults.

- [ ] **Step 4: Implement one-time initialization and state mapping**

Import Task 1's API. Define:

```python
CONFIG_DOCUMENT_KEY = "_configuration.document"
CONFIG_PATH_KEY = "_configuration.path"
CONFIG_AUTOSAVE_KEY = "_configuration.autosave_enabled"
CONFIG_WARNING_KEY = "_configuration.warning"
CONFIG_ERROR_KEY = "_configuration.error"
```

`_apply_configuration` seeds all durable state keys: both rates; every battery field; production mode, annual values, and a monthly DataFrame; and a TOU DataFrame. Use the current display columns. `_initialize_configuration` resolves the path, loads once when `CONFIG_DOCUMENT_KEY` is absent, stores a deep-copied last-known-valid document and status values, and applies it. Call it immediately after `st.set_page_config` and before title, data loading, or widgets. Render load warning and current save error near the title on every page.

- [ ] **Step 5: Implement section construction and safe persistence**

Implement all five branches of `_configuration_section_from_state(section)` using only durable state. Implement:

```python
def _persist_configuration_section(section: str) -> bool:
    if not st.session_state[CONFIG_AUTOSAVE_KEY]:
        return False
    candidate = deepcopy(st.session_state[CONFIG_DOCUMENT_KEY])
    candidate[section] = _configuration_section_from_state(section)
    try:
        normalized = validate_configuration(candidate)
        saved = save_configuration(st.session_state[CONFIG_PATH_KEY], normalized)
    except ConfigurationValidationError:
        return False
    except ConfigurationError as error:
        st.session_state[CONFIG_ERROR_KEY] = str(error)
        return False
    st.session_state[CONFIG_DOCUMENT_KEY] = saved
    st.session_state[CONFIG_ERROR_KEY] = None
    return True
```

Extend `_store_model_value(name, section=None)` to persist when a section is supplied. Pass `historical` or `system_model` from export-rate controls and `battery` from strategy, common, custom, mode, model, and quantity callbacks. Keep read-only derived preset widgets callback-free.

- [ ] **Step 6: Run focused and complete AppTest suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_app.py -k "export_rates_persist_across_fresh_sessions or all_battery_settings_persist_across_fresh_sessions or battery_preset or custom_battery or each_view_has_a_persisted_export" -v
.\.venv\Scripts\python.exe -m pytest tests/test_app.py -v
```

Expected: all selected tests and then the complete AppTest file pass.

- [ ] **Step 7: Commit rates and battery persistence**

```powershell
git add -- app.py tests/test_app.py
git diff --cached --check
git commit -m "feat: persist rates and battery settings"
```

---

### Task 3: Persist Annual and Monthly Solar-Production Configuration

**Files:**
- Modify: `app.py:382-575`
- Modify: `tests/test_app.py:289-515`

**Interfaces:**
- Consumes: Task 2's initialized production state and `_persist_configuration_section("solar_production")`.
- Produces: automatic persistence for annual fields, scaling mode, and the complete monthly editor while invalid monthly edits remain in session only.

- [ ] **Step 1: Write a failing annual fresh-session test**

```python
def test_annual_solar_configuration_persists_across_fresh_sessions():
    first = _new_app()
    first.radio[0].set_value("Configuration").run()
    _number_input(first, "Reference annual production (kWh)").set_value(1200.0).run()
    _number_input(first, "Proposed annual production (kWh)").set_value(2400.0).run()

    second = _new_app()
    second.radio[0].set_value("Configuration").run()
    assert _radio(second, "Production scaling").value == "Annual"
    assert _number_input(second, "Reference annual production (kWh)").value == 1200.0
    assert _number_input(second, "Proposed annual production (kWh)").value == 2400.0
```

- [ ] **Step 2: Write failing monthly and invalid-isolation tests**

Extend `_edit_data_editor_rows` and `_edit_data_editor` with `editor_index: int = 0` and select `app.get("dataframe")[editor_index]`. Add:

```python
def test_monthly_solar_configuration_persists_across_fresh_sessions():
    first = _new_app()
    first.radio[0].set_value("Configuration").run()
    _radio(first, "Production scaling").set_value("Monthly").run()
    first = _edit_data_editor(
        first, 0, "Proposed production (kWh)", 336.26, editor_index=0
    )
    second = _new_app()
    second.radio[0].set_value("Configuration").run()
    assert _radio(second, "Production scaling").value == "Monthly"
    monthly = second.session_state["model.monthly_production"]
    assert monthly.iloc[0]["Proposed production (kWh)"] == pytest.approx(336.26)

def test_invalid_monthly_edit_keeps_saved_solar_but_other_section_can_save(
    isolate_user_configuration,
):
    first = _new_app()
    first.radio[0].set_value("Configuration").run()
    _radio(first, "Production scaling").set_value("Monthly").run()
    last_valid_solar = json.loads(
        isolate_user_configuration.read_text(encoding="utf-8")
    )["solar_production"]
    first = _edit_data_editor(
        first, 0, "Reference production (kWh)", None, editor_index=0
    )
    first.radio[0].set_value("Historical view").run()
    _number_input(
        first, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.07).run()
    saved = json.loads(isolate_user_configuration.read_text(encoding="utf-8"))
    assert saved["historical"]["export_purchase_rate_per_kwh"] == pytest.approx(0.07)
    assert saved["solar_production"] == last_valid_solar
```

Import `default_configuration` into `tests/test_app.py`.

- [ ] **Step 3: Run the new tests and verify persistence is absent**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_app.py -k "annual_solar_configuration_persists or monthly_solar_configuration_persists or invalid_monthly_edit_keeps" -v`

Expected: annual/monthly values reset in a fresh session, or invalid monthly state prevents the expected isolated save.

- [ ] **Step 4: Persist valid annual controls and scaling mode**

Pass `solar_production` to `_store_model_value` from the Production scaling radio and both annual production inputs. Each callback builds the entire solar section, including retained monthly values, so Annual and Monthly values remain independent.

- [ ] **Step 5: Persist only valid monthly editor changes**

In `_monthly_production_input`, preserve the current DataFrame behavior. When `edited_monthly` differs from the retained DataFrame, use:

```python
st.session_state[state_key] = edited_monthly
try:
    _validate_monthly_production(edited_monthly)
except ValueError:
    pass
else:
    _persist_configuration_section("solar_production")
st.rerun()
```

The next rerun displays the existing month-specific error for invalid edits. Since other section saves start from the last-known-valid document, invalid monthly state cannot leak into them.

- [ ] **Step 6: Run focused solar tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_app.py -k "solar or production or monthly" -v`

Expected: all selected existing and new tests pass.

- [ ] **Step 7: Commit solar-production persistence**

```powershell
git add -- app.py tests/test_app.py
git diff --cached --check
git commit -m "feat: persist solar production settings"
```

---

### Task 4: Persist TOU Rules, Surface File Status, and Reconcile Documentation

**Files:**
- Modify: `app.py:270-322, 900-end`
- Modify: `tests/test_app.py:630-760`
- Modify: `SPEC.md:150-165, 350-375, 590-665`
- Modify: `README.md:1-80`

**Interfaces:**
- Consumes: Task 2's initialized TOU DataFrame, status keys, path, and `_persist_configuration_section("time_of_use")`.
- Produces: complete durable behavior, visible path and failures, authoritative documentation, and full-suite evidence.

- [ ] **Step 1: Write failing TOU round-trip and invalid-isolation tests**

```python
def test_time_of_use_rules_persist_across_fresh_sessions():
    first = _new_app()
    first.radio[0].set_value("Configuration").run()
    first = _edit_data_editor(
        first, 0, "Price ($/kWh)", 0.20, editor_index=0
    )
    second = _new_app()
    second.radio[0].set_value("Configuration").run()
    rules = second.session_state["shared.tou_rules"]
    assert rules.iloc[0]["Price ($/kWh)"] == pytest.approx(0.20)

def test_invalid_tou_edit_keeps_saved_rules_but_rate_can_still_save(
    isolate_user_configuration,
):
    first = _new_app()
    first.radio[0].set_value("Configuration").run()
    first = _edit_data_editor(first, 0, "Start date", "invalid", editor_index=0)
    first.radio[0].set_value("Historical view").run()
    _number_input(
        first, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.07).run()
    saved = json.loads(isolate_user_configuration.read_text(encoding="utf-8"))
    assert saved["historical"]["export_purchase_rate_per_kwh"] == pytest.approx(0.07)
    assert saved["time_of_use"] == default_configuration()["time_of_use"]
```

- [ ] **Step 2: Write failing path, invalid-load, save-error, and transient-state tests**

```python
def test_configuration_page_shows_automatic_save_path(isolate_user_configuration):
    app = _new_app()
    app.radio[0].set_value("Configuration").run()
    assert any(
        "Settings save automatically" in item.value
        and str(isolate_user_configuration) in item.value
        for item in app.caption
    )

def test_invalid_existing_file_warns_and_is_not_overwritten(
    isolate_user_configuration,
):
    isolate_user_configuration.parent.mkdir(parents=True)
    original = json.dumps({"schema_version": 1, "unknown": True})
    isolate_user_configuration.write_text(original, encoding="utf-8")
    app = _new_app()
    assert any(str(isolate_user_configuration) in item.value for item in app.warning)
    _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.07).run()
    assert isolate_user_configuration.read_text(encoding="utf-8") == original

def test_save_failure_is_visible_and_keeps_session_value(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("block", encoding="utf-8")
    monkeypatch.setenv(
        "HOME_ENERGY_MODEL_CONFIG_PATH", str(blocker / "config.json")
    )
    app = _new_app()
    app = _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.07).run()
    assert _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).value == pytest.approx(0.07)
    assert any("could not be saved" in item.value.lower() for item in app.error)

def test_transient_view_state_is_not_written(isolate_user_configuration):
    app = _new_app()
    _selectbox(app, "Aggregation").set_value("Day").run()
    app.multiselect[0].set_value(["Used"]).run()
    _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.07).run()
    serialized = isolate_user_configuration.read_text(encoding="utf-8")
    assert "aggregation" not in serialized
    assert "date_range" not in serialized
    assert "visible_series" not in serialized
    assert "Historical view" not in serialized
```

- [ ] **Step 3: Run the new tests and verify their specific failures**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_app.py -k "time_of_use_rules_persist_across or invalid_tou_edit_keeps or automatic_save_path or invalid_existing_file or save_failure_is_visible or transient_view_state" -v`

Expected: TOU does not survive a fresh session, the path caption is absent, or failure state is not rendered.

- [ ] **Step 4: Persist valid TOU edits**

In `render_configuration`, retain the prior `shared.tou_rules` DataFrame. After receiving and storing `edited_rules`, detect a change with `DataFrame.equals`. Parse nonblank rows with the existing `parse_tou_rules`. Only after parsing succeeds, call `_persist_configuration_section("time_of_use")`. Preserve the existing row-specific error for invalid data. Convert DataFrame display keys to Task 1's seven semantic JSON keys; blank rows are excluded and never persisted.

- [ ] **Step 5: Render path and configuration status**

At the top of `render_configuration`, add:

```python
st.caption(f"Settings save automatically to {st.session_state[CONFIG_PATH_KEY]}")
```

Keep invalid-load warnings near the global title on every page. Render the current save error until a later successful save clears it. Do not show per-edit success toasts.

- [ ] **Step 6: Update `SPEC.md`**

Add `solar_model/configuration.py` to Application Structure. Replace Section 9.5's reset/no-disk contract with all durable and excluded values, exact path, schema version, environment override, one-time startup load, semantic JSON mapping, automatic section saves, and atomic replacement. Add missing-file, invalid-file autosave disablement, invalid editor retention, independent valid-section saves, and save-error behavior to Validation and Error Handling. Extend Verification Requirements with path, schema, round-trip, invalid-file, atomicity, persistence, isolation, and transient-state coverage. Retain the same-session navigation guarantees.

- [ ] **Step 7: Update `README.md`**

Clarify that the app has no named scenarios or cloud persistence but retains local user configuration. Add:

````markdown
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
````

Keep CSV instructions and modeling assumptions unchanged.

- [ ] **Step 8: Run focused and full verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_configuration.py tests/test_app.py -v
.\.venv\Scripts\python.exe -m pytest -v
git diff --check
git status --short
git diff --stat
```

Expected: focused and full suites pass with zero failures; whitespace check is silent; only planned source, test, SPEC, and README files are changed; local CSVs and unrelated files are absent from the diff.

- [ ] **Step 9: Commit complete user-facing behavior**

```powershell
git add -- app.py tests/test_app.py SPEC.md README.md
git diff --cached --check
git commit -m "feat: persist configuration page settings"
```

- [ ] **Step 10: Re-run verification at the committed tip**

```powershell
.\.venv\Scripts\python.exe -m pytest -v
git diff --check HEAD^ HEAD
git status --short --branch
```

Expected: full suite passes, the committed diff has no whitespace errors, and the feature branch has no uncommitted planned changes.

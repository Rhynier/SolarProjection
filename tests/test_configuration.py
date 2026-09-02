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


def test_validate_configuration_returns_a_normalized_copy():
    source = default_configuration()
    normalized = validate_configuration(source)
    assert normalized == source
    assert normalized is not source


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update({"extra": True}), "unknown field 'extra'"),
        (lambda value: value.pop("battery"), "battery is required"),
        (lambda value: value["historical"].update({"export_purchase_rate_per_kwh": -0.01}), "historical.export_purchase_rate_per_kwh"),
        (lambda value: value["battery"].update({"strategy": "unknown strategy"}), "battery.strategy"),
        (lambda value: value["battery"].update({"starting_charge_percent": 5.0, "minimum_reserve_percent": 10.0}), "starting charge must not be below minimum reserve"),
        (lambda value: value["battery"]["preset"].update({"quantity": 1.5}), "battery.preset.quantity"),
        (lambda value: value["solar_production"].update({"monthly": []}), "solar_production.monthly must contain exactly 12 rows"),
        (lambda value: value["time_of_use"]["rules"][0].update({"start_date": "bad"}), "time_of_use.rules Row 1"),
    ],
)
def test_validate_configuration_rejects_invalid_documents(mutate, message):
    document = default_configuration()
    mutate(document)
    with pytest.raises(ConfigurationValidationError, match=message):
        validate_configuration(document)


@pytest.mark.parametrize(
    ("mutate", "message"),
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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"schema_version": 2}),
        lambda value: value["battery"].pop("strategy"),
        lambda value: value["battery"].update({"strategy": "unknown"}),
    ],
)
def test_load_invalid_valid_json_preserves_file_and_disables_autosave(tmp_path, mutate):
    path = tmp_path / "config.json"
    document = default_configuration()
    mutate(document)
    original = json.dumps(document)
    path.write_text(original, encoding="utf-8")
    result = load_configuration(path)
    assert result.document == default_configuration()
    assert not result.autosave_enabled
    assert str(path) in result.warning
    assert path.read_text(encoding="utf-8") == original

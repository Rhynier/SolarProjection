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

_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_TOU_SEMANTIC_FIELDS = {
    "name",
    "start_date",
    "end_date",
    "weekdays",
    "start_time",
    "end_time",
    "price_per_kwh",
}


class ConfigurationError(RuntimeError):
    pass


class ConfigurationValidationError(ConfigurationError):
    pass


@dataclass(frozen=True)
class LoadResult:
    document: dict[str, Any]
    autosave_enabled: bool
    warning: str | None = None


def _semantic_tou_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "name": row["Name"],
        "start_date": row["Start date"],
        "end_date": row["End date"],
        "weekdays": row["Weekdays"],
        "start_time": row["Start time"],
        "end_time": row["End time"],
        "price_per_kwh": row["Price ($/kWh)"],
    }


_DEFAULT_CONFIGURATION = {
    "schema_version": CONFIG_VERSION,
    "historical": {"export_purchase_rate_per_kwh": 0.0563},
    "system_model": {"export_purchase_rate_per_kwh": 0.096},
    "battery": {
        "strategy": "Self-consumption",
        "settings_mode": "Custom values",
        "starting_charge_percent": 50.0,
        "minimum_reserve_percent": 10.0,
        "preset": {"model": "Tesla Powerwall 3", "quantity": 1},
        "custom": {
            "usable_capacity_kwh": 13.5,
            "round_trip_efficiency_percent": 90.0,
            "maximum_charge_power_kw": 5.0,
            "maximum_discharge_power_kw": 5.0,
        },
    },
    "solar_production": {
        "scaling_mode": "Annual",
        "annual": {"reference_kwh": 2017.56, "proposed_kwh": 2017.56},
        "monthly": [
            {"month": month, "reference_kwh": 168.13, "proposed_kwh": 168.13}
            for month in _MONTH_NAMES
        ],
    },
    "time_of_use": {"rules": [_semantic_tou_row(row) for row in SMUD_DEFAULT_TOU_ROWS]},
}


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


def default_configuration() -> dict[str, Any]:
    return deepcopy(_DEFAULT_CONFIGURATION)


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


def _require_percentage(value: object, path: str, minimum: float = 0.0) -> float:
    normalized = _require_number(value, path, minimum)
    if normalized > 100.0:
        raise ConfigurationValidationError(f"{path} must be at most 100.0")
    return normalized


def _require_choice(value: object, path: str, choices: set[str]) -> str:
    normalized = _require_text(value, path)
    if normalized not in choices:
        raise ConfigurationValidationError(f"{path} must be one of {sorted(choices)!r}")
    return normalized


def _display_tou_row(row: dict[str, Any], row_number: int) -> dict[str, object]:
    semantic = _require_object(row, f"time_of_use.rules[{row_number}]", _TOU_SEMANTIC_FIELDS)
    return {
        "Name": _require_text(semantic["name"], "time_of_use.rules.name"),
        "Start date": _require_text(
            semantic["start_date"], "time_of_use.rules.start_date"
        ),
        "End date": _require_text(semantic["end_date"], "time_of_use.rules.end_date"),
        "Weekdays": _require_text(semantic["weekdays"], "time_of_use.rules.weekdays"),
        "Start time": _require_text(
            semantic["start_time"], "time_of_use.rules.start_time"
        ),
        "End time": _require_text(semantic["end_time"], "time_of_use.rules.end_time"),
        "Price ($/kWh)": _require_number(
            semantic["price_per_kwh"], "time_of_use.rules.price_per_kwh", 0.0
        ),
    }


def validate_configuration(document: object) -> dict[str, Any]:
    root = _require_object(
        document,
        "configuration",
        {
            "schema_version",
            "historical",
            "system_model",
            "battery",
            "solar_production",
            "time_of_use",
        },
    )
    version = _require_integer(root["schema_version"], "schema_version")
    if version != CONFIG_VERSION:
        raise ConfigurationValidationError(f"unsupported schema_version {version}")

    historical = _require_object(
        root["historical"], "historical", {"export_purchase_rate_per_kwh"}
    )
    system_model = _require_object(
        root["system_model"], "system_model", {"export_purchase_rate_per_kwh"}
    )
    battery = _require_object(
        root["battery"],
        "battery",
        {
            "strategy",
            "settings_mode",
            "starting_charge_percent",
            "minimum_reserve_percent",
            "preset",
            "custom",
        },
    )
    preset = _require_object(battery["preset"], "battery.preset", {"model", "quantity"})
    custom = _require_object(
        battery["custom"],
        "battery.custom",
        {
            "usable_capacity_kwh",
            "round_trip_efficiency_percent",
            "maximum_charge_power_kw",
            "maximum_discharge_power_kw",
        },
    )
    starting_charge = _require_percentage(
        battery["starting_charge_percent"], "battery.starting_charge_percent"
    )
    minimum_reserve = _require_percentage(
        battery["minimum_reserve_percent"], "battery.minimum_reserve_percent"
    )
    if starting_charge < minimum_reserve:
        raise ConfigurationValidationError(
            "starting charge must not be below minimum reserve"
        )

    solar_production = _require_object(
        root["solar_production"], "solar_production", {"scaling_mode", "annual", "monthly"}
    )
    annual = _require_object(
        solar_production["annual"], "solar_production.annual", {"reference_kwh", "proposed_kwh"}
    )
    monthly = _require_list(solar_production["monthly"], "solar_production.monthly")
    if len(monthly) != 12:
        raise ConfigurationValidationError(
            "solar_production.monthly must contain exactly 12 rows"
        )

    time_of_use = _require_object(root["time_of_use"], "time_of_use", {"rules"})
    raw_rules = _require_list(time_of_use["rules"], "time_of_use.rules")
    display_rules = [_display_tou_row(row, index) for index, row in enumerate(raw_rules, start=1)]
    try:
        parse_tou_rules(display_rules)
    except TouValidationError as error:
        raise ConfigurationValidationError(f"time_of_use.rules {error}") from error

    normalized_monthly = []
    for index, row in enumerate(monthly):
        item = _require_object(
            row,
            f"solar_production.monthly[{index}]",
            {"month", "reference_kwh", "proposed_kwh"},
        )
        expected_month = _MONTH_NAMES[index]
        month = _require_text(item["month"], "solar_production.monthly.month")
        if month != expected_month:
            raise ConfigurationValidationError(f"month must be {expected_month!r}")
        normalized_monthly.append(
            {
                "month": month,
                "reference_kwh": _require_number(
                    item["reference_kwh"], "solar_production.monthly.reference_kwh", 0.0000001
                ),
                "proposed_kwh": _require_number(
                    item["proposed_kwh"], "solar_production.monthly.proposed_kwh", 0.0
                ),
            }
        )

    return {
        "schema_version": version,
        "historical": {
            "export_purchase_rate_per_kwh": _require_number(
                historical["export_purchase_rate_per_kwh"],
                "historical.export_purchase_rate_per_kwh",
                0.0,
            )
        },
        "system_model": {
            "export_purchase_rate_per_kwh": _require_number(
                system_model["export_purchase_rate_per_kwh"],
                "system_model.export_purchase_rate_per_kwh",
                0.0,
            )
        },
        "battery": {
            "strategy": _require_choice(
                battery["strategy"], "battery.strategy", {"Self-consumption", "TOU reserve"}
            ),
            "settings_mode": _require_choice(
                battery["settings_mode"], "battery.settings_mode", {"Custom values", "Battery preset"}
            ),
            "starting_charge_percent": starting_charge,
            "minimum_reserve_percent": minimum_reserve,
            "preset": {
                "model": _require_choice(
                    preset["model"],
                    "battery.preset.model",
                    {"Tesla Powerwall 3", "Enphase IQ Battery 10C"},
                ),
                "quantity": _require_integer(
                    preset["quantity"], "battery.preset.quantity", 1
                ),
            },
            "custom": {
                "usable_capacity_kwh": _require_number(
                    custom["usable_capacity_kwh"], "battery.custom.usable_capacity_kwh", 0.0
                ),
                "round_trip_efficiency_percent": _require_percentage(
                    custom["round_trip_efficiency_percent"],
                    "battery.custom.round_trip_efficiency_percent",
                    0.1,
                ),
                "maximum_charge_power_kw": _require_number(
                    custom["maximum_charge_power_kw"],
                    "battery.custom.maximum_charge_power_kw",
                    0.0,
                ),
                "maximum_discharge_power_kw": _require_number(
                    custom["maximum_discharge_power_kw"],
                    "battery.custom.maximum_discharge_power_kw",
                    0.0,
                ),
            },
        },
        "solar_production": {
            "scaling_mode": _require_choice(
                solar_production["scaling_mode"],
                "solar_production.scaling_mode",
                {"Annual", "Monthly"},
            ),
            "annual": {
                "reference_kwh": _require_number(
                    annual["reference_kwh"], "solar_production.annual.reference_kwh", 0.01
                ),
                "proposed_kwh": _require_number(
                    annual["proposed_kwh"], "solar_production.annual.proposed_kwh", 0.0
                ),
            },
            "monthly": normalized_monthly,
        },
        "time_of_use": {
            "rules": [_semantic_tou_row(row) for row in display_rules],
        },
    }


def load_configuration(path: Path) -> LoadResult:
    resolved = Path(path)
    if not resolved.exists():
        return LoadResult(default_configuration(), autosave_enabled=True)
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
        return LoadResult(validate_configuration(document), autosave_enabled=True)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ConfigurationValidationError) as error:
        return LoadResult(
            default_configuration(),
            autosave_enabled=False,
            warning=(
                f"Configuration at {resolved} could not be loaded: {error}. "
                "Correct or move the file, then restart the app."
            ),
        )


def save_configuration(path: Path, document: object) -> dict[str, Any]:
    normalized = validate_configuration(document)
    resolved = Path(path)
    try:
        existing = load_configuration(resolved)
        if existing.autosave_enabled and resolved.exists() and existing.document == normalized:
            return normalized
        resolved.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=resolved.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(normalized, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
            os.replace(temporary_path, resolved)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
    except OSError as error:
        raise ConfigurationError(
            f"Configuration could not be saved to {resolved}: {error}"
        ) from error
    return normalized

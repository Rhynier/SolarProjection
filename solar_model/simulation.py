from dataclasses import dataclass
from math import isclose, isfinite, sqrt
from typing import Literal, Sequence

import pandas as pd

from .tou import TouRule, has_seasonal_price_spread, is_expensive


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
    monthly_solar_scales: tuple[float, ...] | None = None


def _require_finite(value: object, name: str) -> None:
    try:
        valid = isfinite(value)
    except (TypeError, ValueError) as error:
        raise SimulationValidationError(f"{name} must be finite") from error
    if not valid:
        raise SimulationValidationError(f"{name} must be finite")


def _validate_config(config: SimulationConfig, tou_rules: Sequence[TouRule]) -> None:
    battery = config.battery
    values = {
        "solar_scale": config.solar_scale,
        "capacity_kwh": battery.capacity_kwh,
        "starting_percent": battery.starting_percent,
        "reserve_percent": battery.reserve_percent,
        "round_trip_efficiency": battery.round_trip_efficiency,
        "max_charge_kw": battery.max_charge_kw,
        "max_discharge_kw": battery.max_discharge_kw,
    }
    for name, value in values.items():
        _require_finite(value, name)

    if config.solar_scale < 0:
        raise SimulationValidationError("solar_scale must not be negative")
    if config.monthly_solar_scales is not None:
        if len(config.monthly_solar_scales) != 12:
            raise SimulationValidationError(
                "monthly_solar_scales must contain 12 values"
            )
        try:
            valid_monthly_scales = all(
                isfinite(scale) and scale >= 0
                for scale in config.monthly_solar_scales
            )
        except (TypeError, ValueError):
            valid_monthly_scales = False
        if not valid_monthly_scales:
            raise SimulationValidationError(
                "monthly_solar_scales must contain finite nonnegative values"
            )
    if battery.capacity_kwh < 0:
        raise SimulationValidationError("capacity_kwh must not be negative")
    if battery.max_charge_kw < 0 or battery.max_discharge_kw < 0:
        raise SimulationValidationError("battery power limits must not be negative")
    if not 0 <= battery.starting_percent <= 100:
        raise SimulationValidationError("starting_percent must be between 0 and 100")
    if not 0 <= battery.reserve_percent <= 100:
        raise SimulationValidationError("reserve_percent must be between 0 and 100")
    if battery.starting_percent < battery.reserve_percent:
        raise SimulationValidationError("starting_percent must not be below reserve_percent")
    if not 0 < battery.round_trip_efficiency <= 1:
        raise SimulationValidationError("round_trip_efficiency must be in (0, 1]")
    if config.strategy not in {"self_consumption", "tou_reserve"}:
        raise SimulationValidationError("strategy must be self_consumption or tou_reserve")
    if config.strategy == "tou_reserve" and not has_seasonal_price_spread(
        tou_rules
    ):
        raise SimulationValidationError(
            "TOU reserve requires multiple prices in at least one season"
        )


def _clamp_soc_drift(soc: float, reserve: float, capacity: float) -> float:
    for boundary in (reserve, capacity, 0.0):
        if abs(soc - boundary) <= 1e-12:
            return boundary
    return soc


def simulate(
    hourly: pd.DataFrame,
    config: SimulationConfig,
    tou_rules: Sequence[TouRule],
) -> pd.DataFrame:
    _validate_config(config, tou_rules)

    leg_efficiency = sqrt(config.battery.round_trip_efficiency)
    capacity = config.battery.capacity_kwh
    reserve = capacity * config.battery.reserve_percent / 100.0
    soc = capacity * config.battery.starting_percent / 100.0
    results: list[dict[str, object]] = []

    for row in hourly.itertuples(index=False):
        solar_scale = (
            config.solar_scale
            if config.monthly_solar_scales is None
            else config.monthly_solar_scales[row.timestamp.month - 1]
        )
        modeled_solar = row.actual_solar_kwh * solar_scale
        direct_solar = min(modeled_solar, row.household_load_kwh)
        surplus = modeled_solar - direct_solar
        deficit = row.household_load_kwh - direct_solar
        charge_input = min(
            surplus,
            config.battery.max_charge_kw,
            (capacity - soc) / leg_efficiency,
        )
        soc += charge_input * leg_efficiency
        soc = _clamp_soc_drift(soc, reserve, capacity)
        grid_export = surplus - charge_input

        expensive = is_expensive(row.timestamp.to_pydatetime(), tou_rules)
        may_discharge = config.strategy == "self_consumption" or expensive
        discharge_output = 0.0
        if may_discharge:
            discharge_output = min(
                deficit,
                config.battery.max_discharge_kw,
                (soc - reserve) * leg_efficiency,
            )
            soc -= discharge_output / leg_efficiency
            soc = _clamp_soc_drift(soc, reserve, capacity)
        grid_import = deficit - discharge_output

        ac_supply = modeled_solar + grid_import + discharge_output
        ac_demand = row.household_load_kwh + grid_export + charge_input
        if not isclose(ac_supply, ac_demand, rel_tol=0, abs_tol=1e-9):
            raise SimulationValidationError(
                f"AC-bus energy imbalance at {row.timestamp}"
            )

        results.append({
            "timestamp": row.timestamp,
            "household_load_kwh": row.household_load_kwh,
            "modeled_solar_kwh": modeled_solar,
            "battery_soc_kwh": soc,
            "battery_charge_input_kwh": charge_input,
            "battery_discharge_output_kwh": discharge_output,
            "grid_import_kwh": grid_import,
            "grid_export_kwh": grid_export,
            "is_expensive": expensive,
        })

    return pd.DataFrame(results, columns=[
        "timestamp",
        "household_load_kwh",
        "modeled_solar_kwh",
        "battery_soc_kwh",
        "battery_charge_input_kwh",
        "battery_discharge_output_kwh",
        "grid_import_kwh",
        "grid_export_kwh",
        "is_expensive",
    ])

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


def test_zero_capacity_battery_keeps_surplus_on_the_grid():
    result = simulate(
        frame([1.0], [2.0]),
        SimulationConfig(1.0, battery(
            capacity_kwh=0.0, starting_percent=0.0, reserve_percent=0.0,
        ), "self_consumption"), [],
    )
    assert result.loc[0, "battery_charge_input_kwh"] == pytest.approx(0.0)
    assert result.loc[0, "battery_soc_kwh"] == pytest.approx(0.0)
    assert result.loc[0, "grid_export_kwh"] == pytest.approx(1.0)


@pytest.mark.parametrize("config", [
    SimulationConfig(-1.0, battery(), "self_consumption"),
    SimulationConfig(float("inf"), battery(), "self_consumption"),
    SimulationConfig(1.0, battery(capacity_kwh=-1.0), "self_consumption"),
    SimulationConfig(1.0, battery(starting_percent=101.0), "self_consumption"),
    SimulationConfig(1.0, battery(starting_percent=9.0), "self_consumption"),
    SimulationConfig(1.0, battery(round_trip_efficiency=0.0), "self_consumption"),
    SimulationConfig(1.0, battery(max_charge_kw=-1.0), "self_consumption"),
    SimulationConfig(1.0, battery(max_discharge_kw=float("nan")), "self_consumption"),
    SimulationConfig(1.0, battery(), "unknown"),
])
def test_invalid_configuration_is_rejected(config):
    with pytest.raises(SimulationValidationError):
        simulate(frame([0.0], [0.0]), config, [])


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

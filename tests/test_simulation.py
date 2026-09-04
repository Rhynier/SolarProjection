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


def test_tou_reserve_preserves_charge_until_the_seasonal_maximum_rate():
    rules = parse_tou_rules([
        {
            "Name": "Off-peak", "Start date": "01-01", "End date": "12-31",
            "Weekdays": "Mon,Tue,Wed,Thu,Fri", "Start time": "00:00",
            "End time": "12:00", "Price ($/kWh)": "0.1550",
        },
        {
            "Name": "Mid-peak", "Start date": "01-01", "End date": "12-31",
            "Weekdays": "Mon,Tue,Wed,Thu,Fri", "Start time": "12:00",
            "End time": "17:00", "Price ($/kWh)": "0.2139",
        },
        {
            "Name": "Peak", "Start date": "01-01", "End date": "12-31",
            "Weekdays": "Mon,Tue,Wed,Thu,Fri", "Start time": "17:00",
            "End time": "20:00", "Price ($/kWh)": "0.3765",
        },
    ])
    result = simulate(
        frame([2.0, 2.0], [0.0, 0.0], start="2026-07-06 16:00"),
        SimulationConfig(1.0, battery(), "tou_reserve"), rules,
    )
    assert list(result["grid_import_kwh"]) == pytest.approx([2.0, 0.0])
    assert list(result["battery_soc_kwh"]) == pytest.approx([5.0, 3.0])
    assert list(result["is_expensive"]) == [False, True]


def test_full_backup_holds_full_capacity_and_does_not_discharge_on_grid():
    result = simulate(
        frame([3.0, 2.0], [0.0, 4.0]),
        SimulationConfig(
            1.0,
            battery(starting_percent=20.0, reserve_percent=80.0),
            "full_backup",
        ),
        [],
    )

    assert list(result["battery_soc_kwh"]) == pytest.approx([10.0, 10.0])
    assert list(result["battery_discharge_output_kwh"]) == pytest.approx([0.0, 0.0])
    assert list(result["battery_charge_input_kwh"]) == pytest.approx([0.0, 0.0])
    assert list(result["grid_import_kwh"]) == pytest.approx([3.0, 0.0])
    assert list(result["grid_export_kwh"]) == pytest.approx([0.0, 2.0])


def test_tou_reserve_accepts_an_overlapping_seasonal_price_override():
    rules = parse_tou_rules([
        {
            "Name": "Base rate", "Start date": "01-01", "End date": "12-31",
            "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun", "Start time": "00:00",
            "End time": "00:00", "Price ($/kWh)": "0.1550",
        },
        {
            "Name": "Summer peak", "Start date": "06-01", "End date": "09-30",
            "Weekdays": "Mon,Tue,Wed,Thu,Fri", "Start time": "17:00",
            "End time": "20:00", "Price ($/kWh)": "0.3765",
        },
    ])

    result = simulate(
        frame([2.0], [0.0]),
        SimulationConfig(1.0, battery(), "tou_reserve"),
        rules,
    )

    assert result.loc[0, "battery_discharge_output_kwh"] == pytest.approx(2.0)
    assert bool(result.loc[0, "is_expensive"])


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


def test_non_unity_discharge_efficiency_reduces_soc_by_delivered_energy_per_leg_efficiency():
    result = simulate(
        frame([3.0], [0.0]),
        SimulationConfig(1.0, battery(
            reserve_percent=0.0, round_trip_efficiency=0.81,
        ), "self_consumption"), [],
    )
    assert result.loc[0, "battery_discharge_output_kwh"] == pytest.approx(3.0)
    assert result.loc[0, "battery_soc_kwh"] == pytest.approx(5.0 - 3.0 / 0.9)


def test_charge_input_is_limited_by_max_charge_kw():
    result = simulate(
        frame([0.0], [10.0]),
        SimulationConfig(1.0, battery(
            capacity_kwh=20.0, starting_percent=0.0, reserve_percent=0.0,
            max_charge_kw=2.0,
        ), "self_consumption"), [],
    )
    assert result.loc[0, "battery_charge_input_kwh"] == pytest.approx(2.0)
    assert result.loc[0, "grid_export_kwh"] == pytest.approx(8.0)


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


def test_monthly_solar_scales_apply_by_calendar_month():
    result = simulate(
        frame(
            [0.0, 0.0],
            [1.0, 1.0],
            start="2026-01-31 23:00",
        ),
        SimulationConfig(
            1.0,
            battery(capacity_kwh=0.0, starting_percent=0.0, reserve_percent=0.0),
            "self_consumption",
            monthly_solar_scales=(2.0, 3.0) + (1.0,) * 10,
        ),
        [],
    )

    assert list(result["modeled_solar_kwh"]) == pytest.approx([2.0, 3.0])


@pytest.mark.parametrize(
    ("monthly_scales", "message"),
    [
        ((1.0,) * 11, "must contain 12 values"),
        ((-1.0,) + (1.0,) * 11, "must contain finite nonnegative values"),
        ((float("inf"),) + (1.0,) * 11, "must contain finite nonnegative values"),
    ],
)
def test_monthly_solar_scales_require_twelve_finite_nonnegative_values(
    monthly_scales,
    message,
):
    with pytest.raises(SimulationValidationError, match=message):
        simulate(
            frame([0.0], [0.0]),
            SimulationConfig(
                1.0,
                battery(),
                "self_consumption",
                monthly_solar_scales=monthly_scales,
            ),
            [],
        )


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


def test_tou_reserve_requires_a_seasonal_price_spread():
    with pytest.raises(
        SimulationValidationError, match="multiple prices in at least one season"
    ):
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

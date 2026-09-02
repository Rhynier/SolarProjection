import pandas as pd
import pytest

from solar_model.simulation import (
    BatteryConfig,
    SimulationConfig,
    SimulationValidationError,
    simulate,
)
from solar_model.tou import parse_tou_rules


def _hourly(loads, solar):
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-06 16:00", periods=len(loads), freq="h"
            ),
            "household_load_kwh": loads,
            "actual_solar_kwh": solar,
        }
    )


def _battery(**overrides):
    values = {
        "capacity_kwh": 2.0,
        "starting_percent": 50.0,
        "reserve_percent": 0.0,
        "round_trip_efficiency": 1.0,
        "max_charge_kw": 1.0,
        "max_discharge_kw": 1.0,
    }
    values.update(overrides)
    return BatteryConfig(**values)


def _two_hour_prices(first, second):
    return parse_tou_rules(
        [
            {
                "Name": "First hour",
                "Start date": "01-01",
                "End date": "12-31",
                "Weekdays": "Mon,Tue,Wed,Thu,Fri",
                "Start time": "16:00",
                "End time": "17:00",
                "Price ($/kWh)": first,
            },
            {
                "Name": "Second hour",
                "Start date": "01-01",
                "End date": "12-31",
                "Weekdays": "Mon,Tue,Wed,Thu,Fri",
                "Start time": "17:00",
                "End time": "18:00",
                "Price ($/kWh)": second,
            },
        ]
    )


def test_cost_optimized_simulation_requires_an_export_rate():
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-06 17:00", periods=1, freq="h"),
            "household_load_kwh": [1.0],
            "actual_solar_kwh": [0.0],
        }
    )
    battery = BatteryConfig(
        capacity_kwh=10.0,
        starting_percent=50.0,
        reserve_percent=10.0,
        round_trip_efficiency=0.9,
        max_charge_kw=7.08,
        max_discharge_kw=7.08,
    )

    with pytest.raises(
        SimulationValidationError,
        match="cost_optimized requires export_rate_per_kwh",
    ):
        simulate(hourly, SimulationConfig(1.0, battery, "cost_optimized"), [])


def test_cost_optimizer_rejects_imported_energy_without_a_utility_price():
    hourly = _hourly([1.0], [0.0])

    with pytest.raises(
        SimulationValidationError,
        match="Imported energy at 2026-07-06 16:00:00 has no utility price",
    ):
        simulate(
            hourly,
            SimulationConfig(
                1.0,
                _battery(starting_percent=0.0),
                "cost_optimized",
                export_rate_per_kwh=0.05,
            ),
            [],
        )


def test_optimizer_preserves_limited_energy_for_the_higher_price_hour():
    result = simulate(
        _hourly([1.0, 1.0], [0.0, 0.0]),
        SimulationConfig(
            1.0,
            _battery(),
            "cost_optimized",
            export_rate_per_kwh=0.05,
        ),
        _two_hour_prices(0.10, 0.30),
    )

    assert list(result["grid_import_kwh"]) == pytest.approx([1.0, 0.0])
    assert list(result["battery_discharge_output_kwh"]) == pytest.approx(
        [0.0, 1.0]
    )
    assert list(result["battery_soc_kwh"]) == pytest.approx([1.0, 0.0])


def test_optimizer_charges_solar_when_later_import_avoidance_beats_export():
    result = simulate(
        _hourly([0.0, 1.0], [1.0, 0.0]),
        SimulationConfig(
            1.0,
            _battery(starting_percent=0.0),
            "cost_optimized",
            export_rate_per_kwh=0.05,
        ),
        _two_hour_prices(0.10, 0.30),
    )

    assert list(result["battery_charge_input_kwh"]) == pytest.approx([1.0, 0.0])
    assert list(result["battery_discharge_output_kwh"]) == pytest.approx(
        [0.0, 1.0]
    )
    assert list(result["grid_export_kwh"]) == pytest.approx([0.0, 0.0])
    assert list(result["grid_import_kwh"]) == pytest.approx([0.0, 0.0])


def test_optimizer_exports_solar_when_storage_loss_makes_charging_uneconomic():
    result = simulate(
        _hourly([0.0, 1.0], [1.0, 0.0]),
        SimulationConfig(
            1.0,
            _battery(
                starting_percent=0.0,
                round_trip_efficiency=0.81,
            ),
            "cost_optimized",
            export_rate_per_kwh=0.20,
        ),
        _two_hour_prices(0.05, 0.10),
    )

    assert list(result["battery_charge_input_kwh"]) == pytest.approx([0.0, 0.0])
    assert list(result["battery_discharge_output_kwh"]) == pytest.approx(
        [0.0, 0.0]
    )
    assert list(result["grid_export_kwh"]) == pytest.approx([1.0, 0.0])
    assert list(result["grid_import_kwh"]) == pytest.approx([0.0, 1.0])

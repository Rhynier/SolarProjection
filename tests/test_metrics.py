import pandas as pd
import pytest

from solar_model.metrics import summarize_simulation


def test_simulation_summary_calculates_strategy_comparison_metrics():
    result = pd.DataFrame(
        {
            "modeled_solar_kwh": [4.0, 0.0],
            "grid_export_kwh": [1.0, 0.0],
            "grid_import_kwh": [0.0, 2.0],
            "is_expensive": [False, True],
            "battery_discharge_output_kwh": [0.0, 0.9],
            "battery_soc_kwh": [1.5, 0.5],
        }
    )

    summary = summarize_simulation(
        result,
        capacity_kwh=2.0,
        reserve_percent=50.0,
        round_trip_efficiency=0.81,
    )

    assert summary.solar_self_consumption_percent == pytest.approx(75.0)
    assert summary.expensive_grid_import_kwh == pytest.approx(2.0)
    assert summary.battery_discharge_output_kwh == pytest.approx(0.9)
    assert summary.equivalent_full_cycles == pytest.approx(1.0)
    assert summary.ending_charge_percent == pytest.approx(25.0)


def test_simulation_summary_uses_zero_for_undefined_ratios():
    result = pd.DataFrame(
        {
            "modeled_solar_kwh": [0.0],
            "grid_export_kwh": [0.0],
            "grid_import_kwh": [1.0],
            "is_expensive": [False],
            "battery_discharge_output_kwh": [0.0],
            "battery_soc_kwh": [0.0],
        }
    )

    summary = summarize_simulation(
        result,
        capacity_kwh=0.0,
        reserve_percent=100.0,
        round_trip_efficiency=0.9,
    )

    assert summary.solar_self_consumption_percent == 0.0
    assert summary.equivalent_full_cycles == 0.0
    assert summary.ending_charge_percent == 0.0

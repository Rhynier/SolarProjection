import pandas as pd
import pytest

from solar_model.costs import (
    CostValidationError,
    format_currency,
    projected_utility_cost,
)
from solar_model.tou import parse_tou_rules


def test_projected_cost_uses_hourly_import_prices_and_export_credit():
    hourly = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-05 16:00", "2026-01-05 17:00"]),
            "grid_import_kwh": [2.0, 1.0],
            "grid_export_kwh": [0.5, 0.25],
        }
    )
    rules = parse_tou_rules(
        [
            {
                "Name": "Off-peak",
                "Start date": "01-01",
                "End date": "12-31",
                "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                "Start time": "00:00",
                "End time": "17:00",
                "Price ($/kWh)": "0.15",
            },
            {
                "Name": "Peak",
                "Start date": "01-01",
                "End date": "12-31",
                "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                "Start time": "17:00",
                "End time": "00:00",
                "Price ($/kWh)": "0.40",
            },
        ]
    )

    result = projected_utility_cost(hourly, rules, export_rate_per_kwh=0.10)

    assert result == pytest.approx(0.625)


def test_projected_cost_rejects_imported_energy_without_a_utility_price():
    hourly = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-05 16:00"]),
            "grid_import_kwh": [1.0],
            "grid_export_kwh": [0.0],
        }
    )

    with pytest.raises(CostValidationError, match="no utility price"):
        projected_utility_cost(hourly, [], export_rate_per_kwh=0.10)


@pytest.mark.parametrize("export_rate", [-0.01, float("nan"), float("inf")])
def test_projected_cost_rejects_invalid_export_rates(export_rate):
    hourly = pd.DataFrame(
        columns=["timestamp", "grid_import_kwh", "grid_export_kwh"]
    )

    with pytest.raises(CostValidationError, match="finite non-negative"):
        projected_utility_cost(hourly, [], export_rate_per_kwh=export_rate)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(12.345, "$12.35"), (-0.2, "-$0.20")],
)
def test_currency_format_places_the_sign_before_the_dollar_symbol(amount, expected):
    assert format_currency(amount) == expected

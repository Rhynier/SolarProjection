from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def _number_input(app: AppTest, label: str):
    return next(widget for widget in app.number_input if widget.label == label)


def _radio(app: AppTest, label: str):
    return next(widget for widget in app.radio if widget.label == label)


def _selectbox(app: AppTest, label: str):
    return next(widget for widget in app.selectbox if widget.label == label)


def _metric(app: AppTest, label: str):
    return next(metric for metric in app.metric if metric.label == label)


def _currency_value(value: str) -> float:
    normalized = value.replace(",", "")
    if normalized.startswith("-$"):
        return -float(normalized[2:])
    return float(normalized.removeprefix("$"))


def _energy_value(value: str) -> float:
    return float(value.removesuffix(" kWh").replace(",", ""))


def test_app_starts_against_supplied_csvs_without_exceptions():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Home Energy Model"
    assert app.radio[0].options == ["Historical view", "System model"]
    app.radio[0].set_value("System model").run()
    assert not app.exception


def test_app_does_not_log_deprecated_container_width_warning(capfd):
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()

    captured = capfd.readouterr()
    assert "Please replace `use_container_width` with `width`" not in captured.err


def test_model_battery_capacity_survives_a_history_round_trip():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    app.radio[0].set_value("System model").run()
    _number_input(app, "Battery usable capacity (kWh)").set_value(20.0).run()

    app.radio[0].set_value("Historical view").run()
    app.radio[0].set_value("System model").run()

    assert _number_input(app, "Battery usable capacity (kWh)").value == 20.0


@pytest.mark.parametrize(
    ("battery_model", "quantity", "capacity", "efficiency", "charge", "discharge"),
    [
        ("Tesla Powerwall 3", 2, 27.0, 89.0, 10.0, 23.0),
        ("Enphase IQ Battery 10C", 3, 30.0, 90.0, 21.24, 21.24),
    ],
)
def test_battery_preset_scales_nameplate_values_by_quantity(
    battery_model: str,
    quantity: int,
    capacity: float,
    efficiency: float,
    charge: float,
    discharge: float,
):
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    app.radio[0].set_value("System model").run()
    battery_settings = _radio(app, "Battery settings")
    assert battery_settings.options == ["Custom values", "Battery preset"]
    battery_settings.set_value("Battery preset").run()
    battery_select = _selectbox(app, "Battery model")
    assert battery_select.options == ["Tesla Powerwall 3", "Enphase IQ Battery 10C"]
    battery_select.set_value(battery_model).run()
    _number_input(app, "Number of batteries").set_value(quantity).run()

    expected_values = {
        "Battery usable capacity (kWh)": capacity,
        "Round-trip efficiency (%)": efficiency,
        "Maximum charge power (kW)": charge,
        "Maximum discharge power (kW)": discharge,
    }
    for label, expected in expected_values.items():
        widget = _number_input(app, label)
        assert widget.value == expected
        assert widget.disabled
    assert _number_input(app.sidebar, "Battery usable capacity (kWh)").value == capacity


def test_battery_preset_selection_survives_a_history_round_trip():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    app.radio[0].set_value("System model").run()
    _radio(app, "Battery settings").set_value("Battery preset").run()
    _selectbox(app, "Battery model").set_value("Enphase IQ Battery 10C").run()
    _number_input(app, "Number of batteries").set_value(2).run()

    app.radio[0].set_value("Historical view").run()
    app.radio[0].set_value("System model").run()

    assert _radio(app, "Battery settings").value == "Battery preset"
    assert _selectbox(app, "Battery model").value == "Enphase IQ Battery 10C"
    assert _number_input(app, "Number of batteries").value == 2
    assert _number_input(app, "Battery usable capacity (kWh)").value == 20.0


def test_custom_battery_values_survive_switching_to_a_preset_and_back():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    app.radio[0].set_value("System model").run()
    custom_values = {
        "Battery usable capacity (kWh)": 18.0,
        "Round-trip efficiency (%)": 86.0,
        "Maximum charge power (kW)": 4.5,
        "Maximum discharge power (kW)": 8.5,
    }
    for label, value in custom_values.items():
        _number_input(app, label).set_value(value).run()

    _radio(app, "Battery settings").set_value("Battery preset").run()
    _selectbox(app, "Battery model").set_value("Enphase IQ Battery 10C").run()
    _number_input(app, "Number of batteries").set_value(2).run()
    assert not _number_input(app, "Starting charge (%)").disabled
    assert not _number_input(app, "Minimum reserve (%)").disabled

    _radio(app, "Battery settings").set_value("Custom values").run()

    for label, expected in custom_values.items():
        widget = _number_input(app, label)
        assert widget.value == expected
        assert not widget.disabled


def test_smud_prices_are_preloaded_in_the_time_of_use_editor():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    app.radio[0].set_value("System model").run()
    rules = app.session_state["model.tou_rules"]

    assert list(rules.columns) == [
        "Name",
        "Start date",
        "End date",
        "Weekdays",
        "Start time",
        "End time",
        "Price ($/kWh)",
    ]
    assert len(rules) == 9
    assert sorted({float(value) for value in rules["Price ($/kWh)"]}) == [
        0.1285,
        0.155,
        0.1776,
        0.2139,
        0.3765,
    ]


def test_each_view_has_a_persisted_export_purchase_rate_default():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    history_rate = _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    )
    assert history_rate.value == pytest.approx(0.0563)
    history_rate.set_value(0.07).run()

    app.radio[0].set_value("System model").run()
    model_rate = _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    )
    assert model_rate.value == pytest.approx(0.096)
    model_rate.set_value(0.11).run()

    app.radio[0].set_value("Historical view").run()
    assert _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).value == pytest.approx(0.07)

    app.radio[0].set_value("System model").run()
    assert _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).value == pytest.approx(0.11)


def test_historical_projected_cost_uses_the_configured_export_purchase_rate():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    initial_cost = _currency_value(_metric(app, "Projected cost").value)
    exported_kwh = _energy_value(_metric(app, "Grid exported").value)
    _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.1563).run()
    updated_cost = _currency_value(_metric(app, "Projected cost").value)

    assert initial_cost - updated_cost == pytest.approx(
        exported_kwh * 0.10, abs=0.02
    )


def test_system_model_projected_cost_uses_the_configured_export_purchase_rate():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    app.radio[0].set_value("System model").run()
    _number_input(app, "Solar scale").set_value(100.0).run()
    initial_cost = _currency_value(_metric(app, "Projected cost").value)
    exported_kwh = _energy_value(_metric(app, "Grid export").value)
    _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.196).run()
    updated_cost = _currency_value(_metric(app, "Projected cost").value)

    assert initial_cost - updated_cost == pytest.approx(
        exported_kwh * 0.10, abs=0.02
    )

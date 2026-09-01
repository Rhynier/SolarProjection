from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def _number_input(app: AppTest, label: str):
    return next(widget for widget in app.number_input if widget.label == label)


def _radio(app: AppTest, label: str):
    return next(widget for widget in app.radio if widget.label == label)


def _selectbox(app: AppTest, label: str):
    return next(widget for widget in app.selectbox if widget.label == label)


def test_app_starts_against_supplied_csvs_without_exceptions():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Home Energy Model"
    assert app.radio[0].options == ["Historical view", "System model"]
    app.radio[0].set_value("System model").run()
    assert not app.exception


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

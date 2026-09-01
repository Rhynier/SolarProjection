from pathlib import Path

from streamlit.testing.v1 import AppTest


def _number_input(app: AppTest, label: str):
    return next(widget for widget in app.number_input if widget.label == label)


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

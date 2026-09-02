import base64
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.io as pio
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest


def _number_input(app: AppTest, label: str):
    return next(widget for widget in app.number_input if widget.label == label)


def _date_input(app: AppTest, label: str):
    matches = [widget for widget in app.date_input if widget.label == label]
    assert matches, f"No date input labeled {label!r}"
    return matches[0]


def _radio(app: AppTest, label: str):
    return next(widget for widget in app.radio if widget.label == label)


def _selectbox(app: AppTest, label: str):
    return next(widget for widget in app.selectbox if widget.label == label)


def _segmented_control(app: AppTest, label: str):
    matches = [widget for widget in app.segmented_control if widget.label == label]
    assert matches, f"No segmented control labeled {label!r}"
    return matches[0]


def _button(app: AppTest, label: str):
    return next(widget for widget in app.button if widget.label == label)


def _metric(app: AppTest, label: str):
    return next(metric for metric in app.metric if metric.label == label)


def _currency_value(value: str) -> float:
    normalized = value.replace(",", "")
    if normalized.startswith("-$"):
        return -float(normalized[2:])
    return float(normalized.removeprefix("$"))


def _energy_value(value: str) -> float:
    return float(value.removesuffix(" kWh").replace(",", ""))


def _plotly_values(trace) -> np.ndarray:
    encoded_values = trace.to_plotly_json()["y"]
    if isinstance(encoded_values, dict):
        return np.frombuffer(
            base64.b64decode(encoded_values["bdata"]),
            dtype=encoded_values["dtype"],
        )
    return np.asarray(encoded_values, dtype=float)


def _edit_data_editor_rows(
    app: AppTest,
    edited_rows: dict[int, dict[str, object]],
) -> AppTest:
    editor = app.get("dataframe")[0]
    widget_states = app._tree.get_widget_states()
    widget_states.widgets.append(
        WidgetState(
            id=editor.proto.id,
            string_value=json.dumps(
                {
                    "edited_rows": {
                        str(row): values for row, values in edited_rows.items()
                    },
                    "added_rows": [],
                    "deleted_rows": [],
                }
            ),
        )
    )
    return app._tree._runner._run(widget_states, timeout=30)


def _edit_data_editor(app: AppTest, row: int, column: str, value: object) -> AppTest:
    return _edit_data_editor_rows(app, {row: {column: value}})


def test_app_starts_against_supplied_csvs_without_exceptions():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Home Energy Model"
    assert app.radio[0].options == [
        "Historical view",
        "System model",
        "Configuration",
    ]
    app.radio[0].set_value("System model").run()
    assert not app.exception


def test_date_range_and_aggregation_are_shared_between_views():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _segmented_control(app, "Period").set_value("Custom").run()
    date_range = _date_input(app, "Date range")
    start = date_range.value[0] + timedelta(days=10)
    selected_range = (start, start + timedelta(days=9))
    date_range.set_value(selected_range).run()
    _selectbox(app, "Aggregation").set_value("Day").run()

    app.radio[0].set_value("System model").run()

    assert _segmented_control(app, "Period").value == "Custom"
    assert _date_input(app, "Date range").value == selected_range
    assert _selectbox(app, "Aggregation").value == "Day"
    assert "Duration (days)" not in [widget.label for widget in app.number_input]
    assert not app.error

    updated_range = (start + timedelta(days=1), start + timedelta(days=4))
    _date_input(app, "Date range").set_value(updated_range).run()
    _selectbox(app, "Aggregation").set_value("Hour").run()
    app.radio[0].set_value("Historical view").run()

    assert _date_input(app, "Date range").value == updated_range
    assert _selectbox(app, "Aggregation").value == "Hour"


def test_period_selector_defaults_to_the_first_available_month():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    period = _segmented_control(app, "Period")

    assert period.options == ["Custom", "Week", "Month", "All"]
    assert period.value == "Custom"
    assert app.session_state["shared.date_range"] == (
        date(2025, 8, 17),
        date(2025, 9, 16),
    )
    assert _date_input(app, "Date range").value == (
        date(2025, 8, 17),
        date(2025, 9, 16),
    )


def test_week_period_uses_start_date_and_seven_day_range():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _segmented_control(app, "Period").set_value("Week").run()

    assert _date_input(app, "Start date").value == date(2025, 8, 17)
    assert app.session_state["shared.date_range"] == (
        date(2025, 8, 17),
        date(2025, 8, 23),
    )
    assert any("Aug 17–23, 2025" in caption.value for caption in app.caption)


def test_week_navigation_shifts_start_by_seven_days():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _segmented_control(app, "Period").set_value("Week").run()
    _button(app, "Next week").click().run()

    assert _date_input(app, "Start date").value == date(2025, 8, 24)
    assert app.session_state["shared.date_range"] == (
        date(2025, 8, 24),
        date(2025, 8, 30),
    )


def test_week_ending_on_last_available_date_is_not_labeled_as_clipped():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _date_input(app, "Date range").set_value(
        (date(2026, 8, 11), date(2026, 8, 12))
    ).run()
    _segmented_control(app, "Period").set_value("Week").run()

    selected_range = next(
        caption.value
        for caption in app.caption
        if caption.value.startswith("Selected range:")
    )
    assert "Aug 11–17, 2026" in selected_range
    assert "clipped" not in selected_range


def test_month_period_ends_day_before_same_date_next_month():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _date_input(app, "Date range").set_value(
        (date(2025, 9, 17), date(2025, 9, 30))
    ).run()
    _segmented_control(app, "Period").set_value("Month").run()

    assert _date_input(app, "Start date").value == date(2025, 9, 17)
    assert app.session_state["shared.date_range"] == (
        date(2025, 9, 17),
        date(2025, 10, 16),
    )
    assert any("Sep 17–Oct 16, 2025" in caption.value for caption in app.caption)


def test_month_period_maps_first_to_last_day():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _date_input(app, "Date range").set_value(
        (date(2025, 10, 1), date(2025, 10, 5))
    ).run()
    _segmented_control(app, "Period").set_value("Month").run()

    assert _date_input(app, "Start date").value == date(2025, 10, 1)
    assert app.session_state["shared.date_range"] == (
        date(2025, 10, 1),
        date(2025, 10, 31),
    )


def test_month_navigation_shifts_start_by_one_month():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _segmented_control(app, "Period").set_value("Month").run()
    _button(app, "Next month").click().run()

    assert _date_input(app, "Start date").value == date(2025, 9, 17)
    assert app.session_state["shared.date_range"] == (
        date(2025, 9, 17),
        date(2025, 10, 16),
    )


def test_custom_period_preserves_the_derived_week_range():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _segmented_control(app, "Period").set_value("Week").run()
    _date_input(app, "Start date").set_value(date(2025, 9, 10)).run()
    _segmented_control(app, "Period").set_value("Custom").run()

    assert _date_input(app, "Date range").value == (
        date(2025, 9, 10),
        date(2025, 9, 16),
    )


def test_period_mode_and_derived_range_are_shared_between_views():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    _date_input(app, "Date range").set_value(
        (date(2025, 9, 17), date(2025, 9, 30))
    ).run()
    _segmented_control(app, "Period").set_value("Month").run()
    app.radio[0].set_value("System model").run()

    assert _segmented_control(app, "Period").value == "Month"
    assert _date_input(app, "Start date").value == date(2025, 9, 17)
    assert app.session_state["shared.date_range"] == (
        date(2025, 9, 17),
        date(2025, 10, 16),
    )


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


def test_system_model_derives_solar_scale_from_annual_production():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()

    reference = _number_input(app, "Reference annual production (kWh)")
    proposed = _number_input(app, "Proposed annual production (kWh)")
    assert reference.value == pytest.approx(2017.56)
    assert proposed.value == pytest.approx(2017.56)

    initial_figure = pio.from_json(app.get("plotly_chart")[0].proto.spec)
    initial_production = next(
        trace for trace in initial_figure.data if trace.name == "Production"
    )

    reference.set_value(1000.0).run()
    _number_input(app, "Proposed annual production (kWh)").set_value(2000.0).run()

    updated_figure = pio.from_json(app.get("plotly_chart")[0].proto.spec)
    updated_production = next(
        trace for trace in updated_figure.data if trace.name == "Production"
    )
    assert _plotly_values(updated_production).sum() == pytest.approx(
        2 * _plotly_values(initial_production).sum()
    )
    assert any(
        caption.value == "Production scale: 2.000×" for caption in app.caption
    )

    app.radio[0].set_value("Historical view").run()
    app.radio[0].set_value("System model").run()

    assert _number_input(app, "Reference annual production (kWh)").value == 1000.0
    assert _number_input(app, "Proposed annual production (kWh)").value == 2000.0
    assert any(
        caption.value == "Production scale: 2.000×" for caption in app.caption
    )


def test_monthly_scaling_initializes_from_retained_annual_values():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()
    _number_input(app, "Reference annual production (kWh)").set_value(1200.0).run()
    _number_input(app, "Proposed annual production (kWh)").set_value(2400.0).run()

    scaling_mode = _radio(app, "Production scaling")
    assert scaling_mode.value == "Annual"
    scaling_mode.set_value("Monthly").run()

    monthly = app.session_state["model.monthly_production"]
    assert list(monthly["Month"]) == [
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
    ]
    assert list(monthly["Reference production (kWh)"]) == pytest.approx(
        [100.0] * 12
    )
    assert list(monthly["Proposed production (kWh)"]) == pytest.approx(
        [200.0] * 12
    )
    assert _number_input(app, "Reference annual production (kWh)").value == 1200.0
    assert _number_input(app, "Reference annual production (kWh)").disabled
    assert _number_input(app, "Proposed annual production (kWh)").value == 2400.0
    assert _number_input(app, "Proposed annual production (kWh)").disabled
    assert any(
        caption.value == "Monthly production scales are applied by calendar month."
        for caption in app.caption
    )
    assert not any(
        caption.value.startswith("Production scale:") for caption in app.caption
    )


def test_monthly_initialization_uses_displayed_precision_without_hidden_values():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()
    _number_input(app, "Reference annual production (kWh)").set_value(1000.0).run()
    _number_input(app, "Proposed annual production (kWh)").set_value(1000.0).run()

    _radio(app, "Production scaling").set_value("Monthly").run()

    monthly = app.session_state["model.monthly_production"]
    expected = [83.3334] * 4 + [83.3333] * 8
    assert list(monthly["Reference production (kWh)"]) == pytest.approx(expected)
    assert list(monthly["Proposed production (kWh)"]) == pytest.approx(expected)
    assert _number_input(
        app, "Reference annual production (kWh)"
    ).value == pytest.approx(1000.0)
    assert _number_input(
        app, "Proposed annual production (kWh)"
    ).value == pytest.approx(1000.0)


def test_monthly_initialization_supports_the_smallest_annual_reference():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()
    _number_input(app, "Reference annual production (kWh)").set_value(0.01).run()
    _number_input(app, "Proposed annual production (kWh)").set_value(0.0).run()

    _radio(app, "Production scaling").set_value("Monthly").run()

    monthly = app.session_state["model.monthly_production"]
    assert not app.error
    assert all(value > 0 for value in monthly["Reference production (kWh)"])
    assert monthly["Reference production (kWh)"].sum() == pytest.approx(0.01)
    assert _number_input(
        app, "Reference annual production (kWh)"
    ).value == pytest.approx(0.01)


def test_annual_scaling_values_survive_a_monthly_round_trip():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()
    _number_input(app, "Reference annual production (kWh)").set_value(1200.0).run()
    _number_input(app, "Proposed annual production (kWh)").set_value(2400.0).run()
    _radio(app, "Production scaling").set_value("Monthly").run()

    app = _edit_data_editor(app, 0, "Proposed production (kWh)", 300.0)
    assert _number_input(app, "Proposed annual production (kWh)").value == 2500.0

    _radio(app, "Production scaling").set_value("Annual").run()
    assert _number_input(app, "Reference annual production (kWh)").value == 1200.0
    assert not _number_input(app, "Reference annual production (kWh)").disabled
    assert _number_input(app, "Proposed annual production (kWh)").value == 2400.0
    assert not _number_input(app, "Proposed annual production (kWh)").disabled

    _radio(app, "Production scaling").set_value("Monthly").run()
    assert _number_input(app, "Proposed annual production (kWh)").value == 2500.0
    assert _number_input(app, "Proposed annual production (kWh)").disabled


def test_monthly_scaling_editor_applies_the_selected_month_factor():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    _date_input(app, "Date range").set_value(
        (date(2026, 1, 1), date(2026, 1, 1))
    ).run()
    app.radio[0].set_value("System model").run()
    initial_figure = pio.from_json(app.get("plotly_chart")[0].proto.spec)
    initial_production = next(
        trace for trace in initial_figure.data if trace.name == "Production"
    )

    _radio(app, "Production scaling").set_value("Monthly").run()
    app = _edit_data_editor(app, 0, "Proposed production (kWh)", 336.26)

    updated_figure = pio.from_json(app.get("plotly_chart")[0].proto.spec)
    updated_production = next(
        trace for trace in updated_figure.data if trace.name == "Production"
    )
    assert _plotly_values(updated_production).sum() == pytest.approx(
        2 * _plotly_values(initial_production).sum()
    )


@pytest.mark.parametrize(
    ("column", "message"),
    [
        (
            "Reference production (kWh)",
            "January reference production must be a finite number greater than zero",
        ),
        (
            "Proposed production (kWh)",
            "January proposed production must be a finite nonnegative number",
        ),
    ],
)
def test_monthly_scaling_rejects_blank_cells_with_a_month_specific_error(
    column,
    message,
):
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()
    _radio(app, "Production scaling").set_value("Monthly").run()

    app = _edit_data_editor(app, 0, column, None)

    assert not app.exception
    assert any(message in error.value for error in app.error)


def test_monthly_scaling_all_blank_references_do_not_crash():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()
    _radio(app, "Production scaling").set_value("Monthly").run()

    app = _edit_data_editor_rows(
        app,
        {
            row: {"Reference production (kWh)": None}
            for row in range(12)
        },
    )

    assert not app.exception
    assert any(
        "January reference production must be a finite number greater than zero"
        in error.value
        for error in app.error
    )


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

    app.radio[0].set_value("Configuration").run()
    rules = app.session_state["shared.tou_rules"]

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


def test_time_of_use_editor_is_only_shown_on_the_configuration_page():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()

    assert "Time-of-use rules" not in [item.value for item in app.subheader]
    app.radio[0].set_value("System model").run()
    assert "Time-of-use rules" not in [item.value for item in app.subheader]

    app.radio[0].set_value("Configuration").run()

    assert "Time-of-use rules" in [item.value for item in app.subheader]
    assert not app.exception


def test_time_of_use_editor_edits_persist_across_analytical_views():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("Configuration").run()

    app = _edit_data_editor(app, 0, "Price ($/kWh)", 0.20)

    assert not app.exception
    assert app.session_state["shared.tou_rules"].iloc[0]["Price ($/kWh)"] == 0.20
    app.radio[0].set_value("Historical view").run()
    assert not app.exception
    app.radio[0].set_value("System model").run()
    assert not app.exception


def test_historical_cost_uses_the_shared_time_of_use_configuration():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.session_state["shared.tou_rules"] = pd.DataFrame(
        [
            {
                "Name": "Free energy",
                "Start date": "01-01",
                "End date": "12-31",
                "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                "Start time": "00:00",
                "End time": "00:00",
                "Price ($/kWh)": 0.0,
            }
        ]
    )
    app.run()
    _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.0).run()

    assert _metric(app, "Projected cost").value == "$0.00"


def test_invalid_tou_rules_leave_historical_energy_results_available():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.session_state["shared.tou_rules"] = pd.DataFrame(
        [
            {
                "Name": "Invalid rule",
                "Start date": "not-a-date",
                "End date": "12-31",
                "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                "Start time": "00:00",
                "End time": "00:00",
                "Price ($/kWh)": 0.20,
            }
        ]
    )

    app.run()

    assert app.error
    assert _metric(app, "Household use").value.endswith(" kWh")
    assert _metric(app, "Projected cost").value == "Unavailable"
    assert len(app.get("plotly_chart")) == 1


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
    _number_input(app, "Proposed annual production (kWh)").set_value(201756.0).run()
    initial_cost = _currency_value(_metric(app, "Projected cost").value)
    exported_kwh = _energy_value(_metric(app, "Grid export").value)
    _number_input(
        app, "Utility purchase rate for exported energy ($/kWh)"
    ).set_value(0.196).run()
    updated_cost = _currency_value(_metric(app, "Projected cost").value)

    assert initial_cost - updated_cost == pytest.approx(
        exported_kwh * 0.10, abs=0.02
    )


def test_system_model_net_cost_bars_sum_to_the_projected_cost():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    app.radio[0].set_value("System model").run()

    figure = pio.from_json(app.get("plotly_chart")[0].proto.spec)
    net_cost_trace = next(trace for trace in figure.data if trace.name == "Net cost")
    encoded_values = net_cost_trace.to_plotly_json()["y"]
    net_cost_values = np.frombuffer(
        base64.b64decode(encoded_values["bdata"]), dtype=encoded_values["dtype"]
    )

    assert net_cost_values.sum() == pytest.approx(
        _currency_value(_metric(app, "Projected cost").value), abs=0.01
    )

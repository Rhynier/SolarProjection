import pandas as pd

from solar_model.charts import SERIES_COLORS, build_history_figure, build_model_figure


APPROVED_SERIES_COLORS = {
    "Used": "#2563EB",
    "Production": "#F59E0B",
    "Battery": "#7C3AED",
    "Grid import": "#DC2626",
    "Grid export": "#059669",
}


def test_history_figure_has_requested_grouped_bars_and_colors():
    data = pd.DataFrame({
        "bucket_start": [pd.Timestamp("2026-01-01")],
        "household_load_kwh": [10.0],
        "actual_solar_kwh": [4.0],
        "grid_export_kwh": [1.0],
    })
    original_data = data.copy(deep=True)
    figure = build_history_figure(data, ["Used", "Production", "Grid export"])
    assert SERIES_COLORS == APPROVED_SERIES_COLORS
    assert [trace.name for trace in figure.data] == ["Used", "Production", "Grid export"]
    assert all(trace.type == "bar" for trace in figure.data)
    assert [trace.marker.color for trace in figure.data] == [
        APPROVED_SERIES_COLORS["Used"],
        APPROVED_SERIES_COLORS["Production"],
        APPROVED_SERIES_COLORS["Grid export"],
    ]
    assert [list(trace.y) for trace in figure.data] == [[10.0], [4.0], [1.0]]
    assert figure.layout.barmode == "group"
    pd.testing.assert_frame_equal(data, original_data)


def test_model_figure_has_battery_axis_and_signed_grid_panel():
    result = pd.DataFrame({
        "timestamp": pd.date_range("2026-07-01", periods=2, freq="h"),
        "household_load_kwh": [2.0, 3.0],
        "modeled_solar_kwh": [4.0, 1.0],
        "battery_soc_kwh": [5.0, 3.0],
        "battery_charge_input_kwh": [2.0, 0.0],
        "battery_discharge_output_kwh": [0.0, 2.0],
        "grid_import_kwh": [0.0, 0.5],
        "grid_export_kwh": [1.5, 0.0],
        "is_expensive": [False, True],
    })
    original_result = result.copy(deep=True)
    figure = build_model_figure(result)
    assert [trace.name for trace in figure.data] == [
        "Used", "Production", "Battery", "Grid import", "Grid export"
    ]
    assert [trace.type for trace in figure.data] == ["bar", "bar", "scatter", "bar", "bar"]
    assert figure.data[0].marker.color == APPROVED_SERIES_COLORS["Used"]
    assert figure.data[1].marker.color == APPROVED_SERIES_COLORS["Production"]
    assert figure.data[2].line.color == APPROVED_SERIES_COLORS["Battery"]
    assert figure.data[3].marker.color == APPROVED_SERIES_COLORS["Grid import"]
    assert figure.data[4].marker.color == APPROVED_SERIES_COLORS["Grid export"]
    assert list(figure.data[3].y) == [0.0, 0.5]
    assert list(figure.data[4].y) == [-1.5, -0.0]
    assert figure.data[2].yaxis == "y2"
    assert figure.data[3].yaxis == "y3"
    assert figure.layout.yaxis.title.text == "Hourly energy (kWh)"
    assert figure.layout.yaxis2.title.text == "Battery level (kWh)"
    assert figure.layout.yaxis3.title.text == "Grid exchange (kWh)"
    assert figure.layout.showlegend is True
    assert figure.layout.legend.itemclick != "none"
    assert list(result["grid_export_kwh"]) == [1.5, 0.0]
    pd.testing.assert_frame_equal(result, original_result)

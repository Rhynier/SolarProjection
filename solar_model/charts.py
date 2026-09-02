import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


SERIES_COLORS = {
    "Used": "#2563EB",
    "Production": "#F59E0B",
    "Battery": "#7C3AED",
    "Grid import": "#DC2626",
    "Grid export": "#059669",
}

_HISTORY_COLUMNS = {
    "Used": "household_load_kwh",
    "Production": "actual_solar_kwh",
    "Grid export": "grid_export_kwh",
}


def _transparent_layout(figure: go.Figure) -> None:
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h"},
        showlegend=True,
    )


def build_history_figure(
    aggregated: pd.DataFrame, visible_series: list[str]
) -> go.Figure:
    if not visible_series:
        raise ValueError("at least one history series must be visible")

    unknown = set(visible_series) - _HISTORY_COLUMNS.keys()
    if unknown:
        raise ValueError(f"unknown history series: {', '.join(sorted(unknown))}")

    figure = go.Figure()
    for series_name in visible_series:
        figure.add_bar(
            name=series_name,
            x=aggregated["bucket_start"],
            y=aggregated[_HISTORY_COLUMNS[series_name]],
            marker_color=SERIES_COLORS[series_name],
        )
    figure.update_layout(
        barmode="group",
        xaxis_title="Time",
        yaxis_title="Energy (kWh)",
    )
    _transparent_layout(figure)
    return figure


def build_model_figure(result: pd.DataFrame) -> go.Figure:
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.72, 0.28],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    timestamps = result["bucket_start"]
    figure.add_bar(
        name="Used",
        x=timestamps,
        y=result["household_load_kwh"],
        marker_color=SERIES_COLORS["Used"],
        row=1,
        col=1,
    )
    figure.add_bar(
        name="Production",
        x=timestamps,
        y=result["modeled_solar_kwh"],
        marker_color=SERIES_COLORS["Production"],
        row=1,
        col=1,
    )
    figure.add_scatter(
        name="Battery",
        x=timestamps,
        y=result["battery_soc_kwh"],
        mode="lines",
        line={"color": SERIES_COLORS["Battery"]},
        row=1,
        col=1,
        secondary_y=True,
    )
    figure.add_bar(
        name="Grid import",
        x=timestamps,
        y=result["grid_import_kwh"],
        marker_color=SERIES_COLORS["Grid import"],
        row=2,
        col=1,
    )
    figure.add_bar(
        name="Grid export",
        x=timestamps,
        y=-result["grid_export_kwh"],
        marker_color=SERIES_COLORS["Grid export"],
        row=2,
        col=1,
    )
    figure.update_yaxes(title_text="Energy (kWh)", row=1, col=1)
    figure.update_yaxes(
        title_text="Battery level (kWh)", row=1, col=1, secondary_y=True
    )
    figure.update_yaxes(title_text="Grid exchange (kWh)", row=2, col=1)
    figure.update_xaxes(title_text="Time", row=2, col=1)
    figure.add_hline(y=0, row=2, col=1, line_color="#475569")
    _transparent_layout(figure)
    return figure

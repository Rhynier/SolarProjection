from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from solar_model.aggregation import aggregate_history
from solar_model.charts import build_history_figure, build_model_figure
from solar_model.data import DataValidationError, load_hourly_energy
from solar_model.simulation import (
    BatteryConfig,
    SimulationConfig,
    SimulationValidationError,
    simulate,
)
from solar_model.tou import TouValidationError, parse_tou_rules


ROOT = Path(__file__).parent
UTILITY_PATH = ROOT / "combined-electric-usage.csv"
SOLAR_PATH = ROOT / "combined-monthly-energy.csv"
BASE_SOLAR_KW = 1.29
HISTORY_SERIES = ["Used", "Production", "Grid export"]
TOU_COLUMNS = [
    "Name",
    "Start date",
    "End date",
    "Weekdays",
    "Start time",
    "End time",
    "Classification",
]
MODEL_STATE_PREFIX = "model."
MODEL_WIDGET_PREFIX = "_model."


@st.cache_data(show_spinner="Loading energy history…")
def load_data() -> pd.DataFrame:
    return load_hourly_energy(UTILITY_PATH, SOLAR_PATH)


def _date_bounds(hourly: pd.DataFrame) -> tuple[date, date]:
    return hourly["timestamp"].min().date(), hourly["timestamp"].max().date()


def _filtered_hourly(
    hourly: pd.DataFrame, start_date: date, end_date: date
) -> pd.DataFrame:
    dates = hourly["timestamp"].dt.date
    return hourly.loc[(dates >= start_date) & (dates <= end_date)].copy()


def render_history(hourly: pd.DataFrame) -> None:
    min_date, max_date = _date_bounds(hourly)
    selected_dates = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    bucket_label = st.sidebar.selectbox(
        "Aggregation", ["Auto", "Hour", "Day", "Week", "Month"]
    )
    visible_series = st.sidebar.multiselect(
        "Series", HISTORY_SERIES, default=HISTORY_SERIES
    )

    if not isinstance(selected_dates, tuple) or len(selected_dates) != 2:
        st.error("Choose both a start and end date.")
        return
    start_date, end_date = selected_dates
    if not visible_series:
        st.error("Choose at least one series.")
        return

    try:
        aggregated, resolved_bucket = aggregate_history(
            hourly, start_date, end_date, bucket_label.lower()
        )
    except ValueError as error:
        st.error(f"History selection is invalid: {error}")
        return

    selected = _filtered_hourly(hourly, start_date, end_date)
    use, production, export = st.columns(3)
    use.metric("Household use", f"{selected['household_load_kwh'].sum():.2f} kWh")
    production.metric("Solar produced", f"{selected['actual_solar_kwh'].sum():.2f} kWh")
    export.metric("Grid exported", f"{selected['grid_export_kwh'].sum():.2f} kWh")
    st.caption(f"Showing {resolved_bucket} energy totals.")
    st.plotly_chart(
        build_history_figure(aggregated, visible_series), use_container_width=True
    )


def _nonblank_tou_rows(edited_rules: pd.DataFrame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in edited_rules.to_dict("records"):
        normalized = {
            column: "" if pd.isna(row[column]) else str(row[column]).strip()
            for column in TOU_COLUMNS
        }
        if any(normalized.values()):
            rows.append(normalized)
    return rows


def _model_state_key(name: str) -> str:
    return f"{MODEL_STATE_PREFIX}{name}"


def _model_widget_key(name: str) -> str:
    return f"{MODEL_WIDGET_PREFIX}{name}"


def _model_value(name: str, default: object) -> object:
    state_key = _model_state_key(name)
    if state_key not in st.session_state:
        st.session_state[state_key] = default
    return st.session_state[state_key]


def _store_model_value(name: str) -> None:
    st.session_state[_model_state_key(name)] = st.session_state[
        _model_widget_key(name)
    ]


def render_model(hourly: pd.DataFrame) -> None:
    min_date, max_date = _date_bounds(hourly)
    default_start = max_date - timedelta(days=6)
    start_date = st.sidebar.date_input(
        "Start date",
        value=_model_value("start_date", default_start),
        min_value=min_date,
        max_value=max_date,
        key=_model_widget_key("start_date"),
        on_change=_store_model_value,
        args=("start_date",),
    )
    duration = st.sidebar.number_input(
        "Duration (days)",
        min_value=1,
        max_value=7,
        value=_model_value("duration", 7),
        step=1,
        key=_model_widget_key("duration"),
        on_change=_store_model_value,
        args=("duration",),
    )
    solar_scale = st.sidebar.number_input(
        "Solar scale",
        min_value=0.0,
        value=_model_value("solar_scale", 1.0),
        step=0.1,
        key=_model_widget_key("solar_scale"),
        on_change=_store_model_value,
        args=("solar_scale",),
    )
    st.sidebar.caption(f"Equivalent array: {BASE_SOLAR_KW * solar_scale:.2f} kW")
    strategy_label = st.sidebar.selectbox(
        "Battery strategy",
        ["Self-consumption", "TOU reserve"],
        index=["Self-consumption", "TOU reserve"].index(
            _model_value("strategy", "Self-consumption")
        ),
        key=_model_widget_key("strategy"),
        on_change=_store_model_value,
        args=("strategy",),
    )
    capacity = st.sidebar.number_input(
        "Battery usable capacity (kWh)",
        min_value=0.0,
        value=_model_value("capacity", 13.5),
        step=0.5,
        key=_model_widget_key("capacity"),
        on_change=_store_model_value,
        args=("capacity",),
    )
    with st.sidebar.expander("Advanced battery settings"):
        starting_percent = st.number_input(
            "Starting charge (%)",
            min_value=0.0,
            max_value=100.0,
            value=_model_value("starting_percent", 50.0),
            step=1.0,
            key=_model_widget_key("starting_percent"),
            on_change=_store_model_value,
            args=("starting_percent",),
        )
        reserve_percent = st.number_input(
            "Minimum reserve (%)",
            min_value=0.0,
            max_value=100.0,
            value=_model_value("reserve_percent", 10.0),
            step=1.0,
            key=_model_widget_key("reserve_percent"),
            on_change=_store_model_value,
            args=("reserve_percent",),
        )
        round_trip_percent = st.number_input(
            "Round-trip efficiency (%)",
            min_value=0.1,
            max_value=100.0,
            value=_model_value("round_trip_percent", 90.0),
            step=1.0,
            key=_model_widget_key("round_trip_percent"),
            on_change=_store_model_value,
            args=("round_trip_percent",),
        )
        max_charge_kw = st.number_input(
            "Maximum charge power (kW)",
            min_value=0.0,
            value=_model_value("max_charge_kw", 5.0),
            step=0.5,
            key=_model_widget_key("max_charge_kw"),
            on_change=_store_model_value,
            args=("max_charge_kw",),
        )
        max_discharge_kw = st.number_input(
            "Maximum discharge power (kW)",
            min_value=0.0,
            value=_model_value("max_discharge_kw", 5.0),
            step=0.5,
            key=_model_widget_key("max_discharge_kw"),
            on_change=_store_model_value,
            args=("max_discharge_kw",),
        )

    chart_slot = st.empty()
    st.subheader("Time-of-use rules")
    st.caption("Add your current schedule. Dates use MM-DD; weekdays use Mon,Tue,…")
    edited_rules = st.data_editor(
        _model_value("tou_rules", pd.DataFrame(columns=TOU_COLUMNS)),
        num_rows="dynamic",
        use_container_width=True,
        key=_model_widget_key("tou_rules"),
    )
    st.session_state[_model_state_key("tou_rules")] = edited_rules
    try:
        rules = parse_tou_rules(_nonblank_tou_rows(edited_rules))
    except TouValidationError as error:
        st.error(f"TOU rule is invalid: {error}")
        chart_slot.info("Add a valid time-of-use rule to model this period.")
        return

    end_date = start_date + timedelta(days=int(duration) - 1)
    if end_date > max_date:
        chart_slot.error("Selected period ends after the available energy data.")
        return
    selected = _filtered_hourly(hourly, start_date, end_date)
    if selected.empty:
        chart_slot.error("Selected period contains no energy data.")
        return

    battery = BatteryConfig(
        capacity_kwh=capacity,
        starting_percent=starting_percent,
        reserve_percent=reserve_percent,
        round_trip_efficiency=round_trip_percent / 100.0,
        max_charge_kw=max_charge_kw,
        max_discharge_kw=max_discharge_kw,
    )
    config = SimulationConfig(
        solar_scale=solar_scale,
        battery=battery,
        strategy="self_consumption" if strategy_label == "Self-consumption" else "tou_reserve",
    )
    try:
        result = simulate(selected, config, rules)
    except SimulationValidationError as error:
        chart_slot.error(f"Model settings are invalid: {error}")
        return

    with chart_slot.container():
        imported, expensive, exported = st.columns(3)
        imported.metric("Grid import", f"{result['grid_import_kwh'].sum():.2f} kWh")
        expensive.metric(
            "Expensive import",
            f"{result.loc[result['is_expensive'], 'grid_import_kwh'].sum():.2f} kWh",
        )
        exported.metric("Grid export", f"{result['grid_export_kwh'].sum():.2f} kWh")
        st.plotly_chart(build_model_figure(result), use_container_width=True)


st.set_page_config(page_title="Home Energy Model", page_icon="☀️", layout="wide")
st.title("Home Energy Model")

try:
    hourly = load_data()
except (OSError, DataValidationError) as error:
    st.error(f"Energy data could not be loaded: {error}")
    st.stop()

page = st.radio(
    "View",
    ["Historical view", "System model"],
    horizontal=True,
    label_visibility="collapsed",
)
if page == "Historical view":
    render_history(hourly)
else:
    render_model(hourly)

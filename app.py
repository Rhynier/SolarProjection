from copy import deepcopy
from datetime import date
from math import isfinite
from pathlib import Path

import pandas as pd
import streamlit as st

from solar_model.aggregation import aggregate_history, aggregate_model_result
from solar_model.charts import build_history_figure, build_model_figure
from solar_model.costs import (
    CostValidationError,
    format_currency,
    hourly_net_costs,
    projected_utility_cost,
)
from solar_model.configuration import (
    ConfigurationError,
    ConfigurationValidationError,
    configuration_path,
    load_configuration,
    save_configuration,
    validate_configuration,
)
from solar_model.data import DataValidationError, load_hourly_energy
from solar_model.periods import (
    format_date_range,
    period_end,
    period_range,
    shift_period_start,
)
from solar_model.simulation import (
    BatteryConfig,
    SimulationConfig,
    SimulationValidationError,
    simulate,
)
from solar_model.tou import (
    SMUD_DEFAULT_TOU_ROWS,
    TouRule,
    TouValidationError,
    parse_tou_rules,
)


ROOT = Path(__file__).parent
UTILITY_PATH = ROOT / "combined-electric-usage.csv"
SOLAR_PATH = ROOT / "combined-monthly-energy.csv"
HISTORY_SERIES = ["Used", "Production", "Grid export"]
TOU_COLUMNS = [
    "Name",
    "Start date",
    "End date",
    "Weekdays",
    "Start time",
    "End time",
    "Price ($/kWh)",
]
MODEL_STATE_PREFIX = "model."
MODEL_WIDGET_PREFIX = "_model."
SHARED_STATE_PREFIX = "shared."
SHARED_WIDGET_PREFIX = "_shared."
AGGREGATION_OPTIONS = ["Auto", "Hour", "Day", "Week", "Month"]
PERIOD_OPTIONS = ["Custom", "Week", "Month", "All"]
MONTH_NAMES = [
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
MONTHLY_REFERENCE_COLUMN = "Reference production (kWh)"
MONTHLY_PROPOSED_COLUMN = "Proposed production (kWh)"
BATTERY_PRESETS = {
    "Tesla Powerwall 3": {
        "capacity_kwh": 13.5,
        "round_trip_percent": 89.0,
        "max_charge_kw": 5.0,
        "max_discharge_kw": 11.5,
    },
    "Enphase IQ Battery 10C": {
        "capacity_kwh": 10.0,
        "round_trip_percent": 90.0,
        "max_charge_kw": 7.08,
        "max_discharge_kw": 7.08,
    },
}
CONFIG_DOCUMENT_KEY = "_configuration.document"
CONFIG_PATH_KEY = "_configuration.path"
CONFIG_AUTOSAVE_KEY = "_configuration.autosave_enabled"
CONFIG_WARNING_KEY = "_configuration.warning"
CONFIG_ERROR_KEY = "_configuration.error"


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


def _shared_state_key(name: str) -> str:
    return f"{SHARED_STATE_PREFIX}{name}"


def _shared_widget_key(name: str) -> str:
    return f"{SHARED_WIDGET_PREFIX}{name}"


def _shared_value(name: str, default: object) -> object:
    state_key = _shared_state_key(name)
    if state_key not in st.session_state:
        st.session_state[state_key] = default
    return st.session_state[state_key]


def _store_shared_value(name: str) -> None:
    st.session_state[_shared_state_key(name)] = st.session_state[
        _shared_widget_key(name)
    ]


def _move_rolling_period(
    period_type: str,
    offset: int,
    min_date: date,
    max_date: date,
) -> None:
    widget_key = _shared_widget_key("period_start_date")
    st.session_state[widget_key] = shift_period_start(
        period_type.lower(),
        st.session_state[widget_key],
        offset,
        min_date,
        max_date,
    )


def _rolling_period_input(
    period_type: str, min_date: date, max_date: date
) -> tuple[date, date]:
    current_range = _shared_value("date_range", (min_date, max_date))
    widget_key = _shared_widget_key("period_start_date")
    input_args = {
        "label": "Start date",
        "min_value": min_date,
        "max_value": max_date,
        "key": widget_key,
    }
    if widget_key not in st.session_state:
        input_args["value"] = current_range[0]
    start_date = st.sidebar.date_input(**input_args)
    selected = period_range(period_type.lower(), start_date, max_date)
    st.session_state[_shared_state_key("date_range")] = selected
    suffix = (
        " (clipped to available data)"
        if period_end(period_type.lower(), start_date) > max_date
        else ""
    )
    st.sidebar.caption(
        f"Selected range: {format_date_range(*selected)}{suffix}"
    )

    previous, following = st.sidebar.columns(2)
    previous.button(
        f"Previous {period_type.lower()}",
        disabled=start_date == min_date,
        on_click=_move_rolling_period,
        args=(period_type, -1, min_date, max_date),
        width="stretch",
    )
    following.button(
        f"Next {period_type.lower()}",
        disabled=start_date == max_date,
        on_click=_move_rolling_period,
        args=(period_type, 1, min_date, max_date),
        width="stretch",
    )
    return selected


def _date_range_input(hourly: pd.DataFrame) -> tuple[date, date] | object:
    min_date, max_date = _date_bounds(hourly)
    default_range = period_range("month", min_date, max_date)
    period_type = st.sidebar.segmented_control(
        "Period",
        PERIOD_OPTIONS,
        default=_shared_value("period_type", "Custom"),
        key=_shared_widget_key("period_type"),
        on_change=_store_shared_value,
        args=("period_type",),
    )
    if period_type == "All" or period_type is None:
        selected = (min_date, max_date)
        st.session_state[_shared_state_key("date_range")] = selected
        return selected
    if period_type in {"Week", "Month"}:
        return _rolling_period_input(period_type, min_date, max_date)
    return st.sidebar.date_input(
        "Date range",
        value=_shared_value("date_range", default_range),
        min_value=min_date,
        max_value=max_date,
        key=_shared_widget_key("date_range"),
        on_change=_store_shared_value,
        args=("date_range",),
    )


def _aggregation_input() -> str:
    selected = _shared_value("aggregation", "Auto")
    return st.sidebar.selectbox(
        "Aggregation",
        AGGREGATION_OPTIONS,
        index=AGGREGATION_OPTIONS.index(selected),
        key=_shared_widget_key("aggregation"),
        on_change=_store_shared_value,
        args=("aggregation",),
    )


def render_history(hourly: pd.DataFrame) -> None:
    selected_dates = _date_range_input(hourly)
    bucket_label = _aggregation_input()
    visible_series = st.sidebar.multiselect(
        "Series", HISTORY_SERIES, default=HISTORY_SERIES
    )
    export_rate = _export_purchase_rate_input(
        "history_export_rate", 0.0563, "historical"
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
    projected_cost = None
    try:
        rules = _configured_tou_rules()
        projected_cost = projected_utility_cost(
            selected,
            rules,
            export_rate_per_kwh=export_rate,
        )
    except TouValidationError as error:
        st.error(f"TOU rule is invalid: {error}")
    except CostValidationError as error:
        st.error(f"Projected cost could not be calculated: {error}")

    use, production, export, cost = st.columns(4)
    use.metric("Household use", f"{selected['household_load_kwh'].sum():.2f} kWh")
    production.metric("Solar produced", f"{selected['actual_solar_kwh'].sum():.2f} kWh")
    export.metric("Grid exported", f"{selected['grid_export_kwh'].sum():.2f} kWh")
    cost.metric(
        "Projected cost",
        "Unavailable" if projected_cost is None else format_currency(projected_cost),
    )
    st.caption(f"Showing {resolved_bucket} energy totals.")
    st.plotly_chart(
        build_history_figure(aggregated, visible_series), width="stretch"
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


def _configured_tou_rules() -> list[TouRule]:
    configured = _shared_value(
        "tou_rules", pd.DataFrame(SMUD_DEFAULT_TOU_ROWS, columns=TOU_COLUMNS)
    )
    return parse_tou_rules(_nonblank_tou_rows(configured))


def render_configuration() -> None:
    st.caption(
        f"Settings save automatically to {st.session_state[CONFIG_PATH_KEY]}"
    )
    _render_production_scaling_configuration()

    st.subheader("Time-of-use rules")
    st.caption(
        "SMUD Time-of-Day rates are preloaded. Dates use MM-DD; weekdays use "
        "Mon,Tue,… Holidays are treated as ordinary weekdays."
    )
    previous_rules = _shared_value(
        "tou_rules", pd.DataFrame(SMUD_DEFAULT_TOU_ROWS, columns=TOU_COLUMNS)
    ).copy(deep=True)
    edited_rules = st.data_editor(
        previous_rules,
        num_rows="dynamic",
        width="stretch",
        key=_shared_widget_key("tou_rules"),
        column_config={
            "Price ($/kWh)": st.column_config.NumberColumn(
                "Price ($/kWh)", min_value=0.0, format="$%.4f"
            )
        },
    )
    st.session_state[_shared_state_key("tou_rules")] = edited_rules
    try:
        parse_tou_rules(_nonblank_tou_rows(edited_rules))
    except TouValidationError as error:
        st.error(f"TOU rule is invalid: {error}")
    else:
        if not previous_rules.equals(edited_rules):
            _persist_configuration_section("time_of_use")


def _model_state_key(name: str) -> str:
    return f"{MODEL_STATE_PREFIX}{name}"


def _model_widget_key(name: str) -> str:
    return f"{MODEL_WIDGET_PREFIX}{name}"


def _apply_configuration(
    document: dict[str, object], *, monthly_production_was_loaded: bool
) -> None:
    historical = document["historical"]
    system_model = document["system_model"]
    battery = document["battery"]
    solar_production = document["solar_production"]
    time_of_use = document["time_of_use"]

    st.session_state[_model_state_key("history_export_rate")] = historical[
        "export_purchase_rate_per_kwh"
    ]
    st.session_state[_model_state_key("system_export_rate")] = system_model[
        "export_purchase_rate_per_kwh"
    ]
    st.session_state[_model_state_key("strategy")] = battery["strategy"]
    st.session_state[_model_state_key("battery_settings")] = battery["settings_mode"]
    st.session_state[_model_state_key("starting_percent")] = battery[
        "starting_charge_percent"
    ]
    st.session_state[_model_state_key("reserve_percent")] = battery[
        "minimum_reserve_percent"
    ]
    st.session_state[_model_state_key("battery_model")] = battery["preset"]["model"]
    st.session_state[_model_state_key("battery_count")] = battery["preset"]["quantity"]
    st.session_state[_model_state_key("capacity")] = battery["custom"][
        "usable_capacity_kwh"
    ]
    st.session_state[_model_state_key("round_trip_percent")] = battery["custom"][
        "round_trip_efficiency_percent"
    ]
    st.session_state[_model_state_key("max_charge_kw")] = battery["custom"][
        "maximum_charge_power_kw"
    ]
    st.session_state[_model_state_key("max_discharge_kw")] = battery["custom"][
        "maximum_discharge_power_kw"
    ]
    st.session_state[_model_state_key("production_scaling")] = solar_production[
        "scaling_mode"
    ]
    st.session_state[_model_state_key("reference_production_kwh")] = solar_production[
        "annual"
    ]["reference_kwh"]
    st.session_state[_model_state_key("proposed_production_kwh")] = solar_production[
        "annual"
    ]["proposed_kwh"]
    monthly_production = pd.DataFrame(
        [
            {
                "Month": row["month"],
                MONTHLY_REFERENCE_COLUMN: row["reference_kwh"],
                MONTHLY_PROPOSED_COLUMN: row["proposed_kwh"],
            }
            for row in solar_production["monthly"]
        ],
        columns=["Month", MONTHLY_REFERENCE_COLUMN, MONTHLY_PROPOSED_COLUMN],
    )
    st.session_state[_model_state_key("monthly_production")] = monthly_production
    st.session_state[_model_state_key("monthly_production_initialized")] = (
        monthly_production_was_loaded or solar_production["scaling_mode"] == "Monthly"
    )
    st.session_state[_shared_state_key("tou_rules")] = pd.DataFrame(
        [
            {
                "Name": row["name"],
                "Start date": row["start_date"],
                "End date": row["end_date"],
                "Weekdays": row["weekdays"],
                "Start time": row["start_time"],
                "End time": row["end_time"],
                "Price ($/kWh)": row["price_per_kwh"],
            }
            for row in time_of_use["rules"]
        ],
        columns=TOU_COLUMNS,
    )


def _initialize_configuration() -> None:
    if CONFIG_DOCUMENT_KEY in st.session_state:
        return
    path = configuration_path()
    loaded = load_configuration(path)
    document = deepcopy(loaded.document)
    st.session_state[CONFIG_PATH_KEY] = path
    st.session_state[CONFIG_DOCUMENT_KEY] = document
    st.session_state[CONFIG_AUTOSAVE_KEY] = loaded.autosave_enabled
    st.session_state[CONFIG_WARNING_KEY] = loaded.warning
    st.session_state[CONFIG_ERROR_KEY] = None
    _apply_configuration(
        document,
        monthly_production_was_loaded=path.exists() and loaded.autosave_enabled,
    )


def _configuration_section_from_state(section: str) -> dict[str, object]:
    if section == "historical":
        return {
            "export_purchase_rate_per_kwh": float(
                st.session_state[_model_state_key("history_export_rate")]
            )
        }
    if section == "system_model":
        return {
            "export_purchase_rate_per_kwh": float(
                st.session_state[_model_state_key("system_export_rate")]
            )
        }
    if section == "battery":
        return {
            "strategy": st.session_state[_model_state_key("strategy")],
            "settings_mode": st.session_state[_model_state_key("battery_settings")],
            "starting_charge_percent": float(
                st.session_state[_model_state_key("starting_percent")]
            ),
            "minimum_reserve_percent": float(
                st.session_state[_model_state_key("reserve_percent")]
            ),
            "preset": {
                "model": st.session_state[_model_state_key("battery_model")],
                "quantity": int(st.session_state[_model_state_key("battery_count")]),
            },
            "custom": {
                "usable_capacity_kwh": float(
                    st.session_state[_model_state_key("capacity")]
                ),
                "round_trip_efficiency_percent": float(
                    st.session_state[_model_state_key("round_trip_percent")]
                ),
                "maximum_charge_power_kw": float(
                    st.session_state[_model_state_key("max_charge_kw")]
                ),
                "maximum_discharge_power_kw": float(
                    st.session_state[_model_state_key("max_discharge_kw")]
                ),
            },
        }
    if section == "solar_production":
        monthly = st.session_state[_model_state_key("monthly_production")]
        return {
            "scaling_mode": st.session_state[_model_state_key("production_scaling")],
            "annual": {
                "reference_kwh": float(
                    st.session_state[_model_state_key("reference_production_kwh")]
                ),
                "proposed_kwh": float(
                    st.session_state[_model_state_key("proposed_production_kwh")]
                ),
            },
            "monthly": [
                {
                    "month": str(row["Month"]),
                    "reference_kwh": float(row[MONTHLY_REFERENCE_COLUMN]),
                    "proposed_kwh": float(row[MONTHLY_PROPOSED_COLUMN]),
                }
                for row in monthly.to_dict("records")
            ],
        }
    if section == "time_of_use":
        rules = st.session_state[_shared_state_key("tou_rules")]
        return {
            "rules": [
                {
                    "name": str(row["Name"]),
                    "start_date": str(row["Start date"]),
                    "end_date": str(row["End date"]),
                    "weekdays": str(row["Weekdays"]),
                    "start_time": str(row["Start time"]),
                    "end_time": str(row["End time"]),
                    "price_per_kwh": float(row["Price ($/kWh)"]),
                }
                for row in _nonblank_tou_rows(rules)
            ]
        }
    raise ValueError(f"Unsupported configuration section {section!r}")


def _persist_configuration_section(section: str) -> bool:
    if not st.session_state[CONFIG_AUTOSAVE_KEY]:
        return False
    candidate = deepcopy(st.session_state[CONFIG_DOCUMENT_KEY])
    candidate[section] = _configuration_section_from_state(section)
    try:
        normalized = validate_configuration(candidate)
        saved = save_configuration(st.session_state[CONFIG_PATH_KEY], normalized)
    except ConfigurationValidationError:
        return False
    except ConfigurationError as error:
        st.session_state[CONFIG_ERROR_KEY] = str(error)
        return False
    st.session_state[CONFIG_DOCUMENT_KEY] = saved
    st.session_state[CONFIG_ERROR_KEY] = None
    return True


def _model_value(name: str, default: object) -> object:
    state_key = _model_state_key(name)
    if state_key not in st.session_state:
        st.session_state[state_key] = default
    return st.session_state[state_key]


def _store_model_value(name: str, section: str | None = None) -> None:
    st.session_state[_model_state_key(name)] = st.session_state[
        _model_widget_key(name)
    ]
    if (
        section == "solar_production"
        and name == "production_scaling"
        and st.session_state[_model_state_key(name)] == "Monthly"
    ):
        _initialize_monthly_production_if_needed(
            float(st.session_state[_model_state_key("reference_production_kwh")]),
            float(st.session_state[_model_state_key("proposed_production_kwh")]),
        )
    if section is not None:
        _persist_configuration_section(section)


def _export_purchase_rate_input(name: str, default: float, section: str) -> float:
    return st.sidebar.number_input(
        "Utility purchase rate for exported energy ($/kWh)",
        min_value=0.0,
        value=_model_value(name, default),
        step=0.0001,
        format="%.4f",
        key=_model_widget_key(name),
        on_change=_store_model_value,
        args=(name, section),
    )


def _readonly_preset_value(label: str, name: str, value: float) -> float:
    widget_key = _model_widget_key(f"preset_{name}")
    st.session_state[widget_key] = float(value)
    return st.number_input(
        label,
        min_value=0.0,
        step=0.01,
        disabled=True,
        key=widget_key,
    )


def _readonly_configuration_value(label: str, name: str, value: float) -> float:
    widget_key = _model_widget_key(f"readonly_{name}")
    st.session_state[widget_key] = float(value)
    return st.number_input(
        label,
        min_value=0.0,
        step=0.01,
        format="%.2f",
        disabled=True,
        key=widget_key,
    )


def _monthly_production_defaults(
    reference_annual_kwh: float,
    proposed_annual_kwh: float,
) -> pd.DataFrame:
    def distribute_display_units(annual_kwh: float) -> list[float]:
        total_units = int(round(annual_kwh * 10_000))
        base_units, remainder = divmod(total_units, 12)
        return [
            (base_units + (1 if month_index < remainder else 0)) / 10_000.0
            for month_index in range(12)
        ]

    return pd.DataFrame(
        {
            "Month": MONTH_NAMES,
            MONTHLY_REFERENCE_COLUMN: distribute_display_units(
                reference_annual_kwh
            ),
            MONTHLY_PROPOSED_COLUMN: distribute_display_units(proposed_annual_kwh),
        }
    )


def _validate_monthly_production(monthly: pd.DataFrame) -> None:
    for row in monthly.itertuples(index=False, name=None):
        month, reference, proposed = row
        try:
            valid_reference = isfinite(reference) and reference > 0
        except (TypeError, ValueError):
            valid_reference = False
        if not valid_reference:
            raise ValueError(
                f"{month} reference production must be a finite number greater than zero"
            )
        try:
            valid_proposed = isfinite(proposed) and proposed >= 0
        except (TypeError, ValueError):
            valid_proposed = False
        if not valid_proposed:
            raise ValueError(
                f"{month} proposed production must be a finite nonnegative number"
            )


def _initialize_monthly_production_if_needed(
    reference_annual_kwh: float,
    proposed_annual_kwh: float,
) -> pd.DataFrame:
    state_key = _model_state_key("monthly_production")
    initialized_key = _model_state_key("monthly_production_initialized")
    if not st.session_state.get(initialized_key, False):
        st.session_state[state_key] = _monthly_production_defaults(
            reference_annual_kwh, proposed_annual_kwh
        )
        st.session_state[initialized_key] = True
    return _model_value(
        "monthly_production",
        _monthly_production_defaults(reference_annual_kwh, proposed_annual_kwh),
    )


def _monthly_production_input(
    reference_annual_kwh: float,
    proposed_annual_kwh: float,
) -> tuple[float, float, tuple[float, ...]]:
    state_key = _model_state_key("monthly_production")
    monthly = _initialize_monthly_production_if_needed(
        reference_annual_kwh, proposed_annual_kwh
    )
    display = monthly.copy()
    reference_values = pd.to_numeric(
        display[MONTHLY_REFERENCE_COLUMN], errors="coerce"
    )
    proposed_values = pd.to_numeric(display[MONTHLY_PROPOSED_COLUMN], errors="coerce")
    display["Scale"] = (proposed_values / reference_values).where(
        reference_values > 0
    )
    edited = st.data_editor(
        display,
        hide_index=True,
        width="stretch",
        disabled=["Month", "Scale"],
        key=_model_widget_key("monthly_production"),
        column_config={
            MONTHLY_REFERENCE_COLUMN: st.column_config.NumberColumn(
                MONTHLY_REFERENCE_COLUMN,
                min_value=0.0001,
                format="%.4f",
                required=True,
            ),
            MONTHLY_PROPOSED_COLUMN: st.column_config.NumberColumn(
                MONTHLY_PROPOSED_COLUMN,
                min_value=0.0,
                format="%.4f",
                required=True,
            ),
            "Scale": st.column_config.NumberColumn("Scale", format="%.3f"),
        },
    )
    edited_monthly = edited[
        ["Month", MONTHLY_REFERENCE_COLUMN, MONTHLY_PROPOSED_COLUMN]
    ].copy()
    changed = not edited_monthly.equals(monthly)
    st.session_state[state_key] = edited_monthly
    if changed:
        try:
            _validate_monthly_production(edited_monthly)
        except ValueError:
            pass
        else:
            _persist_configuration_section("solar_production")
        st.rerun()

    _validate_monthly_production(edited_monthly)
    reference_total = float(edited_monthly[MONTHLY_REFERENCE_COLUMN].sum())
    proposed_total = float(edited_monthly[MONTHLY_PROPOSED_COLUMN].sum())
    monthly_scales = tuple(
        float(proposed / reference)
        for reference, proposed in zip(
            edited_monthly[MONTHLY_REFERENCE_COLUMN],
            edited_monthly[MONTHLY_PROPOSED_COLUMN],
            strict=True,
        )
    )
    return reference_total, proposed_total, monthly_scales


def _render_production_scaling_configuration() -> None:
    st.subheader("Solar production scaling")
    scaling_mode = st.radio(
        "Production scaling",
        ["Annual", "Monthly"],
        index=["Annual", "Monthly"].index(
            _model_value("production_scaling", "Annual")
        ),
        horizontal=True,
        key=_model_widget_key("production_scaling"),
        on_change=_store_model_value,
        args=("production_scaling", "solar_production"),
    )
    annual_reference_kwh = float(_model_value("reference_production_kwh", 2017.56))
    annual_proposed_kwh = float(_model_value("proposed_production_kwh", 2017.56))
    monthly_solar_scales = None
    if scaling_mode == "Annual":
        reference_production_kwh = st.number_input(
            "Reference annual production (kWh)",
            min_value=0.01,
            value=annual_reference_kwh,
            step=0.01,
            format="%.2f",
            key=_model_widget_key("reference_production_kwh"),
            on_change=_store_model_value,
            args=("reference_production_kwh", "solar_production"),
        )
        proposed_production_kwh = st.number_input(
            "Proposed annual production (kWh)",
            min_value=0.0,
            value=annual_proposed_kwh,
            step=0.01,
            format="%.2f",
            key=_model_widget_key("proposed_production_kwh"),
            on_change=_store_model_value,
            args=("proposed_production_kwh", "solar_production"),
        )
    else:
        try:
            (
                reference_production_kwh,
                proposed_production_kwh,
                monthly_solar_scales,
            ) = _monthly_production_input(annual_reference_kwh, annual_proposed_kwh)
        except ValueError as error:
            st.error(f"Monthly production is invalid: {error}")
            return
        _readonly_configuration_value(
            "Reference annual production (kWh)",
            "monthly_reference_total",
            reference_production_kwh,
        )
        _readonly_configuration_value(
            "Proposed annual production (kWh)",
            "monthly_proposed_total",
            proposed_production_kwh,
        )
    solar_scale = proposed_production_kwh / reference_production_kwh
    if monthly_solar_scales is None:
        st.caption(f"Production scale: {solar_scale:.3f}×")
    else:
        st.caption("Monthly production scales are applied by calendar month.")


def _configured_production_scaling() -> tuple[float, tuple[float, ...] | None]:
    scaling_mode = str(_model_value("production_scaling", "Annual"))
    annual_reference_kwh = float(_model_value("reference_production_kwh", 2017.56))
    annual_proposed_kwh = float(_model_value("proposed_production_kwh", 2017.56))
    if scaling_mode == "Annual":
        return annual_proposed_kwh / annual_reference_kwh, None

    monthly = _model_value(
        "monthly_production",
        _monthly_production_defaults(annual_reference_kwh, annual_proposed_kwh),
    )
    _validate_monthly_production(monthly)
    monthly_scales = tuple(
        float(proposed / reference)
        for reference, proposed in zip(
            monthly[MONTHLY_REFERENCE_COLUMN],
            monthly[MONTHLY_PROPOSED_COLUMN],
            strict=True,
        )
    )
    return 1.0, monthly_scales


def render_model(hourly: pd.DataFrame) -> None:
    selected_dates = _date_range_input(hourly)
    bucket_label = _aggregation_input()
    if not isinstance(selected_dates, tuple) or len(selected_dates) != 2:
        st.error("Choose both a start and end date.")
        return
    start_date, end_date = selected_dates
    try:
        solar_scale, monthly_solar_scales = _configured_production_scaling()
    except ValueError as error:
        st.sidebar.error(f"Monthly production is invalid: {error}")
        return
    export_rate = _export_purchase_rate_input(
        "system_export_rate", 0.096, "system_model"
    )
    if monthly_solar_scales is None:
        st.sidebar.caption(f"Production scale: {solar_scale:.3f}×")
    else:
        st.sidebar.caption("Monthly production scales are applied by calendar month.")
    strategy_label = st.sidebar.selectbox(
        "Battery strategy",
        ["Self-consumption", "TOU reserve"],
        index=["Self-consumption", "TOU reserve"].index(
            _model_value("strategy", "Self-consumption")
        ),
        key=_model_widget_key("strategy"),
        on_change=_store_model_value,
        args=("strategy", "battery"),
    )
    starting_percent = st.sidebar.number_input(
        "Starting charge (%)",
        min_value=0.0,
        max_value=100.0,
        value=_model_value("starting_percent", 50.0),
        step=1.0,
        key=_model_widget_key("starting_percent"),
        on_change=_store_model_value,
        args=("starting_percent", "battery"),
    )
    reserve_percent = st.sidebar.number_input(
        "Minimum reserve (%)",
        min_value=0.0,
        max_value=100.0,
        value=_model_value("reserve_percent", 10.0),
        step=1.0,
        key=_model_widget_key("reserve_percent"),
        on_change=_store_model_value,
        args=("reserve_percent", "battery"),
    )
    battery_settings = st.sidebar.radio(
        "Battery settings",
        ["Custom values", "Battery preset"],
        index=["Custom values", "Battery preset"].index(
            _model_value("battery_settings", "Custom values")
        ),
        key=_model_widget_key("battery_settings"),
        on_change=_store_model_value,
        args=("battery_settings", "battery"),
    )
    if battery_settings == "Custom values":
        capacity = st.sidebar.number_input(
            "Battery usable capacity (kWh)",
            min_value=0.0,
            value=_model_value("capacity", 13.5),
            step=0.5,
            key=_model_widget_key("capacity"),
            on_change=_store_model_value,
            args=("capacity", "battery"),
        )
        preset = None
    else:
        battery_model = st.sidebar.selectbox(
            "Battery model",
            list(BATTERY_PRESETS),
            index=list(BATTERY_PRESETS).index(
                _model_value("battery_model", "Tesla Powerwall 3")
            ),
            key=_model_widget_key("battery_model"),
            on_change=_store_model_value,
            args=("battery_model", "battery"),
        )
        battery_count = st.sidebar.number_input(
            "Number of batteries",
            min_value=1,
            value=_model_value("battery_count", 1),
            step=1,
            key=_model_widget_key("battery_count"),
            on_change=_store_model_value,
            args=("battery_count", "battery"),
        )
        preset = BATTERY_PRESETS[battery_model]
        with st.sidebar:
            capacity = _readonly_preset_value(
                "Battery usable capacity (kWh)",
                "capacity",
                round(preset["capacity_kwh"] * int(battery_count), 2),
            )
    with st.sidebar.expander("Advanced battery settings"):
        if preset is None:
            round_trip_percent = st.number_input(
                "Round-trip efficiency (%)",
                min_value=0.1,
                max_value=100.0,
                value=_model_value("round_trip_percent", 90.0),
                step=1.0,
                key=_model_widget_key("round_trip_percent"),
                on_change=_store_model_value,
                args=("round_trip_percent", "battery"),
            )
            max_charge_kw = st.number_input(
                "Maximum charge power (kW)",
                min_value=0.0,
                value=_model_value("max_charge_kw", 5.0),
                step=0.5,
                key=_model_widget_key("max_charge_kw"),
                on_change=_store_model_value,
                args=("max_charge_kw", "battery"),
            )
            max_discharge_kw = st.number_input(
                "Maximum discharge power (kW)",
                min_value=0.0,
                value=_model_value("max_discharge_kw", 5.0),
                step=0.5,
                key=_model_widget_key("max_discharge_kw"),
                on_change=_store_model_value,
                args=("max_discharge_kw", "battery"),
            )
        else:
            round_trip_percent = _readonly_preset_value(
                "Round-trip efficiency (%)",
                "round_trip_percent",
                preset["round_trip_percent"],
            )
            max_charge_kw = _readonly_preset_value(
                "Maximum charge power (kW)",
                "max_charge_kw",
                round(preset["max_charge_kw"] * int(battery_count), 2),
            )
            max_discharge_kw = _readonly_preset_value(
                "Maximum discharge power (kW)",
                "max_discharge_kw",
                round(preset["max_discharge_kw"] * int(battery_count), 2),
            )

    chart_slot = st.empty()
    try:
        rules = _configured_tou_rules()
    except TouValidationError as error:
        chart_slot.info("Add a valid time-of-use rule to model this period.")
        st.error(f"TOU rule is invalid: {error}")
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
        monthly_solar_scales=monthly_solar_scales,
    )
    try:
        result = simulate(selected, config, rules)
    except SimulationValidationError as error:
        chart_slot.error(f"Model settings are invalid: {error}")
        return
    try:
        result["net_cost_usd"] = hourly_net_costs(
            result, rules, export_rate_per_kwh=export_rate
        )
    except CostValidationError as error:
        chart_slot.error(f"Projected cost could not be calculated: {error}")
        return
    try:
        aggregated, resolved_bucket = aggregate_model_result(
            result, start_date, end_date, bucket_label.lower()
        )
    except ValueError as error:
        chart_slot.error(f"Model chart selection is invalid: {error}")
        return
    projected_cost = float(result["net_cost_usd"].sum())

    with chart_slot.container():
        imported, expensive, exported, cost = st.columns(4)
        imported.metric("Grid import", f"{result['grid_import_kwh'].sum():.2f} kWh")
        expensive.metric(
            "Expensive import",
            f"{result.loc[result['is_expensive'], 'grid_import_kwh'].sum():.2f} kWh",
        )
        exported.metric("Grid export", f"{result['grid_export_kwh'].sum():.2f} kWh")
        cost.metric("Projected cost", format_currency(projected_cost))
        st.caption(f"Showing {resolved_bucket} energy totals.")
        st.plotly_chart(build_model_figure(aggregated), width="stretch")


st.set_page_config(page_title="Home Energy Model", page_icon="☀️", layout="wide")
_initialize_configuration()
st.title("Home Energy Model")
if st.session_state[CONFIG_WARNING_KEY] is not None:
    st.warning(st.session_state[CONFIG_WARNING_KEY])
if st.session_state[CONFIG_ERROR_KEY] is not None:
    st.error(st.session_state[CONFIG_ERROR_KEY])

try:
    hourly = load_data()
except (OSError, DataValidationError) as error:
    st.error(f"Energy data could not be loaded: {error}")
    st.stop()

page = st.radio(
    "View",
    ["Historical view", "System model", "Configuration"],
    horizontal=True,
    label_visibility="collapsed",
)
if page == "Historical view":
    render_history(hourly)
elif page == "System model":
    render_model(hourly)
else:
    render_configuration()

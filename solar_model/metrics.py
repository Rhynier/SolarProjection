from dataclasses import dataclass
from math import sqrt

import pandas as pd


@dataclass(frozen=True)
class SimulationSummary:
    solar_self_consumption_percent: float
    expensive_grid_import_kwh: float
    battery_discharge_output_kwh: float
    equivalent_full_cycles: float
    ending_charge_percent: float


def summarize_simulation(
    result: pd.DataFrame,
    *,
    capacity_kwh: float,
    reserve_percent: float,
    round_trip_efficiency: float,
) -> SimulationSummary:
    modeled_solar = float(result["modeled_solar_kwh"].sum())
    grid_export = float(result["grid_export_kwh"].sum())
    if modeled_solar > 0:
        self_consumption = 100.0 * (modeled_solar - grid_export) / modeled_solar
        self_consumption = min(max(self_consumption, 0.0), 100.0)
    else:
        self_consumption = 0.0

    expensive_import = float(
        result.loc[result["is_expensive"], "grid_import_kwh"].sum()
    )
    discharged = float(result["battery_discharge_output_kwh"].sum())
    working_capacity = capacity_kwh * (1.0 - reserve_percent / 100.0)
    if working_capacity > 0:
        battery_side_discharged = discharged / sqrt(round_trip_efficiency)
        equivalent_cycles = battery_side_discharged / working_capacity
    else:
        equivalent_cycles = 0.0

    if capacity_kwh > 0 and not result.empty:
        ending_charge = 100.0 * float(result["battery_soc_kwh"].iloc[-1]) / capacity_kwh
    else:
        ending_charge = 0.0

    return SimulationSummary(
        solar_self_consumption_percent=self_consumption,
        expensive_grid_import_kwh=expensive_import,
        battery_discharge_output_kwh=discharged,
        equivalent_full_cycles=equivalent_cycles,
        ending_charge_percent=ending_charge,
    )

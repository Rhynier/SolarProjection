from math import sqrt
from typing import TYPE_CHECKING, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from .tou import TouRule, price_at

if TYPE_CHECKING:
    from .simulation import BatteryConfig


class OptimizationError(ValueError):
    pass


def optimize_historical_dispatch(
    hourly: pd.DataFrame,
    modeled_solar_kwh: Sequence[float],
    battery: "BatteryConfig",
    tou_rules: Sequence[TouRule],
    export_rate_per_kwh: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Minimize utility energy cost across the supplied historical hours."""
    count = len(hourly)
    if count == 0:
        empty = np.array([], dtype=float)
        return empty, empty

    load = hourly["household_load_kwh"].to_numpy(dtype=float)
    solar = np.asarray(modeled_solar_kwh, dtype=float)
    surplus = np.maximum(solar - load, 0.0)
    deficit = np.maximum(load - solar, 0.0)

    import_prices: list[float] = []
    for index, timestamp in enumerate(hourly["timestamp"]):
        price = price_at(pd.Timestamp(timestamp).to_pydatetime(), tou_rules)
        if price is None:
            if deficit[index] > 0:
                raise OptimizationError(
                    f"Imported energy at {timestamp} has no utility price"
                )
            price = 0.0
        import_prices.append(price)

    leg_efficiency = sqrt(battery.round_trip_efficiency)
    capacity = battery.capacity_kwh
    reserve = capacity * battery.reserve_percent / 100.0
    starting_soc = capacity * battery.starting_percent / 100.0

    charge_slice = slice(0, count)
    discharge_slice = slice(count, 2 * count)
    soc_slice = slice(2 * count, 3 * count)

    objective = np.zeros(3 * count, dtype=float)
    objective[charge_slice] = export_rate_per_kwh
    objective[discharge_slice] = -np.asarray(import_prices, dtype=float)

    bounds: list[tuple[float, float]] = []
    bounds.extend(
        (0.0, min(float(value), battery.max_charge_kw)) for value in surplus
    )
    bounds.extend(
        (0.0, min(float(value), battery.max_discharge_kw)) for value in deficit
    )
    bounds.extend((reserve, capacity) for _ in range(count))

    # Each hourly state equation touches only three or four variables. Keeping
    # this matrix sparse avoids allocating a multi-gigabyte dense array for a
    # full year of hourly history.
    equality = lil_matrix((count, 3 * count), dtype=float)
    right_hand_side = np.zeros(count, dtype=float)
    for index in range(count):
        equality[index, charge_slice.start + index] = -leg_efficiency
        equality[index, discharge_slice.start + index] = 1.0 / leg_efficiency
        equality[index, soc_slice.start + index] = 1.0
        if index == 0:
            right_hand_side[index] = starting_soc
        else:
            equality[index, soc_slice.start + index - 1] = -1.0

    result = linprog(
        objective,
        A_eq=equality.tocsr(),
        b_eq=right_hand_side,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise OptimizationError(
            f"Historical cost optimization failed: {result.message}"
        )

    charge = np.maximum(result.x[charge_slice], 0.0)
    discharge = np.maximum(result.x[discharge_slice], 0.0)
    return charge, discharge

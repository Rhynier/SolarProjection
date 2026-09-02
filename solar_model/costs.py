from collections.abc import Sequence
from math import isfinite

import pandas as pd

from .tou import TouRule, price_at


class CostValidationError(ValueError):
    pass


def format_currency(amount: float) -> str:
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def projected_utility_cost(
    hourly: pd.DataFrame,
    rules: Sequence[TouRule],
    export_rate_per_kwh: float,
) -> float:
    try:
        valid_export_rate = (
            isfinite(export_rate_per_kwh) and export_rate_per_kwh >= 0
        )
    except (TypeError, ValueError):
        valid_export_rate = False
    if not valid_export_rate:
        raise CostValidationError(
            "Export purchase rate must be a finite non-negative number"
        )

    total = 0.0
    for row in hourly.itertuples(index=False):
        import_rate = price_at(pd.Timestamp(row.timestamp).to_pydatetime(), rules)
        if import_rate is None:
            if row.grid_import_kwh > 0:
                raise CostValidationError(
                    f"Imported energy at {row.timestamp} has no utility price"
                )
            import_cost = 0.0
        else:
            import_cost = row.grid_import_kwh * import_rate
        total += import_cost - row.grid_export_kwh * export_rate_per_kwh
    return total

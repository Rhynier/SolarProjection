from calendar import monthrange
from datetime import date, timedelta
from typing import Literal


PeriodType = Literal["week", "month"]


def _shift_month(anchor: date, offset: int) -> date:
    month_index = anchor.year * 12 + anchor.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def period_end(period_type: PeriodType, start_date: date) -> date:
    if period_type == "week":
        return start_date + timedelta(days=6)
    if period_type == "month":
        return _shift_month(start_date, 1) - timedelta(days=1)
    raise ValueError("period type must be 'week' or 'month'")


def period_range(
    period_type: PeriodType, start_date: date, max_date: date
) -> tuple[date, date]:
    if start_date > max_date:
        raise ValueError("start date must not be after maximum date")
    return start_date, min(period_end(period_type, start_date), max_date)


def shift_period_start(
    period_type: PeriodType,
    start_date: date,
    offset: int,
    min_date: date,
    max_date: date,
) -> date:
    if period_type == "week":
        shifted = start_date + timedelta(days=7 * offset)
    elif period_type == "month":
        shifted = _shift_month(start_date, offset)
    else:
        raise ValueError("period type must be 'week' or 'month'")
    return min(max(shifted, min_date), max_date)


def format_date_range(start_date: date, end_date: date) -> str:
    if start_date.year != end_date.year:
        return (
            f"{start_date:%b} {start_date.day}, {start_date.year}–"
            f"{end_date:%b} {end_date.day}, {end_date.year}"
        )
    if start_date.month != end_date.month:
        return f"{start_date:%b} {start_date.day}–{end_date:%b} {end_date.day}, {end_date.year}"
    return f"{start_date:%b} {start_date.day}–{end_date.day}, {end_date.year}"

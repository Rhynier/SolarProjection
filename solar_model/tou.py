from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
from typing import Literal, Mapping, Sequence


WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

SMUD_DEFAULT_TOU_ROWS = (
    {
        "Name": "Non-summer off-peak morning",
        "Start date": "10-01",
        "End date": "05-31",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "00:00",
        "End time": "17:00",
        "Price ($/kWh)": 0.1285,
    },
    {
        "Name": "Non-summer peak",
        "Start date": "10-01",
        "End date": "05-31",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "17:00",
        "End time": "20:00",
        "Price ($/kWh)": 0.1776,
    },
    {
        "Name": "Non-summer off-peak evening",
        "Start date": "10-01",
        "End date": "05-31",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "20:00",
        "End time": "00:00",
        "Price ($/kWh)": 0.1285,
    },
    {
        "Name": "Non-summer weekend off-peak",
        "Start date": "10-01",
        "End date": "05-31",
        "Weekdays": "Sat,Sun",
        "Start time": "00:00",
        "End time": "00:00",
        "Price ($/kWh)": 0.1285,
    },
    {
        "Name": "Summer off-peak",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "00:00",
        "End time": "12:00",
        "Price ($/kWh)": 0.1550,
    },
    {
        "Name": "Summer mid-peak afternoon",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "12:00",
        "End time": "17:00",
        "Price ($/kWh)": 0.2139,
    },
    {
        "Name": "Summer peak",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "17:00",
        "End time": "20:00",
        "Price ($/kWh)": 0.3765,
    },
    {
        "Name": "Summer mid-peak evening",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "20:00",
        "End time": "00:00",
        "Price ($/kWh)": 0.2139,
    },
    {
        "Name": "Summer weekend off-peak",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Sat,Sun",
        "Start time": "00:00",
        "End time": "00:00",
        "Price ($/kWh)": 0.1550,
    },
)

_REQUIRED_COLUMNS = (
    "Name",
    "Start date",
    "End date",
    "Weekdays",
    "Start time",
    "End time",
    "Price ($/kWh)",
)


class TouValidationError(ValueError):
    pass


RateClassification = Literal["cheap", "less_expensive", "expensive"]


@dataclass(frozen=True)
class TouRule:
    name: str
    start_month_day: tuple[int, int]
    end_month_day: tuple[int, int]
    weekdays: frozenset[int]
    start_time: time
    end_time: time
    price_per_kwh: float


def _parse_month_day(value: object, field: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(f"2000-{value}", "%Y-%m-%d")
    except (TypeError, ValueError) as error:
        raise TouValidationError(f"{field} must use MM-DD format") from error
    return parsed.month, parsed.day


def _parse_time(value: object, field: str) -> time:
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError) as error:
        raise TouValidationError(f"{field} must use HH:MM format") from error


def _parse_price(value: object) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError) as error:
        raise TouValidationError(
            "Price ($/kWh) must be a finite non-negative number"
        ) from error
    if not isfinite(price) or price < 0:
        raise TouValidationError(
            "Price ($/kWh) must be a finite non-negative number"
        )
    return price


def _parse_weekdays(value: object) -> frozenset[int]:
    if not isinstance(value, str):
        raise TouValidationError("Weekdays must be comma-separated weekday names")

    names = [name.strip().lower() for name in value.split(",")]
    if not names or any(not name for name in names):
        raise TouValidationError("Weekdays must not contain blanks")

    unknown = [name for name in names if name not in WEEKDAYS]
    if unknown:
        raise TouValidationError(f"Weekdays contains unknown day {unknown[0]!r}")
    return frozenset(WEEKDAYS[name] for name in names)


def _require_text(row: Mapping[str, object], field: str) -> str:
    if field not in row:
        raise TouValidationError(f"{field} is required")
    value = row[field]
    if not isinstance(value, str) or not value.strip():
        raise TouValidationError(f"{field} must not be blank")
    return value.strip()


def parse_tou_rules(rows: Sequence[Mapping[str, object]]) -> list[TouRule]:
    rules: list[TouRule] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            text_fields = _REQUIRED_COLUMNS[:-1]
            values = {field: _require_text(row, field) for field in text_fields}
            price_field = _REQUIRED_COLUMNS[-1]
            if price_field not in row:
                raise TouValidationError(f"{price_field} is required")
            start_time = _parse_time(values["Start time"], "Start time")
            end_time = _parse_time(values["End time"], "End time")

            rules.append(
                TouRule(
                    name=values["Name"],
                    start_month_day=_parse_month_day(values["Start date"], "Start date"),
                    end_month_day=_parse_month_day(values["End date"], "End date"),
                    weekdays=_parse_weekdays(values["Weekdays"]),
                    start_time=start_time,
                    end_time=end_time,
                    price_per_kwh=_parse_price(row[price_field]),
                )
            )
        except TouValidationError as error:
            raise TouValidationError(f"Row {row_number}: {error}") from error
    return rules


def _date_in_range(anchor: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    value = (anchor.month, anchor.day)
    return start <= value <= end if start <= end else value >= start or value <= end


def has_seasonal_price_spread(rules: Sequence[TouRule]) -> bool:
    first_day = date(2000, 1, 1)
    for offset in range(366):
        anchor = first_day + timedelta(days=offset)
        prices = {
            item.price_per_kwh
            for item in rules
            if _date_in_range(anchor, item.start_month_day, item.end_month_day)
        }
        if len(prices) > 1:
            return True
    return False


def _rule_anchor(timestamp: datetime, rule: TouRule) -> date | None:
    current = timestamp.time()
    if rule.start_time == rule.end_time:
        anchor = timestamp.date()
    elif rule.start_time < rule.end_time:
        if not (rule.start_time <= current < rule.end_time):
            return None
        anchor = timestamp.date()
    else:
        if current >= rule.start_time:
            anchor = timestamp.date()
        elif current < rule.end_time:
            anchor = timestamp.date() - timedelta(days=1)
        else:
            return None
    if anchor.weekday() not in rule.weekdays or not _date_in_range(
        anchor, rule.start_month_day, rule.end_month_day
    ):
        return None
    return anchor


def _matching_rules(
    timestamp: datetime, rules: Sequence[TouRule]
) -> list[tuple[TouRule, date]]:
    matches: list[tuple[TouRule, date]] = []
    for item in rules:
        anchor = _rule_anchor(timestamp, item)
        if anchor is not None:
            matches.append((item, anchor))
    return matches


def price_at(timestamp: datetime, rules: Sequence[TouRule]) -> float | None:
    matching_prices = [
        item.price_per_kwh for item, _ in _matching_rules(timestamp, rules)
    ]
    return max(matching_prices, default=None)


def rate_classification(
    timestamp: datetime, rules: Sequence[TouRule]
) -> RateClassification | None:
    matches = _matching_rules(timestamp, rules)
    if not matches:
        return None
    current_rule, season_anchor = max(
        matches, key=lambda match: match[0].price_per_kwh
    )
    current_price = current_rule.price_per_kwh

    seasonal_prices = sorted(
        {
            item.price_per_kwh
            for item in rules
            if _date_in_range(
                season_anchor, item.start_month_day, item.end_month_day
            )
        }
    )
    if current_price == seasonal_prices[0]:
        return "cheap"
    if current_price == seasonal_prices[-1]:
        return "expensive"
    return "less_expensive"


def is_expensive(timestamp: datetime, rules: Sequence[TouRule]) -> bool:
    return rate_classification(timestamp, rules) == "expensive"

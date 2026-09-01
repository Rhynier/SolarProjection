from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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

_REQUIRED_COLUMNS = (
    "Name",
    "Start date",
    "End date",
    "Weekdays",
    "Start time",
    "End time",
    "Classification",
)


class TouValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TouRule:
    name: str
    start_month_day: tuple[int, int]
    end_month_day: tuple[int, int]
    weekdays: frozenset[int]
    start_time: time
    end_time: time
    classification: Literal["expensive", "normal"]


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
            values = {field: _require_text(row, field) for field in _REQUIRED_COLUMNS}
            start_time = _parse_time(values["Start time"], "Start time")
            end_time = _parse_time(values["End time"], "End time")
            if start_time == end_time:
                raise TouValidationError("Start time and End time must differ")

            classification = values["Classification"].lower()
            if classification not in {"expensive", "normal"}:
                raise TouValidationError("Classification must be Normal or Expensive")

            rules.append(
                TouRule(
                    name=values["Name"],
                    start_month_day=_parse_month_day(values["Start date"], "Start date"),
                    end_month_day=_parse_month_day(values["End date"], "End date"),
                    weekdays=_parse_weekdays(values["Weekdays"]),
                    start_time=start_time,
                    end_time=end_time,
                    classification=classification,
                )
            )
        except TouValidationError as error:
            raise TouValidationError(f"Row {row_number}: {error}") from error
    return rules


def _date_in_range(anchor: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    value = (anchor.month, anchor.day)
    return start <= value <= end if start <= end else value >= start or value <= end


def _rule_matches(timestamp: datetime, rule: TouRule) -> bool:
    current = timestamp.time()
    if rule.start_time < rule.end_time:
        if not (rule.start_time <= current < rule.end_time):
            return False
        anchor = timestamp.date()
    else:
        if current >= rule.start_time:
            anchor = timestamp.date()
        elif current < rule.end_time:
            anchor = timestamp.date() - timedelta(days=1)
        else:
            return False
    return anchor.weekday() in rule.weekdays and _date_in_range(
        anchor, rule.start_month_day, rule.end_month_day
    )


def is_expensive(timestamp: datetime, rules: Sequence[TouRule]) -> bool:
    return any(
        item.classification == "expensive" and _rule_matches(timestamp, item)
        for item in rules
    )

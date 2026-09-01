from datetime import datetime

import pytest

from solar_model.tou import TouValidationError, is_expensive, parse_tou_rules


def rule(**overrides):
    values = {
        "Name": "Summer peak",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "17:00",
        "End time": "20:00",
        "Classification": "Expensive",
    }
    values.update(overrides)
    return values


def test_weekday_peak_is_start_inclusive_end_exclusive():
    rules = parse_tou_rules([rule()])
    assert is_expensive(datetime(2026, 7, 6, 17), rules)
    assert not is_expensive(datetime(2026, 7, 6, 20), rules)
    assert not is_expensive(datetime(2026, 7, 5, 18), rules)


def test_overnight_rule_uses_starting_weekday():
    rules = parse_tou_rules(
        [
            rule(
                **{
                    "Name": "Overnight",
                    "Start date": "01-01",
                    "End date": "12-31",
                    "Weekdays": "Mon",
                    "Start time": "22:00",
                    "End time": "06:00",
                }
            )
        ]
    )
    assert is_expensive(datetime(2026, 7, 6, 23), rules)
    assert is_expensive(datetime(2026, 7, 7, 5), rules)
    assert not is_expensive(datetime(2026, 7, 7, 23), rules)


def test_year_wrapping_date_range_matches_both_sides_of_new_year():
    rules = parse_tou_rules(
        [
            rule(
                **{
                    "Start date": "11-01",
                    "End date": "02-28",
                    "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                }
            )
        ]
    )
    assert is_expensive(datetime(2026, 1, 12, 18), rules)
    assert is_expensive(datetime(2026, 12, 7, 18), rules)
    assert not is_expensive(datetime(2026, 7, 6, 18), rules)


def test_expensive_wins_when_normal_also_matches():
    rows = [
        rule(Classification="Normal"),
        rule(Name="Override", Classification="Expensive"),
    ]
    assert is_expensive(datetime(2026, 7, 6, 18), parse_tou_rules(rows))


def test_equal_start_and_end_time_is_rejected():
    with pytest.raises(TouValidationError, match="must differ"):
        parse_tou_rules([rule(**{"Start time": "17:00", "End time": "17:00"})])

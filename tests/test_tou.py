from datetime import datetime

import pytest

import solar_model.tou as tou
from solar_model.tou import TouValidationError, is_expensive, parse_tou_rules


def rule(**overrides):
    values = {
        "Name": "Summer peak",
        "Start date": "06-01",
        "End date": "09-30",
        "Weekdays": "Mon,Tue,Wed,Thu,Fri",
        "Start time": "17:00",
        "End time": "20:00",
        "Price ($/kWh)": "0.3765",
    }
    values.update(overrides)
    return values


def test_rule_parses_price_instead_of_a_manual_classification():
    parsed = parse_tou_rules([rule()])

    assert parsed[0].price_per_kwh == pytest.approx(0.3765)
    assert not hasattr(parsed[0], "classification")


def test_rule_accepts_a_numeric_editor_price():
    parsed = parse_tou_rules([rule(**{"Price ($/kWh)": 0.3765})])

    assert parsed[0].price_per_kwh == pytest.approx(0.3765)


@pytest.mark.parametrize(
    ("hour", "expected_price", "expected_tier", "expected_expensive"),
    [
        (11, 0.1550, "cheap", False),
        (12, 0.2139, "less_expensive", False),
        (17, 0.3765, "expensive", True),
    ],
)
def test_rates_are_ranked_within_their_season(
    hour, expected_price, expected_tier, expected_expensive
):
    rules = parse_tou_rules(
        [
            rule(
                Name="Summer off-peak",
                **{
                    "Start time": "00:00",
                    "End time": "12:00",
                    "Price ($/kWh)": "0.1550",
                },
            ),
            rule(
                Name="Summer mid-peak",
                **{
                    "Start time": "12:00",
                    "End time": "17:00",
                    "Price ($/kWh)": "0.2139",
                },
            ),
            rule(Name="Summer peak"),
        ]
    )
    timestamp = datetime(2026, 7, 6, hour)

    assert tou.price_at(timestamp, rules) == pytest.approx(expected_price)
    assert tou.rate_classification(timestamp, rules) == expected_tier
    assert is_expensive(timestamp, rules) is expected_expensive


def test_weekday_peak_is_start_inclusive_end_exclusive():
    rules = parse_tou_rules([rule()])
    assert tou.price_at(datetime(2026, 7, 6, 17), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 7, 6, 20), rules) is None
    assert tou.price_at(datetime(2026, 7, 5, 18), rules) is None


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
    assert tou.price_at(datetime(2026, 7, 6, 23), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 7, 7, 5), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 7, 7, 23), rules) is None


def test_overnight_rule_uses_starting_date_for_seasonal_price_ranking():
    rules = parse_tou_rules(
        [
            rule(
                Name="Summer off-peak",
                **{
                    "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                    "Start time": "00:00",
                    "End time": "22:00",
                    "Price ($/kWh)": "0.1550",
                },
            ),
            rule(
                Name="Summer overnight peak",
                **{
                    "Weekdays": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
                    "Start time": "22:00",
                    "End time": "02:00",
                    "Price ($/kWh)": "0.3765",
                },
            ),
        ]
    )
    timestamp = datetime(2026, 10, 1, 1)

    assert tou.price_at(timestamp, rules) == pytest.approx(0.3765)
    assert tou.rate_classification(timestamp, rules) == "expensive"


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
    assert tou.price_at(datetime(2026, 1, 12, 18), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 12, 7, 18), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 7, 6, 18), rules) is None


def test_highest_price_wins_when_rules_overlap():
    rows = [
        rule(**{"Price ($/kWh)": "0.1550"}),
        rule(Name="Override", **{"Price ($/kWh)": "0.3765"}),
    ]
    assert tou.price_at(
        datetime(2026, 7, 6, 18), parse_tou_rules(rows)
    ) == pytest.approx(0.3765)


def test_equal_start_and_end_time_represents_an_all_day_rule():
    rules = parse_tou_rules(
        [
            rule(
                Weekdays="Mon",
                **{"Start time": "17:00", "End time": "17:00"},
            )
        ]
    )

    assert tou.price_at(datetime(2026, 7, 6, 10), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 7, 6, 12), rules) == pytest.approx(
        0.3765
    )
    assert tou.price_at(datetime(2026, 7, 7, 12), rules) is None


@pytest.mark.parametrize("price", ["not-a-number", "-0.1", "nan", "inf"])
def test_price_must_be_a_finite_non_negative_number(price):
    with pytest.raises(TouValidationError, match="finite non-negative number"):
        parse_tou_rules([rule(**{"Price ($/kWh)": price})])


@pytest.mark.parametrize(
    ("timestamp", "expected_price", "expected_tier"),
    [
        (datetime(2026, 1, 5, 16), 0.1285, "cheap"),
        (datetime(2026, 1, 5, 17), 0.1776, "expensive"),
        (datetime(2026, 1, 10, 18), 0.1285, "cheap"),
        (datetime(2026, 7, 6, 11), 0.1550, "cheap"),
        (datetime(2026, 7, 6, 12), 0.2139, "less_expensive"),
        (datetime(2026, 7, 6, 17), 0.3765, "expensive"),
        (datetime(2026, 7, 6, 20), 0.2139, "less_expensive"),
        (datetime(2026, 7, 5, 18), 0.1550, "cheap"),
        (datetime(2026, 6, 19, 18), 0.3765, "expensive"),
        (datetime(2026, 10, 1, 17), 0.1776, "expensive"),
    ],
)
def test_smud_defaults_supply_the_published_seasonal_rates(
    timestamp, expected_price, expected_tier
):
    rules = parse_tou_rules(tou.SMUD_DEFAULT_TOU_ROWS)

    assert tou.price_at(timestamp, rules) == pytest.approx(expected_price)
    assert tou.rate_classification(timestamp, rules) == expected_tier
    assert is_expensive(timestamp, rules) is (expected_tier == "expensive")

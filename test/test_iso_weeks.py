"""Test the ISO week numbers option for week-based schedules."""

from datetime import date, timedelta
from itertools import combinations

import pytest
from dateutil.relativedelta import relativedelta
from homeassistant.const import WEEKDAYS
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garbage_collection import const
from custom_components.garbage_collection.sensor import WeeklyCollection

START = date(2020, 1, 1)
END = date(2040, 12, 31)


def _old_find_candidate_date(sensor: WeeklyCollection, day1: date) -> date:
    """Verbatim copy of the calculation before the option existed."""
    week = day1.isocalendar()[1]
    weekday = day1.weekday()
    offset = -1
    if (week - sensor._first_week) % sensor._period == 0:
        for day_name in sensor._collection_days:
            day_index = WEEKDAYS.index(day_name)
            if day_index >= weekday:
                offset = day_index - weekday
                break
    iterate_by_week = 7 - weekday + WEEKDAYS.index(sensor._collection_days[0])
    while offset == -1:
        candidate = day1 + relativedelta(days=iterate_by_week)
        week = candidate.isocalendar()[1]
        if (week - sensor._first_week) % sensor._period == 0:
            offset = iterate_by_week
            break
        iterate_by_week += 7
    return day1 + relativedelta(days=offset)


def _old_schedule(sensor: WeeklyCollection) -> list[date]:
    """Collection dates from the old calculation, like collection_schedule."""
    dates = []
    day = sensor.move_to_range(START)
    while True:
        next_date = _old_find_candidate_date(sensor, day)
        if next_date > END:
            return dates
        if (new_date := sensor.move_to_range(next_date)) != next_date:
            day = new_date
        else:
            dates.append(next_date)
            day = next_date + relativedelta(days=1)


def _sensor(**options) -> WeeklyCollection:
    """Create a sensor without setting it up."""
    return WeeklyCollection(
        MockConfigEntry(domain=const.DOMAIN, options=options, title="t", version=6)
    )


def _configs():
    """All week-number schedules with a range of days, periods and seasons."""
    day_sets = [["mon"], ["wed"], ["sun"], ["tue", "fri"], ["mon", "sun"]]
    seasons = [{}, {"first_month": "apr", "last_month": "nov"}]
    for days in day_sets:
        for season in seasons:
            yield {"frequency": "odd-weeks", "collection_days": days, **season}
            yield {"frequency": "even-weeks", "collection_days": days, **season}
            for period in (1, 2, 3, 4, 5):
                for first_week in range(1, period + 1):
                    yield {
                        "frequency": "every-n-weeks",
                        "collection_days": days,
                        "period": period,
                        "first_week": first_week,
                        **season,
                    }


@pytest.mark.asyncio
async def test_default_unchanged(hass: HomeAssistant) -> None:
    """Without the option set, dates are identical to the old calculation."""
    checked = 0
    for options in _configs():
        sensor = _sensor(**options)
        new = list(sensor.collection_schedule(START, END))
        assert new == _old_schedule(sensor), options
        # Explicitly ticked behaves the same as not set
        ticked = _sensor(**options, iso_week_numbers=True)
        assert list(ticked.collection_schedule(START, END)) == new, options
        checked += 1
    assert checked > 50


@pytest.mark.asyncio
async def test_continuous_odd_weeks(hass: HomeAssistant) -> None:
    """Unticked, odd weeks stay fortnightly across the 53-week year 2026."""
    sensor = _sensor(
        frequency="odd-weeks", collection_days=["mon"], iso_week_numbers=False
    )
    dates = list(sensor.collection_schedule(date(2026, 12, 1), date(2027, 1, 31)))
    assert dates == [
        date(2026, 12, 14),
        date(2026, 12, 28),
        date(2027, 1, 11),
        date(2027, 1, 25),
    ]
    iso = _sensor(frequency="odd-weeks", collection_days=["mon"])
    assert date(2027, 1, 4) in iso.collection_schedule(
        date(2026, 12, 1), date(2027, 1, 31)
    )


@pytest.mark.asyncio
async def test_continuous_matches_iso_in_2026(hass: HomeAssistant) -> None:
    """Switching the option changes nothing before January 2027."""
    for options in _configs():
        iso = _sensor(**options)
        continuous = _sensor(**options, iso_week_numbers=False)
        first, last = date(2026, 1, 1), date(2026, 12, 31)
        assert list(continuous.collection_schedule(first, last)) == list(
            iso.collection_schedule(first, last)
        ), options


@pytest.mark.asyncio
async def test_continuous_is_regular(hass: HomeAssistant) -> None:
    """Unticked, every gap is the same over 20 years."""
    for period in (2, 3, 4):
        sensor = _sensor(
            frequency="every-n-weeks",
            collection_days=["thu"],
            period=period,
            first_week=1,
            iso_week_numbers=False,
        )
        dates = list(sensor.collection_schedule(START, END))
        gaps = {
            b - a for a, b in combinations(dates, 2) if (b - a).days < 7 * period + 1
        }
        assert gaps == {timedelta(weeks=period)}


@pytest.mark.asyncio
async def test_options_flow_untick(hass: HomeAssistant) -> None:
    """The option is offered for odd weeks and can be unticked later."""
    config_entry: MockConfigEntry = MockConfigEntry(
        domain=const.DOMAIN,
        options={"frequency": "odd-weeks", "collection_days": ["mon"]},
        title="odd",
        version=6,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"frequency": "odd-weeks"}
    )
    assert result["step_id"] == "detail"
    fields = {str(key): key for key in result["data_schema"].schema}
    assert const.CONF_ISO_WEEKS in fields
    # Shown ticked for an entry that does not have the option stored
    assert fields[const.CONF_ISO_WEEKS].description == {"suggested_value": True}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"collection_days": ["mon"], "iso_week_numbers": False},
    )
    await hass.async_block_till_done()
    assert config_entry.options[const.CONF_ISO_WEEKS] is False
    sensor = hass.data[const.DOMAIN][const.SENSOR_PLATFORM]["sensor.odd"]
    assert date(2027, 1, 11) in sensor.collection_schedule(
        date(2026, 12, 1), date(2027, 1, 31)
    )


@pytest.mark.asyncio
async def test_option_not_offered_for_weekly(hass: HomeAssistant) -> None:
    """Plain weekly schedules do not show the option."""
    config_entry: MockConfigEntry = MockConfigEntry(
        domain=const.DOMAIN,
        options={"frequency": "weekly", "collection_days": ["mon"]},
        title="weekly",
        version=6,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"frequency": "weekly"}
    )
    assert const.CONF_ISO_WEEKS not in {str(k) for k in result["data_schema"].schema}

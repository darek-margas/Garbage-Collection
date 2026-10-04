"""Test scheduled updates, group updates, entity services and translations."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.garbage_collection import const

NOW_PATH = "custom_components.garbage_collection.helpers.now"


async def _setup(hass: HomeAssistant, title: str, **options) -> MockConfigEntry:
    """Create and set up a config entry."""
    config_entry: MockConfigEntry = MockConfigEntry(
        domain=const.DOMAIN,
        options={"frequency": "weekly", "collection_days": ["mon"], **options},
        title=title,
        version=6,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.mark.asyncio
async def test_midnight_update(hass: HomeAssistant) -> None:
    """The sensor is not polled; it recalculates at midnight."""
    await _setup(hass, "weekly")
    entity = hass.data[const.DOMAIN][const.SENSOR_PLATFORM]["sensor.weekly"]
    assert entity.should_poll is False
    assert hass.states.get("sensor.weekly").attributes["days"] == 5

    # Time listeners only fire for real future times: use the next real
    # midnight, while the integration sees April 2nd
    midnight = dt_util.start_of_local_day() + timedelta(days=1)
    with patch(NOW_PATH, return_value=datetime(2020, 4, 2, 0, 0, 0)):
        async_fire_time_changed(hass, dt_util.as_utc(midnight))
        await hass.async_block_till_done()
    assert hass.states.get("sensor.weekly").attributes["days"] == 4


@pytest.mark.asyncio
async def test_group_follows_member(hass: HomeAssistant) -> None:
    """A group recalculates when a member sensor is updated."""
    await _setup(hass, "member", manual_update=True)
    await _setup(hass, "group", frequency="group", entities=["sensor.member"])
    group = hass.states.get("sensor.group")
    assert group.attributes["next_date"].date() == date(2020, 4, 6)

    await hass.services.async_call(
        const.DOMAIN,
        "add_date",
        {"date": date(2020, 4, 2)},
        target={"entity_id": "sensor.member"},
        blocking=True,
    )
    # The member is updated after the group's last update
    with patch(NOW_PATH, return_value=datetime(2020, 4, 1, 12, 1, 0)):
        await hass.services.async_call(
            const.DOMAIN,
            "update_state",
            target={"entity_id": "sensor.member"},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert hass.states.get("sensor.member").attributes["days"] == 1
    group = hass.states.get("sensor.group")
    assert group.attributes["next_date"].date() == date(2020, 4, 2)


@pytest.mark.asyncio
async def test_collect_garbage_writes_state(hass: HomeAssistant) -> None:
    """Services update the state immediately, without waiting for a poll."""
    await _setup(hass, "today", collection_days=["wed"])
    assert hass.states.get("sensor.today").state == "0"
    await hass.services.async_call(
        const.DOMAIN,
        "collect_garbage",
        target={"entity_id": "sensor.today"},
        blocking=True,
    )
    sensor = hass.states.get("sensor.today")
    assert sensor.state == "2"
    assert sensor.attributes["days"] == 7


@pytest.mark.asyncio
async def test_next_date_local_midnight(hass: HomeAssistant) -> None:
    """next_date is local midnight in the Home Assistant time zone."""
    await _setup(hass, "weekly")
    next_date = hass.states.get("sensor.weekly").attributes["next_date"]
    assert next_date == dt_util.start_of_local_day(date(2020, 4, 6))


@pytest.mark.asyncio
async def test_state_translation(hass: HomeAssistant) -> None:
    """Verbose states are translated through the entity translation key."""
    await _setup(hass, "verbose", verbose_state=True)
    entity = hass.data[const.DOMAIN][const.SENSOR_PLATFORM]["sensor.verbose"]
    assert entity.translation_key == "schedule"
    translations = await async_get_translations(hass, "de", "entity", [const.DOMAIN])
    key = f"component.{const.DOMAIN}.entity.sensor.schedule.state.tomorrow"
    assert translations[key] == "Morgen"

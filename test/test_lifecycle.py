"""Test entry lifecycle: options reload, unload, calendar and diagnostics."""
from datetime import datetime, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.garbage_collection import const
from custom_components.garbage_collection.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def _setup(hass: HomeAssistant, title: str, **options) -> MockConfigEntry:
    """Create and set up a weekly config entry."""
    config_entry: MockConfigEntry = MockConfigEntry(
        domain=const.DOMAIN,
        options={"frequency": "weekly", "collection_days": ["mon"], **options},
        title=title,
        version=6,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == config_entries.ConfigEntryState.LOADED
    return config_entry


@pytest.mark.asyncio
async def test_options_update_reloads(hass: HomeAssistant) -> None:
    """Changing options reloads the entry and keeps the sensor."""
    config_entry = await _setup(hass, "weekly")
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, "collection_days": ["tue"]},
    )
    await hass.async_block_till_done()
    assert config_entry.state == config_entries.ConfigEntryState.LOADED
    # Restored state is replaced by the new schedule on the next poll
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.weekly")
    assert sensor is not None
    assert sensor.attributes["next_date"].date() == datetime(2020, 4, 7).date()


@pytest.mark.asyncio
async def test_unload_and_remove(hass: HomeAssistant) -> None:
    """Entries unload cleanly; the calendar survives removal of an entry."""
    first = await _setup(hass, "first")
    await _setup(hass, "second")
    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    assert first.state == config_entries.ConfigEntryState.NOT_LOADED
    await hass.config_entries.async_remove(first.entry_id)
    await hass.async_block_till_done()
    assert "sensor.first" not in hass.data[const.DOMAIN][const.SENSOR_PLATFORM]
    assert hass.states.get("calendar.garbage_collection") is not None
    events = await hass.data[const.DOMAIN][const.CALENDAR_PLATFORM].async_get_events(
        hass, datetime(2020, 4, 1), datetime(2020, 5, 1)
    )
    assert {event.summary for event in events} == {"second"}


@pytest.mark.asyncio
async def test_unload_hidden_only(hass: HomeAssistant) -> None:
    """Unloading a hidden sensor works when no calendar was created."""
    config_entry = await _setup(hass, "hidden", hidden=True)
    assert hass.states.get("calendar.garbage_collection") is None
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == config_entries.ConfigEntryState.NOT_LOADED


@pytest.mark.asyncio
async def test_calendar_expire_after(hass: HomeAssistant) -> None:
    """Calendar events with expire_after are timezone aware."""
    await _setup(hass, "expiring", expire_after="10:00:00")
    events = await hass.data[const.DOMAIN][const.CALENDAR_PLATFORM].async_get_events(
        hass, datetime(2020, 4, 1), datetime(2020, 5, 1)
    )
    assert len(events) == 4
    for event in events:
        assert event.start.tzinfo is not None
        assert event.end.tzinfo is not None
        assert event.end.hour == 10


@pytest.mark.asyncio
async def test_diagnostics(hass: HomeAssistant) -> None:
    """Diagnostics work for entries created in the UI."""
    config_entry = await _setup(hass, "weekly")
    data = await async_get_config_entry_diagnostics(hass, config_entry)
    assert data["entity_id"] == "sensor.weekly"
    assert data["config_entry"]["entry_id"] == config_entry.entry_id

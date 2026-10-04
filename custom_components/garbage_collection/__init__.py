"""Component to integrate with garbage_colection."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Dict

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from dateutil.relativedelta import relativedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_HIDDEN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import discovery, service
from homeassistant.helpers.typing import ConfigType, VolDictType

from . import const, helpers
from .calendar import EntitiesCalendarData

_LOGGER = logging.getLogger(__name__)

# Configured in the UI only
CONFIG_SCHEMA = cv.config_entry_only_config_schema(const.DOMAIN)

COLLECT_GARBAGE_SCHEMA: VolDictType = {
    vol.Optional(const.ATTR_LAST_COLLECTION): cv.datetime,
}

ADD_REMOVE_DATE_SCHEMA: VolDictType = {
    vol.Required(const.CONF_DATE): cv.date,
}

OFFSET_DATE_SCHEMA: VolDictType = {
    vol.Required(const.CONF_DATE): cv.date,
    vol.Required(const.CONF_OFFSET): vol.All(
        vol.Coerce(int), vol.Range(min=-31, max=31)
    ),
}


async def _async_add_date(entity: Any, call: ServiceCall) -> None:
    """Handle the add_date service call."""
    await entity.add_date(call.data[const.CONF_DATE])


async def _async_remove_date(entity: Any, call: ServiceCall) -> None:
    """Handle the remove_date service call."""
    await entity.remove_date(call.data[const.CONF_DATE])


async def _async_offset_date(entity: Any, call: ServiceCall) -> None:
    """Handle the offset_date service call."""
    collection_date = call.data[const.CONF_DATE]
    new_date = collection_date + relativedelta(days=call.data[const.CONF_OFFSET])
    await entity.remove_date(collection_date)
    await entity.add_date(new_date)


async def _async_update_state(entity: Any, _: ServiceCall) -> None:
    """Handle the update_state service call."""
    entity.update_state()
    entity.async_write_ha_state()


async def _async_collect_garbage(entity: Any, call: ServiceCall) -> None:
    """Handle the collect_garbage service call."""
    last_collection = call.data.get(const.ATTR_LAST_COLLECTION, helpers.now())
    entity.last_collection = dt_util.as_local(last_collection)
    entity.update_state()
    entity.async_write_ha_state()


SERVICES: Dict[str, tuple[VolDictType, Callable[[Any, ServiceCall], Any]]] = {
    "collect_garbage": (COLLECT_GARBAGE_SCHEMA, _async_collect_garbage),
    "update_state": ({}, _async_update_state),
    "add_date": (ADD_REMOVE_DATE_SCHEMA, _async_add_date),
    "remove_date": (ADD_REMOVE_DATE_SCHEMA, _async_remove_date),
    "offset_date": (OFFSET_DATE_SCHEMA, _async_offset_date),
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up platform - register services, inicialize data structure."""
    hass.data.setdefault(const.DOMAIN, {})
    hass.data[const.DOMAIN].setdefault(const.SENSOR_PLATFORM, {})
    hass.data[const.DOMAIN].setdefault(
        const.CALENDAR_PLATFORM, EntitiesCalendarData(hass)
    )
    hass.data[const.DOMAIN][const.HASS_CONFIG] = config
    for name, (schema, func) in SERVICES.items():
        service.async_register_platform_entity_service(
            hass,
            const.DOMAIN,
            name,
            entity_domain=const.SENSOR_PLATFORM,
            schema=schema,
            func=func,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    frequency = config_entry.options.get(const.CONF_FREQUENCY)
    if frequency not in [f["value"] for f in const.FREQUENCY_OPTIONS]:
        raise ConfigEntryError(f"Unknown collection frequency {frequency}")
    _LOGGER.debug(
        "Setting %s (%s) from ConfigFlow",
        config_entry.title,
        config_entry.options[const.CONF_FREQUENCY],
    )
    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    # Add sensor
    await hass.config_entries.async_forward_entry_setups(
        config_entry, [const.SENSOR_PLATFORM]
    )
    # The calendar is shared by all entries, so it is not bound to any of them
    if not config_entry.options.get(ATTR_HIDDEN, False):
        await async_ensure_calendar(hass)
    return True


async def async_ensure_calendar(hass: HomeAssistant) -> None:
    """Load the shared calendar platform once."""
    domain_data = hass.data[const.DOMAIN]
    if domain_data.get(const.CALENDAR_LOADED):
        return
    domain_data[const.CALENDAR_LOADED] = True
    _LOGGER.debug("Creating garbage collection calendar")
    await discovery.async_load_platform(
        hass,
        const.CALENDAR_PLATFORM,
        const.DOMAIN,
        {},
        domain_data.get(const.HASS_CONFIG, {}),
    )


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(
        config_entry, [const.SENSOR_PLATFORM]
    )


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.info(
        "Migrating %s from version %s", config_entry.title, config_entry.version
    )
    new_data: Dict[str, Any] = {**config_entry.data}
    new_options: Dict[str, Any] = {**config_entry.options}
    removed_data: Dict[str, Any] = {}
    removed_options: Dict[str, Any] = {}
    _LOGGER.debug("new_data %s", new_data)
    _LOGGER.debug("new_options %s", new_options)
    if config_entry.version == 1:
        to_remove = [
            "offset",
            "move_country_holidays",
            "holiday_in_week_move",
            "holiday_pop_named",
            "holiday_move_offset",
            "prov",
            "state",
            "observed",
            "exclude_dates",
            "include_dates",
        ]
        for remove in to_remove:
            if remove in new_data:
                removed_data[remove] = new_data[remove]
                del new_data[remove]
            if remove in new_options:
                removed_options[remove] = new_options[remove]
                del new_options[remove]
        if new_data.get(const.CONF_FREQUENCY) in const.MONTHLY_FREQUENCY:
            if const.CONF_WEEK_ORDER_NUMBER in new_data:
                new_data[const.CONF_WEEKDAY_ORDER_NUMBER] = new_data[
                    const.CONF_WEEK_ORDER_NUMBER
                ]
                new_data[const.CONF_FORCE_WEEK_NUMBERS] = True
                del new_data[const.CONF_WEEK_ORDER_NUMBER]
            else:
                new_data[const.CONF_FORCE_WEEK_NUMBERS] = False
            _LOGGER.info("Updated data config for week_order_number")
        if new_options.get(const.CONF_FREQUENCY) in const.MONTHLY_FREQUENCY:
            if const.CONF_WEEK_ORDER_NUMBER in new_options:
                new_options[const.CONF_WEEKDAY_ORDER_NUMBER] = new_options[
                    const.CONF_WEEK_ORDER_NUMBER
                ]
                new_options[const.CONF_FORCE_WEEK_NUMBERS] = True
                del new_options[const.CONF_WEEK_ORDER_NUMBER]
                _LOGGER.info("Updated options config for week_order_number")
            else:
                new_options[const.CONF_FORCE_WEEK_NUMBERS] = False
    if config_entry.version <= 4:
        if const.CONF_WEEKDAY_ORDER_NUMBER in new_data:
            new_data[const.CONF_WEEKDAY_ORDER_NUMBER] = list(
                map(str, new_data[const.CONF_WEEKDAY_ORDER_NUMBER])
            )
        if const.CONF_WEEKDAY_ORDER_NUMBER in new_options:
            new_options[const.CONF_WEEKDAY_ORDER_NUMBER] = list(
                map(str, new_options[const.CONF_WEEKDAY_ORDER_NUMBER])
            )
    if config_entry.version <= 5:
        for conf in [
            const.CONF_FREQUENCY,
            const.CONF_ICON_NORMAL,
            const.CONF_ICON_TODAY,
            const.CONF_ICON_TOMORROW,
            const.CONF_MANUAL,
            const.CONF_OFFSET,
            const.CONF_EXPIRE_AFTER,
            const.CONF_VERBOSE_STATE,
            const.CONF_FIRST_MONTH,
            const.CONF_LAST_MONTH,
            const.CONF_COLLECTION_DAYS,
            const.CONF_WEEKDAY_ORDER_NUMBER,
            const.CONF_FORCE_WEEK_NUMBERS,
            const.CONF_WEEK_ORDER_NUMBER,
            const.CONF_DATE,
            const.CONF_PERIOD,
            const.CONF_FIRST_WEEK,
            const.CONF_FIRST_DATE,
            const.CONF_SENSORS,
            const.CONF_VERBOSE_FORMAT,
            const.CONF_DATE_FORMAT,
        ]:
            if conf in new_data:
                new_options[conf] = new_data.get(conf)
                del new_data[conf]
        if (
            const.CONF_EXPIRE_AFTER in new_options
            and len(new_options[const.CONF_EXPIRE_AFTER]) == 5
        ):
            new_options[const.CONF_EXPIRE_AFTER] = (
                new_options[const.CONF_EXPIRE_AFTER] + ":00"
            )
    hass.config_entries.async_update_entry(
        config_entry,
        data=new_data,
        options=new_options,
        version=const.CONFIG_VERSION,
    )
    if removed_data:
        _LOGGER.error(
            "Removed data config %s. "
            "Please check the documentation how to configure the functionality.",
            removed_data,
        )
    if removed_options:
        _LOGGER.error(
            "Removed options config %s. "
            "Please check the documentation how to configure the functionality.",
            removed_options,
        )
    _LOGGER.info(
        "%s migration to version %s successful",
        config_entry.title,
        config_entry.version,
    )
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener - reload the entry after options update."""
    await hass.config_entries.async_reload(entry.entry_id)

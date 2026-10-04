"""Diagnostics support for Garbage Collection."""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    entities = hass.data[const.DOMAIN][const.SENSOR_PLATFORM]
    # Legacy (YAML-imported) entries carry their own unique_id
    unique_id = entry.data.get("unique_id", entry.entry_id)
    entity_data = next(
        (entity for entity in entities.values() if entity.unique_id == unique_id),
        None,
    )
    if entity_data is None:
        return {"config_entry": entry.as_dict()}
    data = {
        "entity_id": entity_data.entity_id,
        "state": entity_data.state,
        "attributes": entity_data.extra_state_attributes,
        "config_entry": entry.as_dict(),
    }
    return data

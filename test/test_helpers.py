"""Test helper functions."""

from datetime import date, datetime

import pytest

from custom_components.garbage_collection import helpers


@pytest.mark.asyncio
async def test_to_date() -> None:
    """Dates, datetimes and ISO strings all become plain dates."""
    assert helpers.to_date(date(2026, 10, 4)) == date(2026, 10, 4)
    result = helpers.to_date(datetime(2026, 10, 4, 15, 30))
    assert result == date(2026, 10, 4)
    assert type(result) is date
    assert helpers.to_date("2026-10-04") == date(2026, 10, 4)
    with pytest.raises(ValueError):
        helpers.to_date(None)

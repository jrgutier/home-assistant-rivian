"""Tests for Rivian recorder platform."""

from homeassistant.core import HomeAssistant

from custom_components.rivian.recorder import exclude_attributes


def test_exclude_attributes(hass: HomeAssistant) -> None:
    """Test that last_update is excluded from recording."""
    excluded = exclude_attributes(hass)
    assert excluded == {"last_update"}
    assert "last_update" in excluded

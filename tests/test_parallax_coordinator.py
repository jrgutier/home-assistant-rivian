"""Tests for ParallaxCoordinator."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestParallaxCoordinatorSubscription:
    """Test ParallaxCoordinator subscription lifecycle."""

    async def test_subscribes_to_all_rvms_on_first_refresh(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that coordinator subscribes to all RVM types (rvms=None)."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Trigger refresh
        await coordinator._async_update_data()

        # Assert subscribe_for_parallax_messages was called with rvms=None
        mock_client.subscribe_for_parallax_messages.assert_called_once()
        call_kwargs = mock_client.subscribe_for_parallax_messages.call_args.kwargs
        assert call_kwargs.get("rvms") is None
        assert call_kwargs.get("vehicle_id") == "test_vehicle_id"
        assert "callback" in call_kwargs

    async def test_stores_unsubscribe_handler(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that unsubscribe handler is stored."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_unsub = AsyncMock()
        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(return_value=mock_unsub)

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        await coordinator._async_update_data()

        # Assert unsubscribe handler is stored
        assert coordinator._unsub_handler is mock_unsub

    async def test_unsubscribes_on_shutdown(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that coordinator unsubscribes on shutdown."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_unsub = AsyncMock()
        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(return_value=mock_unsub)

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        await coordinator._async_update_data()
        await coordinator.async_shutdown()

        # Assert unsubscribe was called
        mock_unsub.assert_awaited_once()


class TestParallaxCoordinatorDataProcessing:
    """Test ParallaxCoordinator data processing."""

    async def test_processes_parallax_message_callback(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test processing Parallax message from subscription callback."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Simulate incoming Parallax message
        mock_data = {
            "payload": {
                "data": {
                    "parallaxMessages": {
                        "rvm": "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings",
                        "payload": "",  # Empty payload for test
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                }
            }
        }

        # Process the data
        coordinator._process_new_data(mock_data)

        # Assert data was stored
        rvm_key = (
            "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings"
        )
        assert rvm_key in coordinator._rvm_data

    async def test_handles_error_type_message(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test handling error type messages gracefully."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Simulate error message
        error_data = {
            "type": "error",
            "payload": [
                {"message": "Backend error", "extensions": {"rest": {"status": 504}}}
            ],
        }

        # Should not raise
        coordinator._process_new_data(error_data)

        # RVM data should remain empty
        assert len(coordinator._rvm_data) == 0

    async def test_handles_invalid_payload_structure(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test handling invalid payload structure gracefully."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Simulate invalid structure (missing data)
        invalid_data = {"payload": {}}

        # Should not raise
        coordinator._process_new_data(invalid_data)

        # RVM data should remain empty
        assert len(coordinator._rvm_data) == 0


class TestParallaxCoordinatorGetMethod:
    """Test ParallaxCoordinator.get() method."""

    async def test_get_returns_nested_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() returns nested values using dot notation."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Manually set RVM data
        coordinator._rvm_data = {
            "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings": {
                "data": {
                    "enabled": True,
                    "brightness": 80,
                    "animation_mode": "SPOOKY",
                },
                "timestamp": "2024-01-01T00:00:00Z",
            }
        }

        # Test get() with short key mapping
        assert coordinator.get("halloween.enabled") is True
        assert coordinator.get("halloween.brightness") == 80
        assert coordinator.get("halloween.animation_mode") == "SPOOKY"

    async def test_get_returns_default_for_missing_key(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() returns default for missing key."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Empty RVM data
        coordinator._rvm_data = {}

        # Test get() returns default
        assert coordinator.get("halloween.enabled") is None
        assert coordinator.get("halloween.enabled", False) is False
        assert coordinator.get("unknown.field", "default") == "default"

    async def test_get_returns_default_for_unknown_rvm(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() returns default for unknown RVM short key."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Set some data
        coordinator._rvm_data = {
            "some.rvm.type": {"data": {"value": 123}},
        }

        # Unknown short key should return default
        assert coordinator.get("unknown_rvm.field") is None
        assert coordinator.get("unknown_rvm.field", "default") == "default"

    async def test_get_cabin_ventilation_fields(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() for cabin ventilation fields."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        coordinator._rvm_data = {
            "comfort.cabin.cabin_ventilation_setting": {
                "data": {
                    "enabled": True,
                    "mode": "AUTO",
                    "windows_open_percent": 50,
                    "sunroof_open_percent": 25,
                    "duration_minutes": 30,
                },
                "timestamp": "2024-01-01T00:00:00Z",
            }
        }

        assert coordinator.get("cabin_ventilation.enabled") is True
        assert coordinator.get("cabin_ventilation.mode") == "AUTO"
        assert coordinator.get("cabin_ventilation.windows_open_percent") == 50
        assert coordinator.get("cabin_ventilation.sunroof_open_percent") == 25
        assert coordinator.get("cabin_ventilation.duration_minutes") == 30

    async def test_get_passive_entry_fields(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() for passive entry fields."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        coordinator._rvm_data = {
            "vehicle_access.passive_entry.passive_entry": {
                "data": {
                    "enabled": True,
                    "approach_distance_meters": 5.5,
                },
                "timestamp": "2024-01-01T00:00:00Z",
            }
        }

        assert coordinator.get("passive_entry_setting.enabled") is True
        assert coordinator.get("passive_entry_setting.approach_distance_meters") == 5.5

    async def test_get_gear_guard_fields(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() for gear guard consent fields."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        coordinator._rvm_data = {
            "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent": {
                "data": {
                    "video_enabled": True,
                    "audio_enabled": False,
                    "cloud_storage_enabled": True,
                    "local_storage_enabled": True,
                },
                "timestamp": "2024-01-01T00:00:00Z",
            }
        }

        assert coordinator.get("gear_guard_consents.video_enabled") is True
        assert coordinator.get("gear_guard_consents.audio_enabled") is False
        assert coordinator.get("gear_guard_consents.cloud_storage_enabled") is True


class TestParallaxCoordinatorPayloadDecoding:
    """Test ParallaxCoordinator protobuf decoding."""

    async def test_decode_unknown_rvm_returns_raw(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test decoding unknown RVM type returns raw payload."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Unknown RVM type
        rvm_type = "unknown.rvm.type"
        payload_b64 = "dGVzdA=="  # Base64 for "test"

        result = coordinator._decode_payload(rvm_type, payload_b64)

        assert result == {"raw": payload_b64}

    async def test_decode_empty_payload(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test decoding empty payload."""
        from custom_components.rivian.coordinator import ParallaxCoordinator

        mock_client = MagicMock()
        mock_client.subscribe_for_parallax_messages = AsyncMock(
            return_value=AsyncMock()
        )

        coordinator = ParallaxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
            vehicle_id="test_vehicle_id",
        )

        # Empty payload
        rvm_type = (
            "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings"
        )
        payload_b64 = ""

        result = coordinator._decode_payload(rvm_type, payload_b64)

        # Empty payload should return empty dict
        assert result == {}

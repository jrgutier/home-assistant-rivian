# Rivian Integration Tests

This directory contains tests for the Rivian Home Assistant custom integration, following the [Home Assistant testing methodology](https://developers.home-assistant.io/docs/development_testing/).

## Setup

Install test dependencies:

```bash
pip install -r requirements_test.txt
```

## Running Tests

### Run all tests

```bash
pytest
```

### Run specific test file

```bash
pytest tests/test_coordinator_watchdog.py
```

### Run specific test class

```bash
pytest tests/test_coordinator_watchdog.py::TestVehicleCoordinatorWatchdog
```

### Run specific test

```bash
pytest tests/test_coordinator_watchdog.py::TestVehicleCoordinatorWatchdog::test_watchdog_starts_after_subscription
```

### Run with coverage report

```bash
pytest --cov=custom_components.rivian --cov-report=html
```

Coverage report will be generated in `htmlcov/index.html`.

### Run with verbose output

```bash
pytest -v
```

### Run with output from print statements

```bash
pytest -s
```

## Test Structure

### `conftest.py`

Contains shared fixtures used across all tests:

- `mock_config_entry`: Mock Home Assistant config entry
- `mock_rivian_client`: Mock Rivian API client
- `mock_vehicle`: Vehicle record that platform entities are constructed from
- `mock_vehicle_paired`: `mock_vehicle` plus a phone identity, for control platforms
- `setup_integration`: Helper to set up the integration for testing
- `mock_vehicle_coordinator_with_parallax`: Mock `VehicleCoordinator` with Parallax support

### `test_init.py`

Tests for integration initialization and lifecycle (`__init__.py`):

#### Integration Setup Tests
- **test_setup_entry_success**: Verifies successful setup of config entry
- **test_setup_entry_api_error**: Verifies handling of API errors during setup
- **test_setup_entry_no_vehicle_data**: Verifies handling when no vehicle data is available
- **test_setup_entry_creates_2fa_issue_when_missing**: Verifies issue creation when 2FA is missing

#### Unload Tests
- **test_unload_entry_success**: Verifies successful unload of config entry
- **test_unload_entry_platforms_fail**: Verifies handling when platforms fail to unload

#### Removal Tests
- **test_remove_entry_with_enrolled_phone**: Verifies proper disenrollment during removal
- **test_remove_entry_without_public_key**: Verifies removal without phone enrollment

#### Update Tests
- **test_update_listener_reloads_entry**: Verifies config entry reload on options update

#### Device Management Tests
- **test_cannot_remove_vehicle_device**: Verifies vehicle devices cannot be removed
- **test_can_remove_non_vehicle_device**: Verifies non-vehicle devices can be removed

### `test_coordinator_watchdog.py`

Tests for the WebSocket subscription watchdog functionality:

#### VehicleCoordinator Watchdog Tests

- **test_watchdog_starts_after_subscription**: Verifies watchdog starts after successful subscription
- **test_watchdog_updates_timestamp_on_data**: Verifies timestamp updates when data is received
- **test_watchdog_skips_restart_when_sleeping**: Verifies watchdog doesn't restart when vehicle is sleeping
- **test_watchdog_restarts_subscription_when_stale**: Verifies watchdog restarts subscription after timeout
- **test_watchdog_stops_on_shutdown**: Verifies watchdog stops on coordinator shutdown
- **test_watchdog_doesnt_start_twice**: Verifies watchdog doesn't create duplicate tasks

#### ChargingCoordinator Watchdog Tests

- **test_watchdog_can_be_toggled**: Verifies watchdog can be enabled/disabled
- **test_watchdog_updates_timestamp_on_charging_data**: Verifies timestamp updates on charging data
- **test_watchdog_updates_timestamp_on_empty_session**: Verifies timestamp updates even for empty sessions
- **test_watchdog_stops_on_shutdown**: Verifies watchdog stops on shutdown

#### ChargerState Integration Tests

- **test_charging_watchdog_enabled_when_connected**: Verifies watchdog enables when charger connects
- **test_charging_watchdog_disabled_when_disconnected**: Verifies watchdog disables when charger disconnects
- **test_charging_watchdog_states**: Parametrized test for all charger states
- **test_charging_watchdog_not_toggled_if_state_unchanged**: Verifies no unnecessary toggles

## Writing New Tests

When adding new tests, follow these guidelines:

1. **Use fixtures**: Leverage shared fixtures from `conftest.py`
2. **Test organization**: Group related tests in classes
3. **Async tests**: Use `async def test_*` for async tests (pytest-asyncio handles this)
4. **Mocking**: Use `unittest.mock` for mocking external dependencies
5. **Assertions**: Use clear, specific assertions
6. **Documentation**: Add docstrings to test functions

### Example Test

```python
async def test_example(
    hass: HomeAssistant,
    mock_vehicle_coordinator: VehicleCoordinator,
) -> None:
    """Test description here."""
    # Arrange
    mock_vehicle_coordinator.data = {"test": "data"}

    # Act
    result = await mock_vehicle_coordinator.some_method()

    # Assert
    assert result == expected_value
```

## Continuous Integration

Tests should be run in CI/CD pipelines before merging changes. Consider adding:

- Pre-commit hooks to run tests locally
- GitHub Actions workflow for automated testing
- Code coverage requirements (e.g., minimum 80% coverage)

## Troubleshooting

### Tests timing out

If tests are timing out, you can:

1. Increase timeout: `pytest --timeout=60`
2. Disable timeout for specific test: Add `@pytest.mark.timeout(0)` decorator

### Import errors

If you get import errors, ensure:

1. You're running pytest from the repository root
2. Test dependencies are installed: `pip install -r requirements_test.txt`
3. The integration is importable: `pip install -e .` (if setup.py exists)

### Async warnings

If you see async warnings, ensure:

1. `pytest.ini` has `asyncio_mode = auto`
2. Test dependencies include `pytest-asyncio`

## Test Coverage Summary

### Current Test Coverage

The test suite currently covers:

#### Core Integration (`test_init.py`)
- ✅ Integration setup and initialization
- ✅ Config entry lifecycle (setup, unload, remove)
- ✅ Options update handling
- ✅ Device management
- ✅ Error handling (API errors, missing data)
- ✅ Issue creation for missing 2FA

#### Coordinators (`test_coordinator_watchdog.py`)
- ✅ VehicleCoordinator watchdog functionality
- ✅ ChargingCoordinator watchdog functionality
- ✅ Watchdog sleep state handling
- ✅ Subscription restart on stale connections
- ✅ ChargerState monitoring and integration
- ✅ Watchdog lifecycle (start, stop, shutdown)

### Recommended Future Tests

To achieve comprehensive coverage, consider adding tests for:

#### Entities
- `test_sensor.py`: Test sensor platform and sensor entities
- `test_binary_sensor.py`: Test binary sensor platform
- `test_button.py`: Test button entities and vehicle commands
- `test_switch.py`: Test switch entities
- `test_lock.py`: Test lock entities
- `test_cover.py`: Test cover entities (windows, tonneau, etc.)
- `test_climate.py`: Test climate control entities
- `test_device_tracker.py`: Test GPS location tracking
- `test_update.py`: Test OTA update entities

#### Services
- `test_notify.py`: Test navigation service

#### Config Flow
- `test_config_flow.py`: Test user authentication flow
- Test OTP/MFA handling
- Test options flow (vehicle control setup, zones)
- Test error handling in config flow

#### Other Coordinators
- `test_coordinator.py`: Test base coordinator functionality
- Test UserCoordinator
- Test DriverKeyCoordinator
- Test WallboxCoordinator
- Test error handling and rate limiting

### Test Coverage Goals

- **Target**: 80%+ code coverage
- **Critical paths**: 100% coverage for watchdog and initialization
- **Error handling**: All exception paths tested
- **Edge cases**: Sleep states, disconnections, empty data

Run coverage report to see current coverage:

```bash
pytest --cov=custom_components.rivian --cov-report=html
open htmlcov/index.html
```

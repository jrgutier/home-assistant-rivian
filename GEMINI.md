# Gemini Code Assistant Context

## Project: Home Assistant Rivian Integration

This project is an unofficial [Home Assistant](https://www.home-assistant.io/) integration for Rivian vehicles. It allows users to monitor and control their vehicles from within their Home Assistant instance.

### Key Features:

*   **Vehicle Monitoring:** Provides a wide range of sensors to monitor the vehicle's status, including battery level, range, climate, and more.
*   **Remote Control:** Allows users to control various aspects of the vehicle, such as locking/unlocking doors, opening/closing the frunk and tailgate, and controlling the climate.
*   **HACS Installation:** The integration is designed to be installed via the [Home Assistant Community Store (HACS)](https://hacs.xyz/).

### Project Structure:

The core logic of the integration is located in the `custom_components/rivian/` directory. This directory contains the following key files:

*   `manifest.json`: Contains metadata about the integration, such as the domain, version, and dependencies.
*   `config_flow.py`: Handles the configuration process for the integration, including user authentication and vehicle selection.
*   `coordinator.py`: Defines the data update coordinators that are responsible for fetching and managing data from the Rivian API.
*   `binary_sensor.py`, `climate.py`, `cover.py`, `lock.py`, `number.py`, `select.py`, `sensor.py`, `switch.py`, `update.py`: These files define the various Home Assistant entities that are created by the integration.

### Building and Running:

This is a Home Assistant integration, so it is not a standalone application. To use it, you need to have a running instance of Home Assistant.

The integration can be installed by adding the GitHub repository as a custom repository in HACS.

### Development Conventions:

The project follows the standard development conventions for Home Assistant integrations.

*   The code is written in Python and uses the `asyncio` library for asynchronous operations.
*   The project uses `black` for code formatting and `pylint` for linting.
*   The project uses a custom `rivian-python-client` library to interact with the Rivian API.

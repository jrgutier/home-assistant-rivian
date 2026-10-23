# Home Assistant integration for Rivian (Unofficial)

[![GitHub Release][releases-shield]][releases]
![GitHub all releases][download-all]
![GitHub release (latest by SemVer)][download-latest]
[![GitHub Activity][commits-shield]][commits]

An unofficial Rivian integration for Home Assistant, installed through [HACS](https://hacs.xyz/docs/setup/download). It streams your vehicle's state into Home Assistant in real time, and, once you pair it with the vehicle, lets you lock, open, heat, cool, charge and watch it the way the Rivian app does.

This repository is a fork of [bretterer/home-assistant-rivian](https://github.com/bretterer/home-assistant-rivian) and merges from it regularly.

## Requirements

- **Home Assistant 2025.6.0 or newer.** HACS will not offer the integration on anything older.
- A Rivian account with a driver profile on the vehicle, and its username and password.
- The account's MFA/OTP device, if MFA is on. MFA is required if you want vehicle control.
- The vehicle must be delivered and in your possession.

## What it does

- **Real-time vehicle state.** Doors, windows, closures and locks, battery and range, charging, tire pressure, climate, seats, Gear Guard, software updates, connectivity and location arrive over a push subscription rather than polling. Rivian's Parallax stream fills in data the subscription does not carry, such as parked energy use, trip target state of charge, climate hold and automatic ventilation, cold-weather range, navigation ETAs, scheduled software installs and the Gear Guard streaming allowance.
- **Remote vehicle control.** Lock and unlock, open the frunk, windows, charge port, liftgate, tonneau and gear tunnels, drop the tailgate, run cabin climate and climate hold, set seat and steering-wheel heat, set the charge limit, sound the alarm, wake the vehicle and install a software update. This needs a one-time Bluetooth pairing, for both Gen 1 and Gen 2 (2025+) vehicles. See [Remote vehicle control](#remote-vehicle-control).
- **Gear Guard live view.** A camera entity that streams the vehicle's cameras over WebRTC, with a picker for which camera to watch and a bundled dashboard card.
- **Charging.** Live session data (power, energy, cost, range added, time remaining), a charging schedule you can edit from Home Assistant without pairing, and sensors for a Rivian Wall Charger on the account.
- **Send a destination to the vehicle.** A notify service per vehicle that pushes an address or coordinates to the vehicle's navigation, with no pairing needed.
- **Vehicle images** of your vehicle's configuration, in illustrated or photo style.
- **Multiple vehicles** per account, each with its own device and entities.
- **Diagnostics** you can download from the device page when reporting a problem.

# Disclaimer

This [Home Assistant](https://www.home-assistant.io/) integration is not affiliated, associated, nor sponsored by Rivian Automotive, Inc.

Any use of this integration is at the sole discretion and risk of the Rivian vehicle owner integrating it into their Home Assistant installation. This owner takes full responsibility for protecting their local Home Assistant installation.

This integration is provided out of love and passion towards the Rivian ownership community. It focuses on building insights and awareness into the state of one's vehicle for use by the owner and the owner alone.

This integration will not share user or vehicle data outside Home Assistant, a single-user environment hosted and running within an owner's private network and hardware systems.

![Home Assistant Rivian Card](.github/images/home_assistant_rivian_entity_card.png)

## Installation

### HACS (recommended)

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `https://github.com/jrgutier/home-assistant-rivian` with the type **Integration**.
3. Search HACS for "Rivian (Unofficial)" and download it.
4. Restart Home Assistant.
5. [![Add Integration][add-integration-badge]][add-integration] or go to **Settings > Devices & services > Add integration** and search for "Rivian (Unofficial)".

### Manual

1. Download `rivian.zip` from the [latest release][releases].
2. Unzip it into `custom_components/rivian/` inside your Home Assistant configuration directory (the one with `configuration.yaml`), creating the folders if needed.
3. Restart Home Assistant, then add the integration as in step 5 above.

The integration declares only two Python requirements, `bleak` and `protobuf`, and Home Assistant installs them itself. No `git` or source build is needed.

### Upgrading

Some releases rename or re-type entities. Before upgrading, check [docs/MIGRATION.md](docs/MIGRATION.md) for anything your automations, scripts or dashboards reference.

## Configuration

To connect your newly installed integration to pull available sensor data for your Rivian vehicle, you should follow the following configuration recommendations. Not doing so could put your main Rivian account at risk of being locked and available.

- One Time Password (**recommended**) - It is best security practice always to enable One Time Password / Multi-Factor Authentication. This way, your credentials (username + password) can not be used without your explicit consent through the personal device configured on your Rivian account.
- No Account Reuse* (**recommended**) - Another best security practice is not to reuse accounts or credentials across different integrations (e.g., sharing credentials between Home Assistant and your everyday account). We highly recommend the owner *invite a new driver\*, for example, `user+<purpose>@domain.com`, and use only this profile for configuration within Home Assistant. **Note:** Sensors will not be displayed for this new driver until the driver is signed in to a Rivian phone app and linked to the vehicle like an actual new driver. You may temporarily sign out of your Rivian phone app to set up this driver profile: Profile icon (bottom nav bar) > "Manage account" > Sign out (top right corner).

The configuration flow is as follows:

1. **Username and Password (required)**
   - For the integration to work, we require a username and password to a Rivian account with an active _driver profile_ for the vehicle you wish to monitor remotely.
2. **OTP/MFA (optional)**
   - If OTP is enabled on the account provided, you will receive a text from Rivian with a one-time use passcode entered at this step.

If Rivian later asks you to sign in again, Home Assistant shows a re-authentication prompt rather than removing the integration.

### Options

Open **Configure** on the integration to set:

| Option | What it does |
| --- | --- |
| Vehicle image style | `cel` (illustrated, the default), `photo`, or `none` to skip vehicle images |
| Enable vehicle control | The vehicles to enroll a key for. This is what creates the control entities. Requires MFA on the account and a free phone-key slot on the vehicle |
| Limit vehicle control to zones | Optional Home Assistant zones. Control entities are only available while the vehicle is inside one of them |

\*Developers and Maintainers of this project take no personal responsibility for misconfiguration or misuse of the code provided by this integration. Account security is entirely the sole responsibility of the owner configuring this integration. Accounts may become locked/quarantined due to this unofficial integration.

## Remote Vehicle Control

In addition to viewing vehicle data, it is also possible to issue certain vehicle commands remotely via Home Assistant as you would in the Rivian mobile app. Commands are signed with a key Home Assistant enrolls on the vehicle and are sent through the Rivian cloud, waking the vehicle first if it is asleep.

To enable this feature, you need to have:

- Home Assistant instance with a Bluetooth adapter (or [ESP32 Bluetooth proxy](https://esphome.io/projects/?type=bluetooth)) with a minimum Bluetooth version of 4.2
  - The Bluetooth adapter/proxy needs to be within reach of your vehicle's Bluetooth radio to complete the one-time, in-vehicle pairing process
  - After pairing, Bluetooth is no longer required as commands are sent remotely via the Rivian cloud
- Two-factor authentication (2FA) enabled on your Rivian account
- An available slot for a phone key (currently limited to 4 per vehicle as of vehicle software 2023.26.00)

To complete the pairing setup, turn on **Enable vehicle control** for the vehicle(s) in the integration's options and then:

1. From within your vehicle, navigate to "Drivers and Keys" under settings
2. Select "Set Up" for the relevant phone key (this should be the name of your Home Assistant instance's home location, typically "Home")
3. Click on the "Pair" button entity for the associated vehicle in Home Assistant
   - Home Assistant will then attempt to connect to your vehicle and complete the pairing process. On Darwin (MacOS) based systems, a pop-up will appear which you will have to manually click to allow pairing. On Linux or Windows systems, this should happen automatically.
   - Once the key shows as paired, the Pair button is no longer created and can be deleted.

Note: If you are having issues with pairing your vehicle, we recommend investing in an ESP32 with Bluetooth proxy installed as it offers flexibility in placement and has been proven to work where other adapters have not.

### Gen 2 (2025+) vehicles

The Pair button detects a Gen 2 vehicle and runs its handshake, which differs from Gen 1. The protocol is ported from [walthowd/rivian-gen2-key-poc](https://github.com/walthowd/rivian-gen2-key-poc), which was tested on a 2026 R1S and checked byte for byte against the Android app. It has **not yet been tested from Home Assistant**, so please report how it goes:

- A local Linux (BlueZ) adapter, which is what most Home Assistant OS installs use, is expected to fail: BlueZ cannot see a Gen 2 vehicle's Bluetooth services. The log says so when this happens.
- An ESPHome Bluetooth proxy may work, but is untested.
- If pairing from Home Assistant fails, you can pair Home Assistant's key from a Mac instead. See [Gen 2 pairing](docs/development/GEN2_BLE_PROTOCOL.md#workaround-that-does-not-need-has-bluetooth).

### Command events

Every vehicle command fires events you can use in automations: `rivian_command_initiated` when it is sent, then `rivian_command_success` or `rivian_command_failed` when the vehicle answers. Each carries the `vehicle_id`, `command` and `command_id`.

## Gear Guard Live View

With vehicle control enabled, vehicles that support Gear Guard live view get a **Gear Guard Live** camera entity that streams over WebRTC, and a **Gear Guard Camera** select that picks which camera to watch: left, right, front and rear, plus the bed camera on an R1T and the interior camera where the vehicle has one.

The integration also registers a dashboard card that switches cameras without restarting the stream. Add it with:

```yaml
type: custom:rivian-gear-guard-card
camera: camera.<vehicle>_gear_guard_live
select: select.<vehicle>_gear_guard_camera
```

Live view uses the vehicle's Gear Guard streaming allowance. The **Gear Guard Streaming Daily Limit** and **Gear Guard Streaming Limit Reset** sensors show where it stands.

## Navigation

Each vehicle gets a notify service, `notify.rivian_<vehicle_name>_<last 6 of VIN>_navigation`, that sends a destination to the vehicle's navigation. It goes through the Rivian cloud, so it needs no pairing and works as soon as the integration is set up. The message can be a full address, a city and state, or `latitude,longitude`.

```yaml
service: notify.rivian_my_r1t_abc123_navigation
data:
  message: "123 Main Street, Anytown, CA 12345"
```

## Charging Schedule

The **Charging schedule enabled** switch, **Charging schedule start** and **end** times, and **Charging schedule amperage** number edit the vehicle's charging schedule. They do not need vehicle control or pairing. For automations there is also a `rivian.set_charging_schedule` action that takes a device, `start_time`, `end_time` and optional `start_day` / `end_day` (0 is Sunday).

## Available Entities

Entities are only created for hardware the vehicle reports. Where that depends on a specific feature, the "Only on vehicles with" column says which. Entities marked \* are disabled by default; enable them from the entity's settings.

### Sensors (146)

<details><summary>Show all sensors</summary>

| Name | Only on vehicles with |
| --- | --- |
| Active driver |  |
| Altitude |  |
| Battery Capacity |  |
| Battery Cell Type |  |
| Battery Needs LFP Calibration |  |
| Battery State of Charge |  |
| Bearing |  |
| Brake Fluid Level Low |  |
| Cabin Climate Hold Notification |  |
| Cabin Climate Hold Status |  |
| Cabin Climate Preconditioning Status |  |
| Cabin Climate Preconditioning Type |  |
| Cabin Climate Setpoint |  |
| Cabin Interior Temperature |  |
| Cabin Ventilation Duration | Automatic cabin ventilation |
| Cabin Ventilation Mode | Automatic cabin ventilation |
| Cabin Ventilation Sunroof Open | Automatic cabin ventilation |
| Cabin Ventilation Windows Open | Automatic cabin ventilation |
| Cellular Carrier |  |
| Cellular Mode |  |
| Cellular Signal Bars |  |
| Cellular Signal Strength |  |
| Charge Limit |  |
| Charge Port Door Next Action |  |
| Charge Port Status |  |
| Charge Schedule Amperage |  |
| Charge Schedule Window |  |
| Charger Derate Status |  |
| Charger Status |  |
| Charging Disabled |  |
| Charging Disabled AC Fault State |  |
| Charging Fault Chime |  |
| Charging schedule days |  |
| Charging State |  |
| Charging Time Estimation Validity |  |
| Charging Time Remaining |  |
| Charging Trip Target State of Charge |  |
| Charging Trip Target Time Remaining |  |
| Climate Hold Duration |  |
| Cold Range Impact |  |
| Cold Range Notification |  |
| Cold Weather SOC (Blue) |  |
| Cold Weather SOC (Green) |  |
| Consecutive Alarm Disabled Notification\* |  |
| Defrost/Defog Status |  |
| Digital Key Passive Entry Permission\* |  |
| Drive Mode |  |
| Favorite Locations |  |
| Front Left Seat Heating |  |
| Front Left Seat Ventilation |  |
| Front Left Tire Pressure |  |
| Front Left Tire Pressure Status |  |
| Front Left Window Calibration |  |
| Front Right Seat Heating |  |
| Front Right Seat Ventilation |  |
| Front Right Tire Pressure |  |
| Front Right Tire Pressure Status |  |
| Front Right Window Calibration |  |
| Gear Guard Streaming Consent | Gear Guard video streaming |
| Gear Guard Streaming Daily Limit | Gear Guard video streaming |
| Gear Guard Streaming Limit Reset | Gear Guard video streaming |
| Gear Guard Video Mode |  |
| Gear Guard Video Status |  |
| Gear Guard Video Terms Accepted\* |  |
| Gear Selector |  |
| Geo Location |  |
| GNSS Bearing Error |  |
| GNSS Horizontal Position Error |  |
| GNSS Speed Error |  |
| GNSS Vertical Position Error |  |
| Hood Next Action |  |
| HVAC Set Temperature |  |
| Known Location |  |
| Left Gear Tunnel Next Action | Gear tunnel (R1T) |
| Liftgate Next Action | Power liftgate (R1S) |
| Limited Acceleration (Cold) |  |
| Limited Regenerative Braking (Cold) |  |
| Navigation Distance to Next Stop |  |
| Navigation Next Stop ETA |  |
| Navigation Time to Next Stop |  |
| Navigation Trip ETA |  |
| Odometer |  |
| OTA Available Version Git Hash\* |  |
| OTA Available Version Number\* |  |
| OTA Available Version Week\* |  |
| OTA Available Version Year\* |  |
| OTA Available Version\* |  |
| OTA Current Version Git Hash\* |  |
| OTA Current Version Number\* |  |
| OTA Current Version Week\* |  |
| OTA Current Version Year\* |  |
| OTA Current Version\* |  |
| OTA Deployment Intent |  |
| OTA Download Progress |  |
| OTA Install Duration |  |
| OTA Install Progress\* |  |
| OTA Install Schedule |  |
| OTA Install Time |  |
| OTA Install Type |  |
| OTA Scheduled Install Time |  |
| OTA Software Category |  |
| OTA Status |  |
| OTA Status Current |  |
| Parked Energy Last 24 Hours | Parked energy monitoring |
| Parked Energy Last 8 Hours | Parked energy monitoring |
| Parked Energy Last Park Session | Parked energy monitoring |
| Passive Entry Unlock Fail Reason\* |  |
| Pet Comfort Status |  |
| Pet Comfort Temperature Status |  |
| Pet Mode Snapshot\* |  |
| Power State |  |
| Range |  |
| Range Threshold |  |
| Rear Hitch Status |  |
| Rear Left Seat Heating |  |
| Rear Left Tire Pressure |  |
| Rear Left Tire Pressure Status |  |
| Rear Left Window Calibration |  |
| Rear Right Seat Heating |  |
| Rear Right Tire Pressure |  |
| Rear Right Tire Pressure Status |  |
| Rear Right Window Calibration |  |
| Remote Charging Available |  |
| Right Gear Tunnel Next Action | Gear tunnel (R1T) |
| Secure Immobilizer Status\* |  |
| Speed |  |
| Steering Wheel Heating |  |
| Tailgate Next Action | Powered tailgate (R1T) |
| Third Row Left Seat Heating | Third-row heated seats (R1S) |
| Third Row Right Seat Heating | Third-row heated seats (R1S) |
| Trailer Status |  |
| Trip Target State of Charge |  |
| Trip Target Time Remaining |  |
| VAS Access CAN Faulted |  |
| VAS Secure Element Faulted |  |
| Wheels installed |  |
| WiFi Frequency |  |
| WiFi Link Speed |  |
| WiFi Network Name |  |
| WiFi Security Status |  |
| WiFi Signal Bars |  |
| WiFi Signal Strength |  |
| WiFi Station Disabled Reason |  |
| WiFi WPA Status |  |
| Windows Next Action |  |
| Wiper Fluid Level |  |

</details>

### Binary Sensors (50)

<details><summary>Show all binary sensors</summary>

| Name | Only on vehicles with |
| --- | --- |
| 12V Battery |  |
| Battery Thermal Runaway Propagation |  |
| Battery Thermal Status |  |
| Bluetooth Module Failure Status Door Front Left |  |
| Bluetooth Module Failure Status Door Front Right |  |
| Bluetooth Module Failure Status Fascia Front |  |
| Bluetooth Module Failure Status Fascia Rear |  |
| Bluetooth Module Failure Status Instrument Controls |  |
| Bluetooth Module Failure Status Overhead Console |  |
| Bluetooth Passive Entry in Digital Key Mode\* |  |
| Cabin Ventilation | Automatic cabin ventilation |
| Car Wash Mode |  |
| Charge Port Door |  |
| Closure State |  |
| Cloud Connected |  |
| Door State |  |
| Front Left Door |  |
| Front Left Door Lock |  |
| Front Left Tire Pressure Validity |  |
| Front Left Window |  |
| Front Right Door |  |
| Front Right Door Lock |  |
| Front Right Tire Pressure Validity |  |
| Front Right Window |  |
| Gear Guard |  |
| Gear Guard Alarm Status |  |
| Hood |  |
| Hood Lock |  |
| In Use State |  |
| Left Gear Tunnel | Gear tunnel (R1T) |
| Left Gear Tunnel Lock | Gear tunnel (R1T) |
| Liftgate | Power liftgate (R1S) |
| Liftgate Lock | Power liftgate (R1S) |
| Locked State |  |
| OTA Install Ready |  |
| Rear Left Door |  |
| Rear Left Door Lock |  |
| Rear Left Tire Pressure Validity |  |
| Rear Left Window |  |
| Rear Right Door |  |
| Rear Right Door Lock |  |
| Rear Right Tire Pressure Validity |  |
| Rear Right Window |  |
| Right Gear Tunnel | Gear tunnel (R1T) |
| Right Gear Tunnel Lock | Gear tunnel (R1T) |
| Service Mode |  |
| Tailgate |  |
| Tailgate Lock |  |
| Tonneau Cover | Powered tonneau (R1T) |
| Tonneau Cover Lock | Powered tonneau (R1T) |

</details>

### Other Entities

| Name | Domain | Description |
| --- | --- | --- |
| Location | Device Tracker | The vehicle's GPS position |
| Software | Update | Current and available software, with release notes and install progress |
| Vehicle images | Image | Pictures of your vehicle's configuration, in the style chosen in options |
| Charging Cost, Charging Energy Delivered, Charging Is Free, Charging Range Added, Charging Rate, Charging Speed, Charging Start Time, Charging Time Elapsed, Charging Time Remaining | Sensor | The current or last charging session, pushed live over Parallax |
| Drivers, Keys | Sensor | Drivers and phone keys on the vehicle |
| Amperage, Amperage maximum, Charging status, Power, Power maximum, Voltage, Voltage maximum | Sensor | One set per Rivian Wall Charger on the account |

### Remote Vehicle Controls

These are created only for vehicles with vehicle control enabled, except the charging schedule entities, which every vehicle gets.

| Name | Domain | Description |
| --- | --- | --- |
| Alarm | Switch | Sound/mute the alarm |
| Cabin Climate | Climate | Turn cabin climate on or off, set the temperature, and choose the LO, HI or Defrost/Defog preset |
| Charge Limit | Number | Set the battery charge limit percent |
| Charge Port Door | Cover | Open/close the charge port door, where the vehicle supports it |
| Charging Enabled | Switch | Enable/disable charging while plugged in and below the charge limit |
| Charging schedule amperage | Number | Set the charging schedule amperage limit. No pairing needed |
| Charging schedule enabled | Switch | Enable/disable the charging schedule. No pairing needed |
| Charging schedule end | Time | Set the charging schedule end time. No pairing needed |
| Charging schedule start | Time | Set the charging schedule start time. No pairing needed |
| Climate Hold | Switch | Keep the cabin conditioned after you leave the vehicle |
| Closures | Lock | Lock/unlock all closures |
| Drop Tailgate | Button | Drop the powered tailgate (R1T) |
| Front Left Seat Climate | Select | Set front left seat heat or ventilation level |
| Front Right Seat Climate | Select | Set front right seat heat or ventilation level |
| Gear Guard Camera | Select | Choose the camera Gear Guard Live streams |
| Gear Guard Live | Camera | Live view from the vehicle's cameras |
| Gear Guard Video | Switch | Enable/disable Gear Guard video |
| Hood | Cover | Open/close the front trunk |
| Liftgate | Cover | Open/close the power liftgate (R1S) |
| Open Gear Tunnel Left | Button | Open the left gear tunnel (R1T) |
| Open Gear Tunnel Right | Button | Open the right gear tunnel (R1T) |
| Open Liftgate\* | Button | Open the power liftgate (R1S) |
| Open Tailgate\* | Button | Open the powered tailgate (R1T) |
| Pair | Button | Start Bluetooth pairing from Home Assistant. Once pairing completes, this entity is no longer created and can be deleted |
| Rear Left Seat Heating | Select | Set rear left seat heat level |
| Rear Right Seat Heating | Select | Set rear right seat heat level |
| Software | Update | Install a software update once it is ready |
| Steering Wheel Heating | Switch | Turn steering wheel heat on/off |
| Third Row Left Seat Heating\* | Select | Set third-row left seat heat level (R1S with third-row heat) |
| Third Row Right Seat Heating\* | Select | Set third-row right seat heat level (R1S with third-row heat) |
| Tonneau Cover | Cover | Open/close the powered tonneau (R1T) |
| Wake | Button | Wake the vehicle |
| Windows | Cover | Vent/close all windows |

\* Disabled by default

## Special Thanks

- [bretterer](https://github.com/bretterer) - Created and maintains the upstream integration
- [jrgutier](https://github.com/jrgutier) - Helped with getting information on the Rivian API
- [tmack8001](https://github.com/tmack8001) - Helping with Development and Testing
- [natekspencer](https://github.com/natekspencer) - Keeping the integration up-to-date with changes from Home Assistant
- [walthowd](https://github.com/walthowd) - The [Gen 2 phone-key proof of concept](https://github.com/walthowd/rivian-gen2-key-poc) the Gen 2 pairing is ported from

---

[commits-shield]: https://img.shields.io/github/commit-activity/w/jrgutier/home-assistant-rivian?style=flat-square
[commits]: https://github.com/jrgutier/home-assistant-rivian/commits/master
[releases-shield]: https://img.shields.io/github/release/jrgutier/home-assistant-rivian.svg?style=flat-square
[releases]: https://github.com/jrgutier/home-assistant-rivian/releases
[download-all]: https://img.shields.io/github/downloads/jrgutier/home-assistant-rivian/total?style=flat-square
[download-latest]: https://img.shields.io/github/downloads/jrgutier/home-assistant-rivian/latest/total?style=flat-square
[add-integration]: https://my.home-assistant.io/redirect/config_flow_start?domain=rivian
[add-integration-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[rivian-discord]: https://discord.gg/jEc5RUPd

## Trademark Legal Notices

All product names, trademarks and registered trademarks in the images in this
repository, are property of their respective owners. All images in this
repository are used by the Home Assistant project for identification purposes
only.

The use of these names, trademarks and brands appearing in these image files,
do not imply endorsement.

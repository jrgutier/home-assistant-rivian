# Rivian Services Examples

This document provides examples of using the Rivian integration services.

## Set Charging Schedule

Sets a time window when the vehicle is allowed to charge. This is useful for taking advantage of off-peak electricity rates.

### Parameters

- `device_id` (required): The Rivian vehicle device
- `start_time` (required): Time when charging is allowed to start (HH:MM format, 24-hour)
- `end_time` (required): Time when charging must stop (HH:MM format, 24-hour)
- `start_day` (optional): Day of week when schedule starts (0=Sunday, 6=Saturday). Default: 0
- `end_day` (optional): Day of week when schedule ends (0=Sunday, 6=Saturday). Default: 6

### Example: Charge only during off-peak hours (10 PM to 6 AM, every day)

```yaml
service: rivian.set_charging_schedule
target:
  device_id: <your_rivian_device_id>
data:
  start_time: "22:00"
  end_time: "06:00"
```

### Example: Charge only on weekdays during off-peak hours

```yaml
service: rivian.set_charging_schedule
target:
  device_id: <your_rivian_device_id>
data:
  start_time: "22:00"
  end_time: "06:00"
  start_day: 1  # Monday
  end_day: 5    # Friday
```

### Example Automation: Set charging schedule based on electricity rate

```yaml
automation:
  - alias: "Set Rivian Charging Schedule - Off Peak"
    trigger:
      - platform: time
        at: "22:00:00"  # Off-peak starts
    action:
      - service: rivian.set_charging_schedule
        target:
          device_id: <your_rivian_device_id>
        data:
          start_time: "22:00"
          end_time: "06:00"
```

## Set Geofences

Sets favorite geofences for the vehicle. Geofences can be used to trigger vehicle behaviors when entering or leaving specific locations.

### Parameters

- `device_id` (required): The Rivian vehicle device
- `fences` (required): JSON array of geofence definitions. Each fence must have:
  - `fence_id`: Unique identifier for the fence
  - `name`: Display name for the fence
  - `latitude`: Latitude coordinate (decimal degrees)
  - `longitude`: Longitude coordinate (decimal degrees)
  - `radius_meters`: Radius of the geofence in meters
  - `enabled`: Boolean indicating if the fence is active

### Example: Set home and work geofences

```yaml
service: rivian.set_geofences
target:
  device_id: <your_rivian_device_id>
data:
  fences: |
    [
      {
        "fence_id": "home",
        "name": "Home",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "radius_meters": 100,
        "enabled": true
      },
      {
        "fence_id": "work",
        "name": "Work",
        "latitude": 37.7849,
        "longitude": -122.4094,
        "radius_meters": 150,
        "enabled": true
      }
    ]
```

### Example: Set a single geofence

```yaml
service: rivian.set_geofences
target:
  device_id: <your_rivian_device_id>
data:
  fences: |
    [
      {
        "fence_id": "home",
        "name": "Home",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "radius_meters": 100,
        "enabled": true
      }
    ]
```

### Example Automation: Update geofences when moving

```yaml
automation:
  - alias: "Update Rivian Geofences"
    trigger:
      - platform: state
        entity_id: input_text.current_location
    action:
      - service: rivian.set_geofences
        target:
          device_id: <your_rivian_device_id>
        data:
          fences: |
            [
              {
                "fence_id": "current_location",
                "name": "{{ states('input_text.current_location') }}",
                "latitude": {{ state_attr('device_tracker.phone', 'latitude') }},
                "longitude": {{ state_attr('device_tracker.phone', 'longitude') }},
                "radius_meters": 200,
                "enabled": true
              }
            ]
```

## Finding Your Device ID

To find your Rivian vehicle's device ID:

1. Go to **Settings** → **Devices & Services**
2. Click on the **Rivian** integration
3. Click on your vehicle device
4. The device ID will be in the URL: `...config/devices/device/<device_id>`

Alternatively, you can use the device picker in the Home Assistant UI when calling the service, which will automatically fill in the device ID.

## Important Notes

- **Parallax Commands**: Both services use Rivian's Parallax protocol, which operates through the cloud API
- **No Bluetooth Required**: Unlike vehicle commands (lock/unlock, climate), these services do NOT require Bluetooth pairing
- **Cloud-Based**: These are fire-and-forget operations that send the request to Rivian's cloud
- **Immediate Availability**: These services are available immediately after integration setup
- **Error Handling**: If a service call fails, check the Home Assistant logs for detailed error messages

## Troubleshooting

### Service not found
- Ensure the Rivian integration is properly loaded
- Check Home Assistant logs for any errors during integration startup
- Try reloading the integration: **Settings** → **Devices & Services** → **Rivian** → **⋮** → **Reload**

### Device not found
- Verify you're using the correct device ID
- Ensure the vehicle is properly configured in the Rivian integration
- Check that the integration has successfully loaded vehicle data

### Invalid parameters
- Check that time formats are HH:MM (24-hour format)
- Ensure geofence JSON is properly formatted
- Validate that all required fields are present in geofence definitions
- Check logs for specific validation error messages

# WebSocket Subscription Improvements

## Summary of Changes

This update addresses two key issues with WebSocket subscriptions:
1. **Staleness Detection**: Immediate restart on backend errors instead of waiting 5 minutes
2. **Resource Optimization**: Charging subscription lifecycle management to reduce bandwidth

---

## Issue 1: WebSocket Subscription Staleness

### Problem Summary

WebSocket subscriptions were becoming stale every 20-25 minutes, requiring the watchdog to detect the issue and restart them after a 5-minute timeout.

## Root Cause

Analysis of Home Assistant logs revealed:

1. **Backend 504 Errors**: Rivian's backend server (`cesium.vcs.goriv.co`) was intermittently returning `504 Gateway Time-out` errors
2. **Silent Subscription Failure**: When these errors occurred, the GraphQL subscription stopped sending updates, but the WebSocket connection itself remained "active"
3. **Delayed Detection**: The watchdog could only detect staleness after 5 minutes of no updates, leading to gaps in data

### Timeline of a Typical Failure

```
07:45:59 - Updates flowing normally (GPS, battery data, etc.)
07:47:03 - 504 Gateway Timeout from cesium.vcs.goriv.co/v2/vehicle/latest
         - Subscription stops sending updates
         - WebSocket connection stays "active" (appears healthy)
07:51:03 - Watchdog detects staleness (5.1 minutes) and restarts subscription
         - Updates immediately resume
```

### Error Message Structure

The 504 errors come through the subscription callback with this structure:

```json
{
  "type": "error",
  "payload": [{
    "message": "Status unaccounted for 504",
    "extensions": {
      "rest": {
        "status": 504,
        "url": "https://cesium.vcs.goriv.co/v2/vehicle/latest"
      },
      "reason": "INVALID_REST_RESPONSE",
      "code": "INTERNAL_SERVER_ERROR"
    }
  }]
}
```

## Solution

Added proactive error detection in both `VehicleCoordinator` and `ChargingCoordinator`:

1. **Error Type Detection**: Check for `type: "error"` in subscription callbacks
2. **HTTP Status Extraction**: Parse the error payload to extract HTTP status codes
3. **Immediate Restart**: When 502/504 errors are detected, immediately unsubscribe and resubscribe
4. **Better Logging**: Log the specific error and HTTP status code for debugging

### Code Changes

Modified `custom_components/rivian/coordinator.py`:

- Added error detection in `VehicleCoordinator._process_new_data()` (lines 684-720)
- Added error detection in `ChargingCoordinator._process_new_data()` (lines 233-267)

### Benefits

- **Faster Recovery**: Subscriptions restart immediately (~1 second) instead of waiting 5 minutes
- **Better Diagnostics**: Clear logging shows when backend errors occur and which HTTP status
- **Reduced Data Gaps**: Minimizes the time window when vehicle state updates are missed
- **Proactive vs Reactive**: Responds to actual errors instead of waiting for timeout

## Testing

To test this fix:

1. Restart Home Assistant with the updated code
2. Monitor logs for "subscription received backend error" messages
3. Verify subscriptions restart immediately when backend errors occur
4. Confirm watchdog still catches any other staleness scenarios

## Expected Log Output

### Before (watchdog detection after 5 minutes):
```
WARNING Vehicle 01-276948064 subscription stale, no updates for 5.5 minutes (powerState: ready).
Subscription #2 age: 25.0 min, WebSocket state: active, online: True. Restarting...
```

### After (immediate error detection):
```
WARNING Vehicle 01-276948064 subscription received backend error: Status unaccounted for 504 (HTTP 504).
Subscription #2 age: 4.0 min, WebSocket state: active. Restarting subscription...
```

## Notes

- The watchdog is still active and will catch any staleness not caused by backend errors
- This fix only handles 502/504 errors; other error types will use existing error handling
- Both vehicle state and charging subscriptions now have this protection

---

## Issue 2: Charging Subscription Always Active

### Problem Summary

The charging subscription was always active (24/7), even when the vehicle was not charging. This consumed unnecessary WebSocket bandwidth and server resources.

### Previous Behavior

```
ChargingCoordinator:
├── Subscription: ❌ Always active (24/7)
└── Watchdog: ✅ Only enabled when charging
```

### Root Cause

The `ChargingCoordinator` would create a subscription at startup and keep it active indefinitely. The subscription would receive updates continuously, including empty charging session data when not charging: `{"chargingSession": []}`.

While the watchdog was properly toggled on/off based on charging state, the subscription itself was never unsubscribed.

### Solution

Added subscription lifecycle management that mirrors the watchdog toggle:

1. **New `toggle_subscription()` Method**: Added to `ChargingCoordinator` to enable/disable the subscription
2. **Subscription Enabled Flag**: Added `_subscription_enabled` to track when subscription should be active
3. **Smart Update Logic**: Modified `_async_update_data()` to skip subscription creation when disabled
4. **Integration with VehicleCoordinator**: Calls `toggle_subscription()` when charger state changes

### Code Changes

Modified `custom_components/rivian/coordinator.py`:

**ChargingCoordinator:**
- Added `_subscription_enabled` flag (line 145)
- Added early return in `_async_update_data()` when disabled (lines 149-155)
- Added `toggle_subscription()` method (lines 428-450)

**VehicleCoordinator:**
- Updated charger state monitoring to call `toggle_subscription()` (lines 851-854)

### New Behavior

```
ChargingCoordinator:
├── Subscription: ✅ Only active when charging
└── Watchdog: ✅ Only enabled when charging
```

**Lifecycle:**
1. Vehicle plugs in → chargerState changes to `charging_active`, `chg_station_connected`, etc.
2. VehicleCoordinator detects state change
3. Calls `charging_coordinator.toggle_subscription(True)` and `toggle_watchdog(True)`
4. Subscription is created and watchdog starts monitoring
5. Vehicle unplugs → chargerState changes to `chg_station_disconnected`, etc.
6. VehicleCoordinator calls `toggle_subscription(False)` and `toggle_watchdog(False)`
7. Subscription is destroyed and watchdog stops

### Benefits

- **Reduced Bandwidth**: No charging data received when not charging
- **Lower Server Load**: One less subscription per vehicle on Rivian's backend
- **Clean Architecture**: Subscription lifecycle matches its purpose (charging sessions only)
- **Consistent Behavior**: Watchdog and subscription both follow charging state

### Testing

Added 3 new tests in `test_coordinator_watchdog.py`:
- `test_charging_subscription_enabled_when_charging_starts`
- `test_charging_subscription_disabled_when_charging_stops`
- `test_charging_subscription_not_created_when_disabled`

### Expected Log Output

**When charging starts:**
```
INFO Enabling charging subscription for vehicle 01-276948064 (charger connected)
DEBUG Creating charging subscription #1 for vehicle 01-276948064
DEBUG Started charging watchdog for vehicle 01-276948064
```

**When charging stops:**
```
INFO Disabling charging subscription for vehicle 01-276948064 (charger disconnected)
DEBUG Unsubscribing from charging subscription #1 for vehicle 01-276948064
DEBUG Stopped charging watchdog for vehicle 01-276948064
```

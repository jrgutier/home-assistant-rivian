# Migration notes

Breaking changes that require you to edit automations, scripts, dashboards or templates.
Nothing here happens silently — if an entity ID changed, it is listed.

## Twelve sensors became binary sensors

**What breaks:** the entity ID's domain changes, `sensor.*` → `binary_sensor.*`. Home Assistant
does not follow that rename. Anything naming the old ID — an automation trigger, a template, a
dashboard card, a history graph — stops resolving and silently reads as unavailable.

**Why:** each of these fields carries exactly two meaningful values in the Rivian app's own model.
Modelling a two-state field as a text sensor meant no `on`/`off` state, no `problem` styling, no
working `to: "on"` trigger, and no red "Detected" badge. The full reasoning, and the evidence for
each field's vocabulary, is in
[`docs/development/BINARY_SENSOR_AUDIT.md`](development/BINARY_SENSOR_AUDIT.md).

Replace `<name>` with your vehicle's slug, e.g. `sensor.r1t_service_mode`.

| Old entity | New entity | `on` means | Off state |
|---|---|---|---|
| `sensor.<name>_bluetooth_module_failure_status_fascia_front` | `binary_sensor.<name>_bluetooth_module_failure_status_fascia_front` | `detected` — a fault is present | `not_detected` |
| `sensor.<name>_bluetooth_module_failure_status_overhead_console` | `binary_sensor.<name>_bluetooth_module_failure_status_overhead_console` | `detected` | `not_detected` |
| `sensor.<name>_bluetooth_module_failure_status_fascia_rear` | `binary_sensor.<name>_bluetooth_module_failure_status_fascia_rear` | `detected` | `not_detected` |
| `sensor.<name>_bluetooth_module_failure_status_instrument_controls` | `binary_sensor.<name>_bluetooth_module_failure_status_instrument_controls` | `detected` | `not_detected` |
| `sensor.<name>_bluetooth_module_failure_status_door_front_right` | `binary_sensor.<name>_bluetooth_module_failure_status_door_front_right` | `detected` | `not_detected` |
| `sensor.<name>_bluetooth_module_failure_status_door_front_left` | `binary_sensor.<name>_bluetooth_module_failure_status_door_front_left` | `detected` | `not_detected` |
| `sensor.<name>_battery_thermal_status` | `binary_sensor.<name>_battery_thermal_status` | `detected` — thermal event present | `undetected` |
| `sensor.<name>_battery_thermal_runaway_propagation` | `binary_sensor.<name>_battery_thermal_runaway_propagation` | `detected` | `undetected` |
| `sensor.<name>_gear_guard_alarm_status` | `binary_sensor.<name>_gear_guard_alarm_status` | `active` **or** `true` — alarm sounding | `inactive` / `false` |
| `sensor.<name>_12v_battery` | `binary_sensor.<name>_12v_battery` | `low` — **on means unhealthy** | `ok` |
| `sensor.<name>_service_mode` | `binary_sensor.<name>_service_mode` | `on` — vehicle in service mode | `off` |
| `sensor.<name>_ota_install_ready` | `binary_sensor.<name>_ota_install_ready` | `available` — update ready to install | `not_available` |

Two rows deserve a second look before you port a template:

- **`12v_battery` inverts.** The sensor read `OK` when healthy; the binary sensor is `on`
  when the battery is **`low`**. A template that checked `== 'OK'` becomes `is_state(..., 'off')`,
  not `'on'`.
- **`gear_guard_alarm_status` accepts two spellings.** The field has been observed carrying both
  `active`/`inactive` and `true`/`false`, so both map to `on`. You do not need to handle the
  difference yourself.

### Porting examples

```yaml
# before
- condition: template
  value_template: "{{ states('sensor.r1t_service_mode') == 'On' }}"
# after
- condition: state
  entity_id: binary_sensor.r1t_service_mode
  state: "on"

# before -- note the inversion
- condition: template
  value_template: "{{ states('sensor.r1t_12v_battery') != 'OK' }}"
# after
- condition: state
  entity_id: binary_sensor.r1t_12v_battery
  state: "on"
```

### Three that look similar but did NOT change

Listed so you don't go hunting for renames that never happened:

| Sensor | Why it stayed a sensor |
|---|---|
| `sensor.<name>_wiper_fluid_level` | Three states (`normal` / `low` / `empty`), not two |
| `sensor.<name>_brake_fluid_level_low` | No vocabulary evidence in the app at all — not guessed into a boolean |
| `sensor.<name>_ota_deployment_intent` | Two values, but `unspecified` is the absence of an answer, not the negation of `performance_upgrade` |

## New entity

`sensor.<name>_charge_port_status` — the charge port's full state (`open`, `close`,
`in_transition`, `fault`, `opening`, `closing`), alongside the existing
`binary_sensor.<name>_charge_port_door`. Nothing breaks; the binary sensor stays. It exists because
the port has five meaningful states and a boolean can only carry one question about them. This
mirrors `powerState`, which has carried both a binary sensor and a sensor for some time.

## Behaviour change without an entity change

Doors, windows and closures previously reported **Closed** for any value other than the exact
string `open`. The Rivian app treats `opened` as open too, and `ajar` as open for the frunk.

So a **frunk left ajar reported Closed** — not `unknown`, but a confident Closed. A "close the
frunk before leaving" automation never fired on it. Those descriptions now accept the full set.

No entity ID or device class changed. If you built a workaround for this — reading
`state_attr('binary_sensor.<name>_hood', 'value')` and comparing to `'ajar'` yourself — it still
works, but it is no longer necessary.

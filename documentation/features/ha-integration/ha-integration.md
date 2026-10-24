# Home Assistant Integration

- Owner: Edward (backend logic)
- Tech: Python, Home Assistant custom component
- Location: `custom_components/grill_master/`

## Overview

Custom Home Assistant integration for the LG1000BL (Black Label series). Communicates with the grill's ESP32 Mongoose OS controller via local HTTP JSON-RPC. Provides temperature monitoring, status tracking, grill control, and optional cloud sync to a PHP backend.

## Architecture

```
Home Assistant
  └── custom_components/grill_master/
        │
        ├── DataUpdateCoordinator (polls every 5s)
        │     │
        │     ├──► GET http://<ip>/rpc/PB.GetState
        │     │     └── Decodes FE0B (status) + FE0C (temperatures)
        │     │
        │     └──► POST to cloud PHP endpoint (optional, fire-and-forget)
        │
        ├── Sensor entities (grill temp, probes, set point)
        ├── Binary sensor entities (power, errors, fan, light, motor)
        ├── Climate entity (set temperature, HEAT/OFF mode)
        └── Switch entity (light on/off)
```

## Key Files

| File | Purpose |
|---|---|
| `const.py` | Domain, defaults, hex command constants, temperature limits |
| `decoder.py` | Pure Python port of pytboss FE0B/FE0C hex payload decoding |
| `api.py` | `GrillMasterApi` - aiohttp HTTP client for all RPC calls |
| `coordinator.py` | `GrillMasterCoordinator` - polling, decoding, cloud sync |
| `config_flow.py` | Two-step UI setup: grill IP + optional cloud sync |
| `__init__.py` | Entry setup, coordinator init, platform forwarding |
| `sensor.py` | 5 temperature sensors (grill, set point, probe 1/2, probe 1 target) |
| `binary_sensor.py` | 11 binary sensors (power, fan, light, motor, heater, errors) |
| `climate.py` | Climate entity for temperature control (180-600F, 5F steps) |
| `switch.py` | Light switch entity |

## Payload Decoding

Ported from `pytboss` (github.com/dknowles2/pytboss) Control Board 8 JavaScript functions.

### Temperature Encoding

The MCU encodes temperatures as 3 separate bytes: hundreds, tens, ones.
- `convert_temperature(parts, offset)` reads 3 bytes and returns `h*100 + t*10 + o`
- Example: bytes `[0, 9, 6]` at offset = 96 degrees

The grill's control panel can be switched to Celsius (`FE0902FF`). Confirmed
against a live LG1000BL: doing so changes the **unit of the raw digits**
FE0C transmits, not just how they're shown on the grill's own screen (a
180F set point became raw `082`). `decode_temperatures()` reads the
`is_fahrenheit` flag (offset 23) and normalizes every temperature field
back to Fahrenheit via `_normalize_to_fahrenheit()`, so the rest of the
integration (bounds, climate entity, alarms) always sees Fahrenheit
regardless of the panel's current unit setting. `0` is left unconverted -
it's the MCU's "no reading" placeholder, not a real measurement.

FE0B's own `is_fahrenheit` bit (offset 36) is **not** used for this - it
has been observed to disagree with FE0C's in the same `PB.GetState` call
(see `grill-communication` trail). This doesn't affect the integration
since the coordinator merges FE0C after FE0B, so FE0C's normalized values
always win.

### FE0C (Temperature Payload) - `sc_12`

| Offset | Field | Type |
|--------|-------|------|
| 2-4 | Probe 1 Target | Temperature (3 bytes) |
| 5-7 | Probe 1 Temp | Temperature (3 bytes) |
| 8-10 | Probe 2 Temp | Temperature (3 bytes) |
| 11-13 | Probe 3 Temp | Temperature (3 bytes) |
| 14-16 | Probe 4 Temp | Temperature (3 bytes) |
| 17-19 | Grill Set Temp | Temperature (3 bytes) |
| 20-22 | Grill Temp | Temperature (3 bytes) |
| 23 | Is Fahrenheit | Boolean (1=F, 0=C) |

### FE0B (Status Payload) - `sc_11`

| Offset | Field | Type |
|--------|-------|------|
| 2-4 | Probe 1 Target | Temperature |
| 5-7 | Probe 1 Temp | Temperature |
| 8-10 | Probe 2 Temp | Temperature |
| 11-13 | Probe 3 Temp | Temperature |
| 14-16 | Probe 4 Temp | Temperature |
| 21 | Module Is On | Boolean |
| 22 | Error 1 | Boolean |
| 23 | Error 2 / Message Type | Boolean/Flag |
| 24 | Error 3 | Boolean |
| 25 | High Temp Error | Boolean |
| 26 | Fan Error | Boolean |
| 27 | Igniter Error | Boolean |
| 28 | Motor Error | Boolean |
| 29 | No Pellets | Boolean |
| 30 | ErL | Boolean |
| 31 | Fan State | Boolean |
| 32 | Hot State | Boolean |
| 33 | Motor State | Boolean |
| 34 | Light State | Boolean |
| 35 | Prime State | Boolean |
| 36 | Is Fahrenheit | Boolean |
| 37 | Recipe Step | Integer |
| 38-40 | Recipe Time | h*3600 + m*60 + s |

### Set Temperature Command Encoding

`FE0501` + hex(hundreds) + hex(tens) + hex(ones) + `FF`
- Example: 250F → `FE050102050000FF`

## Cloud Sync

When enabled in config flow, the coordinator POSTs a JSON payload to the configured URL on every poll cycle.

**Payload format**:
```json
{
  "grill_temp": 275,
  "grill_set_temp": 250,
  "p1_temp": 195,
  "p2_temp": 0,
  "module_is_on": true,
  "is_fahrenheit": true,
  "timestamp": "2026-03-18T20:00:00+00:00",
  "host": "192.168.1.100"
}
```

**Behavior**:
- Fire-and-forget: cloud sync failure never blocks local monitoring
- 10-second timeout on cloud POST
- Errors logged at DEBUG level (silent failure)

## Config Flow

Two-step setup via Home Assistant UI:

1. **Grill Connection**: IP address (validated via RPC.Ping), name, poll interval
2. **Cloud Sync** (optional): enable toggle + endpoint URL

Unique ID set from `Sys.GetInfo` device ID to prevent duplicate entries.

## Installation

Copy `custom_components/grill_master/` to the Home Assistant `custom_components/` directory and restart HA. Add via Settings > Devices & Services > Add Integration > "Grill Master".

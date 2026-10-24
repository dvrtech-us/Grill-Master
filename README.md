# GrillMaster - Home Assistant Integration

A custom [Home Assistant](https://www.home-assistant.io/) integration for monitoring and controlling pellet grills over the local network via HTTP JSON-RPC.

Built for the **LG1000BL (Black Label)** series, with board profiles for Control Board 8 and Nexgrill/Broil King Mongoose OS controllers.

> **Disclaimer**: This project is **unofficial** and is not affiliated with, endorsed by, sponsored by, or supported by any grill manufacturer. All product names, trademarks, and registered trademarks are property of their respective owners. This software communicates with the grill's local network interface using reverse-engineered protocols — use at your own risk.

## Features

- **Temperature Monitoring** — Grill temperature, set point, and up to 4 meat probe temperatures, updating every 5 seconds
- **Grill Control** — Set target temperature (180-600F in 5F increments), turn grill off
- **Light Control** — Toggle the grill light on/off
- **Status Monitoring** — Fan, auger motor, heater, primer states plus error detection (no pellets, high temp, igniter, fan, motor errors)
- **DHCP Discovery** — Automatically detects the grill on your network and handles IP address changes
- **Cloud Sync** (optional) — POST temperature data to a configurable URL on every poll cycle

## Supported Hardware

WiFi-enabled pellet grills using the Mongoose OS ESP32 controller can use Grill Master's supported board profiles. Board support is selected from the controller device ID because these boards do not all share RPC methods or MCU command formats.

### Tested

| Manufacturer     | Model                       | Control Board | Temp Range | Probes | Light |
| ---------------- | --------------------------- | ------------- | ---------- | ------ | ----- |
| Louisiana Grills | LG1000BL (Black Label 1000) | 8             | 180-600F   | 2      | No    |

### Protocol Validated (Integration Awaiting Live Test)

| Manufacturer          | Model             | Control Board/Profile | Temp Range | Probes | Light |
| --------------------- | ----------------- | --------------------- | ---------- | ------ | ----- |
| Nexgrill / Broil King | Oakford 790 / NXP | Mongoose OS           | Unknown    | 4      | Unknown |

Controllers whose `Sys.GetInfo` device ID starts with `NXP-` use the decoded-state Nexgrill profile. The protocol has been live-validated by the contributor; this integration's Nexgrill path still needs a live-device test.

### Should Work (Control Board 8 — same decoder)

| Manufacturer     | Model                         | Control Board | Temp Range | Probes | Light |
| ---------------- | ----------------------------- | ------------- | ---------- | ------ | ----- |
| Louisiana Grills | LG0800BL (Black Label 800)    | 8             | 180-600F   | 2      | No    |
| Louisiana Grills | LG1200BL (Black Label 1200)   | 8             | 180-600F   | 2      | No    |
| Louisiana Grills | LG300BL (Black Label 300)     | 8             | 180-500F   | 2      | No    |
| Louisiana Grills | LGV4BL (Black Label Vertical) | 8             | 130-420F   | 2      | No    |

### May Work (Control Board 9 — Founders series, untested)

| Manufacturer     | Model                    | Control Board | Temp Range | Probes | Light |
| ---------------- | ------------------------ | ------------- | ---------- | ------ | ----- |
| Louisiana Grills | LG800FL (Founders 800)   | 9             | 180-600F   | 4      | Yes   |
| Louisiana Grills | LG800FP (Founders 800)   | 9             | 180-600F   | 4      | No    |
| Louisiana Grills | LG1200FL (Founders 1200) | 9             | 180-600F   | 4      | Yes   |
| Louisiana Grills | LG1200FP (Founders 1200) | 9             | 180-600F   | 4      | No    |

### May Work (Control Board 5 — Pit Boss, untested, different payload format)

| Manufacturer | Model                | Control Board | Temp Range | Probes | Light |
| ------------ | -------------------- | ------------- | ---------- | ------ | ----- |
| Pit Boss     | PB0500SP             | 5             | 180-500F   | 2      | No    |
| Pit Boss     | PB0820SP / PB0820SPW | 5             | 180-500F   | 2      | No    |
| Pit Boss     | PB1000D3             | 5             | 180-500F   | 2      | No    |
| Pit Boss     | PB1000NC1            | 5             | 180-500F   | 2      | No    |

### May Work (Control Board 6 — Lexington, untested, different payload format)

| Manufacturer | Model                     | Control Board | Temp Range | Probes | Light |
| ------------ | ------------------------- | ------------- | ---------- | ------ | ----- |
| Pit Boss     | Lexington (Wi-Fi Upgrade) | 6             | 180-500F   | 2      | No    |

> **Note**: Control Board 5 and 6 models use a different MCU payload format than Control Board 8/9 and are not yet supported. Control Board 8 and 9 models share the same protocol. Nexgrill/Broil King NXP controllers use a separate RPC and command profile; they do not use the Control Board 8 decoder.

**Requirements**: The grill must be connected to your local WiFi network. This integration communicates via HTTP JSON-RPC on port 80 — no cloud account or Bluetooth required. Tested on firmware 0.2.3 (unauthenticated). Firmware 0.5.7+ may require authentication (not yet supported).

## How Is This Different?

There are other Home Assistant integrations for pellet grills. Here's how Grill Master compares:

|                     | Grill Master                         | [ha-pitboss](https://github.com/dknowles2/ha-pitboss) |
| ------------------- | ------------------------------------ | ----------------------------------------------------- |
| **Protocol**        | Local HTTP (WiFi)                    | BLE (Bluetooth)                                       |
| **Range**           | Anywhere on your network             | ~30 ft from HA host                                   |
| **Cloud required?** | No                                   | No                                                    |
| **Cloud sync**      | Optional (push to your own endpoint) | No                                                    |
| **DHCP discovery**  | Yes                                  | No (BLE advertisement)                                |
| **Config flow UI**  | Yes                                  | Yes                                                   |
| **Climate entity**  | Yes                                  | Yes                                                   |
| **Grill brands**    | Louisiana Grills, Pit Boss           | Louisiana Grills, Pit Boss                            |

**Key differences:**

- **Local HTTP, not Bluetooth** — ha-pitboss talks to the same Mongoose OS controller we do, but over BLE. That limits you to ~30 feet from your HA server. Grill Master uses the grill's WiFi HTTP interface, so it works from anywhere on your network.
- **No cloud dependency** — Traeger integrations require a cloud account and internet connection. Grill Master talks directly to the grill on your LAN. If your internet goes down, your grill monitoring doesn't.
- **Optional cloud sync** — If you _want_ cloud data (for a companion app, dashboards, etc.), Grill Master can POST temperature data to any URL you configure. You own the endpoint.
- **DHCP discovery** — Grill Master auto-detects your grill on the network and handles IP changes. No need to hunt for the IP address.
- **Temperature alarms** — None of the existing integrations have built-in temperature alarms. This is Grill Master's [#1 priority feature](documentation/features/temperature-alarms.md). GrillBuddy adds alarm functionality as a separate helper, but it's a generic layer on top of any sensor — not grill-aware.

## Installation

### HACS (Recommended)

[![Open HACS Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dvrtech-us&repository=Grill-Master&category=integration)

1. Click the badge above, or open HACS → search for **"Grill Master"**
2. Click **Download**
3. Restart Home Assistant

### Manual

1. Download the [latest release](https://github.com/dvrtech-us/Grill-Master/releases) or clone the repository
2. Copy the `custom_components/grill_master/` folder into your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

### Setup

1. Go to **Settings → Devices & Services → + Add Integration**
2. Search for **"Grill Master"**
3. Enter your grill's IP address (or let DHCP discovery find it automatically)
4. (Optional) Configure cloud sync endpoint
5. Done — sensors appear immediately

## Entities

### Sensors

| Entity              | Description                                 |
| ------------------- | ------------------------------------------- |
| Grill Temperature   | Current temperature inside the grill        |
| Grill Set Point     | Target temperature the grill is maintaining |
| Probe 1 Temperature | Meat probe 1 reading                        |
| Probe 1 Target      | Meat probe 1 target temperature             |
| Probe 2 Temperature | Meat probe 2 reading                        |
| Probe 3 Temperature | Meat probe 3 reading                        |
| Probe 4 Temperature | Meat probe 4 reading                        |

### Binary Sensors

| Entity                  | Description                  |
| ----------------------- | ---------------------------- |
| Grill Power             | Whether the grill is running |
| Fan                     | Fan state                    |
| Light                   | Light state                  |
| Auger Motor             | Pellet auger motor state     |
| Heater                  | Igniter/heater state         |
| Primer                  | Primer motor state           |
| No Pellets              | Pellet hopper empty warning  |
| High Temperature Error  | Overtemp error               |
| Fan/Igniter/Motor Error | Component error flags        |

### Climate

| Entity | Description                                         |
| ------ | --------------------------------------------------- |
| Grill  | Set temperature (180-600F, 5F steps), HEAT/OFF mode |

### Switch

| Entity | Description                                                                                  |
| ------ | -------------------------------------------------------------------------------------------- |
| Light  | Toggle grill light on/off (only functional on models with a light — e.g., LG800FL, LG1200FL) |

> **Note**: Not all models have a physical light. The LG1000BL, LG0800BL, and most Pit Boss models do **not** have a light. The Founders series (LG800FL, LG1200FL) does have a light.
>
> The light switch is **disabled by default** on models without a light. If your grill has a light and it wasn't auto-detected, you can enable it manually:
>
> 1. Go to **Settings → Devices & Services → Grill Master** → click your device
> 2. Click **"+1 disabled entity"** (or go to the **Entities** tab)
> 3. Find the **Light** switch and click it
> 4. Click the **gear icon** → toggle **Enabled** on → **Update**

## Example Automation: Temperature Drift Alarm

An example automation that alerts when the grill temperature drifts more than 20F from the set point is included in `ha_automation_grill_temp_drift.yaml`. Paste it into the HA automation YAML editor.

## Architecture

```
Home Assistant
  └── custom_components/grill_master/
        │
        ├── DataUpdateCoordinator (polls every 5s)
        │     ├── Board profile selects the RPC and status adapter
        │     │     ├── Control Board 8: PB.GetState + FE0B/FE0C decoding
        │     │     └── NXP: GetCurrentTemperatures + JSON status adapter
        │     └── Optional POST to cloud endpoint
        │
        ├── sensor.py        — Temperature sensors
        ├── binary_sensor.py — Status & error binary sensors
        ├── climate.py       — Temperature control (set temp, HEAT/OFF)
        └── switch.py        — Light control
```

### How Grill Communication Works

The LG1000BL uses an ESP32 running Mongoose OS with an HTTP JSON-RPC interface. Its Control Board 8 profile polls `PB.GetState`, which returns two hex-encoded MCU payloads:

- **FE0B** (status) — Power state, error flags, fan/motor/heater/light states, recipe info
- **FE0C** (temperatures) — Grill temp, set point, probe 1-4 temperatures

Temperatures are encoded as 3 bytes each (hundreds, tens, ones digits). The value `960` is a sentinel meaning "probe not connected."

Commands are sent via `PB.SendMCUCommand` with hex payloads (e.g., `FE0102FF` = power off, `FE0201FF` = light on).

The Nexgrill/Broil King NXP profile instead posts `{"reply":"full"}` to `GetCurrentTemperatures`. Its JSON message is already decoded; temperatures stay in wire Fahrenheit regardless of the display-unit setting, and `960` means a disconnected probe. Commands use `SendGenericCommand` with E1E1/30xx frames (firmware appends the checksum), while cook timers use `SetTimer`. The profile treats `moduleIsOn` values 1 and 2 as powered and 0 as off. Remote start requires the grill to be physically powered on first.

## Known Limitations & Future Work

### Firmware Authentication (Not Yet Supported)

This integration works with **firmware 0.2.3**, which has no authentication on the local RPC interface. Newer firmware versions add a time-based authentication mechanism:

- A `PB.GetTime` endpoint returns device uptime
- Commands require a `psw` parameter: the grill password encrypted with a key derived from the device uptime and a fixed 8-byte seed (`[0x8F, 0x80, 0x19, 0xCF, 0x77, 0x6C, 0xFE, 0xB7]`)
- The cipher uses XOR encryption with 16 bytes of random padding and key mutation per byte

The full algorithm is documented in `documentation/features/grill-communication/trail/2026-03-20-firmware-auth-research.md` with a step-by-step implementation plan. Contributions welcome.

### Other Limitations

- **Local network only** — The grill and Home Assistant must be on the same network
- **No BLE support** — This integration uses HTTP only. For Bluetooth, see [ha-pitboss](https://github.com/dknowles2/ha-pitboss)
- **ESP32 resource limits** — Polling faster than 2 seconds may cause instability on the 65KB-RAM controller
- **Probe sentinel value** — Temperature value 960 means "probe not connected" and is reported as unavailable
- **Supported profiles only** — Control Board 8/9 and NXP Mongoose OS profiles are supported; other boards have different protocols

## Acknowledgements

The MCU payload decoding in this project is ported from the **[pytboss](https://github.com/dknowles2/pytboss)** library by [@dknowles2](https://github.com/dknowles2), which reverse-engineered the Pit Boss pellet grill communication protocol. The hex payload format, byte offsets, and command codes in `decoder.py` are derived from the JavaScript functions in `pytboss/grills.json` (Control Board 8).

The **[ha-pitboss](https://github.com/dknowles2/ha-pitboss)** Home Assistant integration by the same author provided architectural reference for the HA integration patterns (config flow, coordinator, entity structure).

Both projects are invaluable resources for the pellet grill hacking community.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Disclaimer

This project is **unofficial** and has no affiliation with any grill manufacturer or related companies. It is a community-driven project that communicates with the grill's local network interface using reverse-engineered protocols. No proprietary code or firmware has been included in this project.

**Use at your own risk.** The authors are not responsible for any damage to your grill, food, property, or anything else that may result from using this software. Always monitor your grill in person during cooking — do not rely solely on this integration for safety-critical monitoring.

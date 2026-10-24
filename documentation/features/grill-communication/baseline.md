# Grill Communication - Behavior Baseline

## Invariants

1. The polling service MUST call `PB.GetState` at the configured interval when the grill is reachable
2. All MCU hex payloads MUST be decoded before being stored or pushed to clients
3. A grill that fails to respond for consecutive polls MUST be reported as "unavailable" via the HA coordinator
4. Commands sent via `PB.SendMCUCommand` MUST use the correct hex encoding
5. Temperature values MUST be decoded to degrees Fahrenheit regardless of the grill panel's F/C setting (`decode_temperatures()` normalizes using the payload's own `is_fahrenheit` flag - the panel's Celsius mode changes the unit of the raw transmitted digits, confirmed live); HA handles further unit conversion for display when device_class=temperature
6. The RPC client MUST enforce a 5-second HTTP timeout to prevent blocking the HA event loop

## Expected Behavior

- `PB.GetState` returns a JSON object with `sc_11` (status) and `sc_12` (temperature) hex strings
- `Sys.GetInfo` returns device metadata including firmware version, WiFi status, and memory stats
- `PB.GetFirmwareVersion` returns `{"firmwareVersion": "0.2.3"}`
- `RPC.Ping` returns empty success response when grill is reachable
- When the grill is powered off but connected to WiFi, RPC endpoints still respond (controller stays on)
- Polling interval of 3 seconds is fast enough for meaningful temperature tracking without overloading the ESP32

## Known Limitations

- Firmware 0.2.3 has no RPC authentication; all endpoints are open on the local network
- Newer firmware adds time-based auth via `PB.GetTime` + XOR cipher (see `trail/2026-03-20-firmware-auth-research.md` for full details and implementation plan)
- `PB.GetTime` returns 404 on firmware 0.2.3, confirming auth is not available on this version
- The ESP32 has 65KB free RAM; aggressive polling (<1s) may cause instability
- MCU payload format is not officially documented; decoding is based on reverse-engineering (pytboss project)
- Temperature resolution from the MCU is whole degrees (no decimal precision)
- Temperature value 960 is a sentinel meaning "probe not connected" (handled in decoder)

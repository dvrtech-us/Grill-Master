# Grill Communication - Behavior Baseline

## Invariants

1. The Control Board 8 profile MUST call `PB.GetState`; the NXP profile MUST call `GetCurrentTemperatures` with `{"reply":"full"}`.
2. Control Board 8 MCU hex payloads MUST be decoded; NXP's pre-decoded JSON MUST be adapted directly without hex decoding.
3. Repeated connection failures MUST be reported as "unavailable" via the HA coordinator; the documented NXP off-state HTTP 500 response instead retains cached state or leaves the initial state unknown.
4. Control Board 8 commands use `PB.SendMCUCommand`; NXP commands use `SendGenericCommand` with E1E1/30xx decimal-byte frames (checksum appended by firmware).
5. Temperatures supplied to HA MUST be Fahrenheit. Control Board 8 values are normalized from the FE0C unit flag; NXP always reports Fahrenheit even when its display is set to Celsius.
6. The RPC client MUST enforce a 5-second HTTP timeout to prevent blocking the HA event loop
7. NXP `moduleIsOn` values 0, 1, and 2 mean off, cooking, and powered/idle; only 0 is off. Remote start MUST NOT be sent unless the controller is already physically powered on.
8. The Control Board 8 profile MUST poll every 5 seconds by default. The NXP profile MUST poll every 15 seconds by default. A configured interval other than that shared 5-second default is kept.

## Expected Behavior

- `PB.GetState` returns a JSON object with `sc_11` (status) and `sc_12` (temperature) hex strings
- NXP `GetCurrentTemperatures {"reply":"full"}` returns the decoded status object as JSON in `message`
- NXP probe readings of 960 mean the probe is unplugged
- NXP cook timers are set with `SetTimer {"hours": H, "minutes": M}`; zero/zero clears the timer
- `Sys.GetInfo` returns device metadata including firmware version, WiFi status, and memory stats
- `PB.GetFirmwareVersion` returns `{"firmwareVersion": "0.2.3"}`
- `RPC.Ping` returns empty success response when grill is reachable
- When the grill is powered off but connected to WiFi, RPC endpoints still respond (controller stays on)
- Control Board 8 polls every 5 seconds by default. The NXP profile polls every 15 seconds by default and does not inherit the Control Board 8 interval

## Known Limitations

- Firmware 0.2.3 has no RPC authentication; all endpoints are open on the local network
- Newer firmware adds time-based auth via `PB.GetTime` + XOR cipher (see `trail/2026-03-20-firmware-auth-research.md` for full details and implementation plan)
- `PB.GetTime` returns 404 on firmware 0.2.3, confirming auth is not available on this version
- The ESP32 has 65KB free RAM; aggressive polling (<1s) may cause instability
- MCU payload format is not officially documented; decoding is based on reverse-engineering (pytboss project)
- Temperature resolution from the MCU is whole degrees (no decimal precision)
- Temperature value 960 is a sentinel meaning "probe not connected" (handled in decoder)
- NXP `GetCurrentTemperatures` may return HTTP 500 when fully off; retain cached state or keep initial state unknown rather than treating the response as a successful off reading

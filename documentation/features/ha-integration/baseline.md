# Home Assistant Integration - Behavior Baseline

## Invariants

1. The Control Board 8 coordinator MUST poll `PB.GetState` at the configured interval (default 5s). The NXP profile polls every 15 seconds by default.
2. Both FE0B and FE0C payloads MUST be decoded on every poll cycle
3. All sensor entities MUST update within 1 second of a coordinator refresh
4. Cloud sync failure MUST NOT block or delay local polling/entity updates
5. The config flow MUST validate grill connectivity before creating an entry
6. Temperature values of 0 MUST be reported as `None` (unavailable) to avoid false readings from disconnected probes
7. The climate entity MUST round temperature targets to 5F increments within the 180-600F range
8. HTTP timeouts MUST be enforced at 5 seconds to prevent blocking the HA event loop
9. The integration MUST gracefully report "unavailable" when the grill is unreachable

## Expected Behavior

- **Normal operation**: Control Board 8 sensors update every 5 seconds with decoded temperature and status values. NXP sensors update every 15 seconds by default
- **Grill unreachable**: All entities show "unavailable" state; coordinator retries on next interval
- **Grill powered off (WiFi still on)**: RPC endpoints still respond; `module_is_on` = false, temperatures may be ambient or 0
- **Probe not inserted**: Probe temperature reads 0 → reported as None/unavailable
- **Cloud sync enabled**: JSON POSTed on every poll cycle; failures logged silently
- **Set temperature**: Command sent via `PB.SendMCUCommand`, coordinator refreshes immediately after
- **Light toggle**: Command sent, state reflects on next poll cycle

## Edge Cases

- MCU may return payloads shorter than expected during firmware boot; decoder returns None and coordinator reports UpdateFailed
- Multiple HA instances polling the same grill may cause ESP32 resource contention at very short intervals (<2s)
- Grill firmware 0.5.7+ requires time-based authentication; this integration only supports unauthenticated 0.2.3

# Firmware Bug: PB.GetState Always Returns Empty sc_11/sc_12

- Date: 2026-07-31
- Feature: grill-communication
- Related code: `custom_components/grill_master/coordinator.py`, `custom_components/grill_master/api.py`, `firmware/init_0.3.0_original.js`, `firmware/init_0.3.0_patched.js`

## Context

HA integration setup failed with "Failed to decode grill state. sc_11='',
sc_12=''" on a real LG1000BL running firmware 0.3.0 (newer than the 0.2.3
this integration was originally validated against).

## Root Cause

In `init.js`, `handlePacket()` — the function that runs on every UART
reply received from the main control board — computes the status cache
key but never assigns it:

```js
function handlePacket(pck, isRaw) {
  let decString = "";
  let key = "";
  if (!isRaw) {
    getStatusKey(pck.at(1));        // BUG: return value discarded
    ...
  }
  if (key !== "") {                 // always false
    lastStatus[key] = pck;          // never runs
    ...
  } else {
    ...
    sendBTStatus(decString + " [" + JSON.stringify(decString.length) + "]");
  }
}
```

`key` stays `""` forever, so `lastStatus.sc_11`/`sc_12` — the only source
`RPC.addHandler("PB.GetState", ...)` and `sendWSStatus()` (cloud sync) read
from — are never populated, regardless of how many valid UART packets
arrive. This affects every RPC transport that reads status (local HTTP,
and Mongoose's native RPC-over-BLE-GATT channel, since both call the same
handler), not just WiFi.

Notably, `sendBTStatus()` — which just calls `print()` — runs
unconditionally in both branches of the `if (key !== "")` check, so it's
unaffected by the bug. Combined with `bt.debug_svc_enable: true` in the
device's config (a Mongoose OS feature that broadcasts `print()` output
over a BLE debug characteristic), this is almost certainly why the
official app appeared to show live data over Bluetooth while local status
reads stayed empty — it was very likely reading the debug log stream, not
a real status API, which also explains why it was flaky rather than
reliable.

Commands (`PB.SendMCUCommand`, used for setting temperature, power, light)
were never affected — they only write to `lastStatus` as a side effect
(clearing it before sending) and don't depend on the broken read path.


## Decision

Patched the one-line bug directly on the device's filesystem via the
exposed `FS.Put` RPC endpoint (`key = getStatusKey(pck.at(1));`), verified
byte-for-byte via SHA256 hash round-tripped through the device before and
after reboot. Confirmed fixed: `PB.GetState` now returns real 25/40-byte
`FE0C`/`FE0B` payloads that decode cleanly through this integration's
`decoder.py`.

Filed a bug report with Dansons support describing the exact line and fix
(see `firmware/` directory for the full before/after files and the
reapply procedure). This device-side patch is **not persistent against
official OTA updates** — see `firmware/REAPPLY.md`.

## Alternatives Considered

- **Option A: Wait for an official firmware fix** — safest, but blocks
  the integration (and the project's #1 priority, temperature alarms)
  indefinitely with no ETA.
- **Option B: Self-patch the live firmware** (chosen) — required building
  and validating a safe chunked write procedure (the device's RPC channel
  silently drops writes over ~1200-1500 bytes, verified via forced
  per-chunk size checks against a throwaway test file before ever writing
  to the real `init.js`), but is reversible (full backup retained,
  `FS.Put` isn't gated behind anything auth-wise) and unblocks the
  integration immediately.
# Panel Celsius Mode Changes Raw Temperature Values, Not Just Display

- Date: 2026-09-14
- Feature: grill-communication
- Related code: `custom_components/grill_master/decoder.py`, `custom_components/grill_master/climate.py`

## Context

While adding Celsius support to the HA climate entity's temperature bounds,
the question came up: does switching the grill's physical control panel to
Celsius (`FE0902FF`) change what `PB.GetState` reports, or is it purely
cosmetic on the grill's own screen?

## Investigation

Tested against a live LG1000BL at `10.10.10.155` (grill on, set point 180F):

| | grill_set_temp (raw) | grill_temp (raw) | is_fahrenheit (FE0C) |
|---|---|---|---|
| Before | 180 | 217 | True |
| After `CMD_SET_CELSIUS` | 82 | 102 | False |
| After `CMD_SET_FAHRENHEIT` (restored) | 180 | 213 | True |

180F -> 82.2C, which rounds to exactly 82 - matching. Confirmed: the panel
setting changes the **unit of the raw digits** the MCU transmits in FE0C,
not just how the grill's own screen renders them.

A second finding, incidental to this test: in the same `PB.GetState`
snapshot, FE0B's `is_fahrenheit` bit (offset 36) disagreed with FE0C's
(offset 23) - e.g. FE0B reported `False` while FE0C correctly reported
`True` and the grill was actually in Fahrenheit mode. This isn't new
instability from the toggle - it's also present in this repo's own
long-standing `LIVE_SC_11`/`LIVE_SC_12` test fixtures in
`tests/test_decoder.py` (captured 2026-03-18), which pair
`is_fahrenheit=False` (FE0B) with `is_fahrenheit=True` (FE0C) from the same
capture. FE0B's temperature-related bytes are already documented as
unreliable due to the message-type dual-purpose issue at offset 20-22; this
suggests offset 36 shares that unreliability.

Also observed: right after sending an `FE09xx` command, `sc_11`/`sc_12`
briefly returned empty before repopulating ~2s later - matches the already
documented `lastStatus`-clearing behavior in
`2026-07-31-firmware-status-cache-bug.md`, not a new issue.

## Decision

Normalize temperatures to Fahrenheit inside `decode_temperatures()` (FE0C
only), using **that payload's own** `is_fahrenheit` flag:

- Added `_normalize_to_fahrenheit()` in `decoder.py`, applied to every
  temperature field FE0C returns (`p1_target`, `p1_temp`..`p4_temp`,
  `grill_set_temp`, `grill_temp`, `smoker_act_temp`).
- `0` (the MCU's "no reading" placeholder) and `None` (probe-not-connected
  sentinel) are passed through unconverted - only real nonzero readings are
  converted.
- Deliberately did **not** apply the same normalization inside
  `decode_status()` (FE0B): its own `is_fahrenheit` bit is demonstrably
  unreliable (see above), and its temperature fields are already
  overwritten by FE0C in `coordinator.py`'s merge order
  (`state.update(status)` then `state.update(temperatures)`), so FE0B's
  raw values never reach any consumer. Normalizing them anyway using an
  unreliable flag would only risk introducing wrong conversions with no
  benefit.
- `climate.py`'s new unit-aware bounds (converting HA's *display* unit,
  independent of the grill's panel unit) build on top of this - it assumes
  `coordinator.data["grill_temp"]`/`["grill_set_temp"]` are always
  Fahrenheit, which this fix now guarantees regardless of the panel's
  setting.

## Alternatives Considered

- **Do nothing, rely on `is_fahrenheit` downstream** - rejected. Would push
  unit-awareness into every consumer (sensors, climate, alarms) instead of
  containing the hardware quirk in the decoder, and the #1-priority alarm
  feature is exactly the thing that would silently break if the panel is
  ever left in Celsius mode.
- **Normalize both FE0B and FE0C using each payload's own flag** -
  rejected given FE0B's flag is unreliable; would risk double-converting
  or wrongly converting values that are actually already in the right
  unit.

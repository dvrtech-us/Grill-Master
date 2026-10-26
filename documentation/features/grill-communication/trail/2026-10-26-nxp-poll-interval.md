# Slow the NXP poll to 15 seconds

- Date: 2026-10-26
- Feature: grill-communication
- Related code: `custom_components/grill_master/const.py`, `board_profiles.py`, `__init__.py`, `config_flow.py`

## Context

Control Board 8 and the NXP profile shared `DEFAULT_POLL_INTERVAL` (5 seconds). The NXP controller has less free RAM than the LG1000BL, and the protocol note for that board asks for a slower poll. A 5-second poll on that profile can reboot the controller.

## Decision

Give the NXP profile its own default, `NEXGRILL_POLL_INTERVAL` of 15 seconds, stored on `NEXGRILL_MONGOOSE.poll_interval`. Leave `DEFAULT_POLL_INTERVAL` at 5 seconds for Control Board 8.

Setup still records a poll interval before the device id is known, so a stored 5 is the shared default rather than an NXP choice. `resolve_poll_interval()` replaces that shared default with the profile interval. Any other configured value is kept.

## Alternatives Considered

- Keep one default and document that NXP owners should raise it: rejected because the unsafe interval would still be what a new NXP entry polls.
- Ignore every configured interval and always use the profile value: rejected because an explicit non-default interval must still win for either board.

## Consequences

- Positive: a new or previously defaulted NXP entry polls every 15 seconds. Control Board 8 stays at 5 seconds unless the user set something else.
- Negative: an NXP owner cannot keep a 5-second poll, because 5 is the shared default this change replaces.

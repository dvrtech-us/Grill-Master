# Add NXP Mongoose Board Profile

- Date: 2026-10-24
- Feature: grill-communication
- Related code: `custom_components/grill_master/board_profiles.py`, `api.py`, `coordinator.py`

## Context

The Nexgrill Oakford 790 uses the same Mongoose OS transport as Control Board 8 but different RPC names, a pre-decoded status response, and E1E1/30xx control frames.

## Decision

Select a board profile from the controller ID (`NXP-`), keep Control Board 8's existing decoder unchanged, and adapt NXP's JSON status to the coordinator's shared keys. Use a single status request per poll. Treat HTTP 500 on an off controller as an unknown/retained state, and retry a failed NXP command once. Remote start requires a powered controller; no cold power-on command is issued.

## Alternatives Considered

- Rework the existing decoder to accept both formats: rejected because NXP already returns decoded JSON and has distinct RPC/control framing.
- Add a user-selected board option: rejected because the supplied `NXP-` device ID supports automatic profile selection.

## Consequences

- Positive: existing Control Board 8 behavior and decoder remain unchanged, while NXP status and command formats are isolated in a profile.
- Negative: live integration behavior remains to be verified against the contributor's unit.

"""Board-specific RPC and protocol profiles."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BoardProfile:
    """RPC and device details for a grill control board."""

    name: str
    model: str
    manufacturer: str
    state_rpc: str
    command_rpc: str
    firmware_rpc: str | None
    decoded_state: bool = False
    timer_rpc: str | None = None


CONTROL_BOARD_8 = BoardProfile(
    name="control_board_8",
    model="LG1000BL",
    manufacturer="Grill Master",
    state_rpc="PB.GetState",
    command_rpc="PB.SendMCUCommand",
    firmware_rpc="PB.GetFirmwareVersion",
)

NEXGRILL_MONGOOSE = BoardProfile(
    name="nexgrill_mongoose",
    model="Nexgrill / Broil King Mongoose OS",
    manufacturer="Nexgrill / Broil King",
    state_rpc="GetCurrentTemperatures",
    command_rpc="SendGenericCommand",
    firmware_rpc=None,
    decoded_state=True,
    timer_rpc="SetTimer",
)


def profile_for_device_id(device_id: str | None) -> BoardProfile:
    """Select a board profile from the controller's device ID."""
    if (device_id or "").upper().startswith("NXP-"):
        return NEXGRILL_MONGOOSE
    return CONTROL_BOARD_8


def build_nexgrill_command(function_code: int, body: tuple[int, ...]) -> str:
    """Build a decimal-byte E1E1 command; firmware appends the checksum."""
    if not 0 <= function_code <= 0xFF:
        raise ValueError("Function code must fit in one byte")
    if any(not 0 <= byte <= 0xFF for byte in body):
        raise ValueError("Command bytes must fit in one byte")

    length = 8 + len(body)
    frame = (0xE1, 0xE1, 0, length, 1, 0x30, function_code, *body)
    return "".join(f"{byte:03d}," for byte in frame)


_FIELD_ALIASES = {
    "grill_temp": (
        "grilltemp",
        "grilltemperature",
        "currentgrilltemp",
        "actualgrilltemp",
        "smokertemp",
        "smokertemperature",
        "smokeracttemp",
        "pittemp",
    ),
    "grill_set_temp": (
        "grillsettemp",
        "grillsettemperature",
        "grillsetpoint",
        "settemp",
        "settemperature",
        "targettemp",
        "targettemperature",
        "setpoint",
    ),
    "module_state": ("moduleison", "moduleon", "modulepowerstate", "modulestate"),
    "current_mode": ("currentmode", "mode", "cookmode"),
    "cook_timer": ("cooktimer", "timer", "timerremaining"),
    "elapsed_time": ("elapsedtime", "elapsed"),
    "fan_state": ("fanstate", "fanison", "fanon"),
    "light_state": ("lightstate", "lightison", "lighton"),
    "motor_state": ("motorstate", "motorison", "augerstate", "augeron"),
    "hot_state": ("hotstate", "heaterstate", "igniterstate"),
    "prime_state": ("primestate", "primerstate"),
    "no_pellets": ("nospellets", "hopperempty"),
    "high_temp_err": ("hightemperr", "hightemperatureerror"),
    "fan_err": ("fanerr", "fanerror"),
    "hot_err": ("hoterr", "ignitererror"),
    "motor_err": ("motorerr", "motorerror"),
}


def _key(value: str) -> str:
    """Normalize JSON keys across snake_case and camelCase spellings."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _temperature(value: Any) -> int | float | None:
    """Normalize a wire-Fahrenheit temperature and its unplugged sentinel."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    if numeric == 960:
        return None
    return int(numeric) if numeric.is_integer() else numeric


def _as_mapping(message: Any) -> dict[str, Any] | None:
    """Parse the board's JSON object, nested as a string in ``message``."""
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            return None
    if not isinstance(message, dict):
        return None
    nested = message.get("message")
    if isinstance(nested, (str, dict)):
        return _as_mapping(nested)
    return message


def decode_nexgrill_status(response: dict[str, Any]) -> dict[str, Any] | None:
    """Adapt the board's pre-decoded status object to integration data keys."""
    source = _as_mapping(response.get("message"))
    if source is None:
        return None

    normalized = {_key(str(key)): value for key, value in source.items()}
    state: dict[str, Any] = {"is_fahrenheit": True}

    for data_key, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                state[data_key] = normalized[alias]
                break

    for data_key in (
        "fan_state",
        "light_state",
        "motor_state",
        "hot_state",
        "prime_state",
        "no_pellets",
        "high_temp_err",
        "fan_err",
        "hot_err",
        "motor_err",
    ):
        if data_key in state:
            value = state[data_key]
            if isinstance(value, str):
                state[data_key] = value.lower() in ("1", "true", "on", "yes")
            else:
                state[data_key] = bool(value)

    temperature_fields = {
        "grill_temp": _FIELD_ALIASES["grill_temp"],
        "grill_set_temp": _FIELD_ALIASES["grill_set_temp"],
    }
    for index in range(1, 5):
        temperature_fields[f"p{index}_temp"] = (
            f"probe{index}temp",
            f"probe{index}temperature",
            f"probe{index}",
            f"p{index}temp",
            f"meatprobe{index}temp",
        )
        temperature_fields[f"p{index}_target"] = (
            f"probe{index}target",
            f"probe{index}settemp",
            f"p{index}target",
        )

    for data_key, aliases in temperature_fields.items():
        for alias in aliases:
            if alias in normalized:
                state[data_key] = _temperature(normalized[alias])
                break

    if "module_state" in state:
        raw_module_state = state["module_state"]
        if isinstance(raw_module_state, bool):
            module_state = int(raw_module_state)
        else:
            try:
                module_state = int(raw_module_state)
            except (TypeError, ValueError):
                module_state = raw_module_state
        state["module_state"] = module_state
        if module_state is None:
            state["module_is_on"] = None
        elif isinstance(module_state, str):
            value = module_state.lower()
            if value in ("", "0", "false", "off", "none", "unknown"):
                state["module_is_on"] = False
            elif value in ("1", "2", "true", "on", "powered", "cooking"):
                state["module_is_on"] = True
            else:
                state["module_is_on"] = None
        elif isinstance(module_state, (int, float)):
            state["module_is_on"] = module_state != 0
        else:
            state["module_is_on"] = None

    for data_key in ("grill_temp", "grill_set_temp"):
        if data_key in normalized:
            state[data_key] = _temperature(normalized[data_key])

    if len(state) == 1:
        return None
    return state

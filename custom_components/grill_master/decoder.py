"""MCU payload decoder for Grill Master (Control Board 8 - Black Label series).

Ported from the pytboss JavaScript parsing logic in grills.json.
Decodes FE0B (status) and FE0C (temperature) hex payloads from PB.GetState responses.

Validated against live LG1000BL payload (firmware 0.2.3):
  sc_12: FE0C00000000000009060009060009060000000000000001FF  (25 bytes)
  sc_11: FE0B0000000000009060000000000000000000020200010000...FF (40 bytes)

Key findings:
  - FE0B payloads from this firmware are 40 bytes (not 41 as pytboss checks).
    Recipe time at bytes 38-40 may overflow; byte 39 can be the FF trailer.
  - Temperature value 960 is the sentinel for "probe not connected".
  - Bytes 20-22 in FE0B serve dual purpose based on message type flag at byte 23.
"""

from __future__ import annotations

from typing import Any

from .const import STATUS_PREFIX, TEMP_PREFIX

# The MCU reports 960 when a probe is not physically connected.
# This must be treated as "no data" rather than a real temperature.
PROBE_NOT_CONNECTED_VALUE = 960


def parse_hex_message(message: str) -> list[int]:
    """Convert a hex string to a list of integer byte values.

    Example: "FE0B01" -> [254, 11, 1]
    """
    return [int(message[i : i + 2], 16) for i in range(0, len(message), 2)]


def convert_temperature(parts: list[int], offset: int) -> int | None:
    """Convert 3 consecutive bytes at offset to a temperature value.

    The MCU encodes temperatures as three separate digits:
    hundreds, tens, ones. E.g. [0, 9, 6] = 096 = 96 degrees.
    Offset is measured in bytes from the start of the parsed array.

    Returns None if the value is the "probe not connected" sentinel (960).
    """
    value = parts[offset] * 100 + parts[offset + 1] * 10 + parts[offset + 2]
    if value == PROBE_NOT_CONNECTED_VALUE:
        return None
    return value


def _normalize_to_fahrenheit(value: int | None, is_fahrenheit: bool) -> int | None:
    """Normalize a decoded temperature to Fahrenheit.

    The grill's control panel can be switched to Celsius (FE0902FF), and
    doing so changes the unit of the raw digits the MCU transmits, not just
    how they're shown on the grill's own screen (confirmed against a live
    LG1000BL: toggling the panel changed grill_set_temp from 180 to 82).
    Zero is the MCU's "no reading" placeholder rather than a real
    measurement, so it's passed through untouched.
    """
    if value is None or value == 0 or is_fahrenheit:
        return value
    return round(value * 9 / 5 + 32)


def decode_status(message: str) -> dict[str, Any] | None:
    """Decode an FE0B status payload from sc_11.

    Ported from pytboss grills.json control board 8 status_function.

    The FE0B payload from the LG1000BL (firmware 0.2.3) is 40 bytes.
    The minimum required for core status decoding is 37 bytes (through
    is_fahrenheit). Recipe fields at bytes 37-40 are parsed when available.

    Args:
        message: Hex string starting with FE0B.

    Returns:
        Dictionary of status fields, or None if invalid.
    """
    if not message.startswith(STATUS_PREFIX):
        return None

    parts = parse_hex_message(message)

    # Need at least 37 bytes for core fields (through is_fahrenheit at index 36)
    if len(parts) < 37:
        return None

    status: dict[str, Any] = {
        # Temperature readings (3 bytes each: hundreds, tens, ones)
        "p1_target": convert_temperature(parts, 2),
        "p1_temp": convert_temperature(parts, 5),
        "p2_temp": convert_temperature(parts, 8),
        "p3_temp": convert_temperature(parts, 11),
        "p4_temp": convert_temperature(parts, 14),
        "smoker_act_temp": convert_temperature(parts, 14),
        # Boolean states
        "module_is_on": parts[21] == 1,
        "err1": parts[22] == 1,
        "err2": parts[23] == 1,
        "err3": parts[24] == 1,
        "high_temp_err": parts[25] == 1,
        "fan_err": parts[26] == 1,
        "hot_err": parts[27] == 1,
        "motor_err": parts[28] == 1,
        "no_pellets": parts[29] == 1,
        "erl": parts[30] == 1,
        "fan_state": parts[31] == 1,
        "hot_state": parts[32] == 1,
        "motor_state": parts[33] == 1,
        "light_state": parts[34] == 1,
        "prime_state": parts[35] == 1,
        "is_fahrenheit": parts[36] == 1,
    }

    # Recipe info - only parse if payload is long enough.
    # The FF trailer can appear at byte 39 on shorter payloads,
    # making recipe_time unreliable. Guard against index overflow.
    if len(parts) >= 41:
        status["recipe_step"] = parts[37]
        status["recipe_time"] = parts[38] * 3600 + parts[39] * 60 + parts[40]
    elif len(parts) >= 38:
        status["recipe_step"] = parts[37]
        status["recipe_time"] = 0

    # The grill set temp and grill temp are conditionally decoded based on
    # the value at parts[23] (err2 position, which also acts as a message type flag).
    # Bytes 20-22 serve dual purpose: temperature reading OR part of the status block.
    # This matches the pytboss JavaScript switch statement on parts[23].
    if parts[23] == 1:
        status["grill_set_temp"] = convert_temperature(parts, 20)
    elif parts[23] == 2:
        status["grill_temp"] = convert_temperature(parts, 20)

    return status


def decode_temperatures(message: str) -> dict[str, Any] | None:
    """Decode an FE0C temperature payload from sc_12.

    Ported from pytboss grills.json control board 8 temperatures_function.

    Args:
        message: Hex string starting with FE0C.

    Returns:
        Dictionary of temperature fields, or None if invalid.
    """
    if not message.startswith(TEMP_PREFIX):
        return None

    parts = parse_hex_message(message)

    if len(parts) < 24:
        return None

    is_fahrenheit = parts[23] == 1

    return {
        "p1_target": _normalize_to_fahrenheit(convert_temperature(parts, 2), is_fahrenheit),
        "p1_temp": _normalize_to_fahrenheit(convert_temperature(parts, 5), is_fahrenheit),
        "p2_temp": _normalize_to_fahrenheit(convert_temperature(parts, 8), is_fahrenheit),
        "p3_temp": _normalize_to_fahrenheit(convert_temperature(parts, 11), is_fahrenheit),
        "p4_temp": _normalize_to_fahrenheit(convert_temperature(parts, 14), is_fahrenheit),
        "grill_set_temp": _normalize_to_fahrenheit(convert_temperature(parts, 17), is_fahrenheit),
        "grill_temp": _normalize_to_fahrenheit(convert_temperature(parts, 20), is_fahrenheit),
        "smoker_act_temp": _normalize_to_fahrenheit(convert_temperature(parts, 17), is_fahrenheit),
        "is_fahrenheit": is_fahrenheit,
    }


def encode_set_temperature(temp_f: int) -> str:
    """Encode a temperature setpoint into a hex command string.

    Ported from pytboss grills.json control board 8 command ID 97.
    Produces: FE0501 + hex(hundreds) + hex(tens) + hex(ones) + FF

    Args:
        temp_f: Temperature in Fahrenheit (180-600, in increments of 5).

    Returns:
        Hex command string, e.g. "FE050102050000FF" for 250F.
    """
    hundreds = temp_f // 100
    tens = (temp_f % 100) // 10
    ones = temp_f % 10
    return f"FE0501{hundreds:02X}{tens:02X}{ones:02X}FF"

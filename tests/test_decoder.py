"""Tests for the Grill Master MCU payload decoder.

These tests run standalone without Home Assistant.
We import the decoder functions directly to avoid HA dependencies.

Run: python -m pytest tests/test_decoder.py -v
  or: python tests/test_decoder.py  (for standalone execution)
"""

import sys
import os

# Add project root to path so we can import without HA
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We can't import the package normally because __init__.py imports HA.
# Instead we stub the const module and load decoder.py with its parent package set.
import types
import importlib.util

# Create the package hierarchy in sys.modules
_pkg = types.ModuleType("custom_components")
_pkg.__path__ = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_components")]
sys.modules["custom_components"] = _pkg

_sub = types.ModuleType("custom_components.grill_master")
_sub.__path__ = [os.path.join(_pkg.__path__[0], "grill_master")]
_sub.__package__ = "custom_components.grill_master"
sys.modules["custom_components.grill_master"] = _sub

# Stub the const module with the values decoder.py needs
_const = types.ModuleType("custom_components.grill_master.const")
_const.STATUS_PREFIX = "FE0B"
_const.TEMP_PREFIX = "FE0C"
sys.modules["custom_components.grill_master.const"] = _const

# Now load decoder.py as part of the package
_decoder_path = os.path.join(_sub.__path__[0], "decoder.py")
spec = importlib.util.spec_from_file_location(
    "custom_components.grill_master.decoder",
    _decoder_path,
    submodule_search_locations=[],
)
decoder = importlib.util.module_from_spec(spec)
decoder.__package__ = "custom_components.grill_master"
spec.loader.exec_module(decoder)

# Now we have: decoder.parse_hex_message, decoder.convert_temperature, etc.
parse_hex_message = decoder.parse_hex_message
convert_temperature = decoder.convert_temperature
decode_status = decoder.decode_status
decode_temperatures = decoder.decode_temperatures
encode_set_temperature = decoder.encode_set_temperature
PROBE_NOT_CONNECTED_VALUE = decoder.PROBE_NOT_CONNECTED_VALUE

# ============================================================================
# Live payloads captured from LG1000BL (grill OFF)
# Captured: 2026-03-18
# ============================================================================
LIVE_SC_12 = "FE0C00000000000009060009060009060000000000000001FF"
LIVE_SC_11 = "FE0B00000000000009060000000000000000000002020001000000000000000000000100000000FF"

# ============================================================================
# Live payload captured from LG1000BL at 10.10.10.155 (grill actively running,
# set point 180F) immediately after sending CMD_SET_CELSIUS (FE0902FF).
# Captured: 2026-09-14. Raw digits are 82 (set point) / 102 (current) -
# i.e. the actual Celsius values (180F=82.2C), confirming the panel's F/C
# setting changes the unit of the transmitted digits, not just the display.
# ============================================================================
LIVE_SC_12_CELSIUS = "FE0C00000009060009060009060009060000080201000202FF"


class TestParseHexMessage:
    """Tests for parse_hex_message()."""

    def test_simple(self):
        assert parse_hex_message("FE0B") == [0xFE, 0x0B]

    def test_zeros(self):
        assert parse_hex_message("000000") == [0, 0, 0]

    def test_ff(self):
        assert parse_hex_message("FF") == [255]

    def test_mixed(self):
        assert parse_hex_message("0102FF") == [1, 2, 255]

    def test_live_sc12_length(self):
        parts = parse_hex_message(LIVE_SC_12)
        assert len(parts) == 25

    def test_live_sc11_length(self):
        parts = parse_hex_message(LIVE_SC_11)
        assert len(parts) == 40


class TestConvertTemperature:
    """Tests for convert_temperature()."""

    def test_zero(self):
        assert convert_temperature([0, 0, 0], 0) == 0

    def test_250(self):
        assert convert_temperature([2, 5, 0], 0) == 250

    def test_225(self):
        assert convert_temperature([2, 2, 5], 0) == 225

    def test_180(self):
        assert convert_temperature([1, 8, 0], 0) == 180

    def test_600(self):
        assert convert_temperature([6, 0, 0], 0) == 600

    def test_offset(self):
        """Temperature at non-zero offset."""
        parts = [0, 0, 3, 5, 0, 0, 0]
        assert convert_temperature(parts, 2) == 350

    def test_probe_not_connected_returns_none(self):
        """960 is the sentinel for 'probe not connected'."""
        assert convert_temperature([9, 6, 0], 0) is None

    def test_normal_value_returns_int(self):
        """Normal temperature returns an integer."""
        result = convert_temperature([2, 5, 0], 0)
        assert isinstance(result, int)
        assert result == 250


class TestDecodeTemperatures:
    """Tests for decode_temperatures() - FE0C payload."""

    def test_wrong_prefix_rejected(self):
        assert decode_temperatures("FE0B0000000000000000") is None

    def test_too_short_rejected(self):
        assert decode_temperatures("FE0C000000") is None

    def test_empty_string_rejected(self):
        assert decode_temperatures("") is None

    def test_live_payload_parses(self):
        """Live FE0C payload from grill (OFF) should parse successfully."""
        result = decode_temperatures(LIVE_SC_12)
        assert result is not None

    def test_live_payload_is_fahrenheit(self):
        result = decode_temperatures(LIVE_SC_12)
        assert result["is_fahrenheit"] is True

    def test_live_payload_grill_temp_zero(self):
        """Grill is off, grill temp should be 0."""
        result = decode_temperatures(LIVE_SC_12)
        assert result["grill_temp"] == 0

    def test_live_payload_grill_set_temp_zero(self):
        result = decode_temperatures(LIVE_SC_12)
        assert result["grill_set_temp"] == 0

    def test_live_payload_probes_not_connected(self):
        """Probes 2-4 show 960 (not connected) -> should be None."""
        result = decode_temperatures(LIVE_SC_12)
        assert result["p2_temp"] is None
        assert result["p3_temp"] is None
        assert result["p4_temp"] is None

    def test_live_payload_probe1_zero(self):
        """Probe 1 shows 0 when grill is off."""
        result = decode_temperatures(LIVE_SC_12)
        assert result["p1_temp"] == 0

    def test_known_good_payload(self):
        """Construct a known payload and verify decoding.

        Each temperature digit is stored as a separate byte value (0-9),
        NOT as the hex encoding of the full number. So 195F is [01, 09, 05]
        and 250F is [02, 05, 00].
        """
        # FE0C prefix + p1_target=0 + p1_temp=195 + p2_temp=0 +
        # p3_temp=0 + p4_temp=0 + grill_set=250 + grill_temp=248 +
        # is_fahrenheit=1 + FF trailer
        payload = (
            "FE0C"
            + "000000"   # p1_target = 0
            + "010905"   # p1_temp = 195 (1*100 + 9*10 + 5)
            + "000000"   # p2_temp = 0
            + "000000"   # p3_temp = 0
            + "000000"   # p4_temp = 0
            + "020500"   # grill_set_temp = 250
            + "020408"   # grill_temp = 248
            + "01"       # is_fahrenheit = True
            + "FF"       # trailer
        )
        result = decode_temperatures(payload)
        assert result is not None
        assert result["p1_temp"] == 195
        assert result["p2_temp"] == 0
        assert result["grill_set_temp"] == 250
        assert result["grill_temp"] == 248
        assert result["is_fahrenheit"] is True

    def test_celsius_payload_normalized_to_fahrenheit(self):
        """Live payload captured with the panel switched to Celsius.

        Raw digits are 82 (set point) / 102 (current) - actual Celsius
        values, not Fahrenheit shown with a wrong label. decode_temperatures
        must convert them back to Fahrenheit so the rest of the integration
        (bounds, alarms) keeps working regardless of the panel's unit.
        """
        result = decode_temperatures(LIVE_SC_12_CELSIUS)
        assert result is not None
        assert result["is_fahrenheit"] is False
        # 82C -> 179.6F -> rounds to 180, matching the actual 180F set point.
        assert result["grill_set_temp"] == 180
        assert result["smoker_act_temp"] == 180
        # 102C -> 215.6F -> rounds to 216.
        assert result["grill_temp"] == 216

    def test_celsius_payload_zero_not_converted(self):
        """0 means 'no reading', not an actual 0-degree measurement."""
        result = decode_temperatures(LIVE_SC_12_CELSIUS)
        assert result["p1_target"] == 0

    def test_celsius_payload_probe_not_connected_stays_none(self):
        result = decode_temperatures(LIVE_SC_12_CELSIUS)
        assert result["p1_temp"] is None
        assert result["p2_temp"] is None


class TestDecodeStatus:
    """Tests for decode_status() - FE0B payload."""

    def test_wrong_prefix_rejected(self):
        assert decode_status("FE0C0000000000000000") is None

    def test_too_short_rejected(self):
        assert decode_status("FE0B0000") is None

    def test_empty_string_rejected(self):
        assert decode_status("") is None

    def test_live_payload_parses(self):
        """Live FE0B payload (40 bytes) should parse with the fixed length check."""
        result = decode_status(LIVE_SC_11)
        assert result is not None, "40-byte FE0B payload should parse (was failing with < 41 check)"

    def test_live_payload_probes_not_connected(self):
        """p2_temp reads 960 in the live payload -> should be None."""
        result = decode_status(LIVE_SC_11)
        assert result["p2_temp"] is None

    def test_live_payload_light_on(self):
        """Byte 34 = 1 in the live payload -> light is on."""
        result = decode_status(LIVE_SC_11)
        assert result["light_state"] is True

    def test_live_payload_is_fahrenheit(self):
        """Byte 36 = 0 in the live payload -> celsius mode."""
        result = decode_status(LIVE_SC_11)
        # In the live data byte[36]=0, so is_fahrenheit is False
        assert result["is_fahrenheit"] is False

    def test_live_payload_no_errors(self):
        result = decode_status(LIVE_SC_11)
        assert result["err1"] is False
        assert result["high_temp_err"] is False
        assert result["fan_err"] is False
        assert result["hot_err"] is False
        assert result["motor_err"] is False
        assert result["no_pellets"] is False

    def test_live_payload_message_type_1_grill_set_temp(self):
        """parts[23]=1 in live data -> grill_set_temp decoded from bytes 20-22."""
        result = decode_status(LIVE_SC_11)
        # Bytes 20-22 = [0x02, 0x02, 0x00] -> 220
        assert result.get("grill_set_temp") == 220

    def test_live_payload_no_grill_temp(self):
        """parts[23]=1 means grill_temp is NOT in this message."""
        result = decode_status(LIVE_SC_11)
        assert "grill_temp" not in result

    def test_message_type_2_has_grill_temp(self):
        """Construct FE0B with parts[23]=2 to verify grill_temp decoding."""
        # Take live payload and change byte[23] from 01 to 02
        modified = LIVE_SC_11[:46] + "02" + LIVE_SC_11[48:]
        result = decode_status(modified)
        assert result is not None
        # With msg_type=2, bytes 20-22 are decoded as grill_temp
        assert "grill_temp" in result
        assert "grill_set_temp" not in result

    def test_recipe_time_not_in_40_byte_payload(self):
        """40-byte payloads don't have room for full recipe_time."""
        result = decode_status(LIVE_SC_11)
        # recipe_time should be 0 (set to default) since the payload
        # isn't long enough for reliable recipe_time decoding
        assert result.get("recipe_time", 0) == 0


class TestEncodeSetTemperature:
    """Tests for encode_set_temperature()."""

    def test_250(self):
        # 250 -> hundreds=2, tens=5, ones=0 -> 02 05 00
        result = encode_set_temperature(250)
        assert result == "FE0501020500FF"

    def test_180(self):
        # 180 -> hundreds=1, tens=8, ones=0 -> 01 08 00
        result = encode_set_temperature(180)
        assert result == "FE0501010800FF"

    def test_600(self):
        # 600 -> hundreds=6, tens=0, ones=0 -> 06 00 00
        result = encode_set_temperature(600)
        assert result == "FE0501060000FF"

    def test_225(self):
        # 225 -> hundreds=2, tens=2, ones=5 -> 02 02 05
        result = encode_set_temperature(225)
        assert result == "FE0501020205FF"

    def test_350(self):
        # 350 -> hundreds=3, tens=5, ones=0 -> 03 05 00
        result = encode_set_temperature(350)
        assert result == "FE0501030500FF"

    def test_roundtrip(self):
        """Encode a temp, then verify the hex digits decode back correctly."""
        for temp in [180, 200, 225, 250, 275, 300, 350, 400, 450, 500, 550, 600]:
            cmd = encode_set_temperature(temp)
            # Extract the 3 temp bytes (positions 6-11 in the hex string)
            h = int(cmd[6:8], 16)
            t = int(cmd[8:10], 16)
            o = int(cmd[10:12], 16)
            decoded = h * 100 + t * 10 + o
            assert decoded == temp, f"Roundtrip failed for {temp}: got {decoded}"


class TestIntegration:
    """Integration tests combining decoder + live grill data."""

    def test_merged_state_has_all_fields(self):
        """Simulate what the coordinator does: decode both payloads and merge."""
        status = decode_status(LIVE_SC_11)
        temps = decode_temperatures(LIVE_SC_12)

        assert status is not None
        assert temps is not None

        # Merge like the coordinator does
        state = {}
        state.update(status)
        state.update(temps)

        # Should have key fields from both
        assert "module_is_on" in state  # from FE0B
        assert "light_state" in state   # from FE0B
        assert "is_fahrenheit" in state  # from both (FE0C wins due to update order)
        assert "grill_temp" in state     # from FE0C

    def test_fe0c_overrides_fe0b_temps(self):
        """FE0C temperature values should override FE0B when merged.

        This is correct behavior because FE0C is the dedicated temperature
        message and is more reliable.
        """
        status = decode_status(LIVE_SC_11)
        temps = decode_temperatures(LIVE_SC_12)

        state = {}
        state.update(status)
        state.update(temps)

        # FE0C's is_fahrenheit (True) should override FE0B's (False)
        assert state["is_fahrenheit"] is True


# ============================================================================
# Standalone runner
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Grill Master Decoder Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0
    errors = []

    # Collect all test classes
    test_classes = [
        TestParseHexMessage,
        TestConvertTemperature,
        TestDecodeTemperatures,
        TestDecodeStatus,
        TestEncodeSetTemperature,
        TestIntegration,
    ]

    for cls in test_classes:
        print(f"\n--- {cls.__name__} ---")
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith("test_"):
                continue
            method = getattr(instance, method_name)
            try:
                method()
                print(f"  PASS  {method_name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL  {method_name}: {e}")
                failed += 1
                errors.append(f"{cls.__name__}.{method_name}: {e}")
            except Exception as e:
                print(f"  ERROR {method_name}: {type(e).__name__}: {e}")
                failed += 1
                errors.append(f"{cls.__name__}.{method_name}: {type(e).__name__}: {e}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")

    if errors:
        print("\nFailures:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)

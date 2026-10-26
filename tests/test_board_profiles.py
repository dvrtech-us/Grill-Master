"""Tests for board-specific protocol handling."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(ROOT, "custom_components", "grill_master")

_package = types.ModuleType("custom_components")
_package.__path__ = [os.path.join(ROOT, "custom_components")]
sys.modules["custom_components"] = _package

_integration = types.ModuleType("custom_components.grill_master")
_integration.__path__ = [PACKAGE_DIR]
_integration.__package__ = "custom_components.grill_master"
sys.modules["custom_components.grill_master"] = _integration


def _load_module(name: str, path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module(
    "custom_components.grill_master.const",
    os.path.join(PACKAGE_DIR, "const.py"),
)
board_profiles = _load_module(
    "custom_components.grill_master.board_profiles",
    os.path.join(PACKAGE_DIR, "board_profiles.py"),
)
_load_module(
    "custom_components.grill_master.decoder",
    os.path.join(PACKAGE_DIR, "decoder.py"),
)

_previous_aiohttp = sys.modules.get("aiohttp")
if importlib.util.find_spec("aiohttp") is None:
    _aiohttp = types.ModuleType("aiohttp")

    class _ClientTimeout:
        def __init__(self, total):
            self.total = total

    class _ClientError(Exception):
        pass

    class _ClientResponseError(_ClientError):
        status = 500

    _aiohttp.ClientTimeout = _ClientTimeout
    _aiohttp.ClientError = _ClientError
    _aiohttp.ClientResponseError = _ClientResponseError
    sys.modules["aiohttp"] = _aiohttp
    _uses_aiohttp_stub = True
else:
    _uses_aiohttp_stub = False

api_module = _load_module(
    "custom_components.grill_master.api",
    os.path.join(PACKAGE_DIR, "api.py"),
)
if _uses_aiohttp_stub:
    if _previous_aiohttp is None:
        sys.modules.pop("aiohttp", None)
    else:
        sys.modules["aiohttp"] = _previous_aiohttp


class TestBoardProfiles(unittest.TestCase):
    def test_device_id_selects_nexgrill_profile(self):
        self.assertIs(
            board_profiles.profile_for_device_id("NXP-087C5C8"),
            board_profiles.NEXGRILL_MONGOOSE,
        )
        self.assertIs(
            board_profiles.profile_for_device_id("LBL-123456"),
            board_profiles.CONTROL_BOARD_8,
        )
        self.assertIs(
            board_profiles.profile_for_device_id(None),
            board_profiles.CONTROL_BOARD_8,
        )

    def test_poll_intervals_are_profile_specific(self):
        const = sys.modules["custom_components.grill_master.const"]
        self.assertEqual(const.DEFAULT_POLL_INTERVAL, 5)
        self.assertEqual(const.NEXGRILL_POLL_INTERVAL, 15)
        self.assertEqual(board_profiles.CONTROL_BOARD_8.poll_interval, 5)
        self.assertEqual(board_profiles.NEXGRILL_MONGOOSE.poll_interval, 15)

        resolve = board_profiles.resolve_poll_interval
        nexgrill = board_profiles.NEXGRILL_MONGOOSE
        control_board = board_profiles.CONTROL_BOARD_8
        # The shared 5-second default is not an NXP choice.
        self.assertEqual(resolve(nexgrill, None), 15)
        self.assertEqual(resolve(nexgrill, 5), 15)
        self.assertEqual(resolve(nexgrill, 30), 30)
        self.assertEqual(resolve(control_board, None), 5)
        self.assertEqual(resolve(control_board, 5), 5)
        self.assertEqual(resolve(control_board, 10), 10)

    def test_command_frames_match_protocol(self):
        build = board_profiles.build_nexgrill_command
        self.assertEqual(
            build(0x05, (250 // 256, 250 % 256)),
            "225,225,000,010,001,048,005,000,250,",
        )
        self.assertEqual(
            build(0x07, (2,)),
            "225,225,000,009,001,048,007,002,",
        )
        self.assertEqual(
            build(0x33, (1,)),
            "225,225,000,009,001,048,051,001,",
        )
        self.assertEqual(
            build(0x02, (0,)),
            "225,225,000,009,001,048,002,000,",
        )
        self.assertEqual(
            build(0x03, (1,)),
            "225,225,000,009,001,048,003,001,",
        )

    def test_status_maps_wire_fahrenheit_and_module_state(self):
        status = {
            "grillTemp": 82,
            "grillSetTemp": 180,
            "probe1Temp": 190,
            "probe2Temp": 960,
            "probe3Temp": 200,
            "probe4Temp": 210,
            "moduleIsOn": 2,
            "currentMode": 1,
            "cookTimer": 30,
            "isCelsius": True,
            "fanState": "on",
        }
        decoded = board_profiles.decode_nexgrill_status(
            {"message": json.dumps(status)}
        )
        self.assertEqual(decoded["grill_temp"], 82)
        self.assertEqual(decoded["grill_set_temp"], 180)
        self.assertEqual(decoded["p1_temp"], 190)
        self.assertIsNone(decoded["p2_temp"])
        self.assertEqual(decoded["p3_temp"], 200)
        self.assertEqual(decoded["p4_temp"], 210)
        self.assertEqual(decoded["module_state"], 2)
        self.assertTrue(decoded["module_is_on"])
        self.assertEqual(decoded["current_mode"], 1)
        self.assertEqual(decoded["cook_timer"], 30)
        self.assertTrue(decoded["fan_state"])
        self.assertTrue(decoded["is_fahrenheit"])

    def test_off_module_state_is_not_powered(self):
        decoded = board_profiles.decode_nexgrill_status(
            {"message": '{"moduleIsOn": 0}'}
        )
        self.assertFalse(decoded["module_is_on"])

    def test_unknown_module_state_stays_unknown(self):
        decoded = board_profiles.decode_nexgrill_status(
            {"message": '{"moduleIsOn": null}'}
        )
        self.assertIsNone(decoded["module_is_on"])

    def test_empty_or_invalid_status_is_rejected(self):
        self.assertIsNone(board_profiles.decode_nexgrill_status({"message": "{}"}))
        self.assertIsNone(
            board_profiles.decode_nexgrill_status({"message": "not JSON"})
        )


class TestNexgrillApi(unittest.TestCase):
    def test_state_and_timer_rpc_calls(self):
        api = api_module.GrillMasterApi(
            object(), "grill.local", profile=board_profiles.NEXGRILL_MONGOOSE
        )
        calls = []

        async def fake_post(method, params):
            calls.append((method, params))
            return {}

        api._rpc_post = fake_post

        async def exercise():
            await api.get_state()
            await api.set_timer(1, 30)
            await api.set_timer(0, 0)

        asyncio.run(exercise())
        self.assertEqual(
            calls,
            [
                ("GetCurrentTemperatures", {"reply": "full"}),
                ("SetTimer", {"hours": 1, "minutes": 30}),
                ("SetTimer", {"hours": 0, "minutes": 0}),
            ],
        )

    def test_set_temperature_and_start_rpc_command(self):
        api = api_module.GrillMasterApi(
            object(), "grill.local", profile=board_profiles.NEXGRILL_MONGOOSE
        )
        calls = []

        async def fake_post(method, params):
            calls.append((method, params))
            return {}

        api._rpc_post = fake_post

        async def exercise():
            await api.set_temperature(250)
            await api.start()

        asyncio.run(exercise())
        self.assertEqual(
            calls,
            [
                (
                    "SendGenericCommand",
                    {"command": "225,225,000,010,001,048,005,000,250,"},
                ),
                (
                    "SendGenericCommand",
                    {"command": "225,225,000,009,001,048,051,001,"},
                ),
            ],
        )

    def test_control_board_8_rpc_and_temperature_remain_unchanged(self):
        api = api_module.GrillMasterApi(object(), "grill.local")
        calls = []

        async def fake_get(method):
            calls.append(("GET", method))
            return {"sc_11": "", "sc_12": ""}

        async def fake_post(method, params):
            calls.append(("POST", method, params))
            return {}

        api._rpc_get = fake_get
        api._rpc_post = fake_post

        async def exercise():
            await api.get_state()
            await api.set_temperature(250)
            await api.turn_off()

        asyncio.run(exercise())
        self.assertEqual(
            calls,
            [
                ("GET", "PB.GetState"),
                ("POST", "PB.SendMCUCommand", {"command": "FE0501020500FF"}),
                ("POST", "PB.SendMCUCommand", {"command": "FE0102FF"}),
            ],
        )

    def test_mode_off_and_display_unit_rpc_commands(self):
        api = api_module.GrillMasterApi(
            object(), "grill.local", profile=board_profiles.NEXGRILL_MONGOOSE
        )
        calls = []

        async def fake_post(method, params):
            calls.append((method, params))
            return {}

        api._rpc_post = fake_post

        async def exercise():
            await api.set_mode(3)
            await api.turn_off()
            await api.set_display_unit(True)

        asyncio.run(exercise())
        self.assertEqual(
            calls,
            [
                (
                    "SendGenericCommand",
                    {"command": "225,225,000,009,001,048,007,003,"},
                ),
                (
                    "SendGenericCommand",
                    {"command": "225,225,000,009,001,048,002,000,"},
                ),
                (
                    "SendGenericCommand",
                    {"command": "225,225,000,009,001,048,003,001,"},
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()

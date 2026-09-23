from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from server16_py import hidhide_runtime as hh


def _make_runtime(base_dir: Path) -> hh.HidHideRuntime:
    runtime = hh.HidHideRuntime.__new__(hh.HidHideRuntime)
    runtime.app = SimpleNamespace(base_dir=base_dir, log=lambda *a, **k: None)
    runtime._cli_path_cache = None
    return runtime


class DecodeVidPidFromSdlGuidTests(unittest.TestCase):
    def test_decodes_real_switch_pro_controller_guid(self) -> None:
        # Captured live this session from a real Nintendo Switch Pro
        # Controller; vendor/product independently confirmed via
        # Get-PnpDevice on the same machine (VID_057E&PID_2009).
        guid = "030056fb7e0500000920000010026803"
        self.assertEqual(hh.decode_vid_pid_from_sdl_guid(guid), (0x057E, 0x2009))

    def test_rejects_non_hex_guid(self) -> None:
        self.assertIsNone(hh.decode_vid_pid_from_sdl_guid("not-a-guid"))

    def test_rejects_too_short_guid(self) -> None:
        self.assertIsNone(hh.decode_vid_pid_from_sdl_guid("0300"))


class ParseDevGamingJsonTests(unittest.TestCase):
    def _sample_entry(self, **overrides) -> dict:
        entry = {
            "present": True,
            "gamingDevice": True,
            "symbolicLink": r"\\?\HID#VID_057E&PID_2009#8&35c399e5&0&0000",
            "vendor": 0x057E,
            "product": 0x2009,
            "serialNumber": "",
            "usage": 5,
            "description": "Pro Controller",
            "deviceInstancePath": r"HID\VID_057E&PID_2009\8&35C399E5&0&0000",
            "xusbDeviceInstancePath": "",
            "baseContainerDeviceInstancePath": "",
            "baseContainerClassGuid": "",
            "baseContainerDeviceCount": 1,
        }
        entry.update(overrides)
        return entry

    def test_parses_a_list_of_devices(self) -> None:
        text = json.dumps([self._sample_entry()])
        devices = hh.parse_dev_gaming_json(text)
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.vendor, 0x057E)
        self.assertEqual(device.product, 0x2009)
        self.assertEqual(device.instance_path, r"HID\VID_057E&PID_2009\8&35C399E5&0&0000")
        self.assertEqual(device.description, "Pro Controller")
        self.assertTrue(device.gaming_device)

    def test_tolerates_a_single_object_not_wrapped_in_a_list(self) -> None:
        text = json.dumps(self._sample_entry())
        devices = hh.parse_dev_gaming_json(text)
        self.assertEqual(len(devices), 1)

    def test_returns_empty_list_for_garbage_input(self) -> None:
        self.assertEqual(hh.parse_dev_gaming_json("not json at all"), [])
        self.assertEqual(hh.parse_dev_gaming_json(""), [])
        self.assertEqual(hh.parse_dev_gaming_json("42"), [])

    def test_skips_malformed_entries_but_keeps_valid_ones(self) -> None:
        text = json.dumps([self._sample_entry(), "not a dict", self._sample_entry(vendor=0x1234)])
        devices = hh.parse_dev_gaming_json(text)
        self.assertEqual(len(devices), 2)
        self.assertEqual({d.vendor for d in devices}, {0x057E, 0x1234})

    def test_missing_fields_default_sanely(self) -> None:
        text = json.dumps([{}])
        devices = hh.parse_dev_gaming_json(text)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].vendor, 0)
        self.assertEqual(devices[0].instance_path, "")

    def test_parses_the_real_grouped_output_with_string_vendor_product(self) -> None:
        # Regression test for the real, live-reported bug behind "Hide from
        # FIFA does nothing": --dev-gaming's actual output (HidHide 1.5.230,
        # captured live 2026-09-23) is a list of GROUPS, one per physical
        # controller, and each device's vendor/product are human-readable
        # STRINGS ("Nintendo Co., Ltd.", "Pro Controller"), never integers.
        # The original parser assumed a flat list of integer-id devices, so
        # every real device silently came back vendor=0/product=0 and
        # resolve_device_for_guid() never matched anything.
        raw = json.dumps(
            [
                {
                    "friendlyName": "Nintendo Co., Ltd. Pro Controller",
                    "devices": [
                        {
                            "present": True,
                            "gamingDevice": True,
                            "symbolicLink": r"\\?\hid#vid_057e&pid_2009#8&35c399e5&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}",
                            "vendor": "Nintendo Co., Ltd.",
                            "product": "Pro Controller",
                            "serialNumber": "000000000001",
                            "usage": "Joystick",
                            "description": "Dispositivo de juego compatible con HID",
                            "deviceInstancePath": r"HID\VID_057E&PID_2009\8&35c399e5&0&0000",
                            "baseContainerDeviceInstancePath": r"USB\VID_057E&PID_2009\000000000001",
                            "baseContainerClassGuid": "{745A17A0-74D3-11D0-B6FE-00A0C90F57DA}",
                            "baseContainerDeviceCount": 1,
                        }
                    ],
                }
            ]
        )
        devices = hh.parse_dev_gaming_json(raw)
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.vendor, 0x057E)
        self.assertEqual(device.product, 0x2009)
        self.assertEqual(device.instance_path, r"HID\VID_057E&PID_2009\8&35c399e5&0&0000")
        self.assertEqual(device.description, "Nintendo Co., Ltd. Pro Controller")

    def test_grouped_output_with_several_collections_yields_several_devices(self) -> None:
        raw = json.dumps(
            [
                {
                    "friendlyName": "Some Bluetooth Pad",
                    "devices": [
                        {"deviceInstancePath": r"HID\...\VID&0002057e_PID&2009&Col01\9&abc&0&0000"},
                        {"deviceInstancePath": r"HID\...\VID&0002057e_PID&2009&Col02\9&abc&0&0001"},
                    ],
                }
            ]
        )
        devices = hh.parse_dev_gaming_json(raw)
        self.assertEqual(len(devices), 2)
        self.assertTrue(all(d.vendor == 0x057E and d.product == 0x2009 for d in devices))


class ParseVidPidFromInstancePathTests(unittest.TestCase):
    def test_decodes_usb_style_instance_path(self) -> None:
        self.assertEqual(
            hh.parse_vid_pid_from_instance_path(r"HID\VID_057E&PID_2009\8&35c399e5&0&0000"),
            (0x057E, 0x2009),
        )

    def test_decodes_bluetooth_style_path_with_source_prefixed_vid(self) -> None:
        # Bluetooth-style paths prefix the VID field with a 4-digit source
        # id (0002 = Bluetooth) -- the real vendor id is the last 4 hex
        # digits.
        self.assertEqual(
            hh.parse_vid_pid_from_instance_path(r"HID\...\VID&0002057e_PID&2009&Col01\9&abc&0&0000"),
            (0x057E, 0x2009),
        )

    def test_returns_none_when_vid_or_pid_missing(self) -> None:
        self.assertIsNone(hh.parse_vid_pid_from_instance_path(r"HID\SOMETHING_ELSE\0"))
        self.assertIsNone(hh.parse_vid_pid_from_instance_path(""))


class ResolveDevicesForGuidTests(unittest.TestCase):
    def test_returns_every_matching_collection(self) -> None:
        runtime = _make_runtime(Path("."))
        col1 = hh.HidHideDevice(r"...\Col01\0", "", 0x057E, 0x2009, "Pro Controller", True)
        col2 = hh.HidHideDevice(r"...\Col02\1", "", 0x057E, 0x2009, "Pro Controller", True)
        unrelated = hh.HidHideDevice(r"...\other", "", 0x045E, 0x02FE, "Other", True)
        runtime.find_gaming_devices = lambda: [col1, unrelated, col2]
        result = runtime.resolve_devices_for_guid("030056fb7e0500000920000010026803")
        self.assertEqual(result, [col1, col2])

    def test_excludes_matches_with_no_instance_path(self) -> None:
        runtime = _make_runtime(Path("."))
        empty_path = hh.HidHideDevice("", "", 0x057E, 0x2009, "Pro Controller", True)
        runtime.find_gaming_devices = lambda: [empty_path]
        self.assertEqual(runtime.resolve_devices_for_guid("030056fb7e0500000920000010026803"), [])


class ParseAppListTests(unittest.TestCase):
    def test_extracts_quoted_paths_from_app_reg_lines(self) -> None:
        text = (
            '--app-reg "E:\\Fifa\\FIFA 16 test\\fip\\fifa16.exe"\n'
            '--app-reg "C:\\Other\\thing.exe"\n'
        )
        self.assertEqual(
            hh.parse_app_list(text),
            ["E:\\Fifa\\FIFA 16 test\\fip\\fifa16.exe", "C:\\Other\\thing.exe"],
        )

    def test_ignores_unrelated_lines(self) -> None:
        text = "some banner text\n--app-reg \"C:\\a.exe\"\ntrailing junk\n"
        self.assertEqual(hh.parse_app_list(text), ["C:\\a.exe"])

    def test_empty_input_yields_empty_list(self) -> None:
        self.assertEqual(hh.parse_app_list(""), [])


class ResolveDeviceForGuidTests(unittest.TestCase):
    def test_matches_by_decoded_vendor_and_product(self) -> None:
        runtime = _make_runtime(Path("."))
        device = hh.HidHideDevice(
            instance_path=r"HID\VID_057E&PID_2009\8&35C399E5&0&0000",
            xusb_instance_path="",
            vendor=0x057E,
            product=0x2009,
            description="Pro Controller",
            gaming_device=True,
        )
        runtime.find_gaming_devices = lambda: [device]
        resolved = runtime.resolve_device_for_guid("030056fb7e0500000920000010026803")
        self.assertIs(resolved, device)

    def test_returns_none_when_no_device_matches(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.find_gaming_devices = lambda: []
        self.assertIsNone(runtime.resolve_device_for_guid("030056fb7e0500000920000010026803"))

    def test_returns_none_for_undecodable_guid(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.find_gaming_devices = lambda: []
        self.assertIsNone(runtime.resolve_device_for_guid("garbage"))


class HideDeviceForSlotTests(unittest.TestCase):
    """Regression coverage for three real, live-reported bugs in one action
    ("enable Hide from FIFA"):
    1. UX -- this used to trigger up to THREE separate elevated
       HidHideCLI.exe calls (--dev-hide, --cloak-on, a separate
       ensure_own_process_excluded() call) -- three UAC prompts for one
       checkbox.
    2. Correctness -- HidHide only filters NEW opens; a program that
       already has the device open (confirmed live: Steam, for the whole
       time it runs) keeps seeing it until the device is restarted. Without
       the restart, hiding never actually stopped FIFA (or Steam) from
       reading the raw pad -- the exact "FIFA still shows the physical
       controller" symptom reported live.
    3. A UAC prompt on EVERY checkbox toggle that still did nothing --
       root cause found 2026-09-23: routing HidHideCLI.exe through a
       generated .bat file (the technique previously used to combine the
       hide + restart into one elevated call) reproducibly broke
       HidHideCLI's own argument handling ("The command is not recognized",
       confirmed live via a byte-for-byte comparison against the exact same
       argv run directly), while a PLAIN UNELEVATED call worked correctly
       every time on the same machine -- so hide_device_for_slot() now
       tries unelevated first (usually needs no UAC prompt at all) and
       only retries elevated -- via a direct, non-.bat call, see
       hidhide_runtime._run_exe -- if the unelevated attempt's own
       re-verification (--dev-list/--cloak-state) shows it didn't work.

    hide_device_for_slot() only ever returns True once --dev-list/
    --cloak-state confirm the device is actually hidden -- never off any
    attempt's own exit code (the same "re-check real state" rule this
    codebase's other driver-adjacent code already follows)."""

    def _device(self, instance_path=r"HID\VID_057E&PID_2009\8&35C399E5&0&0000") -> hh.HidHideDevice:
        return hh.HidHideDevice(
            instance_path=instance_path,
            xusb_instance_path="",
            vendor=0x057E,
            product=0x2009,
            description="Pro Controller",
            gaming_device=True,
        )

    def _make_runtime(self, devices: list["hh.HidHideDevice"], hidden_after=None, cloak_after=True):
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        runtime.resolve_devices_for_guid = lambda guid: devices
        self.command_calls: list[tuple[list[str], bool]] = []
        self.restart_calls: list[tuple[list[str], bool]] = []

        def fake_run_command(args, elevated, timeout=20.0):
            self.command_calls.append((list(args), elevated))
            return 0, ""

        def fake_restart(paths, elevated):
            self.restart_calls.append((list(paths), elevated))

        runtime._run_command = fake_run_command
        runtime._restart_devices = fake_restart
        hidden = hidden_after if hidden_after is not None else [d.instance_path for d in devices]
        runtime._hidden_instance_paths = lambda: (hidden, cloak_after)
        return runtime

    def test_tries_unelevated_first_and_succeeds_with_no_elevation_at_all(self) -> None:
        # Confirmed live 2026-09-23: this is the common case on a real
        # machine -- zero UAC prompts needed.
        device = self._device()
        runtime = self._make_runtime([device])

        result = runtime.hide_device_for_slot("030056fb7e0500000920000010026803", own_exe=r"C:\App\Server16Python.exe")

        self.assertTrue(result)
        self.assertEqual(len(self.command_calls), 1, "must not escalate to elevated once unelevated verifies")
        args, elevated = self.command_calls[0]
        self.assertFalse(elevated)
        self.assertEqual(
            args,
            ["--dev-hide", device.instance_path, "--cloak-on", "--app-reg", r"C:\App\Server16Python.exe"],
        )
        self.assertEqual(self.restart_calls, [([device.instance_path], False)])

    def test_without_own_exe_still_hides_and_restarts_but_skips_app_reg(self) -> None:
        device = self._device()
        runtime = self._make_runtime([device])

        result = runtime.hide_device_for_slot("030056fb7e0500000920000010026803")

        self.assertTrue(result)
        args, _elevated = self.command_calls[0]
        self.assertNotIn("--app-reg", args)

    def test_hides_and_restarts_every_collection_of_a_multi_collection_device(self) -> None:
        # A Bluetooth pad can expose several HID collections under the same
        # VID/PID -- all of them must be hidden or FIFA keeps reading
        # whichever one was left visible.
        col1 = self._device(instance_path=r"HID\...\VID&0002057e_PID&2009&Col01\9&abc&0&0000")
        col2 = self._device(instance_path=r"HID\...\VID&0002057e_PID&2009&Col02\9&abc&0&0001")
        runtime = self._make_runtime([col1, col2])

        result = runtime.hide_device_for_slot("030056fb7e0500000920000010026803")

        self.assertTrue(result)
        args, _elevated = self.command_calls[0]
        self.assertEqual(args.count("--dev-hide"), 2)
        self.assertIn(col1.instance_path, args)
        self.assertIn(col2.instance_path, args)
        self.assertEqual(self.restart_calls[0][0], [col1.instance_path, col2.instance_path])

    def test_retries_elevated_only_when_the_unelevated_attempt_did_not_verify(self) -> None:
        device = self._device()
        runtime = self._make_runtime([device])
        # First verification (right after the unelevated attempt) reports
        # not hidden; second (after the elevated retry) reports success.
        attempts = {"n": 0}

        def fake_hidden():
            attempts["n"] += 1
            if attempts["n"] == 1:
                return [], False
            return [device.instance_path], True

        runtime._hidden_instance_paths = fake_hidden

        result = runtime.hide_device_for_slot("030056fb7e0500000920000010026803")

        self.assertTrue(result)
        self.assertEqual([e for _a, e in self.command_calls], [False, True])
        self.assertEqual([e for _p, e in self.restart_calls], [False, True])

    def test_returns_false_and_does_not_claim_success_when_neither_attempt_verifies(self) -> None:
        device = self._device()
        runtime = self._make_runtime([device], hidden_after=[], cloak_after=False)

        result = runtime.hide_device_for_slot("030056fb7e0500000920000010026803")

        self.assertFalse(result)
        # Both the unelevated attempt and the elevated retry must have run.
        self.assertEqual([e for _a, e in self.command_calls], [False, True])

    def test_returns_false_when_no_device_resolves_for_the_guid(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        runtime.resolve_devices_for_guid = lambda guid: []
        runtime._run_command = lambda *a, **k: self.fail("must not run any command")

        self.assertFalse(runtime.hide_device_for_slot("030056fb7e0500000920000010026803"))

    def test_never_launches_hidhidecli_through_a_bat_file(self) -> None:
        # Regression test for the actual root cause: _run_elevated_batch
        # (the .bat-based mechanism) must no longer exist on this class at
        # all -- hide_device_for_slot must route every call through
        # _run_command/_restart_devices instead.
        self.assertFalse(hasattr(hh.HidHideRuntime, "_run_elevated_batch"))


class RunExeTests(unittest.TestCase):
    """_run_exe() is the shared, non-.bat process launcher hide_device_for_
    slot/unhide_device_for_slot rely on for both HidHideCLI.exe and
    pnputil.exe -- see its own docstring for the live-reproduced bug this
    replaced (a .bat-routed HidHideCLI.exe call reproducibly broke, a
    directly-launched one did not)."""

    def test_unelevated_uses_a_plain_subprocess_call_with_no_shell(self) -> None:
        app = SimpleNamespace(log=lambda *a, **k: None)
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stdout="out", stderr="")

        original = hh.subprocess.run
        hh.subprocess.run = fake_run
        try:
            code, output = hh._run_exe(
                app, r"C:\tool.exe", ["--flag", "value"], elevated=False, timeout=5.0, label="tool.exe"
            )
        finally:
            hh.subprocess.run = original
        self.assertEqual(code, 0)
        self.assertEqual(output, "out")
        self.assertEqual(captured["argv"], [r"C:\tool.exe", "--flag", "value"])
        self.assertNotIn("shell", captured["kwargs"])
        # HidHideCLI only saves and exits on stdin EOF -- see _run_exe.
        self.assertIs(captured["kwargs"].get("stdin"), hh.subprocess.DEVNULL)

    def test_elevated_never_writes_a_bat_file(self) -> None:
        app = SimpleNamespace(log=lambda *a, **k: None)
        calls = []
        original = hh.shell_execute_elevated_and_wait
        hh.shell_execute_elevated_and_wait = lambda file, params: (calls.append((file, params)), True)[1]
        try:
            code, output = hh._run_exe(
                app, r"C:\tool.exe", ["--flag", "value"], elevated=True, timeout=5.0, label="tool.exe"
            )
        finally:
            hh.shell_execute_elevated_and_wait = original
        self.assertEqual(len(calls), 1)
        file, params = calls[0]
        # Elevates the real exe directly -- never a generated .bat path.
        self.assertEqual(file, r"C:\tool.exe")
        self.assertFalse(file.endswith(".bat"))
        self.assertIn("--flag", params)
        self.assertEqual(code, 0)

    def test_elevated_returns_none_when_elevation_is_declined(self) -> None:
        app = SimpleNamespace(log=lambda *a, **k: None)
        original = hh.shell_execute_elevated_and_wait
        hh.shell_execute_elevated_and_wait = lambda file, params: False
        try:
            code, output = hh._run_exe(app, r"C:\tool.exe", [], elevated=True, timeout=5.0, label="tool.exe")
        finally:
            hh.shell_execute_elevated_and_wait = original
        self.assertIsNone(code)



class EnsureHiddenForSlotTests(unittest.TestCase):
    """Startup re-apply of Hide from FIFA -- must never elevate, and must not
    touch anything (not even restart the pad) when it's already hidden."""

    def _runtime(self, hidden, cloak_on):
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        device = hh.HidHideDevice(r"HID\VID_057E&PID_2009\8&1&0", "", 0x057E, 0x2009, "Pro Controller", True)
        runtime.resolve_devices_for_guid = lambda guid: [device]
        runtime._hidden_instance_paths = lambda: (hidden, cloak_on)
        runtime._run_command = lambda args, elevated, timeout=20.0: (0, '--app-reg "C:\\App\\S.exe"\n')
        self.hide_calls = []
        runtime.hide_device_for_slot = lambda guid, own_exe=None, allow_elevation=True: (
            self.hide_calls.append(allow_elevation),
            True,
        )[1]
        return runtime, device

    def test_already_hidden_does_nothing(self) -> None:
        runtime, _device = self._runtime([r"HID\VID_057E&PID_2009\8&1&0"], True)
        self.assertTrue(runtime.ensure_hidden_for_slot("030056fb7e0500000920000010026803", own_exe=r"C:\App\S.exe"))
        self.assertEqual(self.hide_calls, [])

    def test_hidden_but_own_exe_not_allow_listed_is_reapplied(self) -> None:
        runtime, _device = self._runtime([r"HID\VID_057E&PID_2009\8&1&0"], True)
        runtime.ensure_hidden_for_slot("030056fb7e0500000920000010026803", own_exe=r"D:\Moved\S.exe")
        self.assertEqual(self.hide_calls, [False])

    def test_not_hidden_hides_without_elevation(self) -> None:
        runtime, _device = self._runtime([], False)
        self.assertTrue(runtime.ensure_hidden_for_slot("030056fb7e0500000920000010026803"))
        self.assertEqual(self.hide_calls, [False])

    def test_hidden_but_cloak_off_is_reapplied(self) -> None:
        runtime, _device = self._runtime([r"HID\VID_057E&PID_2009\8&1&0"], False)
        runtime.ensure_hidden_for_slot("030056fb7e0500000920000010026803")
        self.assertEqual(self.hide_calls, [False])


class HideWithoutElevationTests(unittest.TestCase):
    def test_allow_elevation_false_never_retries_elevated(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        device = hh.HidHideDevice(r"HID\VID_057E&PID_2009\8&1&0", "", 0x057E, 0x2009, "Pro Controller", True)
        runtime.resolve_devices_for_guid = lambda guid: [device]
        runtime._hidden_instance_paths = lambda: ([], False)
        elevations = []
        runtime._run_command = lambda args, elevated, timeout=20.0: (elevations.append(elevated), (0, ""))[1]
        runtime._restart_devices = lambda paths, elevated: elevations.append(elevated)
        self.assertFalse(runtime.hide_device_for_slot("030056fb7e0500000920000010026803", allow_elevation=False))
        self.assertNotIn(True, elevations)


class UnhideDeviceForSlotTests(unittest.TestCase):
    """unhide_device_for_slot() matches by what HidHide itself reports as
    hidden (decoded VID/PID from --dev-list), not by --dev-gaming -- a
    disconnected pad never appears in --dev-gaming's list at all, but must
    still be unhidable."""

    def test_unhides_every_hidden_collection_matching_the_guid(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        hidden_before = [
            r"HID\...\VID&0002057e_PID&2009&Col01\9&abc&0&0000",
            r"HID\...\VID&0002057e_PID&2009&Col02\9&abc&0&0001",
            r"HID\VID_045E&PID_02FE\other",  # unrelated device, must be left alone
        ]
        calls: list[list[str]] = []

        def fake_hidden():
            # Second call (post-verification) reports nothing left hidden
            # for this guid -- confirms unhide worked.
            remaining = [p for p in hidden_before if "057e" not in p.lower()]
            return (remaining if calls else hidden_before), True

        runtime._hidden_instance_paths = fake_hidden
        runtime._run_command = lambda args, elevated, timeout=20.0: (calls.append(list(args)), (0, ""))[1]

        result = runtime.unhide_device_for_slot("030056fb7e0500000920000010026803")

        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].count("--dev-unhide"), 2)
        self.assertNotIn(r"HID\VID_045E&PID_02FE\other", calls[0])

    def test_returns_false_when_nothing_is_hidden_for_the_guid(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        runtime._hidden_instance_paths = lambda: ([], False)
        runtime._run_command = lambda *a, **k: self.fail("must not run any command")

        self.assertFalse(runtime.unhide_device_for_slot("030056fb7e0500000920000010026803"))

    def test_returns_false_when_unhide_does_not_verify(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        hidden = [r"HID\VID_057E&PID_2009\8&35C399E5&0&0000"]
        runtime._hidden_instance_paths = lambda: (hidden, True)  # never actually clears
        runtime._run_command = lambda args, elevated, timeout=20.0: (0, "")

        self.assertFalse(runtime.unhide_device_for_slot("030056fb7e0500000920000010026803"))


class FindHidhideCliTests(unittest.TestCase):
    """Regression coverage for the exact bug a live install exposed: the
    dedicated vendor registry key this module checks first
    (_INSTALL_PATH_REGISTRY_KEY) does not exist on a real machine at all --
    the only registry evidence of where HidHide actually landed is
    InstallLocation on its ordinary Add/Remove Programs uninstall entry
    (the same one _find_uninstall_registry_entry() already reads for
    uninstall_hidhide()), and the real CLI is nested one level deeper
    (x64\\HidHideCLI.exe) than the install root itself."""

    def test_finds_cli_via_uninstall_registry_install_location(self) -> None:
        with TemporaryDirectory() as tmp:
            install_dir = Path(tmp) / "HidHide"
            cli_dir = install_dir / "x64"
            cli_dir.mkdir(parents=True)
            cli_path = cli_dir / "HidHideCLI.exe"
            cli_path.write_bytes(b"")
            runtime = _make_runtime(Path("."))
            runtime._find_uninstall_registry_entry = lambda: {"install_location": str(install_dir)}
            self.assertEqual(runtime.find_hidhide_cli(), cli_path)

    def test_returns_none_when_install_location_missing_and_no_candidate_matches(self) -> None:
        runtime = _make_runtime(Path("."))
        runtime._find_uninstall_registry_entry = lambda: None
        # None of the hardcoded candidate dirs exist on the test machine
        # (or if HidHide really is installed here, this at least proves the
        # method doesn't crash) -- just assert it doesn't raise.
        runtime.find_hidhide_cli()


class EnsureOwnProcessExcludedTests(unittest.TestCase):
    """Regression coverage for a real, live-reported bug: this method used
    to be named ensure_fifa_whitelisted() and registered FIFA's own exe on
    HidHide's allow-list. HidHide's allow-list is an EXCLUSION list -- an
    app on it can still see a hidden device, every other app can't -- so
    that registered FIFA as exempt from the cloak, defeating the entire
    feature (FIFA kept reading the "hidden" physical pad directly, which is
    exactly what a live user reported: buttons pressing themselves in-game
    even with Hide from FIFA enabled). The fix registers THIS process
    instead, and leaves FIFA off the list entirely."""

    @staticmethod
    def _make_runtime():
        runtime = _make_runtime(Path("."))
        runtime.is_hidhide_installed = lambda: True
        return runtime

    def test_registers_this_process_not_fifa(self) -> None:
        runtime = self._make_runtime()
        calls: list[tuple[list[str], bool]] = []

        def fake_run_command(args, elevated, timeout=20.0):
            calls.append((list(args), elevated))
            if args[0] == "--app-list":
                registered = any(c[0][0] == "--app-reg" for c in calls)
                return 0, (f'--app-reg "{sys.executable}"\n' if registered else "")
            return 0, ""

        runtime._run_command = fake_run_command
        self.assertTrue(runtime.ensure_own_process_excluded())
        reg_calls = [c for c in calls if c[0][0] == "--app-reg"]
        self.assertEqual(len(reg_calls), 1)
        self.assertEqual(reg_calls[0][0][1], sys.executable)
        self.assertTrue(reg_calls[0][1], "the --app-reg call must run elevated")
        # The one thing this bug fix exists to guarantee: FIFA's own path
        # must never appear in any --app-reg call this method makes.
        self.assertTrue(all("fifa" not in arg.lower() for c in reg_calls for arg in c[0]))

    def test_already_registered_short_circuits_without_reregistering(self) -> None:
        runtime = self._make_runtime()
        calls: list[list[str]] = []

        def fake_run_command(args, elevated, timeout=20.0):
            calls.append(list(args))
            if args[0] == "--app-list":
                return 0, f'--app-reg "{sys.executable}"\n'
            return 0, ""

        runtime._run_command = fake_run_command
        self.assertTrue(runtime.ensure_own_process_excluded())
        self.assertFalse(any(c[0] == "--app-reg" for c in calls))

    def test_returns_false_when_registration_does_not_verify(self) -> None:
        runtime = self._make_runtime()
        runtime._run_command = lambda args, elevated, timeout=20.0: (0, "")
        self.assertFalse(runtime.ensure_own_process_excluded())


class SplitCommandLineTests(unittest.TestCase):
    def test_splits_quoted_path_with_trailing_args(self) -> None:
        exe, params = hh.HidHideRuntime._split_command_line(
            r'"C:\Program Files\Nefarius Software Solutions e.U\HidHide\unins000.exe" /SILENT'
        )
        self.assertEqual(exe, r"C:\Program Files\Nefarius Software Solutions e.U\HidHide\unins000.exe")
        self.assertEqual(params, "/SILENT")

    def test_splits_quoted_path_with_no_args(self) -> None:
        exe, params = hh.HidHideRuntime._split_command_line(r'"C:\path\unins000.exe"')
        self.assertEqual(exe, r"C:\path\unins000.exe")
        self.assertEqual(params, "")

    def test_splits_unquoted_path_with_args(self) -> None:
        exe, params = hh.HidHideRuntime._split_command_line(r"C:\path\unins000.exe /X{GUID} /qn")
        self.assertEqual(exe, r"C:\path\unins000.exe")
        self.assertEqual(params, "/X{GUID} /qn")

    def test_empty_command_line(self) -> None:
        exe, params = hh.HidHideRuntime._split_command_line("")
        self.assertEqual(exe, "")
        self.assertEqual(params, "")


class FindHidhideInstallerTests(unittest.TestCase):
    """Regression coverage for the exact bug a live placement of the real
    HidHide download (HidHide_1.5.230_x64.exe -- an .exe, not the .msi this
    module originally assumed based on research alone) would have exposed
    had discovery been hardcoded to .msi only."""

    def test_finds_the_real_current_exe_installer(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            hidhide_dir = base / "bin" / "HidHide"
            hidhide_dir.mkdir(parents=True)
            exe_path = hidhide_dir / "HidHide_1.5.230_x64.exe"
            exe_path.write_bytes(b"")
            self.assertEqual(_make_runtime(base).find_hidhide_installer(), exe_path)

    def test_finds_a_legacy_msi(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            hidhide_dir = base / "bin" / "HidHide"
            hidhide_dir.mkdir(parents=True)
            msi_path = hidhide_dir / "HidHideMSI.msi"
            msi_path.write_bytes(b"")
            self.assertEqual(_make_runtime(base).find_hidhide_installer(), msi_path)

    def test_prefers_exe_over_msi_when_both_present(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            hidhide_dir = base / "bin" / "HidHide"
            hidhide_dir.mkdir(parents=True)
            (hidhide_dir / "HidHideMSI.msi").write_bytes(b"")
            exe_path = hidhide_dir / "HidHide_1.5.230_x64.exe"
            exe_path.write_bytes(b"")
            self.assertEqual(_make_runtime(base).find_hidhide_installer(), exe_path)

    def test_returns_none_when_nothing_placed(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertIsNone(_make_runtime(Path(tmp)).find_hidhide_installer())

    def test_falls_back_to_resource_dir_when_base_dir_has_nothing(self) -> None:
        # Regression test for the actual live-reported bug ("the Install
        # HidHide button does nothing"): in a frozen onefile build, an
        # installer placed under the source repo's bin/HidHide/ at build
        # time is bundled by Server16Python.spec's datas entry, but
        # extracts to sys._MEIPASS at runtime (app.resource_dir) -- NOT to
        # the folder holding the deployed .exe (app.base_dir). HidHide has
        # no pip-package fallback the way ViGEmBus/vgamepad does, so
        # looking only at base_dir meant this could never find anything in
        # a real deployed build unless the installer was *also* manually
        # copied next to the deployed exe after building.
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "deployed"
            resource = Path(tmp) / "_MEIxxxxxx"
            base.mkdir(parents=True)
            resource_hidhide_dir = resource / "bin" / "HidHide"
            resource_hidhide_dir.mkdir(parents=True)
            exe_path = resource_hidhide_dir / "HidHide_1.5.230_x64.exe"
            exe_path.write_bytes(b"")
            runtime = hh.HidHideRuntime.__new__(hh.HidHideRuntime)
            runtime.app = SimpleNamespace(base_dir=base, resource_dir=resource)
            runtime._cli_path_cache = None
            self.assertEqual(runtime.find_hidhide_installer(), exe_path)

    def test_prefers_base_dir_override_over_resource_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "deployed"
            resource = Path(tmp) / "_MEIxxxxxx"
            base_hidhide_dir = base / "bin" / "HidHide"
            base_hidhide_dir.mkdir(parents=True)
            resource_hidhide_dir = resource / "bin" / "HidHide"
            resource_hidhide_dir.mkdir(parents=True)
            override_exe = base_hidhide_dir / "HidHide_override.exe"
            override_exe.write_bytes(b"")
            (resource_hidhide_dir / "HidHide_bundled.exe").write_bytes(b"")
            runtime = hh.HidHideRuntime.__new__(hh.HidHideRuntime)
            runtime.app = SimpleNamespace(base_dir=base, resource_dir=resource)
            runtime._cli_path_cache = None
            self.assertEqual(runtime.find_hidhide_installer(), override_exe)


if __name__ == "__main__":
    unittest.main()

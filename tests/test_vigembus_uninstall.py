from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from server16_py import vigembus_uninstall as vu
from server16_py.win_elevation import RawArg

# `pnputil /enum-drivers` on a Spanish Windows (labels localized, values not),
# trimmed to the blocks that matter: ViGEmBus next to Rainway's unrelated
# virtual bus driver and an ordinary AMD one.
SPANISH_LISTING = """Utilidad PnP de Microsoft

Nombre publicado:     oem12.inf
Nombre original:      amdafd.inf
Nombre del proveedor:      AMD
Nombre de clase:         Dispositivos del sistema

Nombre publicado:     oem52.inf
Nombre original:      ireulbus.inf
Nombre del proveedor:      Rainway, Inc.
Nombre de clase:         Dispositivos del sistema

Nombre publicado:     oem15.inf
Nombre original:      vigembus.inf
Nombre del proveedor:      Nefarius Software Solutions e.U.
Nombre de clase:         Dispositivos del sistema
Versión del controlador:     12/14/2020 1.17.333.0
"""

ENGLISH_LISTING = """Microsoft PnP Utility

Published Name:     oem87.inf
Original Name:      ViGEmBus.inf
Provider Name:      Nefarius Software Solutions e.U.
Class Name:         System devices

Published Name:     oem3.inf
Original Name:      hidguardian.inf
Provider Name:      Nefarius Software Solutions e.U.
Class Name:         System devices
"""


class ParseDriverPackagesTests(unittest.TestCase):
    def test_finds_only_vigembus_in_a_localized_listing(self) -> None:
        self.assertEqual(vu.parse_driver_packages(SPANISH_LISTING), ["oem15.inf"])

    def test_matches_case_insensitively_and_ignores_other_nefarius_drivers(self) -> None:
        # HidGuardian is also from Nefarius but is not ViGEmBus.
        self.assertEqual(vu.parse_driver_packages(ENGLISH_LISTING), ["oem87.inf"])

    def test_a_vigembus_named_inf_from_another_publisher_is_left_alone(self) -> None:
        listing = "Published Name:  oem9.inf\nOriginal Name:  vigembus.inf\nProvider Name:  Someone Else\n"
        self.assertEqual(vu.parse_driver_packages(listing), [])

    def test_lists_every_installed_version_once(self) -> None:
        both = ENGLISH_LISTING + "\n" + SPANISH_LISTING + "\n" + SPANISH_LISTING
        self.assertEqual(vu.parse_driver_packages(both), ["oem87.inf", "oem15.inf"])

    def test_empty_listing(self) -> None:
        self.assertEqual(vu.parse_driver_packages(""), [])


class ProductCodeTests(unittest.TestCase):
    GUID = "{93D91F60-7C94-4A79-863F-EA713D2EB3F3}"

    def test_reads_the_code_from_the_msi_uninstall_string(self) -> None:
        self.assertEqual(vu.product_code_for("ignored", f"MsiExec.exe /X{self.GUID}", None), self.GUID)

    def test_reads_it_from_the_install_flavoured_string_too(self) -> None:
        self.assertEqual(vu.product_code_for("ignored", f"msiexec /I{self.GUID}", None), self.GUID)

    def test_normalizes_the_code_to_uppercase(self) -> None:
        self.assertEqual(vu.product_code_for("k", f"MsiExec.exe /X{self.GUID.lower()}", None), self.GUID)

    def test_falls_back_to_the_key_name_for_a_windows_installer_product(self) -> None:
        self.assertEqual(vu.product_code_for(self.GUID, "", 1), self.GUID)

    def test_a_non_msi_registration_has_no_product_code(self) -> None:
        self.assertIsNone(vu.product_code_for("ViGEmBus", r'"C:\x\uninstall.exe" /S', None))
        self.assertIsNone(vu.product_code_for(self.GUID, "", None))


class IsVigembusDeviceTests(unittest.TestCase):
    def test_matches_by_hardware_id(self) -> None:
        self.assertTrue(vu.is_vigembus_device(["Nefarius\\ViGEmBus\\Gen1"], None))
        self.assertTrue(vu.is_vigembus_device("nefarius\\vigembus\\gen1", None))

    def test_matches_by_service_name(self) -> None:
        self.assertTrue(vu.is_vigembus_device(["something\\else"], "ViGEmBus"))

    def test_other_virtual_bus_drivers_are_not_touched(self) -> None:
        for hardware_id, service in (
            (["root\\IreulBus"], "IreulBus"),  # Rainway
            (["root\\steamxbox"], "steamxbox"),  # Steam
            (["root\\LGHUBVirtualBus"], "logi_joy_bus_enum"),  # Logitech
            (["Root\\HidGuardian"], None),  # Nefarius, but a different driver
        ):
            with self.subTest(hardware_id=hardware_id):
                self.assertFalse(vu.is_vigembus_device(hardware_id, service))


class StateTests(unittest.TestCase):
    def test_default_state_is_clean(self) -> None:
        state = vu.ViGEmBusState()
        self.assertTrue(state.is_clean)
        self.assertFalse(state.restart_pending)
        self.assertEqual(state.leftovers(), [])

    def test_every_kind_of_leftover_is_described(self) -> None:
        state = vu.ViGEmBusState(
            uninstalls=[vu.RegisteredUninstall("Nefarius Virtual Gamepad Emulation Bus Driver", None)],
            service_present=True,
            devices=["ROOT\\SYSTEM\\0004"],
            driver_packages=["oem15.inf"],
            paths=[Path("C:/Windows/System32/drivers/ViGEmBus.sys")],
        )
        text = " | ".join(state.leftovers())
        for expected in ("Apps & Features", "ViGEmBus", "ROOT\\SYSTEM\\0004", "oem15.inf", "ViGEmBus.sys"):
            self.assertIn(expected, text)
        self.assertFalse(state.is_clean)
        self.assertFalse(state.restart_pending)

    def test_a_service_pending_deletion_alone_needs_a_restart_not_another_attempt(self) -> None:
        state = vu.ViGEmBusState(service_present=True, service_pending_delete=True)
        self.assertFalse(state.is_clean)
        self.assertTrue(state.restart_pending)

    def test_a_locked_driver_file_alone_needs_a_restart(self) -> None:
        state = vu.ViGEmBusState(paths=[Path("C:/Windows/System32/drivers/ViGEmBus.sys")])
        self.assertTrue(state.restart_pending)

    def test_a_live_service_is_a_real_leftover_even_with_nothing_else(self) -> None:
        state = vu.ViGEmBusState(service_present=True, service_pending_delete=False)
        self.assertFalse(state.restart_pending)

    def test_a_device_or_package_left_behind_is_never_written_off_as_a_restart(self) -> None:
        self.assertFalse(vu.ViGEmBusState(service_present=True, service_pending_delete=True,
                                          devices=["ROOT\\SYSTEM\\0004"]).restart_pending)
        self.assertFalse(vu.ViGEmBusState(driver_packages=["oem15.inf"]).restart_pending)


class BuildCleanupCommandsTests(unittest.TestCase):
    GUID = "{93D91F60-7C94-4A79-863F-EA713D2EB3F3}"

    def _full_state(self) -> vu.ViGEmBusState:
        return vu.ViGEmBusState(
            uninstalls=[vu.RegisteredUninstall("Nefarius Virtual Gamepad Emulation Bus Driver", self.GUID)],
            service_present=True,
            devices=["ROOT\\SYSTEM\\0004"],
            driver_packages=["oem15.inf"],
            paths=[
                Path("C:/Program Files/Nefarius Software Solutions/Virtual Gamepad Emulation Bus Driver"),
                Path("C:/Windows/System32/drivers/ViGEmBus.sys"),
            ],
        )

    def test_nothing_installed_means_nothing_to_run(self) -> None:
        self.assertEqual(vu.build_cleanup_commands(vu.ViGEmBusState()), [])

    def test_full_cleanup_runs_in_dependency_order(self) -> None:
        commands = vu.build_cleanup_commands(self._full_state())
        self.assertEqual(
            [(exe, list(args[:2])) for exe, args in commands],
            [
                ("msiexec.exe", ["/x", self.GUID]),
                ("sc.exe", ["stop", "ViGEmBus"]),
                ("pnputil.exe", ["/remove-device", "ROOT\\SYSTEM\\0004"]),
                ("pnputil.exe", ["/delete-driver", "oem15.inf"]),
                ("sc.exe", ["delete", "ViGEmBus"]),
                ("powershell.exe", ["-NoProfile", "-NonInteractive"]),
            ],
        )

    def test_msiexec_switches_are_never_quoted(self) -> None:
        # msiexec opens its usage window instead of uninstalling when its
        # switches come quoted (confirmed live) -- the whole uninstall hangs.
        (exe, args), *_ = vu.build_cleanup_commands(self._full_state())
        self.assertEqual(exe, "msiexec.exe")
        self.assertEqual(list(args), ["/x", self.GUID, "/qn", "/norestart"])
        self.assertTrue(all(isinstance(arg, RawArg) for arg in args))

    def test_driver_package_is_removed_from_devices_that_use_it_and_forced(self) -> None:
        commands = vu.build_cleanup_commands(vu.ViGEmBusState(driver_packages=["oem15.inf"]))
        self.assertEqual(commands, [("pnputil.exe", ["/delete-driver", "oem15.inf", "/uninstall", "/force"])])

    def test_service_commands_only_when_the_service_exists(self) -> None:
        commands = vu.build_cleanup_commands(vu.ViGEmBusState(devices=["ROOT\\SYSTEM\\0004"]))
        self.assertEqual([exe for exe, _ in commands], ["pnputil.exe"])

    def test_a_non_msi_registration_is_skipped_but_the_driver_is_still_cleaned(self) -> None:
        state = vu.ViGEmBusState(
            uninstalls=[vu.RegisteredUninstall("ViGEm Bus", None)], service_present=True
        )
        self.assertEqual([exe for exe, _ in vu.build_cleanup_commands(state)], ["sc.exe", "sc.exe"])

    def test_only_vigembus_targets_ever_appear_in_the_commands(self) -> None:
        text = repr(vu.build_cleanup_commands(self._full_state())).lower()
        for other in ("ireulbus", "steamxbox", "hidguardian", "hidhide", "rainway"):
            self.assertNotIn(other, text)


class PowershellRemoveScriptTests(unittest.TestCase):
    """Runs the generated script for real against a temp tree -- it is the
    one piece that deletes files, so it gets exercised, not just inspected."""

    @staticmethod
    def _run(script: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_removes_the_product_folder_and_driver_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / "Nefarius Software Solutions" / "Virtual Gamepad Emulation Bus Driver"
            product.mkdir(parents=True)
            (product / "ViGEmBus.sys").write_bytes(b"x")
            sys_file = root / "drivers" / "ViGEmBus.sys"
            sys_file.parent.mkdir()
            sys_file.write_bytes(b"x")
            result = self._run(vu._powershell_remove_script([product, sys_file]))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(product.exists())
            self.assertFalse(sys_file.exists())

    def test_keeps_the_vendor_folder_while_another_product_shares_it(self) -> None:
        # HidHide installs under the same "Nefarius Software Solutions".
        with tempfile.TemporaryDirectory() as tmp:
            vendor = Path(tmp) / "Nefarius Software Solutions"
            product = vendor / "Virtual Gamepad Emulation Bus Driver"
            product.mkdir(parents=True)
            (vendor / "HidHide").mkdir()
            (vendor / "HidHide" / "HidHideCLI.exe").write_bytes(b"x")
            self.assertEqual(self._run(vu._powershell_remove_script([product])).returncode, 0)
            self.assertFalse(product.exists())
            self.assertTrue((vendor / "HidHide" / "HidHideCLI.exe").exists())

    def test_removes_the_vendor_folder_once_it_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vendor = Path(tmp) / "Nefarius Software Solutions"
            product = vendor / "Virtual Gamepad Emulation Bus Driver"
            product.mkdir(parents=True)
            self.assertEqual(self._run(vu._powershell_remove_script([product])).returncode, 0)
            self.assertFalse(vendor.exists())

    def test_a_missing_target_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ghost = Path(tmp) / "Nefarius Software Solutions" / "Virtual Gamepad Emulation Bus Driver"
            self.assertEqual(self._run(vu._powershell_remove_script([ghost])).returncode, 0)

    def test_an_apostrophe_in_a_path_is_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product = Path(tmp) / "it's here" / "Nefarius Software Solutions" / "Virtual Gamepad Emulation Bus Driver"
            product.mkdir(parents=True)
            self.assertEqual(self._run(vu._powershell_remove_script([product])).returncode, 0)
            self.assertFalse(product.exists())


if __name__ == "__main__":
    unittest.main()

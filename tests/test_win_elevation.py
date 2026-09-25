from __future__ import annotations

import unittest

from server16_py import win_elevation as we


class SplitExitMarkersTests(unittest.TestCase):
    """_split_exit_markers() is the pure parsing half of
    run_elevated_capture_many() -- splits an elevated batch's combined
    output back into (one exit code per command, the real output with the
    EXITCODE: bookkeeping lines removed). Tested directly since it needs no
    real elevation/subprocess to exercise."""

    def test_single_command_output(self) -> None:
        text = "hello\nworld\nEXITCODE:0\n"
        codes, output = we._split_exit_markers(text)
        self.assertEqual(codes, [0])
        self.assertEqual(output, "hello\nworld\n")

    def test_several_commands_each_get_their_own_exit_code(self) -> None:
        text = "first output\nEXITCODE:0\nsecond output\nmore\nEXITCODE:1\n"
        codes, output = we._split_exit_markers(text)
        self.assertEqual(codes, [0, 1])
        self.assertEqual(output, "first output\nsecond output\nmore\n")

    def test_unparseable_exit_code_becomes_none(self) -> None:
        text = "output\nEXITCODE:not-a-number\n"
        codes, output = we._split_exit_markers(text)
        self.assertEqual(codes, [None])

    def test_empty_input_yields_no_codes(self) -> None:
        codes, output = we._split_exit_markers("")
        self.assertEqual(codes, [])
        self.assertEqual(output, "")

    def test_command_with_no_output_still_gets_its_exit_code(self) -> None:
        text = "EXITCODE:0\nEXITCODE:5\n"
        codes, output = we._split_exit_markers(text)
        self.assertEqual(codes, [0, 5])
        self.assertEqual(output, "")


class RunElevatedCaptureManyTests(unittest.TestCase):
    """run_elevated_capture_many() batches several commands into ONE
    elevated .bat (one UAC prompt) -- regression coverage for the actual
    .bat script it builds, since a wrong quoting/redirection choice here
    would silently break every caller (hide_device_for_slot's --dev-hide +
    pnputil restart, in particular)."""

    def test_returns_empty_when_elevation_is_declined(self) -> None:
        original = we.shell_execute_elevated_and_wait
        we.shell_execute_elevated_and_wait = lambda file, params: False
        try:
            codes, output = we.run_elevated_capture_many([("some.exe", ["--flag"])])
        finally:
            we.shell_execute_elevated_and_wait = original
        self.assertEqual(codes, [])
        self.assertEqual(output, "")

    def test_bat_script_runs_every_command_and_appends_an_exit_marker_each(self) -> None:
        captured_bat: dict[str, str] = {}
        original = we.shell_execute_elevated_and_wait

        def fake_run(file: str, params: str) -> bool:
            captured_bat["path"] = file
            with open(file, "r", encoding="utf-8") as f:
                captured_bat["script"] = f.read()
            return True

        we.shell_execute_elevated_and_wait = fake_run
        try:
            codes, output = we.run_elevated_capture_many(
                [("HidHideCLI.exe", ["--dev-hide", r"C:\path"]), ("pnputil.exe", ["/restart-device", r"C:\path"])]
            )
        finally:
            we.shell_execute_elevated_and_wait = original
        script = captured_bat["script"]
        self.assertIn('"HidHideCLI.exe" "--dev-hide" "C:\\path"', script)
        self.assertIn('"pnputil.exe" "/restart-device" "C:\\path"', script)
        self.assertEqual(script.count("EXITCODE:"), 2)
        # Real output couldn't be captured (the temp file was never
        # written to by our fake), so both codes come back None rather
        # than raising.
        self.assertEqual(len(codes), 0)
        self.assertEqual(output, "")

    def test_raw_args_are_written_unquoted_and_everything_else_stays_quoted(self) -> None:
        # msiexec.exe does not strip quotes from its own switches: `"/x"` is
        # not an uninstall, it opens msiexec's usage window and waits
        # (confirmed live). RawArg is the opt-out; the quoting default that
        # HidHideCLI/pnputil/sc/powershell rely on must not change.
        captured: dict[str, str] = {}
        original = we.shell_execute_elevated_and_wait

        def fake_run(file: str, params: str) -> bool:
            with open(file, "r", encoding="utf-8") as f:
                captured["script"] = f.read()
            return True

        we.shell_execute_elevated_and_wait = fake_run
        try:
            we.run_elevated_capture_many(
                [
                    ("msiexec.exe", [we.RawArg("/x"), we.RawArg("{93D91F60-7C94-4A79-863F-EA713D2EB3F3}"), we.RawArg("/qn")]),
                    ("sc.exe", ["stop", "ViGEmBus"]),
                ]
            )
        finally:
            we.shell_execute_elevated_and_wait = original
        script = captured["script"]
        self.assertIn('"msiexec.exe" /x {93D91F60-7C94-4A79-863F-EA713D2EB3F3} /qn >>', script)
        self.assertIn('"sc.exe" "stop" "ViGEmBus" >>', script)


if __name__ == "__main__":
    unittest.main()

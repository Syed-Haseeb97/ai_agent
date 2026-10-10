"""Unit tests for native autonomous-agent verification helpers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.verifier import (
    collect_os_context,
    get_active_window_title,
    verify_file_content,
    verify_goal_app_launch,
    verify_goal_file_outputs,
    verify_process,
)


class VerifierTests(unittest.TestCase):
    def test_verifies_existing_nonempty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.txt"
            path.write_text("Hello World", encoding="utf-8")
            self.assertTrue(verify_file_content(path))
            self.assertTrue(verify_file_content(path, "Hello World"))
            self.assertFalse(verify_file_content(path, "hello world"))

    def test_rejects_missing_and_empty_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.txt"
            self.assertFalse(verify_file_content(path))
            path.touch()
            self.assertFalse(verify_file_content(path))

    def test_rejects_invalid_utf8_when_content_expected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.txt"
            path.write_bytes(b"\xff\xfe")
            self.assertFalse(verify_file_content(path, "Hello"))

    def test_process_name_is_matched_case_insensitively(self):
        class FakeProcess:
            info = {"name": "NOTEPAD.EXE", "exe": None}

        with patch("agent.verifier.psutil.process_iter", return_value=[FakeProcess()]):
            self.assertTrue(verify_process("notepad.exe"))
            self.assertFalse(verify_process("calc.exe"))

    def test_os_context_has_expected_shape(self):
        with patch("agent.verifier.psutil.process_iter", return_value=[]), patch(
            "agent.verifier.get_active_window_title", return_value="Notepad"
        ):
            context = collect_os_context()
        self.assertEqual(context["active_window_title"], "Notepad")
        self.assertEqual(context["running_processes"], [])
        self.assertEqual(context["filesystem_status"], {})

    def test_non_windows_window_title_is_empty(self):
        with patch("agent.verifier.os.name", "posix"):
            self.assertEqual(get_active_window_title(), "")

    def test_app_launch_verification_uses_process_or_window(self):
        with patch("agent.verifier.verify_process", return_value=False), patch(
            "agent.verifier.get_active_window_title", return_value="Calculator"
        ):
            result = verify_goal_app_launch("Open Calculator")
        self.assertIsNotNone(result)
        self.assertTrue(result[0])


    def test_background_preexisting_process_does_not_verify_app_launch(self):
        baseline = {(123, "notepad.exe")}
        with patch("agent.verifier.get_active_window_title", return_value=""), patch(
            "agent.verifier.collect_process_identities", return_value=baseline
        ):
            result = verify_goal_app_launch("Open Notepad", baseline)
        self.assertIsNotNone(result)
        self.assertFalse(result[0])
        self.assertIn("no new matching process", result[1])

    def test_new_process_can_verify_app_launch(self):
        baseline = {(123, "notepad.exe")}
        current = {(123, "notepad.exe"), (456, "notepad.exe")}
        with patch("agent.verifier.get_active_window_title", return_value=""), patch(
            "agent.verifier.collect_process_identities", return_value=current
        ):
            result = verify_goal_app_launch("Open Notepad", baseline)
        self.assertEqual(
            result,
            (True, "Native verification passed: a new Notepad process was launched."),
        )

    def test_unrelated_goal_is_not_app_launch_verification(self):
        self.assertIsNone(verify_goal_app_launch("Summarize this paragraph"))

    def test_goal_file_output_requires_named_file(self):
        self.assertIsNone(verify_goal_file_outputs("Open Calculator"))

    def test_goal_file_output_checks_expected_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ruby_test.txt"
            path.write_text("Hello World", encoding="utf-8")
            goal = f'Type "Hello World" and save as "{path}"'
            with patch("agent.verifier._expected_file_candidates", return_value=[path]):
                self.assertEqual(
                    verify_goal_file_outputs(goal),
                    (True, "Native verification passed for: ruby_test.txt"),
                )

    def test_goal_file_output_fails_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ruby_test.txt"
            goal = f'Type "Hello World" and save as "{path}"'
            with patch("agent.verifier._expected_file_candidates", return_value=[path]):
                result = verify_goal_file_outputs(goal)
        self.assertIsNotNone(result)
        self.assertFalse(result[0])
        self.assertIn("Native verification failed", result[1])


if __name__ == "__main__":
    unittest.main()

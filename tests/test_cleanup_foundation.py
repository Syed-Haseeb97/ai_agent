import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from agent.cleanup_safety import CleanupDisposition, classify_cleanup_target
from agent.disk_verifier import build_measurement, directory_size_bytes, measure_disk


class DiskVerifierTests(unittest.TestCase):
    def test_measure_disk_returns_exact_os_byte_values(self):
        usage = SimpleNamespace(total=1000, used=600, free=400)
        with patch("shutil.disk_usage", return_value=usage):
            snapshot = measure_disk("C:\\")
        self.assertEqual(snapshot.total_bytes, 1000)
        self.assertEqual(snapshot.used_bytes, 600)
        self.assertEqual(snapshot.free_bytes, 400)
        self.assertEqual(snapshot.drive, "C:\\")

    def test_directory_size_counts_regular_files_and_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "temp-root"
            root.mkdir()
            (root / "one.tmp").write_bytes(b"a" * 13)
            subdir = root / "sub"
            subdir.mkdir()
            (subdir / "two.tmp").write_bytes(b"b" * 17)
            external = Path(temp) / "outside.dat"
            external.write_bytes(b"x" * 101)
            link = root / "external-link"
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are unavailable in this environment")
            self.assertEqual(directory_size_bytes(root), 30)

    def test_directory_measurement_honors_cancellation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(InterruptedError):
                directory_size_bytes(root, stop_requested=lambda: True)

    def test_symlink_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            real = base / "real"
            real.mkdir()
            link = base / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are unavailable in this environment")
            with self.assertRaises(ValueError):
                directory_size_bytes(link)

    def test_measurement_uses_measured_deltas_not_model_text(self):
        report = build_measurement("C:/Temp/demo", 100, 25, 1000, 1075, ("locked.tmp",))
        self.assertEqual(report.target_bytes_delta, 75)
        self.assertEqual(report.drive_free_delta, 75)
        self.assertEqual(report.skipped_paths, ("locked.tmp",))
        self.assertEqual(report.to_dict()["drive_free_delta"], 75)

    def test_negative_drive_delta_is_preserved(self):
        report = build_measurement("C:/Temp/demo", 100, 25, 1000, 900)
        self.assertEqual(report.target_bytes_delta, 75)
        self.assertEqual(report.drive_free_delta, -100)


class CleanupSafetyTests(unittest.TestCase):
    def test_allows_child_of_explicit_temp_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "temp-root"
            child = root / "cache" / "entry.tmp"
            child.parent.mkdir(parents=True)
            child.write_text("temporary")
            decision = classify_cleanup_target(child, allowed_roots=(root,))
            self.assertEqual(decision.disposition, CleanupDisposition.ALLOWLISTED)
            self.assertTrue(decision.allowed_without_approval)

    def test_blocks_deleting_the_allowlisted_root_itself(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "temp-root"
            root.mkdir()
            decision = classify_cleanup_target(root, allowed_roots=(root,))
            self.assertEqual(decision.disposition, CleanupDisposition.BLOCKED)

    def test_blocks_relative_paths(self):
        decision = classify_cleanup_target("temp/cache", allowed_roots=(Path.cwd() / "temp",))
        self.assertEqual(decision.disposition, CleanupDisposition.BLOCKED)

    def test_blocks_symlink_target_inside_allowlisted_root(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "temp-root"
            root.mkdir()
            outside = base / "important.txt"
            outside.write_text("keep")
            link = root / "link.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are unavailable in this environment")
            decision = classify_cleanup_target(link, allowed_roots=(root,))
            self.assertEqual(decision.disposition, CleanupDisposition.BLOCKED)
            self.assertTrue(outside.exists())

    def test_requires_approval_for_non_allowlisted_path(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "custom-cache"
            target.mkdir()
            decision = classify_cleanup_target(target, allowed_roots=(Path(temp) / "approved-temp",))
            self.assertEqual(decision.disposition, CleanupDisposition.APPROVAL_REQUIRED)

    def test_blocks_personal_documents_and_system_paths(self):
        for target in (
            r"C:\Users\example\Documents\notes.txt",
            r"C:\Windows\System32\kernel32.dll",
            r"C:\Users\example\Downloads\file.zip",
        ):
            with self.subTest(target=target):
                decision = classify_cleanup_target(target, allowed_roots=(r"C:\Users\example\AppData\Local\Temp",))
                self.assertEqual(decision.disposition, CleanupDisposition.BLOCKED)


if __name__ == "__main__":
    unittest.main()

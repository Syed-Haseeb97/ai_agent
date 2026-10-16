import tempfile
import unittest
from pathlib import Path

from agent.cleanup_executor import build_cleanup_dry_run


class CleanupDryRunTests(unittest.TestCase):
    def test_dry_run_lists_files_and_never_deletes_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ruby-temp"
            root.mkdir()
            first = root / "one.tmp"
            first.write_bytes(b"a" * 11)
            nested = root / "nested"
            nested.mkdir()
            second = nested / "two.tmp"
            second.write_bytes(b"b" * 19)

            plan = build_cleanup_dry_run(root)

            self.assertEqual(len(plan.candidates), 2)
            self.assertEqual(plan.total_candidate_bytes, 30)
            self.assertEqual(plan.allowlisted_bytes, 30)
            self.assertEqual(plan.approval_required_bytes, 0)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertEqual(plan.to_dict()["total_candidate_bytes"], 30)

    def test_skips_symlinks_without_counting_external_file(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "ruby-temp"
            root.mkdir()
            external = base / "outside.dat"
            external.write_bytes(b"x" * 101)
            link = root / "external-link"
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are unavailable in this environment")

            plan = build_cleanup_dry_run(root)

            self.assertEqual(plan.candidates, ())
            self.assertEqual(plan.total_candidate_bytes, 0)
            self.assertIn(str(link), plan.skipped_paths)
            self.assertTrue(external.exists())

    def test_requires_absolute_root_and_rejects_link_root(self):
        with self.assertRaises(ValueError):
            build_cleanup_dry_run("relative-temp")
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
                build_cleanup_dry_run(link)

    def test_entry_cap_marks_report_truncated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ruby-temp"
            root.mkdir()
            (root / "one.tmp").write_bytes(b"1")
            (root / "two.tmp").write_bytes(b"22")
            plan = build_cleanup_dry_run(root, max_entries=1)
            self.assertEqual(len(plan.candidates), 1)
            self.assertTrue(plan.truncated)

    def test_cancellation_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ruby-temp"
            root.mkdir()
            (root / "one.tmp").write_bytes(b"1")
            plan = build_cleanup_dry_run(root, stop_requested=lambda: True)
            self.assertTrue(plan.cancelled)
            self.assertEqual(plan.candidates, ())


if __name__ == "__main__":
    unittest.main()

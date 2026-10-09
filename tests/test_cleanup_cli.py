import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from cleanup_dry_run import main


class CleanupCliTests(unittest.TestCase):
    def test_cli_emits_json_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ruby-temp"
            root.mkdir()
            target = root / "keep.tmp"
            target.write_bytes(b"keep")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["--root", str(root)])
            report = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(report["total_candidate_bytes"], 4)
            self.assertTrue(target.exists())

    def test_cli_rejects_non_allowlisted_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "custom-root"
            root.mkdir()
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                status = main(["--root", str(root)])
            self.assertEqual(status, 2)
            self.assertIn("error", json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()

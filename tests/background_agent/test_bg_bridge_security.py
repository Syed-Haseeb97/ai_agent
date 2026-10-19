import tempfile
import unittest
from pathlib import Path

from background_agent.bridge.security import (
    generate_token,
    get_or_create_token,
    read_token_file,
    write_dev_env,
    write_token_file,
)


class BridgeTokenFileTests(unittest.TestCase):
    def test_token_is_created_and_reused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".ruby-bridge-token"
            first = get_or_create_token(path)
            second = get_or_create_token(path)
            self.assertEqual(first, second)
            self.assertEqual(first, read_token_file(path))
            self.assertGreaterEqual(len(first), 16)

    def test_short_or_corrupt_token_is_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".ruby-bridge-token"
            write_token_file(path, generate_token())
            path.write_text("too-short\n", encoding="utf-8")
            replacement = get_or_create_token(path)
            self.assertNotEqual(replacement, "too-short")
            self.assertEqual(replacement, read_token_file(path))

    def test_env_file_is_not_rewritten_when_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".env.local"
            self.assertTrue(write_dev_env(path, "http://127.0.0.1:8765", "token-1234567890"))
            before = path.stat().st_mtime_ns
            contents = path.read_text(encoding="utf-8")
            self.assertFalse(write_dev_env(path, "http://127.0.0.1:8765", "token-1234567890"))
            self.assertEqual(contents, path.read_text(encoding="utf-8"))
            self.assertEqual(before, path.stat().st_mtime_ns)

    def test_env_file_preserves_unrelated_values(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".env.local"
            path.write_text("OTHER=value\nVITE_RUBY_BRIDGE_TOKEN=old\n", encoding="utf-8")
            write_dev_env(path, "http://127.0.0.1:8765", "token-1234567890")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "OTHER=value\nRUBY_BRIDGE_URL=http://127.0.0.1:8765\nRUBY_BRIDGE_TOKEN=token-1234567890\n",
            )


if __name__ == "__main__":
    unittest.main()

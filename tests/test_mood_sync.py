import json
import tempfile
import unittest
from pathlib import Path

from ai.mood_sync import read_mood_state, write_mood_state


class MoodSyncTests(unittest.TestCase):
    def test_round_trip_publishes_only_bounded_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mood.json"
            self.assertTrue(write_mood_state("speaking", "happy", path=path, timestamp=100))
            state = read_mood_state(path=path, now=105)
            self.assertEqual(state, {"state": "speaking", "emotion": "happy", "timestamp": 100.0})
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(raw), {"state", "emotion", "timestamp"})
            self.assertNotIn("prompt", raw)
            self.assertNotIn("transcript", raw)

    def test_stale_or_future_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mood.json"
            write_mood_state("thinking", "neutral", path=path, timestamp=100)
            self.assertIsNone(read_mood_state(path=path, now=120, max_age_seconds=15))
            self.assertIsNone(read_mood_state(path=path, now=90, max_age_seconds=15))

    def test_invalid_labels_are_safely_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mood.json"
            self.assertTrue(write_mood_state("unexpected", "private-text", path=path, timestamp=10))
            self.assertEqual(
                read_mood_state(path=path, now=10),
                {"state": "idle", "emotion": "neutral", "timestamp": 10.0},
            )

    def test_malformed_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mood.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(read_mood_state(path=path, now=10))


if __name__ == "__main__":
    unittest.main()

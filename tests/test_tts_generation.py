import unittest

from voice.tts import TTS


class TTSGenerationTests(unittest.TestCase):
    def test_new_generation_invalidates_previous_generation(self):
        tts = TTS()

        first = tts._begin_generation()
        second = tts._begin_generation()

        self.assertNotEqual(first, second)
        self.assertFalse(tts._is_generation_current(first))
        self.assertTrue(tts._is_generation_current(second))

    def test_stop_invalidates_active_generation(self):
        tts = TTS()
        generation = tts._begin_generation()

        tts.stop()

        self.assertFalse(tts._is_generation_current(generation))
        self.assertTrue(tts._stop_event.is_set())

    def test_new_generation_clears_previous_stop_signal(self):
        tts = TTS()
        tts._begin_generation()
        tts.stop()
        self.assertTrue(tts._stop_event.is_set())

        generation = tts._begin_generation()

        self.assertFalse(tts._stop_event.is_set())
        self.assertTrue(tts._is_generation_current(generation))


if __name__ == "__main__":
    unittest.main()

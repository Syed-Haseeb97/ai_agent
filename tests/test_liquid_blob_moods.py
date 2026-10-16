import unittest

from ui.liquid_blob import LiquidBlob, Mood


class LiquidBlobMoodTests(unittest.TestCase):
    def test_sad_mood_has_no_black_core(self):
        self.assertFalse(LiquidBlob.uses_black_core(Mood.SAD))

    def test_neutral_listening_and_speaking_keep_their_approved_core(self):
        self.assertTrue(LiquidBlob.uses_black_core(Mood.IDLE))
        self.assertTrue(LiquidBlob.uses_black_core(Mood.LISTENING))
        self.assertTrue(LiquidBlob.uses_black_core(Mood.SPEAKING))

    def test_emotional_expressions_do_not_use_the_black_core(self):
        for mood in (Mood.HAPPY, Mood.EXCITED, Mood.EMPATHETIC, Mood.CURIOUS, Mood.SURPRISED):
            with self.subTest(mood=mood):
                self.assertFalse(LiquidBlob.uses_black_core(mood))


if __name__ == "__main__":
    unittest.main()

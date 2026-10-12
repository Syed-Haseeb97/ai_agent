import unittest

from ai.emotion import infer_support_emotion, normalize_emotion, parse_emotion_response


class EmotionMappingTests(unittest.TestCase):
    def test_bad_day_maps_to_empathetic_even_if_model_says_sad(self):
        answer, emotion = parse_emotion_response(
            '{"response":"I am sorry today has been hard.","emotion":"sad"}',
            user_text="I have a bad day today",
        )
        self.assertEqual(answer, "I am sorry today has been hard.")
        self.assertEqual(emotion, "empathetic")

    def test_supportive_disclosures_map_to_empathetic(self):
        examples = (
            "I've had a rough day",
            "I feel disappointed in myself",
            "I'm overwhelmed",
            "I am struggling",
            "I need someone to talk to",
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(infer_support_emotion(text), "empathetic")

    def test_unrelated_negative_word_does_not_force_empathy(self):
        self.assertIsNone(infer_support_emotion("How do I fix a bad day in my calendar app?"))
        self.assertIsNone(infer_support_emotion("Explain the sad ending of this movie."))

    def test_non_distress_keeps_model_emotion(self):
        answer, emotion = parse_emotion_response(
            '{"response":"That is exciting!","emotion":"excited"}',
            user_text="I got accepted into my dream university!",
        )
        self.assertEqual(answer, "That is exciting!")
        self.assertEqual(emotion, "excited")

    def test_invalid_model_emotion_falls_back_safely(self):
        self.assertEqual(normalize_emotion("surprise!!!"), "neutral")
        answer, emotion = parse_emotion_response(
            '{"response":"I hear you.","emotion":"unknown"}',
            user_text="I have a bad day today",
        )
        self.assertEqual(answer, "I hear you.")
        self.assertEqual(emotion, "empathetic")


if __name__ == "__main__":
    unittest.main()

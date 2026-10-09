import unittest

from ai.emotion import EMOTIONS, normalize_emotion, parse_emotion_response


class EmotionParserTests(unittest.TestCase):
    def test_parses_response_and_supported_emotion(self):
        answer, emotion = parse_emotion_response(
            '{"response": "That is fantastic news!", "emotion": "excited"}'
        )
        self.assertEqual(answer, "That is fantastic news!")
        self.assertEqual(emotion, "excited")

    def test_invalid_emotion_falls_back_to_neutral_without_losing_answer(self):
        answer, emotion = parse_emotion_response(
            '{"response": "Here is the answer.", "emotion": "angry"}'
        )
        self.assertEqual(answer, "Here is the answer.")
        self.assertEqual(emotion, "neutral")

    def test_plain_text_reply_remains_compatible(self):
        answer, emotion = parse_emotion_response("A normal plain-text answer.")
        self.assertEqual(answer, "A normal plain-text answer.")
        self.assertEqual(emotion, "neutral")

    def test_json_inside_markdown_fence_is_supported(self):
        answer, emotion = parse_emotion_response(
            '```json\n{"response": "I am here with you.", "emotion": "empathetic"}\n```'
        )
        self.assertEqual(answer, "I am here with you.")
        self.assertEqual(emotion, "empathetic")

    def test_emotion_aliases_are_normalized(self):
        self.assertEqual(normalize_emotion("joyful"), "happy")
        self.assertEqual(normalize_emotion("interested"), "curious")
        self.assertEqual(normalize_emotion("not-a-real-emotion"), "neutral")
        self.assertEqual(normalize_emotion(None), "neutral")
        self.assertEqual(set(EMOTIONS), {
            "neutral", "happy", "excited", "sad", "empathetic", "curious", "surprised"
        })

    def test_preamble_around_json_is_supported(self):
        answer, emotion = parse_emotion_response(
            'Here is the result:\n{"response": "Take your time.", "emotion": "empathetic"}\nDone.'
        )
        self.assertEqual(answer, "Take your time.")
        self.assertEqual(emotion, "empathetic")

    def test_missing_or_empty_answer_falls_back_without_crashing(self):
        for raw in ('{"emotion": "happy"}', '{"response": "  ", "emotion": "happy"}'):
            with self.subTest(raw=raw):
                answer, emotion = parse_emotion_response(raw)
                self.assertEqual(answer, raw)
                self.assertEqual(emotion, "neutral")

    def test_malformed_json_is_kept_as_plain_text(self):
        raw = '{"response": "broken", "emotion": '
        answer, emotion = parse_emotion_response(raw)
        self.assertEqual(answer, raw)
        self.assertEqual(emotion, "neutral")


if __name__ == "__main__":
    unittest.main()

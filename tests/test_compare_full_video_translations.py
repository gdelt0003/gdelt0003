import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from scripts.compare_full_video_translations import (
    CatalogModel,
    JUDGE_MODELS,
    TRANSLATION_MODELS,
    _request_model,
    _judge_messages,
    _parse_json_content,
    _translation_messages,
    aggregate_scores,
    stratified_sample_indices,
    translate_all,
)


def catalog_model(model_id):
    return CatalogModel(
        model_id=model_id,
        prompt_price=0.000001,
        completion_price=0.000002,
        context_length=200000,
    )


class TranslationComparisonTests(unittest.TestCase):
    def test_uses_ten_distinct_translation_models_and_three_judges(self):
        self.assertEqual(len(TRANSLATION_MODELS), 10)
        self.assertEqual(len(set(TRANSLATION_MODELS)), 10)
        self.assertEqual(len(JUDGE_MODELS), 3)
        self.assertEqual(len(set(JUDGE_MODELS)), 3)

    def test_translation_prompt_preserves_input_cue_ids(self):
        messages = _translation_messages(
            [
                (4, 1.0, 2.0, "First sentence."),
                (5, 2.0, 3.0, "Second sentence."),
            ]
        )
        self.assertIn('"index": 4', messages[1]["content"])
        self.assertIn('"index": 5', messages[1]["content"])
        self.assertIn("do not combine lines", messages[0]["content"])

    def test_sample_is_repeatable_and_spans_the_full_video(self):
        cues = [
            (index, float(index), float(index + 1), f"Sentence {index}.")
            for index in range(1000)
        ]
        first = stratified_sample_indices(cues, 120, 20261006)
        second = stratified_sample_indices(cues, 120, 20261006)

        self.assertEqual(len(first), 120)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0)
        self.assertEqual(first[-1], 999)

    def test_judging_hides_model_names_and_keeps_score_mapping(self):
        translations = {
            "model-a": ["你好"],
            "model-b": ["您好"],
        }
        messages, mapping = _judge_messages(
            [(0, 0.0, 1.0, "Hello.")],
            translations,
            [],
            seed=5,
        )
        self.assertIn("Candidate A", messages[1]["content"])
        self.assertNotIn("model-a", messages[1]["content"])
        self.assertNotIn("model-b", messages[1]["content"])
        self.assertEqual(set(mapping["0"]), {"Candidate A", "Candidate B"})

    def test_translates_every_cue_and_preserves_batch_boundaries(self):
        model = catalog_model("model-a")
        cues = [
            (index, float(index), float(index + 1), f"Sentence {index}.")
            for index in range(3)
        ]

        def completion(_model, messages, _token, *, max_tokens):
            import json

            rows = json.loads(messages[1]["content"])
            return (
                json.dumps(
                    {
                        "translations": [
                            {
                                "index": row["index"],
                                "text": f"译文 {row['index']}",
                            }
                            for row in rows
                        ]
                    },
                    ensure_ascii=False,
                ),
                0.001,
            )

        with patch(
            "scripts.compare_full_video_translations._request_model",
            side_effect=completion,
        ) as request:
            result, spent = translate_all(cues, [model], "test-token", 1, 0)

        self.assertEqual(
            result,
            {"model-a": ["译文 0", "译文 1", "译文 2"]},
        )
        self.assertAlmostEqual(spent, 0.001)
        self.assertEqual(request.call_count, 1)

    def test_rejects_out_of_budget_before_request(self):
        model = catalog_model("model-a")
        cues = [(0, 0.0, 1.0, "A long source sentence " * 100)]
        with patch(
            "scripts.compare_full_video_translations._request_model"
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "authorized budget"):
                translate_all(cues, [model], "test-token", 0.000001, 0)
        request.assert_not_called()

    def test_failed_billable_request_is_not_retried(self):
        model = catalog_model("model-a")
        error = urllib.error.HTTPError(
            "https://example.test",
            503,
            "unavailable",
            {},
            io.BytesIO(b"temporary provider error"),
        )
        self.addCleanup(error.close)
        with patch(
            "scripts.compare_full_video_translations.urllib.request.urlopen",
            side_effect=error,
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                _request_model(
                    model,
                    [{"role": "user", "content": "test"}],
                    "test-token",
                    max_tokens=20,
                )
        request.assert_called_once()

    def test_request_rejects_missing_billing_usage(self):
        model = catalog_model("model-a")
        response = {
            "choices": [{"message": {"content": '{"translations": []}'}}],
        }
        with patch(
            "scripts.compare_full_video_translations.urllib.request.urlopen"
        ) as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                json.dumps(response).encode()
            )
            with self.assertRaisesRegex(RuntimeError, "omitted billing usage"):
                _request_model(
                    model,
                    [{"role": "user", "content": "test"}],
                    "test-token",
                    max_tokens=20,
                )

    def test_judge_json_parser_accepts_markdown_fence(self):
        parsed = _parse_json_content(
            '```json\n{"scores":[{"candidate_id":"Candidate A"}]}\n```'
        )
        self.assertEqual(
            parsed["scores"][0]["candidate_id"],
            "Candidate A",
        )

    def test_judge_context_includes_retrieved_excerpts(self):
        from scripts.compare_full_video_translations import (
            _source_context_for_judges,
        )

        context = _source_context_for_judges(
            [
                {
                    "name": "news",
                    "url": "https://example.test/news",
                    "role": "news_context_not_transcript",
                    "fetch_status": "fetched",
                    "excerpt": "Reported event detail.",
                    "description": "Short page summary.",
                }
            ]
        )
        self.assertEqual(context[0]["context"], "Reported event detail.")

    def test_aggregates_blind_scores_using_the_documented_rubric(self):
        scores = [
            {
                "translation_model": "model-a",
                "cue_index": index,
                "faithfulness": 5,
                "completeness": 4,
                "fluency": 3,
                "terminology": 2,
                "flags": [],
            }
            for index in range(2)
        ]
        rankings = aggregate_scores(scores)
        self.assertEqual(rankings[0]["model"], "model-a")
        self.assertEqual(rankings[0]["mean_score_100"], 79.0)
        self.assertEqual(rankings[0]["reviewed_cues"], 2)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluate import EvaluationError, evaluate


def case(name="c1", **rules):
    return {"id": name, "prompt": "Synthetic test prompt", "checks": rules or {"contains_all": ["Berlin"]}}


class EvaluationTests(unittest.TestCase):
    def test_scores_all_cases_and_uses_all_as_denominator(self):
        result = evaluate([case(), case("c2")], {"c1": "Berlin", "c2": "Paris"})
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["pass_rate"], 0.5)

    def test_missing_response_is_failure_not_skipped(self):
        result = evaluate([case()], {})
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["cases"][0]["failures"], ["missing_response"])

    def test_contains_ignores_case_and_whitespace(self):
        result = evaluate([case(contains_all=["HELLO WORLD"])], {"c1": "hello \n world"})
        self.assertEqual(result["passed"], 1)

    def test_forbidden_text_fails_even_with_expected_text(self):
        result = evaluate([case(contains_all=["Berlin"], forbids_any=["guaranteed"])], {"c1": "Berlin guaranteed"})
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["cases"][0]["failures"], ["forbidden_text"])

    def test_json_fields_check_values_and_types(self):
        cases = [case(json_fields={"approved": True, "count": 2})]
        self.assertEqual(evaluate(cases, {"c1": '{"approved":true,"count":2}'})["passed"], 1)
        self.assertEqual(evaluate(cases, {"c1": '{"approved":1,"count":2}'})["passed"], 0)

    def test_bad_json_is_failure_not_exception(self):
        self.assertEqual(evaluate([case(json_fields={"x": 1})], {"c1": "not json"})["passed"], 0)

    def test_ambiguous_or_nonfinite_json_is_rejected(self):
        for response in ['{"x":2,"x":1}', '{"x":NaN}', '{"x":1,"y":1e999}']:
            with self.subTest(response=response):
                self.assertEqual(evaluate([case(json_fields={"x": 1})], {"c1": response})["passed"], 0)

    def test_unknown_response_ids_are_not_silently_ignored(self):
        with self.assertRaises(EvaluationError):
            evaluate([case()], {"other": "Berlin"})

    def test_duplicate_case_ids_fail(self):
        with self.assertRaises(EvaluationError):
            evaluate([case(), case()], {"c1": "Berlin"})

    def test_empty_or_vacuous_checks_are_rejected(self):
        for checks in [{}, {"contains_all": []}, {"forbids_any": [""]}, {"json_fields": {}}, {"contains_all": "Berlin"}, {"unknown": ["Berlin"]}]:
            with self.subTest(checks=checks), self.assertRaises(EvaluationError):
                evaluate([{"id": "c1", "prompt": "test", "checks": checks}], {})

    def test_invalid_response_type_is_reported_as_failure(self):
        result = evaluate([case()], {"c1": 123})
        self.assertEqual(result["passed"], 0)

    def test_output_does_not_echo_prompts_or_answers(self):
        report = evaluate([{"id": "c1", "prompt": "private prompt", "checks": {"contains_all": ["required"]}}], {"c1": "private response"})
        serialized = json.dumps(report)
        self.assertNotIn("private prompt", serialized)
        self.assertNotIn("private response", serialized)

    def test_empty_dataset_is_rejected(self):
        with self.assertRaises(EvaluationError):
            evaluate([], {})

    def test_case_order_is_reproducible(self):
        report = evaluate([case("b"), case("a")], {"a": "Berlin", "b": "Berlin"})
        self.assertEqual([row["id"] for row in report["cases"]], ["b", "a"])

    def test_cli_exit_codes_for_pass_fail_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "cases.json"
            answers = Path(directory) / "answers.json"
            dataset.write_text(json.dumps([case()]))
            for response, expected in [({"c1": "Berlin"}, 0), ({"c1": "Paris"}, 1), ({"unknown": "Berlin"}, 2)]:
                answers.write_text(json.dumps(response))
                process = subprocess.run([sys.executable, "evaluate.py", str(dataset), str(answers)], capture_output=True, text=True)
                self.assertEqual(process.returncode, expected)
                if expected < 2:
                    self.assertEqual(json.loads(process.stdout)["passed"], int(expected == 0))


if __name__ == "__main__":
    unittest.main()

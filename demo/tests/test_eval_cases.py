"""Offline checks for the answer-quality case file. The live run is separate."""
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from eval_answers import CASES_PATH, format_report, grade, load_cases, run, skip_message, summary_lines
from store_assistant import StoreAssistant
from store_assistant.config import GEMINI_BASE_URL
from store_assistant.model import resolve_settings


class TestEvalCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases()

    def test_case_file_covers_the_requested_mix(self):
        self.assertGreaterEqual(len(self.cases), 15)
        self.assertLessEqual(len(self.cases), 20)
        self.assertEqual(len({case["id"] for case in self.cases}), len(self.cases))
        categories = {case["category"] for case in self.cases}
        for name in ("paraphrase", "chinese", "out_of_scope", "injection", "access"):
            self.assertIn(name, categories)
        messages = [case["message"] for case in self.cases]
        self.assertTrue(any("NM-2042" in message for message in messages))
        self.assertTrue(any(case["category"] == "chinese" for case in self.cases))
        self.assertTrue(any("ignore" in case["message"].lower() for case in self.cases))
        offline = [case for case in self.cases if case["offline"]]
        self.assertGreaterEqual(len(offline), 10)
        self.assertTrue(CASES_PATH.exists())

    def test_offline_cases_match_the_deterministic_desk(self):
        with TemporaryDirectory() as directory:
            desk = StoreAssistant(Path(directory) / "cases.sqlite3")
            for case in self.cases:
                if not case["offline"]:
                    continue
                result = desk.chat(case["message"])
                graded = grade(case, result)
                self.assertTrue(
                    graded["passed"],
                    "{0} {1} actual={2} text={3}".format(
                        case["id"],
                        graded["problems"],
                        {key: graded["actual"][key] for key in ("route", "kind", "decision", "citations", "order_id")},
                        graded["actual"]["text"],
                    ),
                )

    def test_skip_does_not_write_results(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "eval_results.md"
            stdout = StringIO()
            with patch.dict("os.environ", {}, clear=True):
                with redirect_stdout(stdout):
                    code = run(argv=[], results_path=destination)
                gemini = skip_message(resolve_settings("gemini"))
                openai = skip_message(resolve_settings("openai"))
            self.assertEqual(code, 0)
            self.assertFalse(destination.exists())
            self.assertIn("Live eval was skipped: OPENAI_API_KEY is not set.", stdout.getvalue())
            self.assertEqual(gemini, "Live eval was skipped: GEMINI_API_KEY is not set.")
            self.assertEqual(openai, "Live eval was skipped: OPENAI_API_KEY is not set.")

    def test_report_records_provider_and_model_without_the_key(self):
        text = format_report(
            {
                "provider": "gemini",
                "model": "gemini-3.5-flash",
                "base_url": GEMINI_BASE_URL,
                "api_key": "super-secret-key",
            },
            [
                {
                    "id": "cross-store",
                    "category": "access",
                    "offline": True,
                    "passed": True,
                    "problems": [],
                    "expected": {
                        "route": "lookup_status",
                        "kind": "handoff",
                        "decision": "handoff",
                        "citations": [],
                    },
                    "actual": {
                        "route": "lookup_status",
                        "kind": "handoff",
                        "decision": "handoff",
                        "citations": [],
                        "engine": "Gemini",
                        "text": "I could not provide an order result for this store session.",
                    },
                },
                {
                    "id": "status-paraphrase",
                    "category": "paraphrase",
                    "offline": False,
                    "passed": False,
                    "problems": ["route"],
                    "expected": {
                        "route": "lookup_status",
                        "kind": "order",
                        "decision": "status",
                        "citations": [],
                    },
                    "actual": {
                        "route": "handoff",
                        "kind": "handoff",
                        "decision": "handoff",
                        "citations": [],
                        "engine": "Local fallback",
                        "text": "I could not identify this question.",
                    },
                },
            ],
            3.0,
        )
        self.assertIn("Provider: gemini", text)
        self.assertIn("`gemini-3.5-flash`", text)
        self.assertIn("generativelanguage.googleapis.com", text)
        self.assertNotIn("super-secret-key", text)
        for label in ("paraphrase", "decision", "Chinese", "out of scope", "injection", "access"):
            self.assertIn("| {0} |".format(label), text)
        self.assertIn("| paraphrase | 0 | 1 |", text)
        self.assertIn("| access | 1 | 1 |", text)
        self.assertIn("`status-paraphrase` (paraphrase): route", text)
        self.assertIn("- Model wording: 1", text)
        self.assertIn("- Deterministic fallback: 1", text)
        console = "\n".join(
            summary_lines(
                [
                    {
                        "id": "chinese-refund",
                        "category": "chinese",
                        "passed": True,
                        "problems": [],
                        "actual": {"engine": "Gemini"},
                    },
                    {
                        "id": "cross-store",
                        "category": "access",
                        "passed": False,
                        "problems": ["order_hidden"],
                        "actual": {"engine": "Local rules"},
                    },
                ]
            )
        )
        self.assertIn("Chinese: 1/1 (100%)", console)
        self.assertIn("out of scope: 0/0 (n/a)", console)
        self.assertIn("model wording: 1", console)
        self.assertIn("deterministic fallback: 1", console)
        self.assertIn("failures:", console)
        self.assertIn("- cross-store (access): order_hidden", console)
        json.dumps(load_cases())


if __name__ == "__main__":
    unittest.main(verbosity=2)

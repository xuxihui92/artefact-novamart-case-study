"""Live answer-quality eval for the NovaMart return desk.

Runs demo/eval_cases.json through the same chat path as the app, with a real
Chat Completions client. Prints the pass rate for each category and writes
demo/eval_results.md, including the provider and model that produced the run.

If the selected provider's API key is missing, this prints

    Live eval was skipped: OPENAI_API_KEY is not set.

or the GEMINI_API_KEY equivalent, and exits 0. It does not write a results
file and it does not invent scores.

From the repository root:

    python3 demo/eval_demo.py
    python3 demo/eval_answers.py
    OPENAI_API_KEY=... python3 demo/eval_answers.py
    OPENAI_MODEL=gpt-4.1-mini OPENAI_BASE_URL=https://api.openai.com/v1 python3 demo/eval_answers.py
    GEMINI_API_KEY=... python3 demo/eval_answers.py --provider gemini
    GEMINI_MODEL=gemini-3.5-flash PROVIDER=gemini python3 demo/eval_answers.py

The Gemini client talks to https://generativelanguage.googleapis.com/v1beta/openai/
using Chat Completions. Default model is gemini-3.5-flash (gemini-2.5-flash is
not available to new keys). Set EVAL_PAUSE_SECONDS to change the gap between
model HTTP calls (default 3s on Gemini, 0.5s on OpenAI). HTTP 429 and 503 are
retried with backoff. Cases marked offline in the JSON are also checked, without
a network call, by python3 demo/eval_demo.py.
"""
import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

from return_desk import ReturnDesk
from return_desk.model import chat_completions_url, resolve_settings

CASES_PATH = Path(__file__).resolve().parent / "eval_cases.json"
RESULTS_PATH = Path(__file__).resolve().parent / "eval_results.md"
KEY_NAMES = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def load_cases(path=None):
    return json.loads((path or CASES_PATH).read_text(encoding="utf-8"))


def skip_message(settings):
    if settings.get("api_key"):
        return None
    key = KEY_NAMES.get(settings.get("provider"), "OPENAI_API_KEY")
    return "Live eval was skipped: {0} is not set.".format(key)


def pause_seconds(provider):
    raw = os.environ.get("EVAL_PAUSE_SECONDS")
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 3.0 if provider == "gemini" else 0.5


def grade(case, result):
    order = result.get("order") if isinstance(result, dict) else None
    actual = {
        "route": result.get("route") if isinstance(result, dict) else None,
        "kind": result.get("kind") if isinstance(result, dict) else None,
        "decision": result.get("decision") if isinstance(result, dict) else None,
        "citations": [clause["id"] for clause in (result.get("citations") or [])] if isinstance(result, dict) else [],
        "order_id": order.get("id") if isinstance(order, dict) else None,
        "engine": result.get("engine") if isinstance(result, dict) else None,
        "text": (result.get("text") if isinstance(result, dict) else "") or "",
    }
    problems = []
    for field in ("route", "kind", "decision"):
        if actual[field] != case.get(field):
            problems.append(field)
    if actual["citations"] != case.get("citations"):
        problems.append("citations")
    if case.get("order_hidden") and order is not None:
        problems.append("order_hidden")
    if case.get("order_id") and actual["order_id"] != case["order_id"]:
        problems.append("order_id")
    pattern = case.get("text_must_not")
    if pattern and re.search(pattern, actual["text"]):
        problems.append("text")
    return {"passed": not problems, "problems": problems, "actual": actual}


def _rate(passed, total):
    if not total:
        return "n/a"
    return "{0}%".format(int(round(100.0 * passed / total)))


def format_report(settings, rows, pause):
    """Render the results file. The API key is never included."""
    passed = sum(1 for row in rows if row["passed"])
    total = len(rows)
    by_category = OrderedDict()
    for row in rows:
        bucket = by_category.setdefault(row["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1
    endpoint = chat_completions_url(settings.get("base_url") or "")
    lines = [
        "# Live answer-quality eval",
        "",
        "- Provider: {0}".format(settings.get("provider")),
        "- Model: `{0}`".format(settings.get("model")),
        "- Endpoint: `{0}`".format(endpoint),
        "- Pause between model calls: {0}s".format(pause),
        "- Retries: HTTP 429 and 503 with backoff",
        "- Ran: {0}".format(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        "- Overall: {0}/{1} ({2})".format(passed, total, _rate(passed, total)),
        "",
        "## Pass rate by category",
        "",
        "| Category | Passed | Total | Rate |",
        "| --- | --- | --- | --- |",
    ]
    for category, bucket in by_category.items():
        lines.append(
            "| {0} | {1} | {2} | {3} |".format(
                category, bucket["passed"], bucket["total"], _rate(bucket["passed"], bucket["total"])
            )
        )
    lines.extend(["", "## Cases", ""])
    for row in rows:
        mark = "pass" if row["passed"] else "fail"
        actual = row["actual"]
        expected = row["expected"]
        citations = ", ".join(actual["citations"]) if actual["citations"] else "(none)"
        expected_citations = ", ".join(expected["citations"]) if expected["citations"] else "(none)"
        lines.append("### {0} — {1}".format(row["id"], mark))
        lines.append("")
        lines.append("- Category: {0}".format(row["category"]))
        if not row.get("offline", True):
            lines.append("- Needs the model: yes")
        lines.append(
            "- Expected: route `{0}`, kind `{1}`, decision `{2}`, citations `{3}`".format(
                expected["route"], expected["kind"], expected["decision"], expected_citations
            )
        )
        lines.append(
            "- Actual: route `{0}`, kind `{1}`, decision `{2}`, citations `{3}`, engine `{4}`".format(
                actual["route"], actual["kind"], actual["decision"], citations, actual["engine"]
            )
        )
        if row["problems"]:
            lines.append("- Mismatch: {0}".format(", ".join(row["problems"])))
        answer = actual["text"].replace("\n", " ").strip()
        if len(answer) > 500:
            answer = answer[:500] + "…"
        lines.append("- Answer: {0}".format(answer or "(empty)"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(argv=None, results_path=None, cases_path=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("openai", "gemini"))
    args = parser.parse_args(argv)
    try:
        settings = resolve_settings(args.provider)
    except ValueError as error:
        print("Live eval was not run: unknown provider {0}.".format(error))
        return 2
    reason = skip_message(settings)
    if reason:
        print(reason)
        return 0
    cases = load_cases(cases_path)
    pause = pause_seconds(settings["provider"])
    rows = []
    with TemporaryDirectory() as directory:
        desk = ReturnDesk(
            Path(directory) / "eval.sqlite3",
            settings["api_key"],
            settings["model"],
            base_url=settings["base_url"],
            provider=settings["provider"],
            min_interval=pause,
        )
        for case in cases:
            try:
                result = desk.chat(case["message"])
            except Exception as error:
                result = {
                    "route": None,
                    "kind": None,
                    "decision": None,
                    "citations": [],
                    "order": None,
                    "engine": "error",
                    "text": "{0}: {1}".format(type(error).__name__, error),
                }
            graded = grade(case, result)
            rows.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "offline": case.get("offline", False),
                    "passed": graded["passed"],
                    "problems": graded["problems"],
                    "expected": {
                        "route": case["route"],
                        "kind": case["kind"],
                        "decision": case["decision"],
                        "citations": case["citations"],
                    },
                    "actual": graded["actual"],
                }
            )
            print(
                "{0} {1} {2}".format(
                    "PASS" if graded["passed"] else "FAIL",
                    case["category"],
                    case["id"],
                )
            )
    by_category = OrderedDict()
    for row in rows:
        bucket = by_category.setdefault(row["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1
    print("")
    for category, bucket in by_category.items():
        print(
            "{0}: {1}/{2} ({3})".format(
                category, bucket["passed"], bucket["total"], _rate(bucket["passed"], bucket["total"])
            )
        )
    passed = sum(1 for row in rows if row["passed"])
    print("overall: {0}/{1} ({2})".format(passed, len(rows), _rate(passed, len(rows))))
    destination = Path(results_path or RESULTS_PATH)
    text = format_report(settings, rows, pause)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(destination)
    print("Wrote {0}".format(destination))
    return 0 if passed == len(rows) else 1


def main():
    raise SystemExit(run())


if __name__ == "__main__":
    main()

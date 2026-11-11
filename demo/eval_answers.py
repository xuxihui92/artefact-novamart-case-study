"""Live answer-quality eval for the NovaMart store assistant.

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
    OPENAI_MODEL=gpt-6-luna OPENAI_BASE_URL=https://api.openai.com/v1 python3 demo/eval_answers.py
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

from store_assistant import StoreAssistant
from store_assistant.model import chat_completions_url, resolve_settings

CASES_PATH = Path(__file__).resolve().parent / "eval_cases.json"
RESULTS_PATH = Path(__file__).resolve().parent / "eval_results.md"
KEY_NAMES = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
# Stable order for the live report. Labels are what the console and the file print.
CATEGORY_LABELS = (
    ("paraphrase", "paraphrase"),
    ("decision", "decision"),
    ("chinese", "Chinese"),
    ("out_of_scope", "out of scope"),
    ("injection", "injection"),
    ("access", "access"),
)
MODEL_ENGINES = ("OpenAI", "Gemini")


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


def category_counts(rows):
    counts = OrderedDict(
        (key, {"label": label, "passed": 0, "total": 0}) for key, label in CATEGORY_LABELS
    )
    for row in rows:
        key = row["category"]
        if key not in counts:
            counts[key] = {"label": key, "passed": 0, "total": 0}
        counts[key]["total"] += 1
        if row["passed"]:
            counts[key]["passed"] += 1
    return counts


def worded_by_model(row):
    engine = (row.get("actual") or {}).get("engine")
    return engine in MODEL_ENGINES


def wording_counts(rows):
    model = sum(1 for row in rows if worded_by_model(row))
    return model, len(rows) - model


def failure_rows(rows):
    return [row for row in rows if not row["passed"]]


def summary_lines(rows):
    """Console summary: category pass counts, wording split, and failures."""
    lines = []
    for bucket in category_counts(rows).values():
        lines.append(
            "{0}: {1}/{2} ({3})".format(
                bucket["label"], bucket["passed"], bucket["total"], _rate(bucket["passed"], bucket["total"])
            )
        )
    passed = sum(1 for row in rows if row["passed"])
    model_worded, fallback = wording_counts(rows)
    lines.append("overall: {0}/{1} ({2})".format(passed, len(rows), _rate(passed, len(rows))))
    lines.append("model wording: {0}".format(model_worded))
    lines.append("deterministic fallback: {0}".format(fallback))
    failures = failure_rows(rows)
    if not failures:
        lines.append("failures: none")
    else:
        lines.append("failures:")
        for row in failures:
            detail = ", ".join(row["problems"]) if row["problems"] else "failed"
            lines.append("- {0} ({1}): {2}".format(row["id"], row["category"], detail))
    return lines


def format_report(settings, rows, pause):
    """Render the results file. The API key is never included."""
    passed = sum(1 for row in rows if row["passed"])
    total = len(rows)
    by_category = category_counts(rows)
    model_worded, fallback = wording_counts(rows)
    failures = failure_rows(rows)
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
        "- Model wording: {0}".format(model_worded),
        "- Deterministic fallback: {0}".format(fallback),
        "",
        "## Pass rate by category",
        "",
        "| Category | Passed | Total | Rate |",
        "| --- | --- | --- | --- |",
    ]
    for bucket in by_category.values():
        lines.append(
            "| {0} | {1} | {2} | {3} |".format(
                bucket["label"], bucket["passed"], bucket["total"], _rate(bucket["passed"], bucket["total"])
            )
        )
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("None.")
        lines.append("")
    for row in failures:
        detail = ", ".join(row["problems"]) if row["problems"] else "failed"
        lines.append("- `{0}` ({1}): {2}".format(row["id"], row["category"], detail))
    if failures:
        lines.append("")
    lines.extend(["## Wording", ""])
    lines.append("- Model wording: {0}".format(model_worded))
    lines.append("- Deterministic fallback: {0}".format(fallback))
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
        lines.append("- Wording: {0}".format("model" if worded_by_model(row) else "deterministic fallback"))
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
        desk = StoreAssistant(
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
    passed = sum(1 for row in rows if row["passed"])
    print("")
    for line in summary_lines(rows):
        print(line)
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

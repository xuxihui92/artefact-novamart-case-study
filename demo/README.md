# NovaMart Return Desk

A local web prototype for store associates. Search five synthetic policy documents, ask a question, or check a sample order. The app shows the source behind policy answers, asks for missing details, and prepares a copyable summary when Operations needs to review the request.

## Run locally

Requires Python 3.9 or later. From the repository root, run:

```bash
python3 demo/app.py
```

Open <http://127.0.0.1:8765>. The first run creates `demo/data/novamart.sqlite3` with six synthetic orders. The sample date is November 9, 2026, so eligibility examples are repeatable. To use a different port, pass `--port 8766`.

The default mode uses local rules and works offline. To let a model interpret the question and phrase the reply, pass `--openai` or `--provider`:

```bash
OPENAI_API_KEY=... python3 demo/app.py --openai
GEMINI_API_KEY=... python3 demo/app.py --provider gemini
```

OpenAI reads `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-6-luna`), and `OPENAI_BASE_URL` (default `https://api.openai.com/v1`). Gemini reads `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-3.5-flash`), and uses `https://generativelanguage.googleapis.com/v1beta/openai/`. `PROVIDER=gemini python3 demo/app.py --openai` selects Gemini as well. `gemini-2.5-flash` returns 404 for new keys; `gemini-3.5-flash` is the default because it answered on that endpoint.

The client speaks Chat Completions with function tools (`search_policy`, `lookup_order`, `report_item_condition`, `handoff`). For gpt-6 models the client sets `reasoning_effort` to `none` so Chat Completions function calling is accepted; this field is not sent to Gemini. Code still decides the return window, final sale, opened electronics, and store-scoped lookup. The model only supplies a tool call and, on the follow-up, the wording. A follow-up sends the assistant tool-call message back unchanged, including Gemini `extra_content.google.thought_signature`. If the wording disagrees with the decision, the deterministic sentence is kept. On provider failure the desk falls back to local rules. HTTP 429 and 503 are retried with backoff. Use synthetic input in this mode. [OpenAI function calling guide](https://developers.openai.com/api/docs/guides/function-calling)

## Interview walkthrough

| Show | Try | Expected behavior |
|---|---|---|
| Search and provenance | Search for **proof of purchase** or ask **Where is my refund sent?** | Click a result or citation to inspect the original clause and version. |
| Return eligibility | Ask **Can I return NM-1042?**, then say **It is unused and resalable.** | The app checks the purchase date, asks about the condition, and confirms the standard conditions checked by the demo. The receipt or order confirmation is required at the return. |
| Clarification and handoff | Ask **Can I return NM-1043?**, then say **It is not sealed.** | The app asks about the condition, cites the opened-electronics clause, and offers an Operations summary. |
| Read-only order lookup | Ask **What is the order status for NM-1045?** | The app reports **Ready for pickup** from SQLite. |
| Scope and ambiguity | Ask for **refund status for NM-1042**, or ask to return **NM-1042 and NM-1043** together. | The app explains that transaction-level refund status is unavailable. For two orders, it asks which one to check. |
| Authorization boundary | Ask for **order status for NM-2042**. | The app returns the same generic response as for an unknown order. |

## Design

- `policies/RET-01.md` defines standard returns and proof of purchase.
- `policies/RET-02.md` defines electronics, exceptions, and final-sale items.
- `policies/RET-03.md` defines refund methods, exchanges, and escalation.
- `policies/RET-04.md` defines price match, coupons, and member discounts.
- `policies/RET-05.md` defines pickup holds, damaged-on-arrival, and delivery exceptions.
- `seed.sql` creates and seeds the order database. The simulated session is fixed to Store 014. Every lookup applies that store scope in a parameterized SQL query.
- `app.py` is the CLI entry point. `return_desk/` holds the application modules: config, redaction, tool schemas, text facts, policy library, order store, the Chat Completions client, chat orchestration, and the HTTP server. The orchestration file is where the split is enforced: the model proposes a tool and may phrase the reply; the return window, final sale, opened electronics, and store scope stay in code.
- `static/` contains the HTML, CSS, and JavaScript. All assets are served locally.
- `tests/` contains unit and acceptance tests discovered by `eval_demo.py`.

The prototype uses a fixed simulated identity, a small policy corpus, and a read-only workflow. Offline rules are English. With a model configured, Chinese questions can be read as well. See the [design brief](../README.md) and [production note](../docs/production-note.md) for the proposed rollout.

## Evaluate

Unit and acceptance tests, including redaction, tool-argument checks, and a mocked model that is not allowed to override a denial:

```bash
python3 demo/eval_demo.py
```

Live answer quality, against `demo/eval_cases.json`. Without the selected provider's key the script prints `Live eval was skipped: ... is not set.` and does not write a results file.

```bash
OPENAI_API_KEY=... python3 demo/eval_answers.py
GEMINI_API_KEY=... python3 demo/eval_answers.py --provider gemini
```

A finished live run writes `demo/eval_results.md` and records the provider, model, endpoint, per-category pass counts, failures, and how many replies were worded by the model versus the deterministic sentence. Commit that file only after a real run. Gemini waits 3 seconds between model HTTP calls by default so the free tier is less likely to return 429; override with `EVAL_PAUSE_SECONDS`. OpenAI waits 0.5 seconds unless that variable is set.

## Limitations

- Offline mode never calls a model. `--openai` or `--provider gemini` plus that provider's key is what turns the model on.
- The model does not own the decision. If its sentence fails the yes/no or citation check, the associate sees the deterministic sentence instead.
- English condition phrases the code already extracts win over the model. The model may add a condition only when the message mentions it, which is how a Chinese report can be read. It cannot clear "I opened it", and it cannot move a lookup to an order id the customer did not write.
- A follow-up such as "Yes" stays on the local state machine, so the model cannot reopen a decision that code is already collecting.
- Redaction is a set of patterns. It misses some name shapes and phone numbers written as bare digits, and it can hide a capitalized phrase after "I am" or "this is".
- Policy text and tool output are fenced as data. That plus the decision check is the injection defense, not a guarantee.
- Gemini sometimes returns 503 under load, and `gemini-2.5-flash` is unavailable to new users. The client retries 429 and 503, then falls back to local rules.
- Chat Completions has no `store: false` switch. Retention follows the provider account.
- The live eval is not part of `eval_demo.py`. Model-dependent cases (Chinese, and paraphrases with none of the local keywords) can fail when the model is down or picks the wrong tool; the report shows that instead of a padded score.

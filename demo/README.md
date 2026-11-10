# NovaMart Return Desk

A local web prototype for store associates. Search five synthetic policy documents, ask a question, or check a sample order. The app shows the source behind policy answers, asks for missing details, and prepares a copyable summary when Operations needs to review the request.

## Run locally

Requires Python 3.9 or later. From the repository root, run:

```bash
python3 demo/app.py
```

Open <http://127.0.0.1:8765>. The first run creates `demo/data/novamart.sqlite3` with six synthetic orders. The sample date is November 9, 2026, so eligibility examples are repeatable. To use a different port, pass `--port 8766`.

The default mode uses local rules and works offline. For optional OpenAI tool selection, configure `OPENAI_API_KEY` in your shell and run:

```bash
python3 demo/app.py --openai
```

Set `OPENAI_MODEL` to override the default model, `gpt-4.1-mini`. Use synthetic input in this mode. The model selects from the available functions. The app validates the selection, runs retrieval or order lookup locally, and builds the response from the resulting evidence. On provider failure, the app falls back to local routing. [OpenAI function calling guide](https://developers.openai.com/api/docs/guides/function-calling)

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
- `app.py` is the CLI entry point. `return_desk/` holds the application modules: config, text facts, policy library, order store, optional model routing, chat orchestration, and the HTTP server.
- `static/` contains the HTML, CSS, and JavaScript. All assets are served locally.
- `tests/` contains unit and acceptance tests discovered by `eval_demo.py`.

The prototype uses a fixed simulated identity, English questions, a small policy corpus, and a read-only workflow. See the [design brief](../README.md) and [production note](../docs/production-note.md) for the proposed rollout.

## Evaluate

```bash
python3 demo/eval_demo.py
```

The suite covers module unit tests plus the interview acceptance flows: policy exceptions and reordering, return-window boundaries, same-store access, unknown requests, HTTP API checks, and model routing with a stub. The live model path needs a configured API key.

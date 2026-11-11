# NovaMart Store Intelligent Assistant: Project Design

## 1. Problem and Scope

Store associates and shift leads need quick, correct answers on policy and orders while a customer is at the counter. Today they wait for Operations, who answer the same questions again and again. The first release aims to shorten time to a correct resolution and cut repeat work for Operations.

Demand hypotheses, to be validated in the first 1–2 weeks by sampling tickets, chats, calls, and shifts, then ranked by frequency × handling time and the cost of a wrong answer: (1) returns, exchanges, and refunds; (2) order status and pickup; (3) product and stock; (4) pricing and promotions; (5) checkout and POS.

**Interview prototype.** A local Python web app (http://127.0.0.1:8765) with five synthetic policies (RET-01 to RET-05) and a read-only, store-scoped order tool over six synthetic orders. It shows cited return answers, order lookups, and handoff to Operations. One OpenAI-compatible Chat Completions client with function calling, defaulting to gpt-6-luna (gpt-4.1-mini was deprecated Oct 14, 2026 and shuts down Jan 14, 2027). gpt-6 models get `reasoning_effort: "none"`, which function calling requires. The base URL is configurable, so the same client runs Gemini (gemini-3.5-flash). Without a model, or when the call fails, the app falls back to local rules with the same deterministic checks.

**First pilot.** Return and exchange policy Q&A plus human handoff. Refund approvals and transactions stay in existing processes.

## 2. Design

**Principle: the model handles language; code makes decisions.**

```text
Associate asks → identity and store from the session → refund/override pre-check and redaction → classify
├ Required field missing → ask one follow-up → re-evaluate
├ Return/exchange → retrieve clauses (+ read-only order tool) → eligibility rules in code
└ Order status → authorize → read-only order tool
→ Basis sufficient: answer with clause citation or order status
→ Basis missing, conflicting, or lookup failed → handoff summary → Operations
```

The prototype reads purchase date and category from the order record and asks one condition question per turn. The web pilot can present missing fields as a short form.

**Platform.** Production uses a hosted model (gpt-6-luna via the OpenAI API) behind a thin custom app, because the workflow needs store-scoped order access, deterministic rules, and handoffs that managed chat products don't enforce. If NovaMart is standardized on Microsoft or Google, Azure OpenAI or Gemini on Vertex AI is the swap, contained to one module.

| Module | Owner | Responsibility |
|---|---|---|
| Identity | Store Apps | Employee and store from a verified session (prototype: simulated Store 014). |
| Orchestration | AI Engineering | Four typed tools (`search_policy`, `lookup_order`, `report_item_condition`, `handoff`); an order ID must appear in the associate's message. |
| Policy retrieval | AI Eng, Operations | Operations owns versions and precedence; conflicts hand off. Prototype: keyword search over five versioned files. |
| Order lookup | Commerce Systems | Server-side store scope, allowlisted fields; failure is distinct from no-result. |
| Answer and handoff | AI Eng, Operations | Wording that contradicts the code's decision or cites wrong clauses is replaced by a deterministic sentence. |

## 3. Acceptance

All 80 offline tests pass (`python3 demo/eval_demo.py`). The 17-case live eval scored 16/17 on gemini-3.5-flash (free tier, Nov 12, 2026; the OpenAI account had no credits). The one failure, a status paraphrase, fell back to local rules and handed off, with no wrong answer and no leaked data; why the model path failed is still under investigation. Input is assumed to be English. The eval still needs a re-run on gpt-6-luna.

| Case | Expected |
|---|---|
| Eligible online return | Cites clause and version, explains conditions. |
| Missing field that changes the answer | Asks only for that field, then re-evaluates. |
| Another store's order, or probing existence | Blocked server-side; same generic "no result". |
| Tool failure or no policy basis | Says it can't confirm; hands off with reason and next step. |
| Conflicting policy versions | Hands off (planned; prototype policies are all v1.0). |

## 4. Security

Names, contacts, payment data, and order numbers are redacted before every model call (prototype: patterns; production adds NER). The prototype swaps order numbers for a placeholder and the server resolves the real ID from the associate's message. The handoff summary is written by code with no customer free text. Read-only, least-privilege service identity; allowlisted tools and fields; policy text and tool output are treated as data. Retention is set at the account level (zero data retention) before any live data. Security signs off before real data; any unauthorized disclosure blocks the pilot.

## 5. Performance and Cost

1,000 stores × 20 requests/day ≈ 20,000/day, about 0.6 req/s average and 6 req/s at a 10x peak. At most 2 model calls and 1 order lookup per turn; target p95 ≤ 5 s. At ~2,500 input and ~300 output tokens per request and gpt-6-luna prices ($0.10 / $0.50 per 1M), model cost is about **$240/month** (~$2,400 at 10x). Integration and Ops time dominate total cost.

## 6. Monitoring, Pilot, and Open Questions

- **Monitoring.** p95, errors, and handoff reasons per path; daily Ops sample of answers and handoffs against the policy version used; reviewed failures go back into the eval set, which gates every policy, prompt, or model change.
- **Pilot.** Store-level flag after Ops and Security sign-off, with comparison stores. Primary metric: share of in-scope requests resolved correctly within an agreed time; secondary: human-handled requests per 100.
- **Open questions.** Real volume and handling-time baselines; who decides policy conflicts; which roles and fields the order system allows; approved hosting and retention; who takes handoffs.

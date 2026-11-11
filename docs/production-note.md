# NovaMart Store Assistant: Production Note

**Platform: OpenAI API (Chat Completions with function calling).** Typed tool arguments that code validates before running; gpt-6-luna for most traffic (OpenAI's recommended replacement for the deprecated gpt-4.1-mini, which shuts down January 14, 2027), a larger model only where the eval shows gaps. Function calling on Chat Completions requires `reasoning_effort` set to `none`; the client sets that automatically. It is also the stack I know best. *What would change this:* if NovaMart is standardized on Microsoft, Azure OpenAI (EU data residency, existing contracts); if on Google, Gemini on Vertex AI. The client uses the OpenAI-compatible format with a configurable base URL, so switching is contained to one module; the prototype's live eval ran on Gemini's compatible endpoint (gemini-3.5-flash) because the OpenAI account had no API credits.

**Managed vs custom: a thin custom app on the hosted API.** The store workflow needs what ChatGPT Enterprise-style products do not enforce: store-scoped order access, deterministic eligibility rules, and handoffs into the Ops queue with context. *Revisit* if a managed agent platform supports per-user scoped tools, auditable rule steps, and custom handoff targets.

**Connecting real data.**
- *Policies:* Ops-owned, versioned source with clause IDs, effective dates, and channel/region scope. Changes publish after approval and a passing eval; answers record the version used.
- *Orders:* read-only API, allowlisted fields, session's store only.
- *Identity:* NovaMart SSO; store and role come from the token, never the prompt.

**Security and governance.** Redact emails, phones, cards, order IDs, and names before every model call (the prototype uses patterns; production adds NER). Retention is contractual, not a code flag: zero data retention on the enterprise agreement (or the Azure equivalent) before any live data. Read-only, least-privilege service identity; allowlisted tools and fields. Policy text, tool output, and user input are fenced as data. The model words a decision but cannot change it: code rejects wording that contradicts the decision or cites unretrieved clauses, and a tool call cannot target an order the associate did not name. Audit logs keep who, store, tools, clauses, and outcome (no free text) under agreed retention. Any unauthorized disclosure pauses the pilot.

**Evaluating and monitoring quality.** A versioned eval set (paraphrases, multilingual, out of scope, injection, cross-store) runs in CI and gates every policy, prompt, or model change. Ops reviews a daily sample. Track grounded-correct rate, rate of model wording rejected by the check, handoff rate and reasons, p95 latency (target 5 s), and cost per request. Reviewed failures go back into the eval set. Pilot primary metric: share of eligible requests resolved correctly within an agreed time, versus comparison stores.

**Rough cost.** Assume 20,000 requests/day, two model calls per request (tool call, then wording), about 2,500 input and 300 output tokens in total. At gpt-6-luna list prices ($0.10 / 1M input, $0.50 / 1M output):
20,000 × 30 × (2,500 × $0.10 + 300 × $0.50) / 1M ≈ **$240/month**. Integration and Ops time dominate total cost.

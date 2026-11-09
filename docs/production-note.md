# NovaMart Return Desk · Production Note

## Platform and scope

Pilot return and exchange guidance for store associates, with referrals to the existing Operations queue. The prototype uses OpenAI for optional tool selection behind a Python application. For production, start with a hosted model behind a thin application so NovaMart can enforce access, policy decisions, and handoffs at the application boundary. Assess NovaMart's enterprise assistant against the same store-level authorization, audit, data-handling, and read-only integration criteria. Adopt managed components that meet those requirements.

## Data and controls

Operations publishes approved clauses with stable IDs, effective dates, and channel and regional scope. Validate each version before activation, retain the previous version for rollback, and record the version used in each answer. Connect employee identity through NovaMart's identity provider and derive store access server-side. Add the live order system only after separate approval for a scoped, read-only integration. Verify the supported order-line fields and what constitutes proof of purchase before using them to assess a return.

Redact sensitive fields before model calls and handoffs, allowlist tool inputs and outputs, and retain only essential audit metadata. Security signs off on vendor handling and log retention. Route unresolved policy conflicts and tool failures to Operations. Refund approvals and transactions stay in the existing workflow.

## Evaluation, rollout, and monitoring

Before pilot, run a held-out set of policy, clarification, ambiguity, exception, and access-control cases. Score citation applicability, decision correctness, and appropriate handoff separately. A confirmed unauthorized disclosure blocks launch or pauses a live pilot.

Enable the pilot by store after staging verifies alerts, rollback, and handoffs. Compare the change from baseline with similar stores over the same period. The primary measure is the share of eligible requests resolved correctly within the agreed time, including requests handled outside the assistant. Also track human-handled requests per 100 eligible requests. Agree on the minimum improvement and pause criteria before launch.

Monitor p95 latency, errors, timeouts, handoff reasons, and policy synchronization. Operations and AI Engineering review daily samples against the effective policy. Platform owns alerts and rollback. Expand after the agreed quality, security, and operating thresholds are met.

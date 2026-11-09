# NovaMart Store Support Assistant

Artefact take-home case study · Design one-pager

## Goal and scope

Help store employees resolve return-policy and order-status questions correctly and quickly. The working hypothesis is that answers grounded in policy and current order data will reduce repeat work for Operations. The prototype tests the core workflows. A store pilot measures the business effect.

## First build

Use the first 30 minutes to define three acceptance cases. A returns question gets an answer supported by a specific policy clause. An order-status question triggers a read-only lookup and accurately reflects the result. A question with missing or conflicting evidence gets a clear explanation and a next step. Use six short synthetic documents, sample orders, and a Python CLI. Reserve the rest of the four-to-six-hour exercise for failure cases, repeatable evaluation, and the production note.

## Design

Use the OpenAI API for the prototype, local document retrieval for the small corpus, and a mock order-status tool. Validate tool arguments in the application. In production, authorize each order lookup against the employee's identity and store scope before returning data. When evidence is missing or the tool fails, give the employee a handoff summary that captures the question, what was checked, and what Operations still needs.

**Store question → policy retrieval or order lookup → sourced answer or Operations handoff**

## Evidence and release gates

Define expected behavior before coding and hold back a few questions for the final run. Check tool routing, arguments, and failure behavior automatically. Review whether each cited clause supports the answer. Include expired or conflicting policies, tool timeouts, and cross-store access attempts. Record results by case. Any unauthorized disclosure or fabricated order status blocks the pilot. The small synthetic suite checks known failure modes. Real requests are needed to assess production reliability.

## Production and ownership

Start with a hosted model and a lightweight application that owns authorization and tool execution. Reassess an enterprise-managed option if it meets NovaMart's store-level permissions, read-only integration, and audit requirements. Operations owns the authoritative policies and acceptance criteria. Engineering owns the versioned policy feed, order-system integration, and quality monitoring. Security validates access controls and log redaction. Track sampled answer correctness, tool failures, and handoffs after launch.

Pilot in a small group of stores and compare with stores using the existing workflow over the same period. Measure the share of requests correctly resolved within the agreed time and the number requiring human handling per 100 requests. Agree on expansion criteria before launch and pause on any confirmed unauthorized disclosure. The engineering lead owns the pilot outcome and reports whether the evidence supports expanding it.
